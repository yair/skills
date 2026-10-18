# Upstream rules digest

Last checked against `pingdotgg/t3code` main at `2fbd4318f` (2026-10-17, just
after v0.1.0). The sources win over this digest. Before each PR, see what has
changed since then:

```bash
git -C ~/w/t3code fetch -q origin
git -C ~/w/t3code diff 2fbd4318f origin/main -- CONTRIBUTING.md AGENTS.md \
  .github/pull_request_template.md docs/internals/web-ui.md
```

When something has changed, update this file and the SHA above in the same
change as the skill.

## Contribution policy (CONTRIBUTING.md)

- They are not seeking outside contributions. Meeting the rules makes a PR
  eligible for review, nothing more.
- **Problem first.** A substantial bug fix links an issue maintainers have
  triaged: the `via-triage` label, plus a triage comment that says what the
  failure is and what should happen instead. Features and behavior changes need
  explicit approval from a maintainer in an Ideas discussion. Two exceptions
  can skip that, and the PR must explain which one applies: a very small,
  obvious bug fix, or a focused configuration option for an existing
  capability. A configuration option still needs approval if it changes
  workflows or defaults.
- **One underlying problem per PR.** Count defects, not issues. An adjacent
  fix that's useful is still a second PR.
- **Evidence.** Say how the problem was established and how the change was
  checked, and list what wasn't checked. UI changes need before/after
  screenshots, and a recording when motion matters. Host evidence on GitHub,
  and never commit PR-only assets to the branch.
- **Models.** They close PRs whose code was written by any Gemini model or by
  Muse Wonder (Muse Wonder Full is fine). Name the model and harness that did
  the work at the end of the PR body.
- Contributors are labelled `vouch:*` and PRs `size:*`. Vouching does not
  skip triage; only `.github/TRIAGE_EXEMPTIONS.td` does.

Our own rule is stricter than upstream's: nothing is published without
Yair's go-ahead (see SKILL.md). That comes from our side, not from upstream
policy.

## PR template (.github/pull_request_template.md)

The headings are **Problem**, **Change**, **Scope and approval** and
**Verification**. Scope and approval links the triaged issue *and* the
triage comment, or explains which exception applies. If the fix diverges from the direction triage suggested, say
so and explain why there. The title is a conventional commit in plain
language that describes the outcome, e.g. `fix(web): new threads no longer
spike CPU`. Drafts get triaged like ready PRs.

## Code rules that bite (AGENTS.md, docs/internals/web-ui.md)

- **React Compiler everywhere in `apps/web/src`.** `t3code/no-manual-memo`
  rejects `useMemo`, `useCallback` and `"use memo"`. Write plain expressions;
  the compiler memoizes them. `apps/web/src/reactCompilerCoverage.test.ts`
  fails on any function the compiler skips: `try`/`finally`, `throw` inside
  `try`, reading a ref during render, `setState` in an effect.
- **Mobile is converging on the same rule.** `apps/mobile/src/reactCompilerCoverage.test.ts`
  compiles every file and keeps a `KNOWN_BAILOUTS` list that only shrinks.
  Lint still allows `useMemo`/`useCallback` there (`allowMemoHooks`), but once
  a file compiles, upstream drops its manual memoization; #21268 did this for
  `ThreadFeed.tsx`. Write any new mobile code as plain functions. State that
  must outlive renders goes in a ref that only handlers touch, not in a
  `useMemo` cache.
- **Large components** (`ChatView`, `ChatComposer`): handlers are plain
  functions, wrapped in `useStableCallback` only where they leave the
  component.
- **Comments say why**: a constraint, an external quirk, or an invariant the
  code can't show. Don't restate names, narrate steps or record history. The
  `t3code/no-low-value-comments` lint rule catches the mechanical cases.
  #19559 pruned most existing narration, so expect reviewers to flag it.
- `components/ui` components own their look. Choose a `variant`; never
  restyle one with `className`.
- Types are inferred rather than annotated; no `any`.
- Docs: user docs only change when how a feature is used changes. Internal
  docs hold decisions and constraints, rewritten rather than appended to.

## Tooling

- Use pnpm (`pnpm install`, `pnpm run …`). npm support was removed in #20148.
  `vp` is the task runner: `npx vp test run <files>`, `npx vp lint <files>`,
  `npx vp fmt --check <files>`.
- Typecheck one package at a time: `cd apps/web && pnpm run typecheck`
  (`tsc-rs`), and likewise in `apps/mobile` and `packages/shared`. The
  whole-repo `pnpm run typecheck` is slow.
- The pre-commit hook runs `vp fmt` on staged files.
- Bots: Macroscope posts Correctness and Approvability checks and inline
  findings. CodeRabbit runs on some PRs. Fork PRs from first-time
  contributors sit at `action_required` until a maintainer approves the
  workflows. That isn't a failure, and nothing on our side can clear it.
