# Install on Claude Code

The `agent-cli-builder` skill is a folder containing `SKILL.md` plus its references, scaffold templates, and scripts. Drop it into your Claude Code skills directory and it auto-loads in the next session.

## Recommended: official one-liner installers

Either of these auto-detects Claude Code and places the skill at `~/.claude/skills/agent-cli-builder/`:

```bash
gh skill install Zekai-Zhao-321/agent-cli-builder agent-cli-builder
# or
npx skills add Zekai-Zhao-321/agent-cli-builder -a claude-code
```

`gh skill` is built into the GitHub CLI ([docs](https://cli.github.com/manual/gh_skill)). `npx skills` is Vercel's open agent-skills tool ([skills.sh](https://skills.sh)).

## Manual: `git clone`

If you can't use either installer (offline, restricted environment, etc.):

```bash
git clone https://github.com/Zekai-Zhao-321/agent-cli-builder.git /tmp/_acb \
  && mv /tmp/_acb/skills/agent-cli-builder ~/.claude/skills/ \
  && rm -rf /tmp/_acb
```

> **Windows users:** run from Git Bash or WSL, or translate `mv` / `rm -rf` / `~` to your shell of choice. The destination path is `%USERPROFILE%\.claude\skills\agent-cli-builder\`.

### Verify

```bash
ls ~/.claude/skills/agent-cli-builder/
# expected: SKILL.md  references/  scripts/  templates/  evals/
```

Open a fresh Claude Code session and ask:

```
Help me design an agent-native CLI for our analytics service.
```

The skill activates automatically on phrases like "agent-native CLI", "build a CLI for agents", "score my CLI", or any of the trigger phrases listed in the skill's frontmatter.

## Project-level install (only this repo)

If you want the skill scoped to a single project rather than every Claude Code session:

```bash
git clone https://github.com/Zekai-Zhao-321/agent-cli-builder.git /tmp/_acb \
  && mkdir -p .claude/skills \
  && mv /tmp/_acb/skills/agent-cli-builder .claude/skills/ \
  && rm -rf /tmp/_acb
```

Commit `.claude/skills/agent-cli-builder/` if you want every developer on the team to share the same skill version.

## Updating

The skill is a plain git checkout, so:

```bash
cd ~/.claude/skills/agent-cli-builder
git fetch && git pull --ff-only
```

Or re-clone over the top using the install command above.

## Uninstall

```bash
rm -rf ~/.claude/skills/agent-cli-builder
```

## Troubleshooting

- **Skill doesn't activate.** Confirm the path is exactly `~/.claude/skills/agent-cli-builder/SKILL.md`, not nested one level deeper. The most common mistake is cloning to `~/.claude/skills/agent-cli-builder/agent-cli-builder/...` — fix by `mv ~/.claude/skills/agent-cli-builder/agent-cli-builder ~/.claude/skills/ && rm -rf ~/.claude/skills/<empty-parent>`.
- **YAML frontmatter error.** Run `head -n 5 ~/.claude/skills/agent-cli-builder/SKILL.md` and confirm it begins with `---` and contains a `name:` and `description:` line.
- **The agent doesn't reach for it on a relevant prompt.** Try a more explicit phrase like "use the agent-cli-builder skill". If it still doesn't engage, the description in `SKILL.md` may not match your trigger phrasing — open an issue with the prompt that didn't engage and we'll tune the description.
