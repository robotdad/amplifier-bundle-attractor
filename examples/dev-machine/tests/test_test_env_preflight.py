"""Tests for test-env-preflight.py — validate test runner works."""

from conftest import SCRIPTS_DIR, parse_last_json, run_script

SCRIPT = SCRIPTS_DIR / "test-env-preflight.py"


class TestTestEnvPreflightArgs:
    """Tests for argument handling."""

    def test_no_args_exits_nonzero(self):
        """test-env-preflight.py exits non-zero when called with no arguments."""
        result = run_script(SCRIPT)
        assert result.returncode != 0


class TestTestEnvPreflightWorkingRunner:
    """Tests for a working test runner."""

    def test_working_runner_exits_zero(self, tmp_path):
        """When test runner works (exit 0), preflight exits 0."""
        result = run_script(SCRIPT, "true", str(tmp_path))
        assert result.returncode == 0


class TestTestEnvPreflightBrokenRunner:
    """Tests for a broken test runner ('false' command exits non-zero)."""

    def test_broken_runner_exits_99(self, tmp_path):
        """When test runner is broken ('false' command), preflight exits 99."""
        result = run_script(SCRIPT, "false", str(tmp_path))
        assert result.returncode == 99

    def test_broken_runner_writes_postmortem_file(self, tmp_path):
        """Broken runner writes .dev-machine-postmortem file to project_dir."""
        run_script(SCRIPT, "false", str(tmp_path))
        postmortem = tmp_path / ".dev-machine-postmortem"
        assert postmortem.exists()

    def test_broken_runner_writes_sentinel_file(self, tmp_path):
        """Broken runner writes .dev-machine-test-env-broken sentinel file."""
        run_script(SCRIPT, "false", str(tmp_path))
        sentinel = tmp_path / ".dev-machine-test-env-broken"
        assert sentinel.exists()

    def test_broken_runner_outputs_broken_json(self, tmp_path):
        """Broken runner outputs JSON with test_env='broken'."""
        result = run_script(SCRIPT, "false", str(tmp_path))
        data = parse_last_json(result.stdout)
        assert data == {"test_env": "broken"}
