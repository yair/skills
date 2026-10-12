---
name: golem-apps
description: >
  Host a small web app on golem, the fleet's home server, at its own
  https://<app>.albanialink.com on the tailnet, and maintain it yourself:
  deploy a GitHub-built image, check status and logs, restart, roll back and
  set secrets, and give it its own PostgreSQL database. For OpenClaw assistants, Engine geniuses and humans alike. Use
  when asked to "host", "deploy", "put online" or "keep running" an app or
  website for the family's devices, when an app should stop depending on a
  laptop being awake, when a hosted app is down or misbehaving, or when an app
  needs a secret such as an API key.
---

# golem-apps: your app on golem, maintained by you

Paths in this skill like `scripts/ghcr-check` and `assets/golem-image.yml`
are inside this skill's folder: from the root of a skills checkout, that's
`golem-apps/scripts/ghcr-check`.

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
  The narrow exceptions are explicit and per app: **its own database** if it
  has one (section 6), and anything on a short, closed list of services
  golem's admin can grant (empty today).
- **Not public.** Only tailnet devices reach it. Publishing to the internet is
  a different, future procedure through bakkies.
- **No shared data between apps.** Each app has its own `/data` and, if it
  asks, its own database. To use another app's data, call that app's API.

## 1. What your repository must contain

Copy `golem-app-fixture` (github.com/yair/golem-app-fixture): it is the
smallest app that works, and every rule below is visible in it.

**Getting a repository.** GitHub accounts belong to humans. An OpenClaw
assistant asks its human to make the repository once; afterwards the assistant
pushes with its own key.

1. **The human**, starting from a copy of the fixture (or your own code):

       git clone https://github.com/yair/golem-app-fixture myapp && cd myapp
       rm -rf .git && git init -b main && git add -A && git commit -m "start from golem-app-fixture"
       gh auth login                                 # once, as the human, if gh isn't logged in yet
       gh auth refresh -h github.com -s workflow     # once; needed to push the workflow file
       gh repo create OWNER/myapp --public --source . --push

   Then they let the assistant push. Either they attach the assistant's key
   with write access, through the `repo-keys` skill or GitHub > repository >
   Settings > Deploy keys > "Allow write access", or they push for it.
2. **The assistant** clones `git@github.com:OWNER/myapp.git` with that key,
   changes the code, and pushes to `main`. Every push runs the workflow.

A deploy key can push anything **except** files under `.github/workflows/`;
changes to the workflow itself go through the human (see below).

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

**Pushing the workflow file needs a GitHub login allowed to change
workflows:** a classic token or `gh` login with the `workflow` scope, or a
fine-grained token with "Workflows: write". SSH deploy keys and tokens without
it are refused ("refusing to allow ... to create or update workflow"). If that happens, ask a human with that scope to
add the file once; later pushes of other files work normally. One way, with
the GitHub CLI:

    gh auth login                               # if not logged in yet
    gh auth refresh -h github.com -s workflow
    gh api -X PUT repos/OWNER/REPO/contents/.github/workflows/golem-image.yml \
      -f message="golem image workflow" -f content="$(base64 -w0 golem-image.yml)"

## 2. Check the image before you ask for anything

After the workflow is green, from your own machine:

    golem-apps/scripts/ghcr-check OWNER/REPO <commit-sha>     # from a skills checkout

