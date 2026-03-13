"""Tests for build-check.py — Full build + test + paper tiger detection."""

import yaml

from conftest import SCRIPTS_DIR, parse_last_json, run_script

SCRIPT = SCRIPTS_DIR / "build-check.py"


class TestBuildCheckArgs:
    """Tests for argument handling."""

    def test_no_args_exits_nonzero(self):
        """build-check.py exits non-zero when called with no arguments."""
        result = run_script(SCRIPT)
        assert result.returncode != 0


class TestBuildCheckClean:
    """Tests for clean build and test suite."""

    def test_clean_build_exits_zero(self, tmp_path):
        """When build and tests pass, script exits 0."""
        state_file = tmp_path / "STATE.yaml"
        state_file.write_text(
            "project_name: test\nphase: 1\nepoch: 1\nnext_action: do something\nblockers: []\n"
        )
        result = run_script(SCRIPT, "true", "true", str(tmp_path), str(state_file))
        assert result.returncode == 0

    def test_clean_outputs_valid_json_with_build_status(self, tmp_path):
        """Clean run outputs valid JSON containing build_status field."""
        state_file = tmp_path / "STATE.yaml"
        state_file.write_text(
            "project_name: test\nphase: 1\nepoch: 1\nnext_action: do something\nblockers: []\n"
        )
        result = run_script(SCRIPT, "true", "true", str(tmp_path), str(state_file))
        assert result.returncode == 0
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "output should be a JSON object"
        assert "build_status" in data, "JSON output must contain 'build_status' field"

    def test_clean_status_is_clean(self, tmp_path):
        """Clean build and test run outputs build_status='clean'."""
        state_file = tmp_path / "STATE.yaml"
        state_file.write_text(
            "project_name: test\nphase: 1\nepoch: 1\nnext_action: do something\nblockers: []\n"
        )
        result = run_script(SCRIPT, "true", "true", str(tmp_path), str(state_file))
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "output should be a JSON object"
        assert data["build_status"] == "clean"


class TestBuildCheckFailures:
    """Tests for build and test failures."""

    def test_failed_build_status_is_failed(self, tmp_path):
        """When build command fails, build_status='failed'."""
        state_file = tmp_path / "STATE.yaml"
        state_file.write_text(
            "project_name: test\nphase: 1\nepoch: 1\nnext_action: do something\nblockers: []\n"
        )
        result = run_script(SCRIPT, "false", "true", str(tmp_path), str(state_file))
        assert result.returncode == 0  # exits 0 always
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "output should be a JSON object"
        assert data["build_status"] == "failed"

    def test_failed_build_writes_blocker_to_state(self, tmp_path):
        """Failed build writes a blocker entry to STATE.yaml."""
        state_file = tmp_path / "STATE.yaml"
        state_file.write_text(
            "project_name: test\nphase: 1\nepoch: 1\nnext_action: do something\nblockers: []\n"
        )
        run_script(SCRIPT, "false", "true", str(tmp_path), str(state_file))
        with open(state_file) as f:
            state = yaml.safe_load(f)
        assert state.get("blockers"), "STATE.yaml should have at least one blocker"
        assert len(state["blockers"]) > 0
        blocker = state["blockers"][0]
        assert blocker.get("severity") == "high"

    def test_failed_tests_status_is_failed(self, tmp_path):
        """When test command fails, build_status='failed'."""
        state_file = tmp_path / "STATE.yaml"
        state_file.write_text(
            "project_name: test\nphase: 1\nepoch: 1\nnext_action: do something\nblockers: []\n"
        )
        result = run_script(SCRIPT, "true", "false", str(tmp_path), str(state_file))
        assert result.returncode == 0  # exits 0 always
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "output should be a JSON object"
        assert data["build_status"] == "failed"
