---
name: repo-keys
description: >
  Fleet git access via per-repo deploy keys. Use when a git pull/push
  is refused (Permission denied / repository not found), when setting
  up a new machine or homedir, when cloning any yair/* repo on a
  satellite, or when asked to "add a key", "set up repo access", or
  "wire the remotes". Explains the model and drives the add-repo-key
  script.
---

# repo-keys — how this fleet talks to GitHub

## The model (read this before touching anything)

Every homedir (locus) reaches GitHub **only** through per-repo deploy
keys. A GitHub deploy key attaches to exactly ONE repo — so the unit
of access is the (locus × repo) pair, and the key IS the permission
matrix entry. Full design: `design/CREDENTIALS.md` in the engine repo.

- Keys live in `~/.ssh/engine-keys/<repo>` (+ `.pub`). No passphrase —
  they are deliberately NARROW.
- Each key gets an ssh alias in `~/.ssh/config`:

      Host gh-<repo>
          HostName github.com
          IdentityFile ~/.ssh/engine-keys/<repo>
          IdentitiesOnly yes

- Repo remotes use the alias: `git@gh-<repo>:yair/<repo>.git`.
  A plain `github.com` URL will NOT pick the right key.
- Read-only vs read-write is chosen when the key is ATTACHED on
  GitHub, not in the key material. Default is RO. RW is only for a
  locus's own repos (see the matrix in design/CREDENTIALS.md).

## The tail is lazy — and that's fine

Most repos have no key on most machines. A refused pull means "this
locus never got a key for that repo", not breakage. Minting one takes
a minute; that is the intended flow, for humans and agents alike.

## Agents: what you may and may not do

- You MAY generate keys, print pubkeys, edit `~/.ssh/config`, and flip
  git remotes — that's what `add-repo-key` does.
- You may NOT attach keys to GitHub yourself, use yair's personal ssh
  key, or use any `gh` auth/token you find lying around. Attachment is
  the KEYMASTER's move: yair (or his zhizi session) runs the
  `gh repo deploy-key add` command you hand him. If you can run `gh`
  authenticated, you are on the keymaster locus; still confirm with
  yair before attaching.
- Read-only unless the matrix says otherwise. Ask before requesting RW.

## The flow

    ~/w/skills/repo-keys/add-repo-key <repo>            # RO (default)
    ~/w/skills/repo-keys/add-repo-key --rw <repo>       # RW (justify it)

The script is idempotent: it generates the key if missing, ensures the
ssh-config block, prints the pubkey with the exact attach command for
the keymaster, and — once the key is attached — flips the remote of a
checkout you point it at (`--dir`) and verifies with `git ls-remote`.

Typical agent transcript:

1. `add-repo-key zeresh-ops` → prints pubkey + attach command.
2. Hand both to yair ("needs the keymaster"). STOP; do not retry
   the pull until he confirms.
3. After attachment: `add-repo-key zeresh-ops --dir ~/w/zeresh-ops`
   (re-run; now the verify step passes) or clone fresh:
   `git clone git@gh-zeresh-ops:yair/zeresh-ops.git`.

## Yair's own escape hatch (humans only)

The remote flip routes EVERYONE through the deploy key — including
yair's hand-pushes. Where he wants to push as himself (repos with a
protected main, e.g. dotfiles), his personal identity rides a second
remote, added on his say-so only:

    git remote add me git@github.com:yair/<repo>.git   # personal key
    git push me main

Agents never use the `me` remote.

## New machine bootstrap

The five synced repos (engine, skills, brain, token-usage, dotfiles)
each need an RO key, the locus's own admin repo an RW key. Run
`add-repo-key` once per repo, hand the pubkey batch to the keymaster
in one message, then wire remotes. Record the leg on the engine task
for the sync matrix if one is open.
