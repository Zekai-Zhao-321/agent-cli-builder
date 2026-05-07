# Universal install (any agent / any platform)

Skills are plain markdown. Any agent that accepts a system-prompt-style instruction file can use this skill — you just need to put the folder somewhere the agent reads from.

## Try an installer first

Two officially blessed installers handle 95% of cases automatically. Try one of these before going manual:

```bash
gh skill install Zekai-Zhao-321/agent-cli-builder agent-cli-builder
# or
npx skills add Zekai-Zhao-321/agent-cli-builder
```

`gh skill` ([docs](https://cli.github.com/manual/gh_skill)) is built into the GitHub CLI. `npx skills` ([skills.sh](https://skills.sh)) supports 55+ agents and detects which ones you have installed.

If neither covers your agent (custom harness, niche tool, restricted environment), continue with the manual steps below.

## Step 1 — Get the skill folder onto disk

```bash
git clone https://github.com/Zekai-Zhao-321/agent-cli-builder.git
```

The folder you care about is `agent-cli-builder/skills/agent-cli-builder/`. Everything else in the repo (README, LICENSE, etc.) is meta-content for humans browsing GitHub.

## Step 2 — Place it where your agent expects skills

Common conventions per platform:

| Platform | Skills directory |
|---|---|
| Claude Code | `~/.claude/skills/agent-cli-builder/` |
| Cursor | `.cursor/rules/agent-cli-builder/` (project) or `~/.cursor/rules/agent-cli-builder/` (global) |
| Codex CLI | `~/.codex/skills/agent-cli-builder/` |
| Gemini CLI | `~/.gemini/skills/agent-cli-builder/` |
| OpenCode | `~/.opencode/skills/agent-cli-builder/` |
| Antigravity / others using the universal path | `~/.agents/skills/agent-cli-builder/` |
| Custom harness | wherever your harness reads skills from |

Then move the inner folder there:

```bash
mv agent-cli-builder/skills/agent-cli-builder /path/to/your/skills/dir/
rm -rf agent-cli-builder   # the meta-repo, no longer needed
```

The destination should look like:

```
<your-skills-dir>/
└── agent-cli-builder/
    ├── SKILL.md
    ├── references/
    ├── templates/
    ├── scripts/
    └── evals/
```

## Step 3 — Tell your agent the skill exists

How agents discover skills varies:

- **Auto-discovery by phrase match.** Most platforms (Claude Code, Cursor, Codex, Gemini) read `SKILL.md`'s frontmatter `description:` field and route prompts to the skill when phrases match. No further setup needed.
- **Explicit reference in a prompt or AGENTS.md file.** If your agent doesn't auto-discover, add a line like:
  ```
  When the user asks about agent-native CLIs, building / retrofitting / scoring CLIs, JSON output, semantic exit codes, schema introspection, or MCP-vs-CLI architecture, use the agent-cli-builder skill.
  ```

## Step 4 — Verify

Ask your agent:

```
What's the difference between an MCP server and an agent-native CLI?
When should I build one vs. the other?
```

A correct response will reference the **CLI-only / share-core** decision matrix from the skill, name MCP-only as an anti-pattern, and describe the share-core pattern (one `core/` library, two thin adapters).

If the agent doesn't engage with the skill on this prompt, double-check that:

1. `SKILL.md` is at exactly `<skills-dir>/agent-cli-builder/SKILL.md` — not nested deeper.
2. The frontmatter parses as YAML (`---` on its own line, valid `name:` and `description:` keys).
3. Your agent platform actually reads the directory you placed it in.

## Using the scaffold without an agent

The scaffold is a regular Python package; you can run it directly:

```bash
python /path/to/your/skills/dir/agent-cli-builder/scripts/scaffold.py \
  --name flagcli \
  --target ./flagcli \
  --language python-typer

cd flagcli
python -m venv .venv && source .venv/bin/activate
pip install -e .
flagcli hello world --output json
```

Works on macOS, Linux, and Windows. (On Windows, activate the venv with `.venv\Scripts\Activate.ps1` from PowerShell or `.venv\Scripts\activate.bat` from cmd.)

## Multiple agents, one source of truth

If you use several agent platforms and want them all to load the same skill, symlink the folder rather than cloning multiple copies:

```bash
git clone https://github.com/Zekai-Zhao-321/agent-cli-builder.git ~/code/agent-cli-builder

ln -s ~/code/agent-cli-builder/skills/agent-cli-builder ~/.claude/skills/agent-cli-builder
ln -s ~/code/agent-cli-builder/skills/agent-cli-builder ~/.codex/skills/agent-cli-builder
ln -s ~/code/agent-cli-builder/skills/agent-cli-builder ~/.gemini/skills/agent-cli-builder
ln -s ~/code/agent-cli-builder/skills/agent-cli-builder ~/.opencode/skills/agent-cli-builder
```

`git pull` in `~/code/agent-cli-builder` updates every platform at once. (On Windows, symlinks need admin rights; use `mklink /J` for directory junctions instead, or just copy the folder to each location.)
