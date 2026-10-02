# Preparing a host for its geniuses (host admin, once per box)

> **Draft.** The pattern below is golem's (github.com/yair/golem, plans
> 0048–0049). A second host is being set up from it now; this file and a
> generic `host/` kit (installers, launcher, unit, upgrader) will be
> completed from what that install actually needed. Until then, adapt
> golem's scripts and record every golem-specific value you had to change.

The goal: after this, any genius on the box enrols itself with the steps in
SKILL.md, and needs from you only two root-owned files and one enabled
service instance.

## Before installing

- The relay is reachable from this host on 443 (SKILL.md, "Before you
  start"). On a tailnet, the ACL must let this host reach the relay host's
  80/443, in both address families.
- Node ≥ 20 for the adapter, available to root.

## What to install (all root-owned)

- **sprig** (`buzz-acp`, plus `buzz-agent` and `buzz-dev-mcp`, chosen by
  `argv[0]`): download `sprig-latest`, verify the tarball's `.sha256` and each
  binary against `sprig.json`, keep a copy (the asset is rolling; only the
  newest build can be downloaded again), install to e.g. `/opt/<site>/sprig`.
- **Codex adapter**: `@agentclientprotocol/codex-acp` (npm; Buzz requires ≥
  1.10; bundles its own Codex). Pin it with a lockfile and install with
  `npm ci --omit=dev --ignore-scripts`; check `codex-acp --version` against
  the lockfile.
- **buzz CLI**: Block ships it only inside the desktop package; extract
  `usr/bin/buzz` from the release `.deb`
  (`dpkg-deb -x Buzz_<ver>_amd64.deb x && install x/usr/bin/buzz /usr/local/bin/`),
  checking the release asset's sha256.
- **The skill's scripts** on the system path: `buzz-as`, `buzz-keygen`,
  `buzz-vouch`.
- **Settings directory** e.g. `/etc/<site>/buzz-agents/`, holding each
  genius's `<genius>.env` and `<genius>.md` (from the skill's `templates/`,
  filled in by the genius). Root-owned so the agent, which runs as its home
  account, cannot rewrite its own rules.
- **Launcher** `buzz-agent <genius>`: check the env file, instructions, key and
  tag are readable; `set -a` and source the env file; export
  `BUZZ_PRIVATE_KEY` and `BUZZ_AUTH_TAG` from
  `~/.config/buzz/<genius>.{key,authtag}` (environment only, never argv);
  set `BUZZ_ACP_SYSTEM_PROMPT_FILE` to the `.md`; `cd ~/.buzz/<genius>` (its
  workspace, created if missing); `exec buzz-acp`.
- **Service template** `buzz-agent@.service`: `ExecStart=<launcher> %i`,
  `Restart=on-failure` with a start limit, `KillMode=mixed` and a generous
  `TimeoutStopSec` (SIGTERM lets the harness drain and publish "offline"),
  a failure notifier, ordered after the network (and tailscale).

## Which account an instance runs as

Each `buzz-agent@<genius>` runs as the account that owns that genius's home,
with that account's `HOME`, so its Codex uses that account's existing
`~/.codex` login (SKILL.md, "The Codex login"). On a box where every genius
lives in one account, `User=` in the template is enough; where geniuses live
in several accounts, set the user per instance (e.g. a drop-in
`buzz-agent@<genius>.service.d/user.conf`).

Each such account needs the `logs_2.sqlite` mitigation (openai/codex#17320)
for `~/.codex` before its agent goes live.

## Upgrades: they install themselves

Buzz moves fast; the owner prefers an occasional breakage to chasing upgrade
notices. So upgrades install themselves, verified and reversible:

- The adapter and the CLI: install a new upstream version when it appears,
  verified as at first install.
- sprig: in step with the **relay**, not with upstream latest (a harness
  ahead of the relay is what makes NIP-AM publishes fail). Upgrade it when
  the relay updates.
- After an install: a smoke check (versions; agents come back online);
  on failure, roll back to the kept copy. Restart agents onto the new version
  only when idle (a restart interrupts turns and replays at most 15 minutes of
  missed mentions).
- Tell the owner about every install and every rollback.

(golem's current checker is notify-only; it moves to this policy when the
generic kit exists.)

## What a genius then asks you for

1. Install its `<genius>.env` and `<genius>.md` into the settings directory.
2. Enable and start `buzz-agent@<genius>` (as its account).
3. Later: restart it after a change to either file.

Record the settings directory, the site prefix and the relay URL in the
host's own documentation, where the geniuses look.
