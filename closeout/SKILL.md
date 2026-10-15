---
name: closeout
description: Close out an agent session cleanly before it is settled or abandoned. Checks that everything the session meant to do is done, filed as an Engine task, or a brain todo; that its Engine tasks and MRs are landed or deliberately parked; that it left no uncommitted files, unsubmitted commits, undeployed changes or running jobs; that what it learned is in brain; and finishes with a debrief filed to brain. Fails with a numbered list of exactly what is left, and halts to ask about other sessions' mess it finds on the way. Use when the user says "closeout", "close out", "wrap up", "are we done here", "can I settle this", "what's left in this session", or at the natural end of a session's work.
---

# closeout — leave a session settled, or say exactly why not

A session is done when nothing it started is dangling and someone looking
at it later can tell what happened without scrolling. This skill gates
that. Its last act is a debrief in brain; after that the user can settle
or close the session. (`settle` is T3's own action; this skill never
writes T3 state, it only says when settling is safe.)

The checker is `scripts/closeout` (Python, stdlib only, read-only). It
finds the running session on its own (`$CLAUDE_CODE_SESSION_ID`, the
`claude --resume` / `codex resume` ancestor, or the newest transcript for
the directory); pass `--session ID-or-transcript-path` when it can't.
In the commands below, `closeout` means the `scripts/closeout` file in
this skill's directory.

Work through the steps in order. Do not skip ahead to the debrief.

## 1. Mechanical check

```
closeout check
```

The first line is the verdict: `CLEAN`, `NEEDS WORK (…)` (exit 1) or
`NEEDS YOU (n item(s) from other sessions)` (exit 2). Numbered lines are
open items, each with a `->` next action. What it checks:

| area | what blocks |
|---|---|
| git | files this session wrote that are still uncommitted, in canonical checkouts or worktrees; commits ahead of upstream that this session made |
| engine | tasks this session claimed or worked that are open with no live MR; MRs not landed (`approved` is `AUTO`: land it); in-place repository locks still held |
| deploy | changes not yet live, per the repository's deploy model (see [references/deploy-models.md](references/deploy-models.md)) |
| live | files written outside any repository, unless a repository owns an identical copy |
| procs | shell jobs the session started that are still running |
| FOREIGN | dirty files in the same repositories that this session did not write |
| PARKED | never blocks: untracked files hidden only by the repository's local `.git/info/exclude`. It is listed every time on purpose, as a reminder |

Authorship comes from the transcript: tool writes (Write/Edit/apply_patch),
plus the plain shell forms (`>`, `tee`, `cp`, `sed -i`, `curl -o`, …).
Anything written in a way the parser can't see shows up as FOREIGN, so
**check a FOREIGN item against your own memory of the session before
calling it someone else's.**

## 2. Intent and knowledge sweep (judgement)

The checker can't tell what was *meant*. Read the session. If the context
has been compacted, or the session was long, use the digest. It reads the
transcript from disk, so it covers what your context no longer holds:

```
closeout digest            # user messages, intent-like lines, files, state-changing commands, brain writes
```

Build three lists and resolve every entry:

1. **Intents.** Every request the user made, every "later / we should
   also / out of scope / next time", and every promise you made. Each
   one ends as **done** (point at the evidence), **an Engine task** (id),
   or **a brain todo** (id). A work item that belongs to a repository goes
   to Engine, filed for the genius that owns it (the `engine` skill says
   how). A personal or non-repository item goes to a brain todo.
   Something the user explicitly dropped needs nothing.
2. **Done claims.** Every "done", "landed", "deployed", "fixed" or
   "verified" in your own messages. Re-check it now against the system
   (MR status, `git log origin/main`, the live file, the service state),
   not against the transcript.
3. **Knowledge.** Facts, decisions, gotchas, preferences and working
   methods learned in the session that a future session would want.
   `brain search` first to avoid duplicates (update or supersede instead);
   then `brain remember` with the right kind, the project slug and
   entity refs. Corrections the user gave about *how to work* also go to
   the harness's own memory, if it has one.

