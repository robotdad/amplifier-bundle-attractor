"""post-session-reconcile.py — Stale metadata, wiring audit, periodic checks.

Usage:
    python post-session-reconcile.py <state_file> <specs_dir> <project_dir>
                                     <install_command> <test_command>

Four reconciliation functions:

1. Stale metadata reconciliation: verifies meta.total_features_completed
   matches len(completed_features), fixes if diverged.

2. Integration wiring audit at epoch boundaries: when all features complete,
   scans packages/src/lib for module pairs, uses grep to check if mod_a
   references mod_b, cross-references with specs_dir for expected dependencies,
   flags unwired connections, prepends wiring reminder to next_action.

3. Periodic clean-room check every 10 sessions: fresh install + full test run,
   adds medium-severity blocker on failure.

4. Periodic integration test check every 5 epochs: looks for tests/integration,
   tests/e2e, etc., runs tests if found, adds proposed_features entry if no
   integration tests exist.

Final JSON: {reconciled: true, wiring_issues: N}

Exits 0 always (continue_on_fail).
"""

import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


# ── Helpers ──────────────────────────────────────────────────────────────────


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
        yaml.dump(state, f, default_flow_style=False, sort_keys=False, width=120)


def add_blocker(
    state_file: Path, blocker_id: str, description: str, severity: str = "high"
) -> None:
    """Add a blocker to STATE.yaml.

    Args:
        state_file: Path to STATE.yaml.
        blocker_id: Unique identifier for this blocker.
        description: Human-readable description of the blocker.
        severity: Severity level (high, medium, low).
    """
    state = load_state(state_file)
    if "blockers" not in state or state["blockers"] is None:
        state["blockers"] = []

    existing_ids = {b.get("id") for b in state["blockers"] if isinstance(b, dict)}
    if blocker_id in existing_ids:
        return

    state["blockers"].append(
        {
            "id": blocker_id,
            "description": description,
            "severity": severity,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )
    save_state(state_file, state)


def run_command(cmd_str: str, cwd: Path | None = None) -> int:
    """Run a shell command string. Returns exit code."""
    try:
        cmd_parts = shlex.split(cmd_str)
        proc = subprocess.run(cmd_parts, capture_output=True, cwd=cwd)
        return proc.returncode
    except Exception:
        return 1


# ── Function 1: Stale metadata reconciliation ────────────────────────────────


def reconcile_stale_metadata(state_file: Path) -> bool:
    """Verify meta.total_features_completed matches len(completed_features), fix if diverged.

    Returns:
        True if a fix was applied (metadata was diverged), False if already correct.
    """
    state = load_state(state_file)
    completed_features = state.get("completed_features") or []
    actual_count = len(completed_features)

    meta = state.setdefault("meta", {})
    stored_count = meta.get("total_features_completed")

    if stored_count != actual_count:
        print(
            f"RECONCILE: meta.total_features_completed diverged: "
            f"stored={stored_count}, actual={actual_count} — fixing."
        )
        meta["total_features_completed"] = actual_count
        save_state(state_file, state)
        return True

    return False


# ── Function 2: Integration wiring audit ─────────────────────────────────────


def _find_module_files(project_dir: Path) -> list[Path]:
    """Scan packages/src/lib directories for source module files."""
    module_files: list[Path] = []
    scan_dirs = ["packages", "src", "lib"]
    extensions = (".ts", ".tsx", ".py", ".rs", ".js")

    for scan_dir in scan_dirs:
        target = project_dir / scan_dir
        if not target.exists():
            continue
        for ext in extensions:
            for f in target.rglob(f"*{ext}"):
                # Skip test files and node_modules
                parts = f.parts
                if any(
                    skip in parts
                    for skip in (
                        "node_modules",
                        "__pycache__",
                        ".git",
                        "dist",
                        ".venv",
                        "target",
                    )
                ):
                    continue
                if any(
                    pat in f.name for pat in ("test_", "_test.", ".test.", ".spec.")
                ):
                    continue
                module_files.append(f)

    return module_files


def _grep_for_reference(mod_a: Path, mod_b_stem: str) -> bool:
    """Check if mod_a references mod_b_stem using grep."""
    try:
        result = subprocess.run(
            ["grep", "-l", mod_b_stem, str(mod_a)],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except Exception:
        return False


def _get_expected_deps_from_specs(specs_dir: Path) -> dict[str, list[str]]:
    """Cross-reference specs_dir for expected module dependencies.

    Looks for spec files that mention 'depends_on' or 'imports' patterns.
    Returns a dict mapping module name to list of expected dependencies.
    """
    expected: dict[str, list[str]] = {}
    if not specs_dir.exists():
        return expected

    for spec_file in specs_dir.rglob("*.md"):
        try:
            content = spec_file.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue

        # Simple heuristic: look for "depends on" or "imports" patterns
        # The spec name becomes the module key
        stem = spec_file.stem.lower().replace("-spec", "").replace("-module", "")
        deps = []
        for line in content.splitlines():
            if "depends on" in line or "imports" in line:
                # Extract possible module names (words with hyphens/underscores)
                import re

                words = re.findall(r"[a-z][a-z0-9_-]+", line)
                deps.extend([w for w in words if len(w) > 3])
        if deps:
            expected[stem] = deps

    return expected


def wiring_audit(state_file: Path, specs_dir: Path, project_dir: Path) -> int:
    """Integration wiring audit at epoch boundaries.

    When all features are complete, scans for module pairs and checks
    if expected wiring connections exist. Prepends wiring reminder to
    next_action if issues found.

    Returns:
        Number of wiring issues found.
    """
    state = load_state(state_file)
    features = state.get("features") or {}

    # Only run at epoch boundaries (when all live features are complete/done)
    live_features = {
        fid: fd
        for fid, fd in features.items()
        if isinstance(fd, dict) and fd.get("status") not in ("completed", "done")
    }

    if live_features:
        # Not at epoch boundary — skip wiring audit
        return 0

    print("=== WIRING AUDIT: all features complete — checking module connections ===")

    module_files = _find_module_files(project_dir)
    if len(module_files) < 2:
        print("WIRING AUDIT: fewer than 2 modules found — skipping pair analysis.")
        return 0

    expected_deps = _get_expected_deps_from_specs(specs_dir)
    wiring_issues = 0
    unwired = []

    # Check each pair: does mod_a reference mod_b?
    for i, mod_a in enumerate(
        module_files[:20]
    ):  # Limit to avoid combinatorial explosion
        for mod_b in module_files[i + 1 : 20]:
            mod_b_stem = mod_b.stem
            if not _grep_for_reference(mod_a, mod_b_stem):
                # Cross-reference with specs to see if this is an expected dependency
                mod_a_stem = mod_a.stem.lower()
                expected = expected_deps.get(mod_a_stem, [])
                if mod_b_stem.lower() in expected:
                    print(
                        f"  UNWIRED: {mod_a.name} should reference {mod_b.name} "
                        f"(per spec), but no reference found."
                    )
                    unwired.append(f"{mod_a.name} → {mod_b.name}")
                    wiring_issues += 1

    if wiring_issues > 0:
        print(f"WIRING AUDIT: {wiring_issues} unwired connection(s) found.")
        # Prepend wiring reminder to next_action
        state = load_state(state_file)
        current_action = state.get("next_action") or ""
        reminder = (
            f"WIRING REMINDER: {wiring_issues} unwired module connection(s) detected "
            f"({', '.join(unwired[:3])}). Verify integration before proceeding. "
        )
        state["next_action"] = reminder + current_action
        save_state(state_file, state)
    else:
        print("WIRING AUDIT: OK — no unwired connections detected.")

    return wiring_issues


# ── Function 3: Periodic clean-room check every 10 sessions ──────────────────


def periodic_clean_room_check(
    state_file: Path, project_dir: Path, install_command: str, test_command: str
) -> None:
    """Run fresh install + full test run every 10 sessions.

    Adds medium-severity blocker on failure.
    """
    state = load_state(state_file)
    meta = state.get("meta") or {}
    session_count = meta.get("session_count") or 0

    if session_count == 0 or session_count % 10 != 0:
        return  # Not a clean-room check session

    print(f"=== CLEAN-ROOM CHECK (session {session_count}, every 10 sessions) ===")
    print(f"Running: {install_command}")
    install_exit = run_command(install_command, cwd=project_dir)

    if install_exit != 0:
        print(f"CLEAN-ROOM INSTALL FAILED (exit {install_exit})")
        add_blocker(
            state_file,
            "blocker-clean-room-install-failed",
            (
                f"Clean-room install failed at session {session_count}: "
                f"`{install_command}` exited {install_exit}. "
                "Dependency or environment issue requires investigation."
            ),
            severity="medium",
        )
        return

    print(f"Running: {test_command}")
    test_exit = run_command(test_command, cwd=project_dir)

    if test_exit != 0:
        print(f"CLEAN-ROOM TESTS FAILED (exit {test_exit})")
        add_blocker(
            state_file,
            "blocker-clean-room-tests-failed",
            (
                f"Clean-room test run failed at session {session_count}: "
                f"`{test_command}` exited {test_exit}. "
                "Tests passed locally but fail in clean environment — environment dependency issue."
            ),
            severity="medium",
        )
    else:
        print("CLEAN-ROOM CHECK: PASSED — fresh install + full test suite OK.")


# ── Function 4: Periodic integration test check every 5 epochs ───────────────


INTEGRATION_TEST_DIRS = [
    "tests/integration",
    "tests/e2e",
    "tests/integration_tests",
    "test/integration",
    "test/e2e",
    "e2e",
    "integration",
    "integration_tests",
]


def periodic_integration_test_check(
    state_file: Path, project_dir: Path, test_command: str
) -> None:
    """Run integration tests every 5 epochs.

    Looks for tests/integration, tests/e2e, etc. If found, runs tests.
    If no integration tests exist, adds a proposed_features entry.
    """
    state = load_state(state_file)
    epoch = state.get("epoch") or 0

    if epoch == 0 or epoch % 5 != 0:
        return  # Not an integration check epoch

    print(f"=== INTEGRATION TEST CHECK (epoch {epoch}, every 5 epochs) ===")

    # Find integration test directories
    integration_dirs = [
        project_dir / d for d in INTEGRATION_TEST_DIRS if (project_dir / d).exists()
    ]

    if integration_dirs:
        print(
            f"Integration test directories found: {[str(d) for d in integration_dirs]}"
        )
        print(f"Running: {test_command}")
        test_exit = run_command(test_command, cwd=project_dir)
        if test_exit != 0:
            print(f"INTEGRATION TESTS FAILED (exit {test_exit})")
            add_blocker(
                state_file,
                f"blocker-integration-tests-failed-epoch-{epoch}",
                (
                    f"Integration tests failed at epoch {epoch}: "
                    f"`{test_command}` exited {test_exit}."
                ),
                severity="high",
            )
        else:
            print("INTEGRATION TEST CHECK: PASSED.")
    else:
        print(
            "WARNING: No integration test directories found "
            f"(checked: {', '.join(INTEGRATION_TEST_DIRS[:4])}...)."
        )
        # Add a proposed_features entry to create integration tests
        state = load_state(state_file)
        proposed = state.setdefault("proposed_features", {})
        feat_id = f"add-integration-tests-epoch-{epoch}"
        if feat_id not in proposed:
            proposed[feat_id] = {
                "description": (
                    "Add integration/e2e test suite. No integration tests found "
                    f"as of epoch {epoch}. Critical for system-level correctness."
                ),
                "priority": "medium",
                "source": "periodic-integration-check",
            }
            save_state(state_file, state)
            print(f"Proposed feature added: {feat_id}")


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    """Entry point. Returns exit code (always 0 — continue_on_fail)."""
    if len(sys.argv) < 6:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": (
                        "Usage: post-session-reconcile.py <state_file> <specs_dir> "
                        "<project_dir> <install_command> <test_command>"
                    ),
                }
            )
        )
        return 1

    state_file = Path(sys.argv[1]).resolve()
    specs_dir = Path(sys.argv[2]).resolve()
    project_dir = Path(sys.argv[3]).resolve()
    install_command = sys.argv[4]
    test_command = sys.argv[5]

    try:
        # 1. Stale metadata reconciliation
        reconciled = reconcile_stale_metadata(state_file)

        # 2. Integration wiring audit (at epoch boundaries)
        wiring_issues = wiring_audit(state_file, specs_dir, project_dir)

        # 3. Periodic clean-room check every 10 sessions
        periodic_clean_room_check(
            state_file, project_dir, install_command, test_command
        )

        # 4. Periodic integration test check every 5 epochs
        periodic_integration_test_check(state_file, project_dir, test_command)

        print(json.dumps({"reconciled": reconciled, "wiring_issues": wiring_issues}))
        return 0

    except Exception as e:
        # continue_on_fail — still exit 0 but include error info
        print(json.dumps({"reconciled": False, "wiring_issues": 0, "error": str(e)}))
        return 0


if __name__ == "__main__":
    sys.exit(main())
