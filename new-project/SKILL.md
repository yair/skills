---
name: new-project
description: >
  Create a new project from scratch. Sets up git repo in ~/repos/,
  Discord channel under Projects category, brain entries, README,
  and initial directory structure. Use when starting any new project,
  side project, or experiment that deserves its own repo.
---

# New Project Skill

## When to Use
- Jay says "let's start a new project" or "create a repo for X"
- A discussion has crystallized into something that needs its own space
- An experiment has grown beyond a single script

## Steps

1. **Name it.** Ask for a name if not provided. Short, memorable, lowercase.

2. **Create the repo:**
   ```bash
   cd ~/repos && git init <name> && cd <name> && git checkout -b main
   ```

3. **Write README.md** with:
   - One-line description
   - Why it exists (the motivation)
   - Architecture/approach (if known)
   - Status: 🚧 WIP

4. **Create Discord channel** under Projects category (1484904927623905340):
   ```
   message(action=channel-create, channel=discord, guildId=1475247187528253461,
           name=<project-name>, parentId=1484904927623905340,
           topic="<one-line description>")
   ```

5. **Brain entry:**
   ```bash
   brain remember --kind decision --title "Project <name>: <description>" \
     --body "<motivation and scope>" --source jay --tags projects
   ```

6. **Initial commit:**
   ```bash
   git add -A && git commit -m "Initial commit: project scaffolding"
   ```

7. **Create GitHub repo and push** (if public):
   ```bash
   gh repo create <name> --public --source=. --push
   ```
   If private or not ready for GitHub yet, skip this step.

8. **Checkout locally** — remind Jay to clone on zhizi too if Code will work on it.

## Edge Cases
- If name conflicts with existing repo: ask for alternative
- If Discord channel already exists: skip creation, note it
- If no GitHub CLI (`gh`): note it as a TODO, don't block

## Quality Gate
After creation, verify:
- [ ] Repo exists in ~/repos/<name>/
- [ ] README.md has description and status
- [ ] Discord channel exists
- [ ] Brain entry recorded
- [ ] Jay knows where it is
