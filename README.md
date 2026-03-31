# Skills

Reusable AI agent skills for [OpenClaw](https://github.com/openclaw/openclaw) and Claude Code.

Built by [Yair Mahalalel](https://github.com/yairmlll) and Zeresh 😈 — a human-agent team in Tirana, Albania.

## What's Here

Production-tested skills for real workflows, not demos. Each skill follows the [March 2026 standard](https://natesnewsletter.substack.com/p/your-ai-skills-fail-10-of-the-time): hardened for unattended agent execution, not just human-supervised prompting.

## Structure

```
skills/
├── skill-name/
│   ├── SKILL.md          ← reasoning: when/why/how, edge cases, quality gates
│   ├── scripts/          ← determinism: reliable scripts that always work the same
│   ├── references/       ← context: docs the agent loads when needed
│   └── assets/           ← templates, examples
└── ...
```

**Key principle:** Scripts handle deterministic work. SKILL.md handles reasoning. Don't use a skill where a script suffices. Don't use a script where reasoning is required.

## Skills

| Skill | Description | Status |
|-------|-------------|--------|
| `new-project` | Create a new project with repo, Discord channel, brain entries, and proper layout | 🚧 WIP |
| `code-review` | Review git commits for bugs, style, architecture concerns | 🚧 WIP |
| `commit-and-push` | Audit, clean, stage, message, commit, push — the full workflow | 🚧 WIP |
| `youtube-transcript` | Fetch and clean YouTube video transcripts | 🚧 WIP |
| `nate-analysis` | Analyze NateBJones content with Opus-level depth | 🚧 WIP |

## Design Philosophy

- **10% vs 100%:** A skill that works when you're watching but fails when agents run it unattended is not a skill — it's a draft. Every skill here is tested for unattended execution.
- **Output-extraction method:** Skills are built from real outputs that worked, not from imagined ideal processes. Reverse-engineer methodology from your best work.
- **Progressive disclosure:** Description fields are routing mechanisms, not human labels. The body loads only when matched.
- **Deterministic where possible:** If a task can be a script, it should be. Skills wrap scripts with judgment, they don't replace reliability with reasoning.

## Layout Convention

All repos live in `~/repos/`. Skills reference this convention.

```
~/repos/          ← git repos (backed by GitHub)
~/.openclaw/      ← agent workspace (nightly backup)
~/data/           ← big files, media (SyncThing)
```

## License

MIT
