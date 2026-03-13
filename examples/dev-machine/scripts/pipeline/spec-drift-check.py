"""spec-drift-check.py — Compare spec mtimes vs implementation mtimes.

Usage:
    python spec-drift-check.py <specs_dir> <project_dir>

Scans specs_dir for *.md files. For each spec, finds matching implementation
files in project_dir. If any impl file is more than 7 days newer than the spec,
flags as drift.

Exits 0 always (informational check). Missing specs dir is not an error.
Outputs diagnostic text followed by a final JSON line with drift_count and status.
"""

import json
import os
import sys
from pathlib import Path

STALE_THRESHOLD = 7 * 86400  # 7 days in seconds
EXCLUDE_DIRS = {"node_modules", ".git", "dist", "__pycache__", ".venv", "target"}
IMPL_PATTERNS = ("*.ts", "*.tsx", "*.py", "*.rs", "*.js")
STRIP_SUFFIXES = ("-spec", "-module", "-feature", "-design")


def check_drift(specs_dir: Path) -> list[tuple[str, str, float]]:
    """Check for spec drift from the current directory.

    Args:
        specs_dir: Absolute path to the specs directory.

    Returns:
        List of (spec_file, impl_file, days_diff) tuples where drift was found.
    """
    drift_flags: list[tuple[str, str, float]] = []

    if not specs_dir.exists():
        return drift_flags

    for spec_file in sorted(specs_dir.rglob("*.md")):
        spec_mtime = spec_file.stat().st_mtime
        stem = spec_file.stem
        for suffix in STRIP_SUFFIXES:
            stem = stem.replace(suffix, "")
        stem = stem.lower()
        if len(stem) < 4:
            continue  # too short — too many false positives

        for pattern in IMPL_PATTERNS:
            for impl_file in Path(".").rglob(pattern):
                parts = str(impl_file).split(os.sep)
                if any(skip in parts for skip in EXCLUDE_DIRS):
                    continue
                if specs_dir.name in parts:
                    continue  # don't compare spec against spec
                if stem in impl_file.stem.lower():
                    impl_mtime = impl_file.stat().st_mtime
                    age_diff_s = impl_mtime - spec_mtime
                    if age_diff_s > STALE_THRESHOLD:
                        drift_flags.append(
                            (
                                str(spec_file),
                                str(impl_file),
                                round(age_diff_s / 86400, 1),
                            )
                        )

    return drift_flags


def main() -> int:
    """Entry point. Returns exit code."""
    if len(sys.argv) < 3:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": "Usage: spec-drift-check.py <specs_dir> <project_dir>",
                }
            )
        )
        return 1

    # Resolve paths to absolute before any chdir
    specs_dir = Path(sys.argv[1]).resolve()
    project_dir = Path(sys.argv[2]).resolve()

    if project_dir.exists():
        os.chdir(project_dir)

    drift_flags = check_drift(specs_dir)

    if drift_flags:
        print(f"=== SPEC DRIFT DETECTED ({len(drift_flags)} candidate(s)) ===")
        for spec_f, impl_f, days in drift_flags[:10]:
            print(f"  HOUSEKEEPING: {spec_f} is {days}d older than {impl_f}")
        if len(drift_flags) > 10:
            print(f"  ... ({len(drift_flags) - 10} more candidates)")
        print(
            "  Add spec-sync tasks to the next epoch, prioritized before new feature work."
        )
        result = {"drift_count": len(drift_flags), "status": "drift"}
    else:
        print("=== SPEC DRIFT CHECK: OK (no significant drift detected) ===")
        result = {"drift_count": 0, "status": "ok"}

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
