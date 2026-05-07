# Install on OpenCode

OpenCode reads skills from `~/.opencode/skills/` (user-level), `.opencode/skills/` (project-level), and via its `AGENTS.md` configuration.

## Recommended: official one-liner installers

```bash
gh skill install Zekai-Zhao-321/agent-cli-builder agent-cli-builder
# or
npx skills add Zekai-Zhao-321/agent-cli-builder -a opencode
```

Both detect OpenCode and place the skill in the right directory. `gh skill` is built into the GitHub CLI ([docs](https://cli.github.com/manual/gh_skill)); `npx skills` is Vercel's open tool ([skills.sh](https://skills.sh)).

## Manual: user-level `git clone`

```bash
git clone https://github.com/Zekai-Zhao-321/agent-cli-builder.git /tmp/_acb \
  && mkdir -p ~/.opencode/skills \
  && mv /tmp/_acb/skills/agent-cli-builder ~/.opencode/skills/ \
  && rm -rf /tmp/_acb
```

> **Windows users:** run from Git Bash or WSL, or adapt the commands. The destination is `%USERPROFILE%\.opencode\skills\agent-cli-builder\`.

## Project-level install

```bash
git clone https://github.com/Zekai-Zhao-321/agent-cli-builder.git /tmp/_acb \
  && mkdir -p .opencode/skills \
  && mv /tmp/_acb/skills/agent-cli-builder .opencode/skills/ \
  && rm -rf /tmp/_acb
```

## Activate via AGENTS.md

If your project uses `AGENTS.md` to declare which skills are available, add:

```markdown
## Skills

- `agent-cli-builder` — building, retrofitting, and scoring agent-native CLIs. Auto-loads on prompts about CLI design, JSON output, exit codes, schema introspection, MCP-vs-CLI architecture, retrofitting human-first CLIs, or scoring against the agent-readiness rubric.
```

## Update / uninstall

```bash
# update
cd ~/.opencode/skills/agent-cli-builder && git pull --ff-only

# uninstall
rm -rf ~/.opencode/skills/agent-cli-builder
```
