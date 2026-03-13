"""Tests for orient.py — reads STATE.yaml and outputs structured status JSON."""

from conftest import FIXTURES_DIR, SCRIPTS_DIR, parse_last_json, run_script

ORIENT = SCRIPTS_DIR / "orient.py"
STATE_YAML = FIXTURES_DIR / "STATE.yaml"
STATE_BLOCKED_YAML = FIXTURES_DIR / "STATE-blocked.yaml"


class TestOrientHealthyState:
    """Tests using the healthy STATE.yaml fixture."""

    def test_healthy_state_exits_zero(self):
        """orient.py exits 0 when given a valid state file."""
        result = run_script(ORIENT, str(STATE_YAML))
        assert result.returncode == 0

    def test_outputs_valid_json(self):
        """orient.py outputs a single valid JSON line to stdout."""
        result = run_script(ORIENT, str(STATE_YAML))
        assert result.stdout.strip(), "stdout should not be empty"
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "output should be a JSON object"

    def test_required_fields_present(self):
        """JSON output contains all required fields: phase, epoch, ready_count, status."""
        result = run_script(ORIENT, str(STATE_YAML))
        data = parse_last_json(result.stdout)
        for field in ("phase", "epoch", "ready_count", "status"):
            assert field in data, f"required field '{field}' missing from output"

    def test_healthy_status(self):
        """status is 'healthy' when blockers list is empty."""
        result = run_script(ORIENT, str(STATE_YAML))
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict)
        assert data["status"] == "healthy"

    def test_ready_count_respects_completed_features(self):
        """ready_count=1 because feature-b is ready and its dep feature-a is in completed_features."""
        result = run_script(ORIENT, str(STATE_YAML))
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict)
        assert data["ready_count"] == 1

    def test_all_output_fields(self):
        """JSON output contains phase, phase_name, epoch, next_action, ready_count, completed_count, status."""
        result = run_script(ORIENT, str(STATE_YAML))
        data = parse_last_json(result.stdout)
        expected_fields = {
            "phase",
            "phase_name",
            "epoch",
            "next_action",
            "ready_count",
            "completed_count",
            "status",
        }
        for field in expected_fields:
            assert field in data, f"field '{field}' missing from output"


class TestOrientBlockedState:
    """Tests using the blocked STATE-blocked.yaml fixture."""

    def test_blocked_status(self):
        """status is 'blocked' when blockers list is non-empty."""
        result = run_script(ORIENT, str(STATE_BLOCKED_YAML))
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict)
        assert data["status"] == "blocked"


class TestOrientErrorHandling:
    """Tests for error handling: missing file and no args."""

    def test_missing_file_exits_nonzero(self):
        """orient.py exits non-zero when the state file does not exist."""
        result = run_script(ORIENT, "/nonexistent/path/STATE.yaml")
        assert result.returncode != 0

    def test_no_args_exits_nonzero(self):
        """orient.py exits non-zero when called with no arguments."""
        result = run_script(ORIENT)
        assert result.returncode != 0