## 3. Fix what needs nobody

Do these without asking, using the session's own Engine actor:

- land `approved` MRs (`engine mr land … --by ACTOR`) where the
  repository's rules let the session land
- file Engine tasks and brain todos for intents that are unambiguous
- write the brain entries from the knowledge list
- stop background jobs, monitors and session crons this session started
  and no longer needs
- remove worktrees whose task is done (`engine worktree rm`)
- finish the session's *own* routine flow when the work is already
  complete and verified: commit on its task branch and `engine submit`

Never do these on your own: discard or delete work, push to a remote
outside the Engine landing flow, deploy to a live system, adjudicate a
change, decide an ambiguous intent, or touch another session's files.
Those go to the user. When it is unclear which side something falls on,
ask. Asking costs a turn; guessing wrong can lose work.

Then run `closeout check` again.

## 4. Stop and ask: what is still open

If anything is open (own blockers, unresolved sweep items, or FOREIGN
items), **stop before the debrief**. For FOREIGN items, first find who
left them. The search is bounded by `--budget`, 20 seconds by default.
Pass all the paths in one call:

```
closeout whose PATH...
```

It reports, for each path: the session that wrote it (or the one that was
running when it changed), that session's T3 thread title, whether it is
live or settled, open Engine tasks that mention the path, and the last
commit that touched it.

Report to the user in this shape, verdict first. Always give session ids
in full: `claude --resume`, `codex resume` and transcript search take
only the whole UUID. Engine ids may be shortened; the CLI resolves
prefixes.

```
NEEDS YOU (4)
1. MR 3f2a… (task dacf…) in review, verdict land-candidate — adjudicate, or leave it in the queue?
2. ~/w/zhizi/scripts/foo.sh — this session wrote it, never committed. Keep (I commit + submit) or delete?
3. ~/w/zhizi/docs/mic-troubleshooting.md — not ours. Written by claude 0fd10795-… (full id; not running,
   not a T3 thread); open task 78277c9d "Commit the stray mic-troubleshooting files" covers it.
   Leave it to that task / resolve it here / route it to its session?
4. ~/w/zhizi/vmi2636596 — not ours, no recorded writer; T3 "Bakkies hosting company support"
   (settled) was running when it appeared. Leave / delete / file a task?
```

For each FOREIGN item, offer these options:

- **resolve here**: this session takes it on (file and claim a task, or
  fold it into the current one)
- **route to its session**: if that session is live, give the user a
  one-line message to paste into it
- **leave deliberately**: file an Engine task for it if none exists, or
  name the task that does

Repeat any PARKED lines at the end of the report, in one line each. They
are not questions, only reminders.

When the user decides to leave something open, record it with an ack
(`closeout check --ack PATH-or-ID-or-GLOB`, repeatable). The debrief
must state each ack's reason. Acks hold only for that run; nothing is
stored.

## 5. Debrief: the final act

Only when `closeout check [--ack …]` exits 0 and the sweep has nothing
unresolved. Look for an earlier debrief of this session first:
`brain search "<session id>"`. If one exists, supersede it.

```
brain remember --kind debrief --project <project slug> \
  --title "Debrief: <what the session was for> (<harness> <full session id>)" \
  --tags "debrief,closeout,session:<session id>" --entity-refs "<repo/genius slugs>" \
  --body "<body>"
```

The body is plain prose under these headings, each short:

- **Goal**: what the user asked for, in a sentence or two.
- **Outcome**: what changed and where it stands. Name MR ids, task
  ids, commits, and whether the change is deployed.
- **Filed for later**: Engine tasks and brain todos created, with ids.
- **Learned**: brain entries written, with ids.
- **Left open deliberately**: each acked item, why, and who owns it now,
  plus the PARKED files still present.
- **Session**: harness, full session id (never shortened), T3 thread title, transcript path.

Show the user the same debrief, then end with one line: *Debrief filed
(brain <id>). Safe to settle.*

If the session goes on afterwards, run closeout again at its new end.
The new debrief supersedes this one.
