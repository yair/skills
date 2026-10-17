---
name: t3code-upstream
description: >
  Contribute to upstream T3 Code (pingdotgg/t3code) from Yair's fork. Covers
  checking that the issue is triaged, branching, fixing in the repo's idiom,
  focused checks, live before/after evidence from an isolated dev server
  running inside the live T3, optional replay against real thread data,
  adversarial review, a PR that follows their template, and babysitting the
  bots, rebases and related PRs afterwards. Use when asked to fix a T3 Code
  bug upstream, open, update or rebase a T3 PR, comment on a T3 issue or PR,
  or watch one. Not for running or configuring T3 on our machines; for that,
  see docs/t3code.md in the zhizi repo.
---

# t3code-upstream — getting a fix into pingdotgg/t3code

T3 Code is Yair's main agent interface, so its bugs are worth fixing upstream.
Upstream accepts few outside PRs and triages them strictly. A PR that breaks
their rules is closed, however good the code. This skill is the route that
produced PR #20861 (issue #10553). It also covers the mistakes made along the
way.

Read [`references/upstream-rules.md`](references/upstream-rules.md) first, and
run the diff command at its top: upstream rules change between releases.

## Where things are

| | |
|---|---|
| Checkout | `~/w/t3code`. `origin` = pingdotgg/t3code (partial clone); `fork` = yair/t3code |
| Pushing | `git push fork <branch>` only. Never push to `origin` |
| Branch | `fix/<slug>` from fresh `origin/main` |
| PR body draft | `~/w/t3code/.git/PR_BODY_<issue>.md`. Keep it there, edit it, `gh pr edit --body-file` |
| Evidence | orphan branch `evidence/pr-<issue>-<slug>` on the fork; embed via `https://raw.githubusercontent.com/yair/t3code/<sha>/<file>.png`, pinned to the commit SHA |
| Scripts | `S=~/w/skills/t3code-upstream/scripts`: `$S/t3dev`, `$S/shot.mjs`, `$S/beforeafter`, `$S/lintdiff`. Call them by that absolute path; they are not in the checkout |
| Live T3 | the `t3code.service` user unit on zhizi, version under `~/.t3/runtime/versions/`. Don't touch it |

## Tracking and approval

All T3 work belongs to the `zhizi-admin` genius. File one engine task per
upstream PR (`engine task new --genius zhizi-admin --execution-mode
interactive --by zhizi-admin …`) and claim it. Its approval boundary:
**anything published needs Yair's go-ahead**. That covers pushing to the
fork, opening or editing a PR, and commenting on issues or PRs. Engine does not
land this work, because upstream decides the merge. Close the task when the PR
merges or is closed, and note the outcome on it.

## Procedure

### 1. Establish the problem

- Read the whole issue, every comment included. Later comments often add
  cases the first proposed fix misses.
- It must be triaged: the `via-triage` label plus a maintainer's triage
  comment. Save that comment's URL for Scope and approval. If there's no
  issue, write one first, with a minimal repro using made-up paths.
