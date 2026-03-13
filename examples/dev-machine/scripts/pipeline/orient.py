"""orient.py — Read STATE.yaml and output structured status as a single JSON line.

Usage:
    python orient.py <state_file>

Exits 0 on success, 1 on error (missing file or no arguments).
"""

import json
import sys
from pathlib import Path

import yaml


def orient(state_file: str) -> dict:
    """Read a STATE.yaml file and return computed status as a dict."""
    with open(state_file) as f:
        state = yaml.safe_load(f)

    blockers = state.get("blockers", [])
    completed_list = set(state.get("completed_features", []))
    features = state.get("features", {})

    ready_count = 0
    for _fid, fd in features.items():
        s = fd.get("status", "")
        if s == "ready":
            deps = fd.get("depends_on", [])
            if all(
                d in completed_list
                or features.get(d, {}).get("status") in ("completed", "done")
                for d in deps
            ):
                ready_count += 1

    return {
        "phase": state.get("phase", 0),
        "phase_name": state.get("phase_name", "unknown"),
        "epoch": state.get("epoch", 0),
        "next_action": state.get("next_action", ""),
        "ready_count": ready_count,
        "completed_count": len(completed_list),
        "status": "blocked" if blockers else "healthy",
    }


def main() -> int:
    """Entry point. Returns exit code."""
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "error": "Usage: orient.py <state_file>"}))
        return 1

    state_file = sys.argv[1]

    if not Path(state_file).exists():
        print(json.dumps({"status": "error", "error": f"File not found: {state_file}"}))
        return 1

    try:
        result = orient(state_file)
        print(json.dumps(result))
        return 0
    except Exception as e:
        print(json.dumps({"status": "error", "error": str(e)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
