# Deploy models: how closeout knows a change is live

Repositories that administer a machine do not all go live the same way.
`closeout check` works out each touched repository's model, says which one
it used and why (`deploy model scripts (detected …)`), and then checks
the session's changes against it.

## How the model is chosen

1. A declaration file `.closeout.json` at the root of the canonical
   checkout. This always wins.
2. Engine routing: `work_mode: in-place` in `~/w/engine/routing.json`.
3. Detection: an executable `*-deploy` in `bin/`, `sbin/`, `scripts/` or the
   root that mentions `--check` gives the **manifest** model. Otherwise any
   `scripts/install-*.sh`, `scripts/setup-*.sh` or `scripts/configure-*.sh`
   gives the **scripts** model.
4. Otherwise **none**.

Detection is a guess. A repository whose admin knows better should
declare its model.

## The models

| model | shape | what closeout checks |
|---|---|---|
| `none` | code or docs; nothing on this host changes when it lands | nothing beyond git/Engine |
| `manifest` | the repository is the source and the host holds copies; one idempotent tool deploys them all and can verify (`golem-deploy --check`) | runs `deploy.check`; a non-zero exit blocks, and the next action is `deploy.apply` after landing |
| `scripts` | each component has its own installer that copies its files into place (zhizi's `scripts/install-*.sh`) | every non-doc file the session changed must be referenced by an installer, and that installer must have run after the last edit. A file under `config/` or `services/` that no installer references blocks |
| `in-place` | Engine in-place repository (bakkies-docker, zeresh-ops): the canonical checkout *is* the live system, edited under a repository lock | covered by the lock and capture checks: a held lock, or uncommitted changes, block |
| `custom` | anything else, described by a check command | runs `deploy.check`, like `manifest` |

Independently of the model, a file the session wrote **outside** every
repository is compared with any tracked repository file whose path ends
the same way (`/etc/apt/mirrors/debian.list` matches
`config/apt/mirrors/debian.list`). Identical copies pass, different
copies block, and files with no counterpart block as unscripted live
changes.

## Declaring a model

`.closeout.json`, committed at the repository root:

```json
{
  "version": 1,
  "deploy": {
    "model": "manifest",
    "check": "sudo -n /usr/local/sbin/golem-deploy --check",
    "apply": "sudo golem-deploy",
    "installers": ["scripts/install-*.sh"]
  },
  "notes": "free text, shown to the agent: rollback procedure, ordering, who must run it"
}
```

- `model`: one of `none`, `manifest`, `scripts`, `in-place`, `custom`.
- `check`: shell command run from the canonical checkout, with a 120 s
  timeout. Exit 0 means live matches the repository; anything else is
  drift, and the last lines of its output are shown. It must be
  read-only and must never prompt: use `sudo -n`, and make sure the
  account has the NOPASSWD rule it needs. If the check cannot run
  unattended, leave it out and rely on `scripts`-style tracking.
- `apply`: the command a human or the session runs to deploy. Closeout
  shows it and never runs it.
- `installers`: glob(s) for the `scripts` model, relative to the root.
- `notes`: anything the agent should know, such as a rollback script or
  "deploy only after the backup at 03:00".

## Per host (as known when this was written)

| repository | locus | model | notes |
|---|---|---|---|
| zhizi | yair@zhizi | scripts (detected) | `scripts/{install,setup,configure}-*.sh` copy from `config/` |
| golem | yair@golem | manifest | `golem-deploy` with MANIFEST and `--check`; no system path may symlink into the checkout |
| bakkies-docker | yair@bakkies | in-place | root's crontab runs `scripts/*.sh` straight from the checkout, so saving is deploying |
| zeresh-ops | oc@bakkies | in-place | |
| brain, engine, zchat, token-usage, handwave repos | various | none, unless a declaration says otherwise | services that restart from the checkout should declare `custom` with a version or health check |

Each admin should confirm their own row and commit a `.closeout.json`
when detection gets it wrong.
