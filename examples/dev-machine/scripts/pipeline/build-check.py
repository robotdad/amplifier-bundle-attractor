"""build-check.py — Full build + test + paper tiger detection.

Usage:
    python build-check.py <build_command> <test_command> <project_dir> <state_file>

Changes to project_dir. Runs:
  1. Build/type-check via build_command.
  2. Full test suite via test_command (no file filters — regression detection).
  3. Integration verification checklist (3-item checklist about entry points,
     stubs, and type registry).
  4. Paper tiger detection:
     PT-1: Greps for stub patterns in non-test production source.
     PT-2: Checks for standard entry files (main.py, app.py, index.ts, etc.).

Uses add_blocker() to write blockers to STATE.yaml on build or test failure
(severity=high with datetime). Final JSON: build_status='clean' or 'failed'.
Exits 0 always (caller reads status from JSON).
"""

import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

# Standard entry point filenames to check in PT-2
ENTRY_FILES = [
    "main.py",
    "app.py",
    "index.ts",
    "index.js",
    "server.ts",
    "server.js",
    "app.ts",
]

# Stub patterns for PT-1 grep
STUB_PATTERN = (
    r"(raise NotImplementedError|pass$|return \{\}$|return \[\]$"
    r"|TODO: implement|FIXME: implement|stub implementation|not yet implemented)"
)

# File extensions to scan for stubs
STUB_INCLUDES = ["*.ts", "*.tsx", "*.py", "*.rs", "*.js"]

# Directories to exclude from stub scanning
STUB_EXCLUDE_DIRS = ["node_modules", ".git", "dist", "__pycache__", ".venv", "target"]


def load_state(state_file: Path) -> dict:
    """Load STATE.yaml, returning empty dict if unreadable."""
    try:
        with open(state_file) as f:
            data = yaml.safe_load(f) or {}
        return data
    except (OSError, yaml.YAMLError):
        return {}


def save_state(state_file: Path, state: dict) -> None:
    """Save state dict to STATE.yaml."""
    with open(state_file, "w") as f:
        yaml.dump(state, f, default_flow_style=False, sort_keys=False)


