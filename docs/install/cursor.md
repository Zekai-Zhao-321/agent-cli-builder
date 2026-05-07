# Install on Cursor

Cursor reads `.cursor/rules/` files as project-scoped agent rules, and a global `~/.cursor/rules/` for user-wide rules. The `agent-cli-builder` skill is a self-contained folder, so drop it into either location.

## Recommended: official one-liner installers

```bash
gh skill install Zekai-Zhao-321/agent-cli-builder agent-cli-builder
# or
npx skills add Zekai-Zhao-321/agent-cli-builder -a cursor
```

Both detect Cursor and place the skill in the right rules directory. `gh skill` is built into the GitHub CLI ([docs](https://cli.github.com/manual/gh_skill)); `npx skills` is Vercel's open tool ([skills.sh](https://skills.sh)).

## Manual: project-level install (for teams committing the skill to the repo)

```bash
git clone https://github.com/Zekai-Zhao-321/agent-cli-builder.git /tmp/_acb
mkdir -p .cursor/rules
cp -r /tmp/_acb/skills/agent-cli-builder .cursor/rules/
rm -rf /tmp/_acb
```

Commit `.cursor/rules/agent-cli-builder/` to share with the team.

> **Windows users:** run from Git Bash or WSL, or adapt `cp -r` / `mkdir -p` / `~` to your shell. The destination is `<project>\.cursor\rules\agent-cli-builder\`.

## Global install (your account, every project)

```bash
git clone https://github.com/Zekai-Zhao-321/agent-cli-builder.git /tmp/_acb
mkdir -p ~/.cursor/rules
cp -r /tmp/_acb/skills/agent-cli-builder ~/.cursor/rules/
rm -rf /tmp/_acb
```

## Activating the skill

Cursor activates `.md` rules when their content matches your prompt. The skill's frontmatter `description:` is written to match phrases like:

- "build an agent-native CLI"
- "scaffold a CLI for Claude Code / Cursor"
- "score my CLI for agent-readiness"
- "retrofit my Click CLI"
- "should this be a CLI or an MCP server?"

If you want it always active in a project (independent of phrasing), reference it explicitly in your `.cursor/rules/AGENTS.md` or as `@agent-cli-builder` in chat.

## Updating

```bash
cd .cursor/rules/agent-cli-builder           # or ~/.cursor/rules/agent-cli-builder
git -C $(git rev-parse --show-toplevel 2>/dev/null) pull 2>/dev/null \
  || (cd /tmp && rm -rf _acb && git clone https://github.com/Zekai-Zhao-321/agent-cli-builder.git _acb \
      && rm -rf "$OLDPWD" && cp -r _acb/skills/agent-cli-builder "$OLDPWD")
```

(Cursor doesn't currently expose a "reinstall this rule" command — re-cloning over the top is the simplest path.)

## Uninstall

```bash
rm -rf .cursor/rules/agent-cli-builder       # or ~/.cursor/rules/agent-cli-builder
```

## Troubleshooting

- **The skill loads as a single rule but never as references.** Cursor loads the top-level rule by phrase match; the `references/*.md` files are progressively loaded only when the SKILL.md explicitly points the agent there. If you see the agent missing reference content, ensure your prompt is specific enough to surface the relevant section (e.g. "score it against the rubric" rather than "is it good?").
- **Multiple skills colliding.** If you also have `agent-native-design` or another CLI-focused skill installed, Cursor may activate the wrong one. The trigger phrases here are intentionally distinct from `agent-native-design`'s (which lean toward "review" / "evaluate" / "audit"); use "build", "scaffold", "retrofit", or "agent-cli-builder" by name to disambiguate.
