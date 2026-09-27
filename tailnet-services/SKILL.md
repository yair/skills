---
name: tailnet-services
description: >
  How a new web service on one of the fleet's tailnet hosts (golem, zhizi,
  effc) gets a name, tailnet DNS, and a trusted HTTPS certificate. Use when
  installing or exposing a service on one of those machines, when choosing its
  hostname, when a *.albanialink.com name does not resolve or shows a
  certificate warning on the tailnet, when setting up the host's landing page
  or reverse proxy, or when asked to "add a service", "give it a domain", "get
  a cert", or "put it on the tailnet". For Engine geniuses and OpenClaw
  assistants alike.
---

# tailnet-services — names, DNS and certificates for tailnet hosts

## The model (read this before asking for anything)

**bakkies is the only public node.** Every `*.albanialink.com` name resolves
publicly to bakkies, which answers "404, never heard of it" for anything it
does not serve. That makes bakkies the only machine that can prove a name to
Let's Encrypt, so **bakkies issues every host's certificate**. Your host never
talks to Let's Encrypt.

Inside the tailnet, bakkies' headscale overrides those names to point at your
host. Tailnet machines resolve through MagicDNS. Pi-hole on golem forwards the
whole albanialink.com zone to MagicDNS, so a device that asks Pi-hole directly
gets the same answers, with nothing copied by hand. Services stay tailnet-only:
nothing on the public internet reaches them.

Each host has **one certificate carrying all of its names**. Adding a name
reissues it, which also changes its NPM id (`npm-N`).

The registry of every name is `tailnet/services.json` in bakkies' repository.
It, not this file, is the source of truth.

## Names: exactly two shapes

| Shape | Use for | Example |
|---|---|---|
| `<svc>.albanialink.com` | a service with one home | `buzz.albanialink.com`, `telemetry.albanialink.com` |
| `<svc>.<host>.tn.albanialink.com` | one instance per host of something that runs everywhere | `st.zhizi.tn.albanialink.com` for zhizi's Syncthing |

Each host's own `<host>.albanialink.com` is its **landing page**: a list of
everything registered to that host. Serve it. It is how Yair, Assaf and David
find what runs where once there is too much to remember.

Refused, and why:

- `<svc>.<host>.albanialink.com`, e.g. `st.golem.albanialink.com`: each host
  has a public record, and a DNS wildcard never reaches below an existing
  name, so these are NXDOMAIN publicly and can never be certified.
- A bare label such as `buzz` or `jellyfin`: fine to *type* (the tailnet's
  search domain resolves it), but no certificate authority issues for it.
  Serve it as a **plain-http redirect** to the real HTTPS name. Redirects only
  rescue `http://`: TLS happens before any redirect can.
- `foo.golem`: most resolvers only apply search domains to single labels, and
  no authority issues for it.
- Anything with an IPv6 (AAAA) record: the tailnet runs on IPv4, and bakkies
  drops inbound IPv6, which would silently break certificate renewal.

## Getting a name: ask, don't do it yourself

Never edit another machine to get a name, including bakkies. Ask bakkies'
admin:

- **Engine geniuses:** file a task for bakkies:
  `engine task new --spec-file req.json --target-locus repo:bakkies-docker --by <your-actor>`.
  Say which **host**, which **names** (in the shapes above), and **what each
  serves**. An interactive task is fine; it is quick work.
- **OpenClaw assistants and humans:** ask Yair, with the same three facts.

bakkies then:

1. registers the names (a reviewed change),
2. publishes them in tailnet DNS, so they resolve to your host within seconds,
3. reissues your host's certificate with its complete name list,
4. tells you the new certificate id.

Pi-hole needs nothing: it forwards to MagicDNS, so it follows automatically.

A name already registered to another host is refused. Pick another.

## What you do on your host

1. **Route the name** in your reverse proxy (Caddy on golem) to the service.
   Listen on the tailnet only.
2. **Serve the landing page** at `<host>.albanialink.com`. bakkies can
   generate the list: `tailnet-service landing --host <host> --format html|json`.
3. **Install the certificate** when it changes: write the pair atomically,
   check that its SAN list is exactly your registered names before trusting it,
   then **reload** your proxy. Caddy does not notice changed certificate files
   by itself, and a renewed certificate that is never served is the most common
   way certificates "expire" here.

## Getting the certificate onto your host

Each host has its own account on bakkies, `cert-<host>`, whose key can do exactly
one thing: hand over that host's certificate, key and manifest as a tar. The key
works only from your host's tailnet address, and it cannot open a shell, run a
command, forward a port, or read another host's files.

1. **Make the key on your host**, and never copy it anywhere else:

       ssh-keygen -t ed25519 -N '' -C cert-<host>-fetch -f ~/.ssh/bakkies-cert

   Send only the `.pub` to bakkies: Engine geniuses through their task for
   bakkies, OpenClaw assistants through Yair.
2. **Fetch** (over the tailnet):

       ssh -i ~/.ssh/bakkies-cert -o IdentitiesOnly=yes -o BatchMode=yes \
           cert-<host>@bakkies.tn.albanialink.com > bundle.tar

   bakkies' host key is ED25519 `SHA256:kcBAnnLiVUikVs60xYK8lUiNSQRKGukZDzZ3qXNCvgo`.
   Pin it rather than accepting whatever answers.
3. **Validate before trusting.** Unpack to a private temp directory, then check:
   - `manifest.json` names your host, and exactly your registered names;
   - `openssl x509 -in fullchain.pem -noout -ext subjectAltName` agrees;
   - `openssl x509 -checkend 0` passes;
   - the certificate's public key equals `openssl pkey -in privkey.pem -pubout`;
   - the manifest's `sha256` equals the certificate's SHA-256 fingerprint
     (colons removed, lowercase).
4. **Install only when `sha256` changed:** stage beside the destination, key
   `0600`, rename both, then **reload** your proxy once.
5. **Schedule it** hourly or daily. It is idempotent, so a missed run heals on
   the next one. bakkies refreshes its side hourly, and certificates renew 30
   days before they expire.

A new name, or a renewal, arrives the same way, with nothing to change on your
side: the manifest's `sha256` changes and your job installs it.

**Windows (effc):** Windows 10/11 ship `ssh.exe` and `tar.exe`, so the same two
commands work in PowerShell; `openssl` is not built in (use Git's copy or
`certutil`).

Never use any other key or account to reach bakkies for this.

## Current registrations (snapshot, 2026-09-27)

| Host | Address | Certificate | Names |
|---|---|---|---|
| golem | 100.64.0.4 | `npm-20` | golem, buzz, jellyfin, seerr, audiobookshelf, kavita, files, syncthing, qbittorrent, sonarr, radarr, lidarr, prowlarr, netalertx, pihole (`.albanialink.com`); `st.golem.tn` |
| zhizi | 100.64.0.2 | `npm-21` | zhizi, telemetry, engine, tu, zchat (`.albanialink.com`); `st.zhizi.tn` |
| effc | 100.64.0.5 | `npm-22` | effc, david, concrete, zodiduck (`.albanialink.com`); `st.effc.tn`, `widgets.effc.tn` |

`david.albanialink.com` points at effc on the tailnet already. It answers as
soon as effc serves it, and nothing on bakkies needs to change first.

## effc

effc is a Windows laptop, administered by David (Assaf's OpenClaw assistant),
and not part of Engine. Requests and certificates reach it through Yair.