def add_blocker(state_file: Path, blocker_id: str, description: str) -> None:
    """Add a high-severity blocker to STATE.yaml.

    Args:
        state_file: Path to STATE.yaml.
        blocker_id: Unique identifier for this blocker.
        description: Human-readable description of the blocker.
    """
    state = load_state(state_file)
    if "blockers" not in state or state["blockers"] is None:
        state["blockers"] = []

    # Avoid duplicate blockers for the same id
    existing_ids = {b.get("id") for b in state["blockers"] if isinstance(b, dict)}
    if blocker_id in existing_ids:
        return

    state["blockers"].append(
        {
            "id": blocker_id,
            "description": description,
            "severity": "high",
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )
    save_state(state_file, state)


def run_command(cmd_str: str) -> int:
    """Run a shell command string, streaming output. Returns exit code."""
    cmd_parts = shlex.split(cmd_str)
    proc = subprocess.run(cmd_parts, capture_output=False)
    return proc.returncode


def run_pt1_stub_check(project_dir: Path) -> list[str]:
    """PT-1: Grep for stub/placeholder patterns in non-test production source.

    Args:
        project_dir: Root directory to scan.

    Returns:
        List of matching lines (up to 20).
    """
    args = ["grep", "-rn", "-E", STUB_PATTERN]
    for ext in STUB_INCLUDES:
        args += [f"--include={ext}"]
    for excl in STUB_EXCLUDE_DIRS:
        args += [f"--exclude-dir={excl}"]
    args.append(".")

    try:
        result = subprocess.run(args, capture_output=True, text=True)
        lines = result.stdout.splitlines()
    except Exception:
        lines = []

    # Filter out test files
    filtered = [
        line
        for line in lines
        if not any(pat in line for pat in ["test_", "_test.", ".test.", ".spec."])
    ]
    return filtered[:20]


def main() -> int:
    """Entry point. Returns exit code (always 0)."""
    if len(sys.argv) < 5:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": (
                        "Usage: build-check.py <build_command> <test_command> "
                        "<project_dir> <state_file>"
                    ),
                }
            )
        )
        return 1

    build_command = sys.argv[1]
    test_command = sys.argv[2]
    project_dir = Path(sys.argv[3]).resolve()
    state_file = Path(sys.argv[4]).resolve()

    # Change to project_dir as specified by the pipeline contract.
    if project_dir.exists():
        os.chdir(project_dir)

    build_failed = False
    test_failed = False

    # --- 1. Build / type-check ---
    print("=== POST-SESSION BUILD + REGRESSION CHECK ===")
    print(f"--- Build: {build_command} ---")
    build_exit = run_command(build_command)
    if build_exit == 0:
        print("BUILD: clean")
    else:
        print(f"BUILD FAILED (exit {build_exit})")
        build_failed = True

    # --- 2. Full test suite (regression detection) ---
    print()
    print(
        f"--- Full test suite: {test_command} (no file filters -- regression check) ---"
    )
    test_exit = run_command(test_command)
    if test_exit == 0:
        print("TESTS: all passing")
    else:
        print(
            f"TESTS FAILED (exit {test_exit}) "
            "-- check for regressions in previously-passing tests"
        )
        test_failed = True

    # --- 3. Integration verification checklist ---
    print()
    print("=== INTEGRATION VERIFICATION CHECKLIST (next session must confirm) ===")
    print(
        "  [1] Completed features are reachable through actual entry points -- not just"
    )
    print(
        "      unit-tested in isolation. Verify the wiring from top-level to implementation."
    )
    print("  [2] No stub/mock implementations remain in production code paths.")
    print(
        "      grep for: TODO, FIXME, 'stub', 'mock', 'placeholder', 'not implemented'"
    )
    print("      in non-test source files. Each hit is a candidate blocker.")
    print(
        "  [3] If the project has a schema or type registry, verify all referenced types"
    )
    print("      exist in it. No dangling references to unregistered/undefined types.")

    # --- 4. Paper tiger detection ---
    print()
    print("=== PAPER TIGER DETECTION ===")
    pt_flags = 0

    # PT-1: Stub signatures in production source (non-test files)
    print("--- PT-1: Stub/placeholder implementations in production code ---")
    stub_hits = run_pt1_stub_check(project_dir)
    if stub_hits:
        print("WARNING: Possible stub implementations in production paths:")
        for line in stub_hits:
            print(f"  {line}")
        pt_flags += 1
    else:
        print("OK: No obvious stub patterns found in production source.")

    # PT-2: Route/entry-point registration check
    print()
    print("--- PT-2: Entry-point registration check ---")
    entry_found = False
    for ef in ENTRY_FILES:
        ef_path = project_dir / ef
        if ef_path.is_file():
            line_count = len(
                ef_path.read_text(encoding="utf-8", errors="replace").splitlines()
            )
            print(f"Entry file found: {ef} ({line_count} lines)")
            entry_found = True
    if not entry_found:
        print(
            "INFO: No standard entry file found at project root "
            "(may use non-standard structure)."
        )

    # PT summary
    print()
    if pt_flags > 0:
        print(
            f"PAPER TIGER CHECK: {pt_flags} warning(s). "
            "Review stub hits above before marking features complete."
        )
    else:
        print("PAPER TIGER CHECK: clean (no obvious stubs detected).")

    # --- Write blockers to STATE.yaml on failure ---
    if build_failed:
        print()
        print(f"Adding build blocker to {state_file}...")
        add_blocker(
            state_file,
            "blocker-build-failed",
            (
                f"{build_command} failed after working session -- "
                "fix build errors before resuming"
            ),
        )

    if test_failed:
        print()
        print(f"Adding regression blocker to {state_file}...")
        add_blocker(
            state_file,
            "blocker-tests-failed",
            (
                f"{test_command} failed after working session -- "
                "run full test suite with no file filters to identify regressions"
            ),
        )

    # --- Final JSON output ---
    if build_failed or test_failed:
        print(json.dumps({"build_status": "failed"}))
    else:
        print(json.dumps({"build_status": "clean"}))

    return 0


if __name__ == "__main__":
    sys.exit(main())
