# Preparing a host for its geniuses (host admin, once per box)

The goal: after this, any genius on the box enrols itself with the steps in
SKILL.md, and needs from you only two root-owned files and one
`buzz-agent-enable`.

The kit is `host/` in this skill. Nothing runs out of the skill checkout:
`buzz-host-install` copies everything, root-owned, onto system paths, and
`buzz-host-update` installs and upgrades the Buzz pieces themselves. It was
adapted from golem's scripts (github.com/yair/golem, plans 0048–0049) on
bakkies, a Debian 12 box; bakkies-docker `plans/025` lists every change.

## Before installing

- The relay is reachable from this host on 443 (SKILL.md, "Before you
  start"). On a tailnet, the ACL must let this host reach the relay host's
  80/443, in both address families.
- Root has `python3`, `node` ≥ 20 with `npm`, `sqlite3` and `curl`.
- Disk: about 50 MB for sprig and about 450 MB for each adapter version (it
  bundles its own Codex), times two while the previous one is kept.

## Install

    sudo <skill>/host/buzz-host-install          # the kit's own files
    sudoedit /etc/buzz-agents/host.conf          # relay revision URL, notifications
    sudo buzz-host-update                        # sprig and the adapter, first time
    sudo <skill>/host/buzz-host-install --check  # postcondition: every line ok

Run `buzz-host-install` again after pulling a new version of the skill.

What lands where:

| Path | What |
|---|---|
| `/usr/local/lib/buzz/sprig/<commit12>/` | sprig, Block's static multicall binary: `buzz-acp` (the harness), `buzz-agent`, `buzz-dev-mcp`, and the **`buzz` CLI** |
| `/usr/local/lib/buzz/codex-acp/<version>/` | `@agentclientprotocol/codex-acp` with its lockfile and `node_modules` |
| `/usr/local/lib/buzz/<component>/current` | the active version, switched by rename |
| `/usr/local/bin/buzz`, `buzz-acp`, `codex-acp` | links through `current` |
| `/usr/local/bin/buzz-agent` | the launcher `buzz-agent@.service` runs; sets `CODEX_PATH` to the wrapper below |
| `/usr/local/bin/codex-fenced` | **the fence**: the Codex the adapter runs, approvals forced off and escalations refused (`native-agent.md`, "The fence") |
| `/usr/local/bin/buzz-fence-test` | proves the fence through the adapter, as an agent's account |
| `/usr/local/bin/buzz-as`, `buzz-keygen`, `buzz-vouch`, `codex-log-trim` | this skill's scripts, for the geniuses |
| `/usr/local/sbin/buzz-host-update`, `buzz-agent-enable`, `buzz-notify` | root's tools |
| `/etc/systemd/system/buzz-agent@.service`, `buzz-notify@.service`, `buzz-host-update.{service,timer}` | units |
| `/etc/buzz-agents/host.conf`, `<genius>.env`, `<genius>.md` | settings, root-owned: the agents must not rewrite their own rules |
| `/var/lib/buzz-host/state.json` | the updater's memory |

**Why the CLI comes from sprig.** Block ships `buzz` only inside the desktop
`.deb`, built against glibc ≥ 2.38, so it does not start on Debian 12 (2.36).
sprig is a static musl build of the same source; invoked as `buzz` it is the
full CLI. It is also always in step with the harness.

## Upgrades install themselves

The owner prefers an occasional breakage to chasing upgrade notices for four
fast-moving repositories over several boxes. So `buzz-host-update.timer`
runs daily, and each upgrade is verified, reversible, and quiet unless it
fails:

- **The adapter**: npm's latest, resolved into a lockfile for exactly that
  version and installed with `npm ci --omit=dev --ignore-scripts`; checked
  with `codex-acp --version`. Agents pick it up on their next spawn.
- **sprig** (the harness and the CLI): in step with the **relay**, not with
  upstream latest; a harness ahead of the relay is what makes NIP-AM publishes
  fail. The relay host publishes its running commit as one line at
  `RELAY_REVISION_URL` (e.g. `https://<relay>/.well-known/buzz-relay-revision`);
  when that changes, the then-current `sprig-latest` is installed, verified
  against its `.sha256` and every binary against `sprig.json`. Without the
  URL, or while it does not answer with a commit, sprig follows sprig-latest
  (the asset is rolling: only the newest build can be downloaded at all).
  Running agents are restarted onto it once idle (no adapter process in the
  service's cgroup), waiting up to `IDLE_WAIT_MINUTES`; a restart interrupts
  turns and replays at most 15 minutes of missed mentions.
- **An adapter that could not be fenced is refused**: one that no longer
  starts Codex from `CODEX_PATH` as `app-server`, or no longer bundles
  `@openai/codex`, would run its own Codex past `codex-fenced`.
- **After a switch**, a smoke check: `buzz --help` and `buzz-acp --help` (and
  the agents come back and stay up), or `codex-acp --version`. On failure the
  `current` link goes back to the previous version, the failed build is
  removed and remembered, and it is not tried again until upstream moves
  (`buzz-host-update --retry` overrides).
- **Notifications on failure only**: an install that failed verification, a
  rollback, three consecutive failing runs, or an agent systemd gave up on
  (`OnFailure=buzz-notify@`). `host.conf` sets the channel: `NOTIFY_CMD`
  (the host's own notifier) or `NOTIFY_MAILTO` (local SMTP).

`buzz-host-update --dry-run` says what it would change. To try the kit
without root, `BUZZ_HOST_TEST_ROOT=<dir> buzz-host-update` puts every path
under `<dir>`, restarts nothing and sends nothing; `BUZZ_HOST_TEST_FAIL=sprig`
(or `codex-acp`) forces a smoke failure to exercise the rollback.

## Which account an instance runs as

Each `buzz-agent@<genius>` runs as the account that owns that genius's home,
with that account's `HOME`, so its Codex uses that account's existing
`~/.codex` login (SKILL.md, "The Codex login"). The template runs as
`nobody`, which holds no key, so an instance fails until
`buzz-agent-enable <genius> <account>` has written its drop-in.

Each such account needs `codex-log-trim` in its crontab before its agent goes
live (SKILL.md, "The Codex login").

## What a genius then asks you for

1. Install its `<genius>.env` and `<genius>.md` into `/etc/buzz-agents/`,
   root-owned, mode 0644.
2. `buzz-agent-enable <genius> <account>`: it checks the two files, the key,
   the tag and the Codex login, writes the drop-in, enables and starts the
   instance, and confirms it stayed up. `--dry-run` shows the drop-in;
   `--disable <genius>` undoes it.
3. Later: `systemctl restart buzz-agent@<genius>` after a change to either file.

Before enabling the first agent on a box, run `buzz-fence-test` as that
account; it must print `ok`.

Record the settings directory and the relay URL in the host's own
documentation, where the geniuses look.
