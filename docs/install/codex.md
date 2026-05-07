# Install on OpenAI Codex CLI

Codex CLI reads skills from `~/.codex/skills/` (user-level) or `.codex/skills/` (project-level). It also recognises the universal `~/.agents/skills/` location used by several other tools.

## Recommended: official one-liner installers

```bash
gh skill install Zekai-Zhao-321/agent-cli-builder agent-cli-builder
# or
npx skills add Zekai-Zhao-321/agent-cli-builder -a codex
```

Both detect Codex CLI and place the skill in the right directory. `gh skill` is built into the GitHub CLI ([docs](https://cli.github.com/manual/gh_skill)); `npx skills` is Vercel's open tool ([skills.sh](https://skills.sh)).

## Manual: user-level `git clone`

```bash
git clone https://github.com/Zekai-Zhao-321/agent-cli-builder.git /tmp/_acb \
  && mkdir -p ~/.codex/skills \
  && mv /tmp/_acb/skills/agent-cli-builder ~/.codex/skills/ \
  && rm -rf /tmp/_acb
```

Or, if you already use the universal path:

```bash
git clone https://github.com/Zekai-Zhao-321/agent-cli-builder.git /tmp/_acb \
  && mkdir -p ~/.agents/skills \
  && mv /tmp/_acb/skills/agent-cli-builder ~/.agents/skills/ \
  && rm -rf /tmp/_acb
```

> **Windows users:** run from Git Bash or WSL, or adapt the commands. The destination is `%USERPROFILE%\.codex\skills\agent-cli-builder\` (or `%USERPROFILE%\.agents\skills\agent-cli-builder\` for the universal path).

## Project-level install

```bash
git clone https://github.com/Zekai-Zhao-321/agent-cli-builder.git /tmp/_acb \
  && mkdir -p .codex/skills \
  && mv /tmp/_acb/skills/agent-cli-builder .codex/skills/ \
  && rm -rf /tmp/_acb
```

## Activate

Open a Codex CLI session in a project where you'd want the skill active:

```bash
codex
> Build me an agent-native CLI for the github API.
```

The skill's frontmatter `description:` is written so Codex picks it up on phrases like "build / scaffold / retrofit / score an agent-native CLI", "JSON output mode", "semantic exit codes", "schema introspection".

## Update / uninstall

```bash
# update
cd ~/.codex/skills/agent-cli-builder && git pull --ff-only

# uninstall
rm -rf ~/.codex/skills/agent-cli-builder
```
