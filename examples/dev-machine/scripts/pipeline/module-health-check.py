"""module-health-check.py — LOC per package with content-aware bypass.

Usage:
    python module-health-check.py <state_file> <project_dir> <threshold>

Scans packages/*/src/ directories in project_dir, counts LOC in
*.ts/*.tsx/*.py/*.rs files. If any package exceeds threshold:
  - Reads STATE.yaml next_action to check if oversized module is already
    mentioned (content-aware bypass).
  - If module IS in next_action: warns only (health='warn-oversized', planned=True).
  - If module NOT in next_action (unplanned): adds blocker to STATE.yaml with
    severity=high and datetime, outputs health='needs-refactoring'.

If no packages exceed threshold: health='ok'.
Exits 0 always (informational check).
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml

LOC_EXTENSIONS = (".ts", ".tsx", ".py", ".rs")


def count_package_loc(pkg_src: Path) -> int:
    """Count lines of code in *.ts/*.tsx/*.py/*.rs files under a directory.

    Args:
        pkg_src: Path to the src directory to scan.

    Returns:
        Total line count across all matching files.
    """
    total = 0
    if not pkg_src.exists():
        return total
    for ext in LOC_EXTENSIONS:
        for f in pkg_src.rglob(f"*{ext}"):
            try:
                total += len(
                    f.read_text(encoding="utf-8", errors="replace").splitlines()
                )
            except OSError:
                pass
    return total


def scan_packages(project_dir: Path) -> dict[str, int]:
    """Scan packages/*/src/ directories and return LOC per package name.

    Args:
        project_dir: Root project directory.

    Returns:
        Dict mapping package name to LOC count.
    """
    packages_dir = project_dir / "packages"
    if not packages_dir.exists():
        return {}

    result: dict[str, int] = {}
    for pkg_dir in sorted(packages_dir.iterdir()):
        if not pkg_dir.is_dir():
            continue
        pkg_src = pkg_dir / "src"
        loc = count_package_loc(pkg_src)
        result[pkg_dir.name] = loc
    return result


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


def add_blocker(state_file: Path, package_name: str, loc: int, threshold: int) -> None:
    """Add a high-severity blocker to STATE.yaml for an unplanned oversized module.

    Args:
        state_file: Path to STATE.yaml.
        package_name: Name of the oversized package.
        loc: Actual LOC count.
        threshold: The configured threshold.
    """
    state = load_state(state_file)
    if "blockers" not in state or state["blockers"] is None:
        state["blockers"] = []

    blocker_id = f"blocker-oversize-{package_name}"
    # Avoid duplicate blockers for the same package
    existing_ids = {b.get("id") for b in state["blockers"] if isinstance(b, dict)}
    if blocker_id in existing_ids:
        return

    state["blockers"].append(
        {
            "id": blocker_id,
            "description": (
                f"Package '{package_name}' has {loc} LOC, exceeding threshold of {threshold}. "
                "Refactoring required before further feature work."
            ),
            "severity": "high",
            "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "package": package_name,
        }
    )
    save_state(state_file, state)


def main() -> int:
    """Entry point. Returns exit code (always 0)."""
    if len(sys.argv) < 4:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": "Usage: module-health-check.py <state_file> <project_dir> <threshold>",
                }
            )
        )
        return 1

    state_file = Path(sys.argv[1]).resolve()
    project_dir = Path(sys.argv[2]).resolve()
    try:
        threshold = int(sys.argv[3])
    except ValueError:
        print(json.dumps({"status": "error", "error": "threshold must be an integer"}))
        return 1

    # Change to project_dir
    if project_dir.exists():
        os.chdir(project_dir)

    # Scan packages
    packages_loc = scan_packages(project_dir)

    # Find oversized packages
    oversized = {pkg: loc for pkg, loc in packages_loc.items() if loc > threshold}

    if not oversized:
        print("=== MODULE HEALTH CHECK: OK (all packages within threshold) ===")
        result = {"health": "ok", "packages": packages_loc}
        print(json.dumps(result))
        return 0

    # Load state to check next_action for content-aware bypass
    state = load_state(state_file)
    next_action: str = str(state.get("next_action", "") or "").lower()

    # Check each oversized package: planned (mentioned in next_action) or unplanned
    planned_packages = []
    unplanned_packages = []

    for pkg_name, loc in oversized.items():
        pkg_lower = pkg_name.lower()
        if pkg_lower in next_action:
            planned_packages.append((pkg_name, loc))
        else:
            unplanned_packages.append((pkg_name, loc))

    if unplanned_packages:
        # Add blockers for unplanned oversized packages
        for pkg_name, loc in unplanned_packages:
            print(
                f"  BLOCKER: Package '{pkg_name}' has {loc} LOC (threshold={threshold}), "
                "not planned in next_action — adding blocker."
            )
            add_blocker(state_file, pkg_name, loc, threshold)

        result = {
            "health": "needs-refactoring",
            "oversized": {pkg: loc for pkg, loc in unplanned_packages},
            "packages": packages_loc,
        }
        if planned_packages:
            result["planned"] = {pkg: loc for pkg, loc in planned_packages}
        print(json.dumps(result))
        return 0

    # All oversized packages are planned — warn only
    for pkg_name, loc in planned_packages:
        print(
            f"  WARN: Package '{pkg_name}' has {loc} LOC (threshold={threshold}), "
            "but refactoring is planned in next_action."
        )

    result = {
        "health": "warn-oversized",
        "planned": True,
        "oversized": {pkg: loc for pkg, loc in planned_packages},
        "packages": packages_loc,
    }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
