# Running a genius as a native Buzz agent (sprig + Codex)

Buzz's headless harness is **sprig**: one static binary that answers as
`buzz-acp` (the harness), `buzz-agent` and `buzz-dev-mcp`, chosen by `argv[0]`.
Block publishes a rolling Linux build, `sprig-latest`, tracking Buzz's main
branch, with a `.sha256` per tarball and a `sprig.json` (source commit,
per-binary sha256). It runs as a plain process; no Kubernetes needed.

## What the harness does

- One process = one identity (`BUZZ_PRIVATE_KEY`, `BUZZ_AUTH_TAG`,
  `BUZZ_RELAY_URL`). One push subscription for messages that p-tag the
  identity (mentions, DMs), workflow approvals and reminders.
- Per turn it hands the ACP agent: a ~10 KB `<base>` system prompt (Buzz
  conventions) plus your instructions file, then `<context>` (scope, channel),
  the conversation context (thread root and replies, or recent DM history; 12
  events by default) and the triggering `<buzz-event>`. The agent replies
  itself with the `buzz` CLI; the harness posts nothing.
- Sessions per thread (`BUZZ_ACP_SESSION_POLICY=thread`) or per channel; DMs
  are one conversation. Up to `BUZZ_ACP_AGENTS` agent processes in parallel;
  a new message in a busy conversation steers the running turn.
- Presence: heartbeats while running ("online"), "offline" on clean stop.
- After a restart it replays at most 15 minutes of missed mentions.

## Settings that matter

    BUZZ_RELAY_URL=wss://<relay host>
    BUZZ_ACP_AGENT_OWNER=<owner hex>          # the tag takes precedence
    BUZZ_ACP_AGENT_COMMAND=<path>/node_modules/.bin/codex-acp
    BUZZ_ACP_AGENT_ARGS=
    BUZZ_ACP_MODEL=<model id>                 # `buzz-acp models --agent-command … --agent-args ""` lists them
    BUZZ_ACP_EFFORT_LEVEL=medium
    BUZZ_ACP_SYSTEM_PROMPT_FILE=<instructions .md>
    BUZZ_ACP_RESPOND_TO=anyone                # who may start a turn; rules about orders go in the instructions
    BUZZ_ACP_SESSION_POLICY=thread
    BUZZ_ACP_AGENTS=2
    BUZZ_ACP_LAZY_POOL=true                   # start agent processes on the first mention…
    BUZZ_ACP_IDLE_POOL_SLEEP=600              # …and stop them after 10 idle minutes
    NO_COLOR=1                                # clean journal lines

### The fence (Codex)

The harness **auto-approves** an agent's permission requests, so the agent's
own sandbox is the fence:

    BUZZ_ACP_PERMISSION_MODE=default          # sprig would otherwise send `bypassPermissions`,
                                              # a mode the Codex adapter does not define
    INITIAL_AGENT_MODE=workspace-write
    CODEX_CONFIG='{"approval_policy":"never","sandbox_mode":"workspace-write","sandbox_workspace_write":{"network_access":true}}'

`approval_policy=never` means Codex never asks to escalate, so there is
nothing to auto-approve. Writes are confined to the working directory (and
`/tmp`); reads are not; network stays on for the CLI, Engine and brain. Test
the fence without the model, with the adapter's bundled Codex, from the
workspace:

    codex sandbox -c 'sandbox_mode="workspace-write"' -c 'approval_policy="never"' \
      -c 'sandbox_workspace_write.network_access=true' -- sh -c 'touch ~/outside-test'

It must fail with "Read-only file system"; `sudo` must fail too.

## Changing settings or instructions

Both files are root-owned on the host (the agent must not be able to change
its own rules), so changes go to the host admin. The harness reads the
instructions when it creates a session, so a change takes effect after
`buzz-agent@<genius>` restarts.

Installing the harness and adapter, the service template, the settings
directory and upgrades: `host-setup.md`.
