"""post-session-archive.py — Archive completed features and old sessions.

Usage:
    python post-session-archive.py <state_file> <context_file>

Reads STATE.yaml and finds features with status 'completed' or 'done', moves them
from features{} to completed_features list, and writes feature details to
FEATURE-ARCHIVE.yaml (append-only, creates if missing with description header).

Reads CONTEXT-TRANSFER.md and finds '### Session N Summary' headings. If more than
KEEP_SESSIONS=5, archives older sessions to SESSION-ARCHIVE.md (append-only, creates
if missing, dedup check), and rewrites CONTEXT-TRANSFER.md with note about archived
sessions.

Writes updated STATE.yaml.

Final JSON output: {"archived_features": N, "archived_sessions": N}

Exits 0 on success, 1 on failure.
"""

import json
import re
import sys
from pathlib import Path

import yaml

KEEP_SESSIONS = 5


def archive_features(state: dict, state_dir: Path) -> int:
    """Archive completed/done features from state to FEATURE-ARCHIVE.yaml.

    Moves features with status 'completed' or 'done' out of state['features']
    and into state['completed_features']. Writes feature details to FEATURE-ARCHIVE.yaml.

    Returns:
        Number of features archived.
    """
    features = state.get("features", {})
    completed_list = state.get("completed_features", [])

    if not isinstance(completed_list, list):
        return 0

    newly_completed = {
        fid: fd
        for fid, fd in features.items()
        if fd.get("status") in ("completed", "done")
    }
    if not newly_completed:
        return 0

    archive_path = state_dir / "FEATURE-ARCHIVE.yaml"
    try:
        with open(archive_path) as f:
            archive = yaml.safe_load(f) or {}
    except FileNotFoundError:
        archive = {
            "description": "Completed feature archive. Append-only.",
            "features": {},
        }

    arch_feats = archive.get("features", {})
    for fid, fd in newly_completed.items():
        if fid not in completed_list:
            completed_list.append(fid)
        arch_feats[fid] = fd
        del features[fid]

    archive["features"] = arch_feats
    state["completed_features"] = completed_list
    state["features"] = features

    with open(archive_path, "w") as f:
        yaml.dump(archive, f, default_flow_style=False, sort_keys=False, width=120)

    return len(newly_completed)


def archive_sessions(context_file: str) -> int:
    """Archive old session summaries from context file if more than KEEP_SESSIONS exist.

    Finds '### Session N Summary' headings in CONTEXT-TRANSFER.md. If there are more
    than KEEP_SESSIONS, the older ones are appended to SESSION-ARCHIVE.md and
    CONTEXT-TRANSFER.md is rewritten with only the most recent KEEP_SESSIONS.

    Returns:
        Number of sessions archived.
    """
    ctx_path = Path(context_file)
    if not ctx_path.exists():
        return 0

    ctx_dir = ctx_path.parent
    session_archive = ctx_dir / "SESSION-ARCHIVE.md"

    with open(ctx_path) as f:
        ctx = f.read()

    sess = list(re.finditer(r"^### Session \d+ Summary", ctx, re.MULTILINE))
    if len(sess) <= KEEP_SESSIONS:
        return 0

    num_to_archive = len(sess) - KEEP_SESSIONS
    header = ctx[: sess[0].start()]
    keep_from = sess[-KEEP_SESSIONS]
    to_archive = ctx[sess[0].start() : keep_from.start()]
    keep = ctx[keep_from.start() :]

    if to_archive.strip():
        existing = ""
        if session_archive.exists():
            with open(session_archive) as f:
                existing = f.read()

        # Use the first session heading as a dedup marker — session-specific and unambiguous
        heading_match = re.search(r"^### Session \d+ Summary", to_archive, re.MULTILINE)
        dedup_marker = heading_match.group(0) if heading_match else to_archive[:80]
        if dedup_marker not in existing:
            if not existing:
                # Create file with header on first write
                with open(session_archive, "w") as f:
                    f.write(
                        "# Session Archive\n\n> Archived session summaries. Append-only.\n\n"
                    )
                    f.write(to_archive)
            else:
                with open(session_archive, "a") as f:
                    f.write(to_archive)

    with open(ctx_path, "w") as f:
        f.write(header)
        f.write("> **Note**: Older sessions archived in SESSION-ARCHIVE.md.\n")
        f.write(f"> Only the last {KEEP_SESSIONS} sessions kept here.\n\n")
        f.write(keep)

    return num_to_archive


def main() -> int:
    """Entry point. Returns exit code."""
    if len(sys.argv) < 3:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": "Usage: post-session-archive.py <state_file> <context_file>",
                }
            )
        )
        return 1

    state_file = sys.argv[1]
    context_file = sys.argv[2]

    try:
        with open(state_file) as f:
            state = yaml.safe_load(f)

        if state is None:
            raise ValueError("State file is empty or invalid YAML")

        state_dir = Path(state_file).parent

        archived_features = archive_features(state, state_dir)
        archived_sessions = archive_sessions(context_file)

        # Write updated state
        with open(state_file, "w") as f:
            yaml.dump(state, f, default_flow_style=False, sort_keys=False, width=120)

        print(
            json.dumps(
                {
                    "archived_features": archived_features,
                    "archived_sessions": archived_sessions,
                }
            )
        )
        return 0

    except Exception as e:
        print(json.dumps({"status": "error", "error": str(e)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
