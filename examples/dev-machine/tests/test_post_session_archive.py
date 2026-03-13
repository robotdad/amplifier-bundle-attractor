"""Tests for post-session-archive.py — Archive completed features and old sessions."""

import yaml

from conftest import FIXTURES_DIR, SCRIPTS_DIR, parse_last_json, run_script

SCRIPT = SCRIPTS_DIR / "post-session-archive.py"
STATE_YAML = FIXTURES_DIR / "STATE.yaml"


def _make_state_with_completed(tmp_path):
    """Create a STATE.yaml with a completed feature (feat-done) and a live feature."""
    state = {
        "project_name": "test-project",
        "phase": 1,
        "phase_name": "foundation",
        "epoch": 3,
        "next_action": "implement next feature",
        "blockers": [],
        "completed_features": ["feature-a"],
        "features": {
            "feat-done": {
                "status": "done",
                "depends_on": [],
                "description": "A feature that is done",
            },
            "feat-active": {
                "status": "in-progress",
                "depends_on": [],
                "description": "An active feature",
            },
        },
    }
    state_file = tmp_path / "STATE.yaml"
    with open(state_file, "w") as f:
        yaml.dump(state, f, default_flow_style=False, sort_keys=False)
    return state_file


def _make_context_file(tmp_path, num_sessions=3):
    """Create a CONTEXT-TRANSFER.md with the given number of Session N Summary headings."""
    lines = ["# Context Transfer Document\n\n"]
    for i in range(num_sessions, 0, -1):
        lines.append(
            f"### Session {i} Summary\n\nSome content for session {i}.\n\n---\n\n"
        )
    ctx_file = tmp_path / "CONTEXT-TRANSFER.md"
    ctx_file.write_text("".join(lines))
    return ctx_file


class TestPostSessionArchiveExitCodes:
    """Tests for exit code behaviour."""

    def test_exits_zero_with_fixture_data(self, tmp_path):
        """Script exits 0 when given valid STATE.yaml and CONTEXT-TRANSFER.md."""
        state_file = _make_state_with_completed(tmp_path)
        ctx_file = _make_context_file(tmp_path)
        result = run_script(SCRIPT, str(state_file), str(ctx_file))
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}. stderr: {result.stderr}"
        )

    def test_no_args_exits_nonzero(self):
        """Script exits non-zero when called with no arguments."""
        result = run_script(SCRIPT)
        assert result.returncode != 0


class TestPostSessionArchiveOutput:
    """Tests for JSON output format."""

    def test_outputs_valid_json_with_archived_features(self, tmp_path):
        """Script outputs valid JSON containing archived_features key."""
        state_file = _make_state_with_completed(tmp_path)
        ctx_file = _make_context_file(tmp_path)
        result = run_script(SCRIPT, str(state_file), str(ctx_file))
        assert result.returncode == 0
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "Output should be a JSON object"
        assert "archived_features" in data, (
            "JSON output must contain 'archived_features'"
        )


class TestPostSessionArchiveEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_state_file_exits_nonzero_with_meaningful_error(self, tmp_path):
        """Script exits non-zero with a clear error when state file is empty YAML."""
        state_file = tmp_path / "STATE.yaml"
        state_file.write_text("")  # Empty YAML → yaml.safe_load returns None
        ctx_file = _make_context_file(tmp_path)
        result = run_script(SCRIPT, str(state_file), str(ctx_file))
        assert result.returncode != 0
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "Error output should be a JSON object"
        error_msg = data.get("error", "").lower()
        assert "state" in error_msg or "empty" in error_msg or "invalid" in error_msg, (
            f"Error message should describe the problem clearly, got: {data.get('error')}"
        )

    def test_archives_old_sessions_to_session_archive(self, tmp_path):
        """Sessions beyond KEEP_SESSIONS=5 are archived to SESSION-ARCHIVE.md."""
        state_file = _make_state_with_completed(tmp_path)
        ctx_file = _make_context_file(tmp_path, num_sessions=7)
        result = run_script(SCRIPT, str(state_file), str(ctx_file))
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}. stderr: {result.stderr}"
        )

        # SESSION-ARCHIVE.md should be created
        archive_path = tmp_path / "SESSION-ARCHIVE.md"
        assert archive_path.exists(), (
            "SESSION-ARCHIVE.md should be created when sessions exceed KEEP_SESSIONS"
        )

        # CONTEXT-TRANSFER.md should be rewritten with a note about archiving
        ctx_content = ctx_file.read_text()
        assert "archived" in ctx_content.lower(), (
            "CONTEXT-TRANSFER.md should contain a note about archived sessions"
        )

        # Output should report a non-zero archived_sessions count
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "Output should be a JSON object"
        assert data.get("archived_sessions", 0) > 0, (
            "archived_sessions should be non-zero when sessions were archived"
        )


class TestPostSessionArchiveFeatures:
    """Tests for feature archiving behaviour."""

    def test_moves_completed_features_to_archive(self, tmp_path):
        """feat-done is removed from features{} and added to completed_features list."""
        state_file = _make_state_with_completed(tmp_path)
        ctx_file = _make_context_file(tmp_path)
        run_script(SCRIPT, str(state_file), str(ctx_file))

        with open(state_file) as f:
            updated_state = yaml.safe_load(f)

        assert "feat-done" not in updated_state.get("features", {}), (
            "feat-done should be removed from features{}"
        )
        assert "feat-done" in updated_state.get("completed_features", []), (
            "feat-done should appear in completed_features list"
        )

    def test_writes_feature_archive_yaml(self, tmp_path):
        """FEATURE-ARCHIVE.yaml is created and contains feat-done details."""
        state_file = _make_state_with_completed(tmp_path)
        ctx_file = _make_context_file(tmp_path)
        run_script(SCRIPT, str(state_file), str(ctx_file))

        archive_path = tmp_path / "FEATURE-ARCHIVE.yaml"
        assert archive_path.exists(), "FEATURE-ARCHIVE.yaml should be created"

        with open(archive_path) as f:
            archive = yaml.safe_load(f)

        assert isinstance(archive, dict), "FEATURE-ARCHIVE.yaml should be a YAML dict"
        arch_features = archive.get("features", {})
        assert "feat-done" in arch_features, (
            "feat-done should appear in FEATURE-ARCHIVE.yaml features"
        )
