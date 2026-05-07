"""Mechanical verification that a scaffolded CLI meets the agent-first invariants.

Usage:
    python evals/verify_scaffold.py /path/to/scaffolded/cli

This script runs the scaffolded CLI and asserts:
- `cli --output json hello world` returns a parseable JSON success envelope
  matching the {ok, data, metadata} shape.
- `cli hello world --output json` (flag AFTER subcommand) also works.
- Exit code is 0 on success; the `data` field is present.
- `metadata.source` carries the CLI name + version.
- `cli schema show hello` returns parseable JSON Schema with request/response.
- `cli schema output hello` returns a parseable envelope schema with
  ok/data/metadata properties.
- A nonexistent method exits with code 2 and a structured error containing
  `error.suggestions: list[str]`.
- A path traversal in a resource ID is rejected with exit code 2.
- A typo'd command (`cli helo`) is suggested back as `hello` (suggesting group).
- The shipped SKILL.md exists and has the required frontmatter fields.

Returns a JSON report on stdout describing which checks passed / failed
and an exit code (0 = all pass, 1 = at least one failure).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


CHECKS: list[tuple[str, str, str]] = []


def add(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, "pass" if ok else "fail", detail))


def run(cli: str, args: list[str], **kwargs: Any) -> tuple[int, str, str]:
    proc = subprocess.run(
        [cli, *args],
        capture_output=True,
        text=True,
        timeout=20,
        **kwargs,
    )
    return proc.returncode, proc.stdout, proc.stderr


def parse_json(s: str) -> Any:
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def is_success_envelope(body: Any) -> bool:
    return (
        isinstance(body, dict)
        and body.get("ok") is True
        and "data" in body
        and isinstance(body.get("metadata"), dict)
        and isinstance(body["metadata"].get("source"), str)
    )


def is_error_envelope(body: Any) -> bool:
    if not (isinstance(body, dict) and body.get("ok") is False):
        return False
    err = body.get("error")
    if not isinstance(err, dict):
        return False
    return (
        isinstance(err.get("code"), str)
        and isinstance(err.get("exit_code"), int)
        and isinstance(err.get("message"), str)
        and isinstance(err.get("suggestions"), list)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cli", help="The CLI binary name on PATH (e.g. 'acmecli', 'ff').")
    parser.add_argument("--skill-path", default=None, help="Path to the shipped SKILL.md.")
    args = parser.parse_args()

    cli = args.cli
    if shutil.which(cli) is None:
        print(json.dumps({"ok": False, "error": f"CLI '{cli}' not found on PATH"}), file=sys.stderr)
        return 1

    # 1. Flag after subcommand
    code, out, _ = run(cli, ["hello", "world", "--output", "json"])
    body = parse_json(out)
    add(
        "flag_after_subcommand_returns_json_envelope",
        code == 0 and is_success_envelope(body),
        f"exit={code}, body={body}",
    )

    # 2. Flag before subcommand
    code, out, _ = run(cli, ["--output", "json", "hello", "world"])
    body = parse_json(out)
    add(
        "flag_before_subcommand_returns_json_envelope",
        code == 0 and is_success_envelope(body),
        f"exit={code}",
    )

    # 3. Auto-JSON when piped (subprocess pipes stdout)
    code, out, _ = run(cli, ["hello", "world"])
    body = parse_json(out)
    add(
        "auto_json_when_non_tty",
        code == 0 and is_success_envelope(body),
        f"exit={code}",
    )

    # 4. metadata.source identifies the CLI + version
    add(
        "metadata_source_present",
        is_success_envelope(body) and (cli in (body["metadata"]["source"] or "")),
        f"metadata={body.get('metadata') if isinstance(body, dict) else None}",
    )

    # 5. data nesting (no top-level command-specific keys)
    add(
        "data_field_nests_payload",
        is_success_envelope(body)
        and isinstance(body["data"], dict)
        and "greeting" in body["data"],
        f"data={body.get('data') if isinstance(body, dict) else None}",
    )

    # 6. schema show returns valid JSON with request + response
    code, out, _ = run(cli, ["schema", "show", "hello"])
    body = parse_json(out)
    add(
        "schema_show_returns_request_and_response",
        code == 0
        and isinstance(body, dict)
        and "request" in body
        and "response" in body,
        f"exit={code}",
    )

    # 7. schema output returns the envelope shape
    code, out, _ = run(cli, ["schema", "output", "hello"])
    body = parse_json(out)
    add(
        "schema_output_returns_envelope_shape",
        code == 0
        and isinstance(body, dict)
        and "properties" in body
        and "ok" in body["properties"]
        and "data" in body["properties"]
        and "metadata" in body["properties"],
        f"exit={code}",
    )

    # 8. Unknown schema -> exit 2 with structured error and suggestions[]
    code, out, err = run(cli, ["schema", "show", "definitely.not.a.method", "--output", "json"])
    err_body = parse_json(err) or parse_json(out)
    add(
        "unknown_method_exits_validation_with_suggestions",
        code == 2
        and is_error_envelope(err_body)
        and len(err_body["error"]["suggestions"]) > 0,
        f"exit={code}, err_body={err_body}",
    )

    # 9. Path traversal in resource name -> exit 2 with structured error
    code, out, err = run(cli, ["hello", "../../etc/passwd", "--output", "json"])
    err_body = parse_json(err) or parse_json(out)
    add(
        "path_traversal_rejected",
        code == 2 and is_error_envelope(err_body),
        f"exit={code}, err_body={err_body}",
    )

    # 10. dry-run on hello returns structured plan
    code, out, _ = run(cli, ["hello", "alice", "--dry-run", "--output", "json"])
    body = parse_json(out)
    add(
        "dry_run_returns_structured_plan",
        code == 0
        and is_success_envelope(body)
        and isinstance(body["data"], dict)
        and body["data"].get("dry_run") is True,
        f"exit={code}, body={body}",
    )

    # 11. Typo'd top-level command -> usage error mentioning a suggestion
    code, _, err = run(cli, ["helo", "world"])
    add(
        "typo_command_suggests_fix",
        code != 0 and ("Did you mean" in err or "did you mean" in err.lower()),
        f"exit={code}, stderr_first_120={err[:120]!r}",
    )

    # 12. SKILL.md exists if path given
    if args.skill_path:
        skill = Path(args.skill_path)
        text = skill.read_text(encoding="utf-8") if skill.exists() else ""
        has_name = "\nname:" in text or text.startswith("---\nname:") or "name: " in text
        has_desc = "description:" in text
        add(
            "shipped_skill_md_present",
            skill.exists() and has_name and has_desc,
            f"path={skill}, has_name={has_name}, has_desc={has_desc}",
        )

    # Final report
    report = {
        "cli": cli,
        "checks": [{"name": n, "status": s, "detail": d} for (n, s, d) in CHECKS],
        "summary": {
            "total": len(CHECKS),
            "passed": sum(1 for _, s, _ in CHECKS if s == "pass"),
            "failed": sum(1 for _, s, _ in CHECKS if s == "fail"),
        },
    }
    print(json.dumps(report, indent=2))
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
