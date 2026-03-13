"""post-session-status.py — Increment epoch, output final JSON status.

Usage:
    python post-session-status.py <state_file> <session_count>

Reads STATE.yaml, increments epoch by 1, sets last_session to current UTC ISO
timestamp. Writes updated STATE.yaml.

Computes:
  - remaining features (not completed/done)
  - at_epoch_boundary (remaining==0 and features exist)
  - status ('blocked' if blockers, 'complete' if remaining==0, else 'healthy')

Final JSON: {status, session_count: str(int(session_count)+1),
             at_epoch_boundary: bool, next_action, total_features}

Exits 0 on success, 1 on failure.
"""

import json
import sys
from datetime import datetime, timezone

import yaml


def main() -> int:
    """Entry point. Returns exit code."""
    if len(sys.argv) < 3:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": "Usage: post-session-status.py <state_file> <session_count>",
                }
            )
        )
        return 1

    state_file = sys.argv[1]
    session_count = sys.argv[2]

    try:
        with open(state_file) as f:
            state = yaml.safe_load(f)

        if state is None:
            raise ValueError("State file is empty or invalid YAML")

        # Increment epoch by 1
        state["epoch"] = state.get("epoch", 0) + 1

        # Set last_session to current UTC ISO timestamp
        state["last_session"] = datetime.now(timezone.utc).isoformat()

        # Write updated STATE.yaml
        with open(state_file, "w") as f:
            yaml.dump(state, f, default_flow_style=False, sort_keys=False, width=120)

        # Compute derived values
        features = state.get("features") or {}
        blockers = state.get("blockers") or []
        remaining = sum(
            1
            for feat in features.values()
            if isinstance(feat, dict)
            and feat.get("status") not in ("completed", "done")
        )
        at_epoch_boundary = remaining == 0 and len(features) > 0
        if blockers:
            status = "blocked"
        elif remaining == 0:
            status = "complete"
        else:
            status = "healthy"

        # session_count output is str(int(session_count)+1)
        session_num = str(int(session_count) + 1)

        total_features = state.get("meta", {}).get("total_features_completed", 0)

        print(
            json.dumps(
                {
                    "status": status,
                    "session_count": session_num,
                    "at_epoch_boundary": at_epoch_boundary,
                    "next_action": state.get("next_action", ""),
                    "total_features": total_features,
                }
            )
        )
        return 0

    except Exception as e:
        print(json.dumps({"status": "error", "error": str(e)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