It prints `OK` and the image digest, or says exactly what is wrong: no such
tag (the workflow didn't publish it), or the package is **private**. Packages
published from a public repository have come out public so far, but don't
assume: `ghcr-check` tells you. If yours is private, either make it public
(`https://github.com/users/OWNER/packages/container/REPO/settings`, "Change
visibility"; for an organization, `orgs/` instead of `users/`) or ask golem's
admin to install a **read-only registry token** for your app. That is an
admin handoff, arranged with golem's admin: `secret-set` does **not** affect
image pulls. Quote the digest in your request.

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
| database? | yes | its own PostgreSQL database (section 6) |
| digest | from `ghcr-check` | proves the image exists |

golem's admin registers the app and requests its name from bakkies. The
address works once bakkies has published the name and reissued golem's
certificate, usually within the hour; until then `https://<app>...` won't
connect, but you can already deploy.

## 5. Day to day

Every command has the same shape. Use your key and golem's tailnet name:

    ssh -i ~/.ssh/golem-apps golem-apps@golem.tn.albanialink.com <command>

**First login.** Wait until golem's admin confirms your key is installed.
Then check golem's host key before trusting it:

    ssh-keyscan -t ed25519 golem.tn.albanialink.com 2>/dev/null | ssh-keygen -lf -

It must print `SHA256:nOFBuRFkoaPBzoN3kzyOQUNicGsOAFjtw30KNF6AFQo`. If it
doesn't, stop and tell golem's admin. If it matches, connect once with
`-o StrictHostKeyChecking=accept-new` and run `apps`; you should see your
app(s). From then on, an entry in `~/.ssh/config` saves typing:

    Host golem-apps
        HostName golem.tn.albanialink.com
        User golem-apps
        IdentityFile ~/.ssh/golem-apps
        IdentitiesOnly yes

after which every command is `ssh golem-apps <command>`, e.g.
`ssh golem-apps status testapp`. A command you are not allowed to run fails
with a one-line reason. You never get a shell.

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
| `db-check`, `db-sql`, `db-dump` | the app's database (section 6) |

Deploy by commit SHA (what the workflow tags), not `latest`, so `releases`
tells you exactly what ran. golem keeps the last five healthy releases.

### Secrets

Secrets become environment variables of your app, from the next `deploy` or
`restart`. **Send them from a file, never type or paste them where a
transcript or chat can see them:**

    ssh -i ~/.ssh/golem-apps golem-apps@golem.tn.albanialink.com secret-set smokelog API_KEY < api-key.txt

Names look like `API_KEY` (capitals, digits, `_`). `PORT` and
`DATABASE_URL` are reserved: golem sets them. Values
are one line, up to 4 KB. A secret you generate yourself never needs a human:
`openssl rand -hex 32 > session-secret.txt`.

If someone else holds the secret (say, Assaf's password for a service), they
give it to you the way they normally share things with you, you put it in a
file, and you run `secret-set`. Don't put it in Buzz, Engine, GitHub or chat.

## 6. A database

An app can have its own PostgreSQL database (on bakkies, backed up nightly).
Ask for it with the app, or later; golem's admin arranges it.

- **Your app gets it as `DATABASE_URL`**
  (`postgresql://user:password@host:port/database?sslmode=disable`). Most
  libraries take that string directly. You never see or handle the password.
  golem rotates it when needed.
- **The app's own role reads and writes data but cannot change the schema**
  (no creating, altering or dropping tables). So schema changes are not done
  by the app at start-up. **You** make them, as the database's owner, through
  golem:

      ssh ... golem-apps@golem.tn.albanialink.com db-sql smokelog < migrations/0003-add-mood.sql

  Inside its own database the owner can do anything: create, alter and drop
  tables, indexes and views, and read or fix data. It has no rights anywhere
  else. Tables the owner creates in the `public` schema are automatically
  readable and writable by the app.
- **Everything you send in one `db-sql` runs as one transaction:** if any
  statement fails, none of it is applied. The exception: if your SQL contains
  its own `COMMIT`, what came before it stays committed even if a later
  statement fails, so check the state before retrying. Simplest: don't put
  `BEGIN` or `COMMIT` in it. Send plain SQL only; psql's
  backslash commands (`\d`, `\i`, `\copy` ...) are not available. To list
  tables, query `information_schema.tables`.

| Command | Does |
|---|---|
| `db-check <app>` | connects exactly as the app does and prints the role and database |
| `db-sql <app>` | runs SQL from standard input as the owner, as one transaction unless it commits itself (up to 100 KB in, 1 MB out, 15 minutes); split bigger loads |
| `db-dump <app>` | prints a plain-SQL dump of the whole database: your own copy, e.g. before a risky change |

**Order for a change that touches the schema:**
1. `db-dump` to a file, so a restore can go back to exactly this point.
2. A **backwards-compatible** `db-sql` migration: add, don't rename or drop
   yet. The release that is running now must keep working with it.
3. `deploy` the new release.
4. Clean up (drop old columns) in a later migration, once you won't roll
   back past it.

`rollback` restores code, never the schema or data.

**Restoring data is not self-service.** There is no restore command, and
`db-sql` cannot replay a dump: `pg_dump` output loads table data with
`COPY ... FROM stdin`, which `db-sql` does not support, and its input is capped
at 100 KB. To restore, ask golem's admin, who arranges it with bakkies' admin.
Say:
- which app;
- which point in time: one of bakkies' nightly dumps (03:00, kept by bakkies),
  or a `db-dump` file you kept, which you then hand over as the admin directs;
- whether the whole database is to be replaced, or which tables;
- whether the app should be stopped meanwhile.

A restore replaces data written since that point, so say what may be lost.

## 7. When things go wrong

**Practise a failed release first** (with the fixture, or any app that
supports it). The fixture fails its health check on purpose when the secret
`FIXTURE_FAIL_HEALTH_VERSION` equals its commit SHA. You need a **second,
published** release, different from the one running now: if you marked the
running release, the restored release would fail too.

    echo <sha of a published release that is NOT running now> > fail.txt
    ssh golem-apps secret-set testapp FIXTURE_FAIL_HEALTH_VERSION < fail.txt
    ssh golem-apps deploy testapp $(cat fail.txt)    # fails; previous release is restored
    ssh golem-apps releases testapp                  # shows the failed attempt
    ssh golem-apps secret-unset testapp FIXTURE_FAIL_HEALTH_VERSION
    ssh golem-apps deploy testapp $(cat fail.txt)    # now healthy
    ssh golem-apps rollback testapp                  # and back again


- **Deploy says the health check failed:** the previous release is back and
  healthy. Read the log lines it printed, fix, push, deploy the new SHA.
- **Deploys are not zero-downtime.** golem replaces the container in place, so
  expect a few seconds of 502 during any deploy, restart or rollback. A
  failed deploy can mean up to about a minute of errors (the health-check
  window) before the previous release is back. Deploy when that is acceptable.
- **`cannot pull`:** run `ghcr-check`. Usually the tag doesn't exist yet
  (workflow still running or red) or the package is private.
- **The app is up but behaves badly:** `logs`, then `rollback` if a recent
  deploy caused it.
- **What rollback does not undo:** anything your app wrote to `/data` or its
  database, and any schema change. Make changes backwards-compatible, and take
  a `db-dump` first (section 6). Restores go through golem's admin
  (section 6).
- **`/data` is not backed up yet** (planned). Until it is, keep anything you
  can't afford to lose in the database, which bakkies dumps nightly, or export
  it through your app.
- **`db-check` fails:** the database may not be provisioned yet, or the app has
  never been deployed (its network carries the database path). Deploy once,
  then retry. If it still fails, ask golem's admin.
- **"you do not maintain an app called ..."**: wrong app name, or you aren't
  listed as its maintainer. Ask golem's admin.
- **"another operation on this app is running"**: wait and retry; one
  operation per app at a time.
- **Anything else** (the app must reach some private service, needs more
  memory, a new maintainer, retirement): ask golem's admin, as in section 4.
