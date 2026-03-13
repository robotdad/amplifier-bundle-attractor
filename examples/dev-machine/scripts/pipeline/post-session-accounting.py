"""post-session-accounting.py — Session counting and zero-change tracking.

Usage:
    python post-session-accounting.py <state_file> <project_dir> <session_count>

Reads STATE.yaml, increments meta.session_count by 1.

Zero-change tracking: runs `git -C project_dir rev-parse HEAD` to get current HEAD,
compares to meta.last_session_head. If same HEAD (no commits this session):
increments meta.zero_change_sessions, prints warning. If different HEAD: resets
zero_change_sessions to 0. Updates meta.last_session_head.

Writes updated STATE.yaml.

Final JSON: {"session_count": N, "zero_change_sessions": N}

Exits 0 on success, 1 on failure. Git errors are non-fatal (pass).
"""

import json
import subprocess
import sys

import yaml


def main() -> int:
    """Entry point. Returns exit code."""
    if len(sys.argv) < 3:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": "Usage: post-session-accounting.py <state_file> <project_dir> <session_count>",
                }
            )
        )
        return 1

    state_file = sys.argv[1]
    project_dir = sys.argv[2]

    try:
        with open(state_file) as f:
            state = yaml.safe_load(f)

        if state is None:
            raise ValueError("State file is empty or invalid YAML")

        meta = state.setdefault("meta", {})

        # Increment session_count
        meta["session_count"] = meta.get("session_count", 0) + 1

        # Zero-change tracking via git HEAD comparison
        try:
            result = subprocess.run(
                ["git", "-C", project_dir, "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            current_head = result.stdout.strip()
            last_head = meta.get("last_session_head", "")
            if last_head and current_head == last_head:
                meta["zero_change_sessions"] = meta.get("zero_change_sessions", 0) + 1
                print(
                    f"ZERO-CHANGE SESSION #{meta['zero_change_sessions']}: "
                    f"no code commits this session (HEAD: {current_head[:8]})"
                )
            else:
                meta["zero_change_sessions"] = 0
            meta["last_session_head"] = current_head
        except Exception:
            pass  # non-fatal: git unavailable or not a repo

        state["meta"] = meta

        # Write updated STATE.yaml
        with open(state_file, "w") as f:
            yaml.dump(state, f, default_flow_style=False, sort_keys=False, width=120)

        print(
            json.dumps(
                {
                    "session_count": meta["session_count"],
                    "zero_change_sessions": meta.get("zero_change_sessions", 0),
                }
            )
        )
        return 0

    except Exception as e:
        print(json.dumps({"status": "error", "error": str(e)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
