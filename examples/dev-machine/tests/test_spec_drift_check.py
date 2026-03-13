"""Tests for spec-drift-check.py — compare spec mtimes vs implementation mtimes."""

from conftest import SCRIPTS_DIR, parse_last_json, run_script

SCRIPT = SCRIPTS_DIR / "spec-drift-check.py"


class TestSpecDriftCheckArgs:
    """Tests for argument handling."""

    def test_no_args_exits_nonzero(self):
        """spec-drift-check.py exits non-zero when called with no arguments."""
        result = run_script(SCRIPT)
        assert result.returncode != 0


class TestSpecDriftCheckMissingDirs:
    """Tests for missing/empty directories."""

    def test_nonexistent_specs_dir_exits_zero(self, tmp_path):
        """Missing specs dir is not an error — exits 0."""
        nonexistent = tmp_path / "nonexistent_specs"
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        result = run_script(SCRIPT, str(nonexistent), str(project_dir))
        assert result.returncode == 0

    def test_empty_specs_dir_exits_zero(self, tmp_path):
        """Empty specs dir exits zero."""
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        result = run_script(SCRIPT, str(specs_dir), str(project_dir))
        assert result.returncode == 0


class TestSpecDriftCheckOutput:
    """Tests for output format and content."""

    def test_ok_message_when_no_drift(self, tmp_path):
        """Outputs OK message when no drift detected."""
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        # Create a spec file but no matching impl files
        spec_file = specs_dir / "myfeature-spec.md"
        spec_file.write_text("# My Feature Spec")
        result = run_script(SCRIPT, str(specs_dir), str(project_dir))
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_outputs_json_with_drift_count_and_status(self, tmp_path):
        """Output includes final JSON line with drift_count and status."""
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        result = run_script(SCRIPT, str(specs_dir), str(project_dir))
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "output should be a JSON object"
        assert "drift_count" in data
        assert "status" in data
        assert data["status"] in ("ok", "drift")