- Look for competing work: `gh pr list -R pingdotgg/t3code --search "<terms>"`,
  and the issue's cross-references (`gh api
  repos/pingdotgg/t3code/issues/<n>/timeline`). If a fix is already merged
  but not yet released, say so instead of duplicating it. Compare
  `git tag --contains <sha>` with the version Yair runs.
- If the triage suggested an approach you're not taking, you need a reason
  you can state in one paragraph.

### 2. Implement

Branch from fresh `origin/main` and run `pnpm install`. Follow the
surrounding code, and the rules digest for React Compiler, comments and
`components/ui`. Upstream lands hundreds of commits a day, and `ChatView.tsx`
and `ChatMarkdown.tsx` churn constantly, so keep your footprint there small.
Put logic in `packages/shared` and keep a thin wiring layer in web and mobile.
A change that affects both web and mobile needs both, or the PR has to say
why one is out of scope.

### 3. Focused checks

Run them in this order, and don't repeat a passing check until the code changes:

```bash
cd ~/w/t3code
npx vp test run <your test files> <neighbouring suites> apps/web/src/reactCompilerCoverage.test.ts
for p in apps/web apps/mobile packages/shared; do (cd $p && pnpm run typecheck); done   # only the packages you touched
npx vp fmt --check <touched files>
$S/lintdiff        # commit first: it refuses while touched files have uncommitted changes
```

Lint: what matters is no *new* diagnostics, because main already has many.
`lintdiff` lints the changed files at the branch and at the merge base,
compares rule and message per file (line moves don't count), and requires new
files to be clean. It exits 1 when the branch adds anything or lint fails.

A failing test needs the same comparison by hand. Commit or stash, check out
the base's version of the code under test (`git checkout origin/main -- <file>`),
rerun, then `git checkout HEAD -- <file>`. Report it as pre-existing only if it
fails there too.

### 4. Live evidence

UI changes need before/after screenshots. Get them from a dev server with
throwaway state and dummy fixtures, never from Yair's live install or real
paths.

1. Build fixtures under one root, e.g. `/tmp/t3dev/fixtures`: small git repos
   (`git init`, a commit), an outside folder, a real media file if media is
   involved (`ffmpeg -f lavfi -i sine=d=4 x.mp3`). The paths will show up in
   screenshots, so make them read as obviously made up.
2. `$S/t3dev start --home /tmp/t3dev/home`, with the branch under test checked
   out. It strips the live service's `T3CODE_*` environment, which would
   otherwise aim the dev server at the live port and state, and it refuses a
   home inside `~/.t3`. It prints the web URL and a pairing URL.
3. Drive it with `PAIR_URL="$($S/t3dev pair-url --home /tmp/t3dev/home)" $S/shot.mjs steps.json`
   (the `PAIR_URL` prefix is only needed the first time a browser profile is
   used). The step format is in the script header, and it exits 1 if any step
   failed. Add a project with the fixture repo, then send the agent
   a prompt that makes it use tools and reply the way the bug needs, e.g.
   "use the Read tool on X, run `cd Y && ls raw`, then reply with these
   relative links". A cheap model is fine, and its real tool calls are the
   point. Pull the facts out with `eval` steps (hrefs, `audio.duration`,
   error text), not just pixels.
4. Before: stop the server, check out `origin/main` in the same checkout, start
   it again on the **same home**, and run the same steps with the same clips.
   After: switch back to the branch and repeat. Thread state persists in the
   home, so both builds render the same agent reply. Panels remember whether
   they were open, so close them conditionally in an `eval` rather than
   toggling them.
5. `$S/beforeafter before.png after.png out.png` stacks each pair with
   labels. Look at every image before using it. Tooltips get clipped and
   panels left open spoil shots.
6. `$S/t3dev stop --home /tmp/t3dev/home` stops exactly the processes that
   start launched, including children that outlive the runner. Then restore `apps/web/src/routeTree.gen.ts`, which the dev
   server rewrites, and never `git commit -a` while it's modified.

### 5. Real-data replay (optional, private)

If the bug is about how real threads render, run the change over Yair's own
history. Snapshot the database with SQLite's backup, which includes the WAL
(a plain `cp` of a live database can miss committed data):
`sqlite3 -readonly ~/.t3/userdata/statev2.sqlite ".backup /tmp/t3-replay.sqlite"`.
The frozen V1 `state.sqlite` holds threads from before 0.1.0. Open the copy
read-only and count outcomes: fixed, unchanged, regressed, moved from one
existing file to another. Count the change's raw proposals as well as its
final behaviour, or a safety gate in the replay hides the cases it blocks. `references/examples/replay-file-links.ts` is the
example from #20861. In the PR, report only counts. **Delete the copy** when
you're done, and say that you did.

### 6. Adversarial review

Before publishing, have the other lineage attack it. In T3, use
`delegate_task` to Codex with GPT-6.1-Sol; elsewhere, use `~/.local/bin/codex-run`.
Give it the issue, the diff, the evidence, and the instruction to find
concrete failing inputs. Fix what holds up, and list what changed in the PR's
Verification section. Last time this found the most important design flaw:
a working link could silently move to another file.

### 7. Publish (after Yair's go-ahead)

- Squash into one commit. The title is a plain-language conventional commit
  describing the outcome. The body says why, ends with `Fixes #<n>` and the
  `Co-Authored-By` trailer.
- Body: their template's four headings, in this order. Scope and approval
  links the issue and the triage comment. Verification covers the live table
  or screenshots, focused tests, typecheck and lint against main, the
  adversarial review, and **Not checked** (device, other providers,
  desktop…). The last line names the model and harness, e.g. "Written by
  Claude Opus 5.5 in Claude Code; reviewed by GPT-6.1-Sol in Codex.", followed
  by the Claude Code attribution line.
- Push the evidence branch first (a `git init` scratch repo, orphan commit,
  `git push https://github.com/yair/t3code.git HEAD:refs/heads/evidence/…`),
  then check that every `raw.githubusercontent` URL returns 200. Push the code
  branch with `git push fork`, then `gh pr create -R pingdotgg/t3code --head
  yair:<branch> --body-file …`.
- In T3: run `link_pull_request` on the PR URL immediately. If there's a
  related or competing PR, comment there with a short table of how the two
  differ, and say who rebases if both land.

### 8. Babysit

- In T3, run `watch_pull_request` and end the turn. It wakes you on checks,
  comments and conflicts. Run `unwatch_pull_request` before handing back.
- `action_required` on every workflow means a maintainer has to approve CI
  for a fork PR. Nothing failed. Say so and wait.
- Bot findings (Macroscope, CodeRabbit): check each one against the source.
  Fix the real ones in a new commit, not a force-push, so reviewers can see
  the delta. Reply on each thread with the commit SHA and what changed, and
  explain why when you take a different route. Dismiss false positives with a
  reason. Keep the PR body's numbers current (test counts, etc.).
- If main moves under the PR, rebase onto fresh `origin/main`. In
  conflicted files that upstream has reworked, take theirs (`git checkout
  --ours` during a rebase) and re-apply your change by meaning, rather than
  merging hunk by hunk. Then rerun all of §3 and a quick live check.

## Gotchas

- An agent session runs *inside* the live T3. Its environment carries
  `T3CODE_HOST`, `T3CODE_PORT=3773` and `T3CODE_HOME=~/.t3`. A dev server
  started without `t3dev` would bind the live port or read live state.
- `pkill -f <pattern>` from the Bash tool also matches the tool's own shell
  and kills it (exit 143/144). Kill by PID or process group; `t3dev stop`
  does.
- A fresh browser profile is not paired. The symptom is WebSocket "HTTP
  Authentication failed" in the console and an empty app.
- Yair's install trails main. Before calling something a bug, check whether
  main has already fixed it: find the fixing commit and run
  `git tag --contains`.
- Personal data stays out of anything published: no real paths, thread
  contents or client names. Use made-up paths in the PR and fixtures in
  screenshots.
