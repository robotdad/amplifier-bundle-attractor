"""Tests for post-session-accounting.py — Session counting and zero-change tracking."""

import subprocess

import yaml

from conftest import SCRIPTS_DIR, parse_last_json, run_script

SCRIPT = SCRIPTS_DIR / "post-session-accounting.py"


def _make_state(tmp_path, session_count=5, zero_change_sessions=0, last_head="abc1234"):
    """Create a STATE.yaml with meta fields for accounting tests."""
    state = {
        "project_name": "test-project",
        "phase": 1,
        "phase_name": "foundation",
        "epoch": 3,
        "next_action": "implement next feature",
        "blockers": [],
        "completed_features": ["feature-a"],
        "features": {
            "feature-b": {
                "status": "ready",
                "depends_on": ["feature-a"],
                "description": "Second feature",
            }
        },
        "meta": {
            "session_count": session_count,
            "zero_change_sessions": zero_change_sessions,
            "last_session_head": last_head,
            "total_features_completed": 1,
        },
    }
    state_file = tmp_path / "STATE.yaml"
    with open(state_file, "w") as f:
        yaml.dump(state, f, default_flow_style=False, sort_keys=False)
    return state_file


class TestPostSessionAccountingExitCodes:
    """Tests for exit code behaviour."""

    def test_exits_zero_with_valid_state(self, tmp_path):
        """Script exits 0 when given valid STATE.yaml and project_dir."""
        state_file = _make_state(tmp_path)
        result = run_script(SCRIPT, str(state_file), str(tmp_path), "5")
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}. stderr: {result.stderr}"
        )

    def test_no_args_exits_nonzero(self):
        """Script exits non-zero when called with no arguments."""
        result = run_script(SCRIPT)
        assert result.returncode != 0


class TestPostSessionAccountingOutput:
    """Tests for JSON output format."""

    def test_outputs_valid_json_with_session_count(self, tmp_path):
        """Script outputs valid JSON containing session_count key."""
        state_file = _make_state(tmp_path)
        result = run_script(SCRIPT, str(state_file), str(tmp_path), "5")
        assert result.returncode == 0
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "Output should be a JSON object"
        assert "session_count" in data, "JSON output must contain 'session_count'"
        assert "zero_change_sessions" in data, (
            "JSON output must contain 'zero_change_sessions'"
        )

    def test_increments_session_count_from_5_to_6(self, tmp_path):
        """Script increments meta.session_count from 5 to 6."""
        state_file = _make_state(tmp_path, session_count=5)
        result = run_script(SCRIPT, str(state_file), str(tmp_path), "5")
        assert result.returncode == 0

        # Verify JSON output reflects incremented count
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "Output should be a JSON object"
        assert data["session_count"] == 6, (
            f"session_count should be 6, got {data['session_count']}"
        )

        # Verify STATE.yaml was updated on disk
        with open(state_file) as f:
            updated_state = yaml.safe_load(f)
        assert updated_state["meta"]["session_count"] == 6, (
            "STATE.yaml meta.session_count should be incremented to 6"
        )


class TestPostSessionAccountingZeroChange:
    """Tests for zero-change session detection."""

    def test_zero_change_detection_with_same_head(self, tmp_path):
        """Detects zero-change session when HEAD matches last_session_head."""
        # Create a real git repo so HEAD comparison can succeed.
        git_dir = tmp_path / "repo"
        git_dir.mkdir()
        subprocess.run(["git", "init", str(git_dir)], capture_output=True)
        subprocess.run(
            ["git", "-C", str(git_dir), "config", "user.email", "test@test.com"],
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(git_dir), "config", "user.name", "Test"],
            capture_output=True,
        )
        # Create a commit so HEAD exists
        (git_dir / "README.md").write_text("hello")
        subprocess.run(["git", "-C", str(git_dir), "add", "."], capture_output=True)
        subprocess.run(
            ["git", "-C", str(git_dir), "commit", "-m", "init"],
            capture_output=True,
        )
        # Get the actual HEAD
        head_result = subprocess.run(
            ["git", "-C", str(git_dir), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        )
        actual_head = head_result.stdout.strip()

        # State has last_session_head = actual_head (simulating same HEAD)
        state_file = _make_state(
            tmp_path, session_count=3, zero_change_sessions=0, last_head=actual_head
        )
        result = run_script(SCRIPT, str(state_file), str(git_dir), "3")
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}. stderr: {result.stderr}"
        )

        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "Output should be a JSON object"
        assert data["zero_change_sessions"] == 1, (
            f"zero_change_sessions should be 1 after zero-change detection, got {data['zero_change_sessions']}"
        )

        # STATE.yaml should reflect incremented zero_change_sessions
        with open(state_file) as f:
            updated_state = yaml.safe_load(f)
        assert updated_state["meta"]["zero_change_sessions"] == 1, (
            "STATE.yaml meta.zero_change_sessions should be incremented to 1"
        )
