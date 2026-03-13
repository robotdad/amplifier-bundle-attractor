"""test-env-preflight.py — Validate test runner works.

Usage:
    python test-env-preflight.py <test_command> <project_dir>

Runs test_command with --collect-only -q (pytest dry-run mode) to verify
the test runner itself is functional. This is NOT about failing tests —
it's about detecting broken test infrastructure (missing deps, import
errors, syntax errors) BEFORE wasting a working session.

Exits 0 if runner is functional, outputs JSON {test_env: 'ok'}.
Exits 99 if runner is broken (writes postmortem and sentinel files,
    outputs JSON {test_env: 'broken'}).
Exits 1 if called with missing arguments.
"""

import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    """Entry point. Returns exit code."""
    if len(sys.argv) < 3:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": "Usage: test-env-preflight.py <test_command> <project_dir>",
                }
            )
        )
        return 1

    test_command = sys.argv[1]
    project_dir = Path(sys.argv[2]).resolve()

    # Change to project directory before running
    if project_dir.exists():
        os.chdir(project_dir)

    # Build the command: test_command --collect-only -q
    cmd_parts = shlex.split(test_command) + ["--collect-only", "-q"]

    # Run the test runner in collect-only (dry-run) mode
    proc = subprocess.run(
        cmd_parts,
        capture_output=True,
        text=True,
    )

    collect_output = proc.stdout + proc.stderr
    collect_exit = proc.returncode

    # Show first 40 lines of output
    for line in collect_output.splitlines()[:40]:
        print(line)

    if collect_exit == 0:
        print("Test runner is functional.")
        print(json.dumps({"test_env": "ok"}))
        return 0

    # --- Broken runner path ---
    print()
    print(
        f"TEST RUNNER FAILED (exit {collect_exit}) -- structural failure, not a test failure."
    )
    print("Retrying will NOT fix a broken test runner. Writing postmortem and halting.")

    # Write postmortem file
    postmortem_path = project_dir / ".dev-machine-postmortem"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    postmortem_lines = [
        "=== Dev Machine Post-Mortem: Test Environment Broken ===",
        f"Date:   {now}",
        f"Reason: test-env-preflight failed -- {test_command} --collect-only exited {collect_exit}",
        "",
        "The test runner itself is broken. This is NOT a test failure -- it is a",
        "structural failure (e.g. missing dependency, import error, syntax error in",
        "test infrastructure). Retrying will not fix this.",
        "",
        "To resume: fix the test runner error shown above, delete this file and",
        ".dev-machine-test-env-broken, then restart the container.",
        "",
        "=== Preflight output ===",
        collect_output,
    ]
    postmortem_path.write_text("\n".join(postmortem_lines))

    # Write sentinel file — entrypoint checks for this to skip retry loop
    sentinel_path = project_dir / ".dev-machine-test-env-broken"
    sentinel_path.touch()

    print(json.dumps({"test_env": "broken"}))
    return 99


if __name__ == "__main__":
    sys.exit(main())
