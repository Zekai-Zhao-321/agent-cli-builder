# Install on Gemini CLI

Gemini CLI reads skills via several mechanisms:

1. The official **`gh skill install`** (GitHub CLI, preview) and **`npx skills add`** (Vercel) both auto-detect Gemini CLI and install correctly.
2. The native **`gemini skills install`** subcommand (built into Gemini CLI itself).
3. Manual `git clone` into `~/.gemini/skills/`.

## Recommended: official one-liner installers

```bash
gh skill install Zekai-Zhao-321/agent-cli-builder agent-cli-builder
# or
npx skills add Zekai-Zhao-321/agent-cli-builder -a gemini-cli
```

`gh skill` is built into the GitHub CLI ([docs](https://cli.github.com/manual/gh_skill)); `npx skills` is Vercel's open tool ([skills.sh](https://skills.sh)).

## Native: `gemini skills install`

If your version of Gemini CLI ships the install subcommand:

```bash
gemini skills install https://github.com/Zekai-Zhao-321/agent-cli-builder.git \
  --path skills/agent-cli-builder
```

The `--path` flag tells Gemini CLI which subdirectory inside the cloned repo is the actual skill (since this repo uses the `skills/<name>/` layout).

## Manual: `git clone`

```bash
git clone https://github.com/Zekai-Zhao-321/agent-cli-builder.git /tmp/_acb \
  && mkdir -p ~/.gemini/skills \
  && mv /tmp/_acb/skills/agent-cli-builder ~/.gemini/skills/ \
  && rm -rf /tmp/_acb
```

> **Windows users:** run from Git Bash or WSL, or adapt the commands. The destination is `%USERPROFILE%\.gemini\skills\agent-cli-builder\`.

## Project-level install

```bash
git clone https://github.com/Zekai-Zhao-321/agent-cli-builder.git /tmp/_acb \
  && mkdir -p .gemini/skills \
  && mv /tmp/_acb/skills/agent-cli-builder .gemini/skills/ \
  && rm -rf /tmp/_acb
```

## Activate

```bash
gemini
> Score my CLI against the agent-readiness rubric.
```

The agent reads the top-level SKILL.md, then loads `references/evaluation.md` on demand when scoring is requested.

## Update / uninstall

```bash
# update
cd ~/.gemini/skills/agent-cli-builder && git pull --ff-only

# uninstall
rm -rf ~/.gemini/skills/agent-cli-builder
```
