"""api-inventory.py — Scan source for public APIs, write to SCRATCH.md.

Usage:
    python api-inventory.py <project_dir> [scratch_file]

Scans project_dir for public APIs in TypeScript/JS, Python, and Rust.
Appends a timestamped '## API Inventory' section to scratch_file
(defaults to project_dir/SCRATCH.md). Creates the file if missing,
preserves existing content.

Exits 0 always (informational). Outputs diagnostic text followed by
a final JSON line with status and scratch_file path.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

LINE_LIMIT = 60


def run_grep(args: list[str]) -> list[str]:
    """Run grep via subprocess and return output lines.

    Returns an empty list if grep finds nothing or errors.
    """
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
        )
        lines = result.stdout.splitlines()
        return lines
    except Exception:
        return []


def scan_typescript_js() -> list[str]:
    """Find TypeScript/JS public exports in current directory."""
    args = [
        "grep",
        "-rn",
        "--include=*.ts",
        "--include=*.tsx",
        "--include=*.js",
        "-E",
        r"^export (default )?(interface|type|class|function|async function|const|enum|abstract class)",
        "--exclude-dir=node_modules",
        "--exclude-dir=dist",
        "--exclude-dir=.git",
        "--exclude-dir=build",
        ".",
    ]
    lines = run_grep(args)
    return lines[:LINE_LIMIT]


def scan_python() -> list[str]:
    """Find Python public classes/functions in current directory, excluding test files."""
    args = [
        "grep",
        "-rn",
        "--include=*.py",
        "-E",
        r"^(class [A-Z]|def [a-z][^_]|async def [a-z][^_])",
        "--exclude-dir=__pycache__",
        "--exclude-dir=.git",
        "--exclude-dir=.venv",
        "--exclude=test_*",
        "--exclude=*_test.py",
        ".",
    ]
    lines = run_grep(args)
    return lines[:LINE_LIMIT]


def scan_rust() -> list[str]:
    """Find Rust public items in current directory."""
    args = [
        "grep",
        "-rn",
        "--include=*.rs",
        "-E",
        r"^pub (struct|enum|fn|trait|type|const)",
        "--exclude-dir=target",
        "--exclude-dir=.git",
        ".",
    ]
    lines = run_grep(args)
    return lines[:LINE_LIMIT]


def build_inventory_section() -> str:
    """Build the API inventory markdown section."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "",
        f"## API Inventory (auto-generated {timestamp})",
        "",
        "### TypeScript / JavaScript public exports",
    ]

    ts_lines = scan_typescript_js()
    if ts_lines:
        lines.extend(ts_lines)
    else:
        lines.append("(none found)")

    lines.append("")
    lines.append("### Python public classes / functions")

    py_lines = scan_python()
    if py_lines:
        lines.extend(py_lines)
    else:
        lines.append("(none found)")

    lines.append("")
    lines.append("### Rust public items")

    rs_lines = scan_rust()
    if rs_lines:
        lines.extend(rs_lines)
    else:
        lines.append("(none found)")

    lines.append("")
    lines.append("---")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    """Entry point. Returns exit code."""
    if len(sys.argv) < 2:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": "Usage: api-inventory.py <project_dir> [scratch_file]",
                }
            )
        )
        return 1

    project_dir = Path(sys.argv[1]).resolve()
    if len(sys.argv) >= 3:
        scratch_file = Path(sys.argv[2]).resolve()
    else:
        scratch_file = project_dir / "SCRATCH.md"

    if project_dir.exists():
        os.chdir(project_dir)
    else:
        print(f"Warning: {project_dir} not found, scanning CWD")

    print("=== API INVENTORY ===")

    section = build_inventory_section()

    # Append to SCRATCH.md (create if missing, preserve existing content)
    try:
        with open(scratch_file, "a") as f:
            f.write(section)
    except OSError as e:
        print(
            json.dumps(
                {"status": "error", "error": str(e), "scratch_file": str(scratch_file)}
            )
        )
        return 0

    print(f"API inventory appended to {scratch_file}")

    result = {
        "status": "ok",
        "scratch_file": str(scratch_file),
    }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
