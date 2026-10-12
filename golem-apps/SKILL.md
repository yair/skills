---
name: golem-apps
description: >
  Host a small web app on golem, the fleet's home server, at its own
  https://<app>.albanialink.com on the tailnet, and maintain it yourself:
  deploy a GitHub-built image, check status and logs, restart, roll back and
  set secrets. For OpenClaw assistants, Engine geniuses and humans alike. Use
  when asked to "host", "deploy", "put online" or "keep running" an app or
  website for the family's devices, when an app should stop depending on a
  laptop being awake, when a hosted app is down or misbehaving, or when an app
  needs a secret such as an API key.
---

# golem-apps: your app on golem, maintained by you

## What you get, and what you don't

golem runs your app as one container, built by **your** GitHub repository's
Actions workflow and published to GitHub's registry (GHCR). Once it's set up:

- it answers at `https://<app>.albanialink.com` from any device on the tailnet
  (phones included), with a trusted certificate, even when your laptop is off;
- it restarts by itself after crashes and reboots;
- you deploy, inspect and roll it back yourself over SSH, without asking anyone.

What you don't get, by design:

- **No shell on golem**, no files, no Docker. Your SSH key can run only the
  commands listed below, and only for apps you maintain.
- **No reach into the tailnet.** Your app can reach the public internet and
  nothing private (not golem's other services, not other apps, not the LAN).
  A short, closed list of services can be granted per app by golem's admin;
  today that list is empty.
- **Not public.** Only tailnet devices reach it. Publishing to the internet is
  a different, future procedure through bakkies.
- **No shared data between apps.** Each app has its own `/data` and (later)
  its own database. To use another app's data, call that app's API.

## 1. What your repository must contain

Copy `golem-app-fixture` (github.com/yair/golem-app-fixture): it is the
smallest app that works, and every rule below is visible in it.

- A `Dockerfile` at the root. The image must run as **any non-root user id
  golem gives it**: no `USER root`, no `chown` or `apt` at start-up.
- It may write **only to `/tmp`** and, if you ask for persistent storage, to
  **`/data`**. Everything else is read-only.
- It listens on **one TCP port, plain HTTP**, read from the `PORT`
  environment variable (default 8080). HTTPS ends at golem's proxy.
- It answers **`GET /healthz`** (or a path you choose) with **200 within 60
  seconds** of starting. A deploy that fails this is undone automatically.
- All configuration comes from **environment variables**. Secrets arrive the
  same way (section 5).
- **`.github/workflows/golem-image.yml`**, copied from
  `assets/golem-image.yml` in this skill. Change `HEALTH_PATH` and `APP_PORT`
  if yours differ. On every push to `main` it builds the image, **starts it
  exactly as golem will** (random uid, read-only, no capabilities) and checks
  health, and only then publishes it to `ghcr.io/<owner>/<repo>`, tagged with
  the commit SHA. A red run publishes nothing.

**Pushing the workflow file needs a GitHub login with the `workflow`
scope.** Deploy keys and most bot tokens are refused ("refusing to allow ... to
create or update workflow"). If that happens, ask a human with that scope to
add the file once; later pushes of other files work normally. One way, with
the GitHub CLI:

    gh auth refresh -h github.com -s workflow
    gh api -X PUT repos/OWNER/REPO/contents/.github/workflows/golem-image.yml \
      -f message="golem image workflow" -f content="$(base64 -w0 golem-image.yml)"

## 2. Check the image before you ask for anything

After the workflow is green, from your own machine:

    scripts/ghcr-check OWNER/REPO <commit-sha>

It prints `OK` and the image digest, or says exactly what is wrong: no such
tag (the workflow didn't publish it), or the package is **private**. New
packages from public repositories are usually public. If yours is private,
either make it public (GitHub > your package > Package settings > Change
visibility) or arrange a read-only token for golem (section 5). Quote the
digest in your request.

On Windows, run it from Git Bash; `curl.exe` comes with Windows 10 and later.

## 3. Get access (once per maintainer)

Make a key on **the machine you run commands from**, and keep the private
half there:

    ssh-keygen -t ed25519 -N '' -C golem-apps-<your-name> -f ~/.ssh/golem-apps

Windows PowerShell: `ssh-keygen -t ed25519 -C golem-apps-<your-name> -f $HOME\.ssh\golem-apps`
and press Enter twice for no passphrase.

Send only `~/.ssh/golem-apps.pub` (one line starting `ssh-ed25519`).

## 4. Ask for your app (once per app)

Ask golem's admin, through Yair if you're an OpenClaw assistant, or with an
Engine task for genius `golem-admin` if you're a genius. Give:

| Field | Example | Notes |
|---|---|---|
| app name | `smokelog` | lowercase letters, digits, `-`; becomes `smokelog.albanialink.com` |
| image | `ghcr.io/david/smokelog` | the repository only, no tag |
| port | 8080 | inside the container |
| health path | `/healthz` | |
| persistent `/data`? | yes | survives deploys and restarts |
| memory | 128m | up to 1g |
| maintainers | `david`, `zeresh` | each needs a key (section 3) |
| digest | from `ghcr-check` | proves the image exists |

golem's admin registers the app and requests its name from bakkies. The
address works once bakkies has published the name and reissued golem's
certificate, usually within the hour; until then `https://<app>...` won't
connect, but you can already deploy.

## 5. Day to day

Every command has the same shape. Use your key and golem's tailnet name:

    ssh -i ~/.ssh/golem-apps golem-apps@golem.tn.albanialink.com <command>

The first time, check golem's host key: ED25519
`SHA256:nOFBuRFkoaPBzoN3kzyOQUNicGsOAFjtw30KNF6AFQo`.

| Command | Does |
|---|---|
| `apps` | lists the apps you maintain |
| `status <app>` | container state, health, current release, last operation |
| `deploy <app> <tag-or-digest>` | pulls that image from your repository, starts it, checks health. **If health fails, the previous release is restored** and you get the reason and the app's last log lines. |
| `logs <app> [--lines N] [--since 30m]` | the app's own output (N up to 1000) |
| `restart <app>` | restarts the current release and re-applies secrets |
| `releases <app>` | the release history |
| `rollback <app> [sha256:...]` | goes back to the previous healthy release, or a named one |
| `secret-set <app> <NAME>` | stores a secret, **value on standard input** |
| `secret-list <app>` | secret names only, never values |
| `secret-unset <app> <NAME>` | removes one |

Deploy by commit SHA (what the workflow tags), not `latest`, so `releases`
tells you exactly what ran. golem keeps the last five healthy releases.

### Secrets

Secrets become environment variables of your app, from the next `deploy` or
`restart`. **Send them from a file, never type or paste them where a
transcript or chat can see them:**

    ssh -i ~/.ssh/golem-apps golem-apps@golem.tn.albanialink.com secret-set smokelog API_KEY < api-key.txt

Names look like `API_KEY` (capitals, digits, `_`). `PORT` is reserved. Values
are one line, up to 4 KB. A secret you generate yourself never needs a human:
`openssl rand -hex 32 > session-secret.txt`.

If someone else holds the secret (say, Assaf's password for a service), they
give it to you the way they normally share things with you, you put it in a
file, and you run `secret-set`. Don't put it in Buzz, Engine, GitHub or chat.

## 6. When things go wrong

- **Deploy says the health check failed:** nothing changed for your users;
  the old release is back. Read the log lines it printed, fix, push, deploy
  the new SHA.
- **`cannot pull`:** run `ghcr-check`. Usually the tag doesn't exist yet
  (workflow still running or red) or the package is private.
- **The app is up but behaves badly:** `logs`, then `rollback` if a recent
  deploy caused it.
- **What rollback does not undo:** anything your app wrote to `/data` (or,
  later, to its database). If a release changes stored data, make the change
  backwards-compatible, or back the data up through the app first.
- **"you do not maintain an app called ..."**: wrong app name, or you aren't
  listed as its maintainer. Ask golem's admin.
- **"another operation on this app is running"**: wait and retry; one
  operation per app at a time.
- **Anything else** (the app must reach some private service, needs more
  memory, a new maintainer, retirement): ask golem's admin, as in section 4.
