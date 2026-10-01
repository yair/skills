---
name: ha
description: >
  Read and control a Home Assistant instance (lights, sensors, Matter devices,
  schedules) from an agent session with the `ha` CLI in this skill. Use when
  asked to turn a light on or off or dim it, change its colour temperature,
  check what a device or sensor reports, look at history or the logbook, pause
  or resume a light schedule, or answer "what's the state of X at home". Not
  for changing Home Assistant's configuration.
---

# ha — Home Assistant for agents

A small stdlib-Python CLI, `scripts/ha` in this skill, over Home Assistant's
REST and WebSocket APIs. It costs no context until an agent uses it, unlike an
MCP server, whose tool definitions load into every session.

## Before using it

- **A non-admin token, read from a file.** The CLI authenticates with a
  long-lived token of a dedicated **non-admin** HA user (it can read states and
  call services, but cannot reconfigure HA). It reads the token from
  `$HA_TOKEN_FILE` (default `~/.config/ha/token`, mode 600). **Never** put a
  token on a command line, in a URL, in chat, or in git. If the file is
  missing, ask the human. Do not use an admin token for this.
- **Which server:** `$HA_URL`, default `http://127.0.0.1:8123` (on the HA host
  itself). From elsewhere, use the instance's HTTPS name.
- **Host-specific notes** (entity names, rooms, schedules, where the token is
  provisioned) live with the host's own documentation, not here. For golem,
  see `~/w/golem/plans/` 0039–0041.

## Commands

    ha states [PATTERN]                     # entity, state, %/K for lights, name
    ha get ENTITY                           # full JSON
    ha on light.x brightness_pct=40 color_temp_kelvin=2700 transition=3
    ha off light.x
    ha call DOMAIN.SERVICE [ENTITY] [key=value ...]
    ha services [DOMAIN]
    ha history ENTITY [HOURS]
    ha logbook [ENTITY] [HOURS]
    ha template '{{ states("sensor.x") }}'
    ha schedule [resume]                    # where a light-schedule package is installed

Run it as `~/w/skills/ha/scripts/ha …` (or via an `ha` on PATH where the host
provides one). Unknown commands exit 2; HTTP errors are printed and exit 1.

## Rules for changing things

- **Look before you change.** `ha states PATTERN` first, so you act on the
  right entity and know its current state.
- **Schedules treat your change as a manual override.** If a light schedule
  runs (check `ha schedule`), any change you make pauses it, typically until
  its next waypoint. That is right when the human asked for the change. If you
  only changed something to test or demonstrate, restore it with
  `ha schedule resume` and say so.
- Use `color_temp_kelvin`, not mireds. Check a light's
  `min_color_temp_kelvin` and `max_color_temp_kelvin` with `ha get`.
- **Configuration is not done through this CLI:** automations, helpers,
  integrations, users and HTTP settings belong in the host's repository and
  deployment process, or with the human.
