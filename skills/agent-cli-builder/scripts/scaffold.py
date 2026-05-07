"""Scaffold a new agent-native CLI from the bundled template.

Usage:
    python scripts/scaffold.py --name acme --target ./acme --language python-typer

What it does:
1. Copies the chosen template into `--target`.
2. Renames `mycli` → `<name>` everywhere (filesystem and file content).
3. Updates pyproject.toml so the entry-point matches the new name.
4. Updates the shipped SKILL.md so its frontmatter and recipes reference the
   new CLI name.

The output is a fully working CLI you can `pip install -e .` and start using
immediately. From there, follow the cold-start checklist in the parent
`agent-cli-builder` SKILL.md.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

VALID_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", required=True, help="The name of your CLI (kebab/snake-case, lowercase).")
    parser.add_argument("--target", required=True, help="Output directory. Must not exist.")
    parser.add_argument(
        "--language",
        default="python-typer",
        choices=["python-typer", "rust-clap"],
        help="Template to use.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the target directory if it exists.",
    )
    args = parser.parse_args(argv)

    if not VALID_NAME.match(args.name):
        print(
            f"error: --name '{args.name}' must be lowercase and start with a letter; "
            "use only [a-z0-9_-].",
            file=sys.stderr,
        )
        return 2

    src = TEMPLATE_DIR / args.language
    if not src.exists():
        print(f"error: template '{args.language}' not found at {src}", file=sys.stderr)
        return 2

    dst = Path(args.target).resolve()
    if dst.exists():
        if not args.force:
            print(f"error: target '{dst}' already exists. Pass --force to overwrite.", file=sys.stderr)
            return 2
        try:
            shutil.rmtree(dst)
        except PermissionError as exc:
            print(
                f"error: cannot remove '{dst}' ({exc}).\n"
                f"hint: if you previously ran `pip install -e .` in that directory, "
                f"first run `pip uninstall -y {args.name}` and close any editor/terminal "
                f"that has it open, then retry.",
                file=sys.stderr,
            )
            return 1

    shutil.copytree(src, dst)
    rename_in_tree(dst, old="mycli", new=args.name)
    print(f"ok: scaffolded {args.name} -> {dst}", file=sys.stderr)
    print(_next_steps(args.name, dst, args.language), file=sys.stderr)
    return 0


def rename_in_tree(root: Path, *, old: str, new: str) -> None:
    """Rename `old` → `new` in filenames, directories, and file contents.

    Both lowercase and UPPERCASE forms are renamed in a single pass:
    `mycli` → `<new>` and `MYCLI` → `<NEW>`. This matters for env-var
    references like `MYCLI_TOKEN`, which would otherwise survive a
    case-sensitive rename and ship as broken defaults in every new CLI.

    Binary files are skipped silently.
    """
    old_upper = old.upper()
    new_upper = new.upper()

    def replace_both(text: str) -> str:
        # Order matters: replace upper first so we don't double-touch chars
        # that share casing across `old`/`old_upper` (e.g. when old is digits-only).
        if old_upper != old:
            text = text.replace(old_upper, new_upper)
        return text.replace(old, new)

    # First, rename directories from deepest to shallowest. Substring-aware:
    # `mycli` -> `<new>` and any compound name like `mycli-cli` -> `<new>-cli`,
    # `crates/mycli-core` -> `crates/<new>-core`. Same for the uppercase
    # variant. Renaming deepest-first avoids invalidating parent paths in
    # the same pass.
    dirs_to_rename: list[tuple[Path, Path]] = []
    for path in sorted(root.rglob("*"), key=lambda p: -len(p.parts)):
        if path.is_dir():
            renamed = replace_both(path.name)
            if renamed != path.name:
                dirs_to_rename.append((path, path.with_name(renamed)))
    for old_path, new_path in dirs_to_rename:
        old_path.rename(new_path)

    # Then files: rename, then content-replace.
    for path in sorted(root.rglob("*")):
        if path.is_file():
            renamed = replace_both(path.name)
            if renamed != path.name:
                target = path.with_name(renamed)
                path.rename(target)
                path = target
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            new_content = replace_both(content)
            if new_content != content:
                path.write_text(new_content, encoding="utf-8")


def _next_steps(name: str, dst: Path, language: str) -> str:
    if language == "rust-clap":
        return _next_steps_rust(name, dst)
    return _next_steps_python(name, dst)


def _next_steps_python(name: str, dst: Path) -> str:
    if sys.platform == "win32":
        activate = ".venv\\Scripts\\Activate.ps1"
    else:
        activate = ". .venv/bin/activate"
    return f"""
Next steps:

  cd {dst}
  python -m venv .venv && {activate}
  pip install -e .
  {name} --help
  {name} hello world --output json
  {name} schema hello

Then follow the agent-cli-builder cold-start checklist:
  - Replace the demo `hello` command in src/{name}/cli.py with your own.
  - Add a SCHEMAS entry per command so `{name} schema <method>` returns a real schema.
  - If your CLI wraps a REST API, use HttpClient from src/{name}/http.py - it maps
    HTTP status codes to the right exit codes automatically.
  - Fill in the recipes in skills/{name}/SKILL.md with your real workflows.
  - Score against the agent-readiness rubric (references/evaluation.md) before
    declaring shippable; aim for "Agent-ready" (>=65%) at minimum.
"""


def _next_steps_rust(name: str, dst: Path) -> str:
    return f"""
Next steps:

  cd {dst}
  cargo install --path crates/{name}-cli --locked
  {name} --help
  {name} hello world --output json
  {name} schema show hello
  {name} schema output hello

Or run uninstalled from the workspace:

  cargo run -p {name}-cli -- hello world --output json

Then follow the agent-cli-builder cold-start checklist:
  - Replace the demo `hello` command in crates/{name}-cli/src/commands/hello.rs.
  - Add request/response types to crates/{name}-core/src/schemas.rs and
    register them in registered_methods() so `{name} schema show <method>`
    picks them up. Same types feed the schema and the wire format - cannot drift.
  - If your CLI wraps a REST API, use HttpClient from crates/{name}-core/src/http.rs.
    It uses rustls-tls-native-roots, so corporate-proxy CA chains in the system
    trust store work without OpenSSL setup.
  - Fill in the recipes in skills/{name}/SKILL.md with your real workflows.
  - Score against the agent-readiness rubric (references/evaluation.md) before
    declaring shippable; aim for "Agent-ready" (>=65%) at minimum.
"""


if __name__ == "__main__":
    sys.exit(main())
