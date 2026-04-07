---
name: commit
description: >
  Structured commit workflow: preflight checks, adversarial code review,
  polish, build/deploy/test, staging with user review, and commit.
  PROACTIVELY suggest committing whenever a logical unit of work is done —
  a bug is fixed, a feature works, tests pass, or you're about to start
  a different task. Say something like "This looks like a good commit
  point — want me to run /commit?" You should feel a mild compulsion to
  suggest this at natural breakpoints, even if the user hasn't mentioned
  committing. The user is always in the loop and must approve, but YOU
  should be the one to bring it up. Also triggers on /commit, "let's
  commit", "ready to commit", "stage the changes", or "prepare a commit".
---

# Commit Workflow

You are guiding a structured commit process. The user cares about code
quality and wants to understand every change going in. Never rush, never
skip phases, and never commit without explicit approval.

Project-specific details (build command, deploy scripts, config files to
review, binary size baselines) come from the project's CLAUDE.md or the
conversation context. The workflow below is the universal structure.

## When to suggest a commit

Be proactive: if a feature is working, tests pass, and the code is in a
good state, suggest committing. Say something like "This looks like a
good point to commit — want me to run /commit?" But never start the
workflow without the user's go-ahead.

## Phase 1 — Preflight

Run these checks and present the results before doing anything else:

1. **Branch check**: Show current branch. Fetch upstream. Check for new
   commits on the base branch (typically `main`) that might need merging.
   If there are upstream changes, warn the user — they may want to merge
   or rebase before committing.

2. **Git status**: Show modified, staged, and untracked files. Flag any
   files that look like they shouldn't be committed (credentials, build
   artifacts, large binaries, `.env` files).

3. **Config review**: If the project has a primary config file (e.g.,
   `app.json`, `.env.example`, `config.yaml` — check CLAUDE.md), read
   and present it even if unchanged. Config drift causes subtle bugs.
   If any values look unexpected, flag them.

4. **Commit granularity**: Look at the changes and suggest whether this
   should be one commit or multiple logical units. Ask the user to decide.
   Each commit should be one coherent change — don't mix unrelated work.

## Phase 2 — Bug Hunt

This is an adversarial code review, not a rubber stamp.

For every changed file, read the diff AND the surrounding code. Then:

- **Find real bugs**: overflow, off-by-one, null deref, use-after-free,
  race conditions, integer truncation, missing error handling.
- **Check edge cases**: what happens at min/max values, at zero, at
  boundary conditions? What if a function returns an error?
- **Review adjacent code**: code that calls or is called by our changes.
  If pre-existing code has a bug that interacts with our changes, flag
  it. Note who wrote it and whether we're comfortable modifying it.
- **Classify findings**: BUG (must fix), RISK (worth discussing),
  NIT (minor, fix if easy). Present all findings to the user.

Fix bugs you're confident about. Raise uncertainties with the user.
For pre-existing issues in other people's code, always ask before
changing — explain what's wrong, what the fix is, and what could break.

## Phase 3 — Polish

Can be combined with the bug hunt if that's more efficient.

- Remove debug prints, TODO comments that are done, commented-out code
  that's no longer relevant.
- Verify variable and function names are clear and consistent.
- Ensure comments are present where the logic isn't self-evident, but
  not excessive. Remove comments that just restate the code.
- **Unused functions**: if any function exists but isn't called, add a
  comment block explaining WHY it's kept (future use, manual testing,
  diagnostic tool, etc.). Don't silently leave dead code.

## Phase 4 — Build & Test

1. **Build**: Run the project's build command. The build must succeed
   with no new warnings in our code. Pre-existing warnings in other
   people's untouched code are noted but not blockers for this commit —
   log them as a separate TODO.

2. **Binary size** (compiled projects): Check the output binary size
   and compare against the last known size. Report the delta. A large
   unexpected increase means something got accidentally linked or an
   optimization was lost.

3. **Deploy & verify** (if the project has a device or staging target):
   Use the project's deploy script. Reconnect if needed. Verify the
   deployed artifact is running correctly.

4. **Sanity check**: Ask the user to verify on their end. Wait for
   their confirmation before proceeding.

## Phase 5 — Stage & Review

1. **Stage files**: Use `git add` for files that belong entirely to this
   commit. Use `git add -p` when a file contains changes for multiple
   commits (split by hunk). Never `git add -A` or `git add .`.

2. **Present for review**: Show the user:
   - List of staged files with a one-line description of each
   - The full `git diff --cached`
   - Your proposed commit message

3. **Commit message format**:
   - First line: imperative mood, under 72 characters, summarizes the
     change (e.g., "Fix gain oscillation via sensor dgain compensation")
   - Blank line
   - Body: explain WHY, not WHAT. What problem did this solve? What was
     the root cause? What approach was taken and why?
   - Always end with: `Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>`

4. **Wait for approval**: Do NOT commit until the user explicitly says
   to proceed. They may want to adjust the message, change what's staged,
   or split things differently. Use a HEREDOC for the commit message to
   preserve formatting.

## Phase 6 — Commit & Push

1. **Commit** with the approved message.
2. **Push**: Only if the user explicitly asks. Never push unprompted.
3. **Post-commit**: If significant findings came up during the bug hunt
   or the session produced notable insights, suggest saving them to
   memory files or brain. Offer, don't force.
4. If there are more commits to make (from the granularity decision in
   Phase 1), loop back to Phase 5 for the next one.

## Principles

- The user's approval gates every commit. No exceptions.
- Quality over speed. A thorough review now prevents a revert later.
- When in doubt, ask. It's cheaper to pause than to commit a bug.
- Track what you learn. If the bug hunt reveals something about the
  codebase, that knowledge should outlive this commit — save it to
  persistent memory.
