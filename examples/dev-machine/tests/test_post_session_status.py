"""Tests for post-session-status.py — Increment epoch, output final JSON status."""

import shutil

import yaml

from conftest import FIXTURES_DIR, SCRIPTS_DIR, parse_last_json, run_script

SCRIPT = SCRIPTS_DIR / "post-session-status.py"


def _make_state(tmp_path, epoch=3, blockers=None, features=None):
    """Create a STATE.yaml for post-session-status tests."""
    state = {
        "project_name": "test-project",
        "phase": 1,
        "phase_name": "foundation",
        "epoch": epoch,
        "next_action": "implement feature-b core logic",
        "blockers": blockers if blockers is not None else [],
        "completed_features": ["feature-a"],
        "features": features
        if features is not None
        else {
            "feature-b": {
                "status": "ready",
                "depends_on": ["feature-a"],
                "description": "Second feature, depends on feature-a",
            },
            "feature-c": {
                "status": "in-progress",
                "depends_on": [],
                "description": "Third feature, currently in progress",
            },
        },
        "meta": {
            "session_count": 5,
            "zero_change_sessions": 0,
            "last_session_head": "abc1234",
            "total_features_completed": 1,
        },
    }
    state_file = tmp_path / "STATE.yaml"
    with open(state_file, "w") as f:
        yaml.dump(state, f, default_flow_style=False, sort_keys=False)
    return state_file


class TestPostSessionStatusExitCodes:
    """Tests for exit code behaviour."""

    def test_exits_zero_with_valid_state(self, tmp_path):
        """Script exits 0 when given valid STATE.yaml and session_count."""
        state_file = _make_state(tmp_path)
        result = run_script(SCRIPT, str(state_file), "5")
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}. stderr: {result.stderr}"
        )

    def test_missing_file_exits_nonzero(self, tmp_path):
        """Script exits non-zero when given a missing STATE.yaml path."""
        missing_file = tmp_path / "NONEXISTENT.yaml"
        result = run_script(SCRIPT, str(missing_file), "5")
        assert result.returncode != 0, (
            f"Expected non-zero exit for missing file, got {result.returncode}"
        )

    def test_no_args_exits_nonzero(self):
        """Script exits non-zero when called with no arguments."""
        result = run_script(SCRIPT)
        assert result.returncode != 0


class TestPostSessionStatusOutput:
    """Tests for JSON output format and required fields."""

    def test_outputs_valid_json(self, tmp_path):
        """Script outputs valid JSON on stdout."""
        state_file = _make_state(tmp_path)
        result = run_script(SCRIPT, str(state_file), "5")
        assert result.returncode == 0
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "Output should be a JSON object"

    def test_required_fields_present(self, tmp_path):
        """JSON output contains all required fields."""
        state_file = _make_state(tmp_path)
        result = run_script(SCRIPT, str(state_file), "5")
        assert result.returncode == 0
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "Output should be a JSON object"
        assert "status" in data, "JSON must contain 'status'"
        assert "session_count" in data, "JSON must contain 'session_count'"
        assert "at_epoch_boundary" in data, "JSON must contain 'at_epoch_boundary'"
        assert "next_action" in data, "JSON must contain 'next_action'"
        assert "total_features" in data, "JSON must contain 'total_features'"

    def test_session_count_incremented_in_output(self, tmp_path):
        """session_count in JSON is str(int(session_count)+1)."""
        state_file = _make_state(tmp_path)
        result = run_script(SCRIPT, str(state_file), "5")
        assert result.returncode == 0
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "Output should be a JSON object"
        # session_count arg is "5", so output should be str(5+1) = "6"
        assert data["session_count"] == "6", (
            f"session_count should be '6', got {data['session_count']!r}"
        )


class TestPostSessionStatusBehavior:
    """Tests for status computation and state mutation."""

    def test_status_healthy_when_no_blockers(self, tmp_path):
        """Status is 'healthy' when there are no blockers and features remain."""
        state_file = _make_state(tmp_path, blockers=[])
        result = run_script(SCRIPT, str(state_file), "5")
        assert result.returncode == 0
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "Output should be a JSON object"
        assert data["status"] == "healthy", (
            f"Expected 'healthy', got {data['status']!r}"
        )

    def test_status_blocked_when_blockers_present(self, tmp_path):
        """Status is 'blocked' when blockers exist (using STATE-blocked.yaml fixture)."""
        blocked_fixture = FIXTURES_DIR / "STATE-blocked.yaml"
        state_file = tmp_path / "STATE-blocked.yaml"
        shutil.copy(blocked_fixture, state_file)

        result = run_script(SCRIPT, str(state_file), "12")
        assert result.returncode == 0
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "Output should be a JSON object"
        assert data["status"] == "blocked", (
            f"Expected 'blocked', got {data['status']!r}"
        )

    def test_increments_epoch_from_3_to_4(self, tmp_path):
        """Epoch is incremented by 1 in STATE.yaml (3 → 4)."""
        state_file = _make_state(tmp_path, epoch=3)
        result = run_script(SCRIPT, str(state_file), "5")
        assert result.returncode == 0

        with open(state_file) as f:
            updated_state = yaml.safe_load(f)
        assert updated_state["epoch"] == 4, (
            f"Expected epoch 4, got {updated_state['epoch']}"
        )
