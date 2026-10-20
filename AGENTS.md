# Changing the skills (for agents)

Several admin agents change these skills, on several hosts, for Claude Code,
Codex and OpenClaw sessions. The engine doesn't enrol this repository yet, so
every change follows the procedure below, whoever makes it and wherever.

## Why `main` is special

- **What a clone has checked out is live.** Homes link skills by hand from a
  local clone, normally `~/w/skills`, into `~/.claude/skills`,
  `~/.codex/skills` and OpenClaw's skills directory. Whatever that clone has
  checked out is what every session on the home uses. Some skills run on every
  prompt: a hook in every Claude and Codex session calls `t3-inbox`.
- **The updater fast-forwards every clone.** On each home, `chezmoi-autoupdate`
  fast-forwards every clone of this repository every 30 minutes. A clone with
  uncommitted changes, or one that has diverged from `origin/main`, isn't
  pulled, and the updater pages about it once a day.

So clones stay on `main`, clean and level with `origin/main`. Work happens on
branches, in separate worktrees.

## The procedure

1. **Cut a branch in a worktree** from `origin/main`:

       git -C ~/w/skills fetch origin
       git -C ~/w/skills worktree add -b <branch> ~/w/.worktrees/skills-<slug> origin/main

2. **Edit and test there.** If a skill has `tests/`, run them from the skill's
   directory: `python3 -B -m unittest discover -s tests`. A new skill also
   gets a row in the README's table.
3. **Commit on the branch.** Never on `main`. Never rewrite what is already on
   `origin`.
4. **Get it reviewed through the engine.** Freeze the branch as a review
   dossier in your own genius's repository, under
   `docs/reviews/<slug>-<task id, 8 chars>/`, and submit the task as usual. A
   dossier holds:
   - `README.md`: the sources (branch, commits, parent), what changed and why,
     how to run the checks, and what wasn't tested;
   - `manifest.json`: full SHAs, and sha256 digests of the snapshot files;
   - `skills.patch`: `git format-patch --stdout origin/main..<branch>`;
   - `snapshot/`: the resulting files, so the reviewer can read and run them;
   - `verify.py`: hermetic checks, with a temporary `HOME`, no network and no
     live services.

   `docs/reviews/` in `yair/zhizi` has worked examples. If the engine's
   whitespace check trips on patch context, add `*.patch -whitespace` to
   `docs/reviews/.gitattributes`.
5. **After it lands, hand it to Yair** with the branch name and this command:

       git -C ~/w/skills push origin <branch>:main

   Every clone on every home fast-forwards to it within 30 minutes. A new
   skill still has to be linked by hand on each home that should have it. Then
   remove your worktree and branch.

**Never push,** by any route: git, `gh`, the GitHub API or HTTPS. Only Yair
pushes.

## Speed bumps

`.githooks/` refuses commits on `main` and all pushes from Claude and Codex
sessions. `chezmoi-autoupdate` points `core.hooksPath` at it in every clone
it syncs. It's a reminder, not security: `--no-verify` gets past it, and you
must not use it here.
