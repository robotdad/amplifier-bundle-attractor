"""Tests for module-health-check.py — LOC per package with content-aware bypass."""

from conftest import SCRIPTS_DIR, parse_last_json, run_script

SCRIPT = SCRIPTS_DIR / "module-health-check.py"


class TestModuleHealthCheckArgs:
    """Tests for argument handling."""

    def test_no_args_exits_nonzero(self):
        """module-health-check.py exits non-zero when called with no arguments."""
        result = run_script(SCRIPT)
        assert result.returncode != 0


class TestModuleHealthCheckNoPackages:
    """Tests for projects with no packages directory."""

    def test_ok_when_no_packages_dir(self, tmp_path):
        """Exits 0 with health=ok when packages/ dir does not exist."""
        state_file = tmp_path / "STATE.yaml"
        state_file.write_text(
            "project_name: test\nphase: 1\nepoch: 1\nnext_action: do something\nblockers: []\n"
        )
        result = run_script(SCRIPT, str(state_file), str(tmp_path), "100")
        assert result.returncode == 0
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "output should be a JSON object"
        assert data["health"] == "ok"

    def test_empty_project_exits_zero_with_ok(self, tmp_path):
        """Empty project directory (no packages/) exits 0 with health=ok."""
        state_file = tmp_path / "STATE.yaml"
        state_file.write_text(
            "project_name: test\nphase: 1\nepoch: 1\nnext_action: do something\nblockers: []\n"
        )
        result = run_script(SCRIPT, str(state_file), str(tmp_path), "500")
        assert result.returncode == 0


class TestModuleHealthCheckOutput:
    """Tests for output format and content."""

    def test_outputs_valid_json_with_health_field(self, tmp_path):
        """Output includes valid JSON with a health field."""
        state_file = tmp_path / "STATE.yaml"
        state_file.write_text(
            "project_name: test\nphase: 1\nepoch: 1\nnext_action: do something\nblockers: []\n"
        )
        result = run_script(SCRIPT, str(state_file), str(tmp_path), "100")
        assert result.returncode == 0
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "output should be a JSON object"
        assert "health" in data, "JSON output must contain 'health' field"
        assert data["health"] in ("ok", "warn-oversized", "needs-refactoring")


class TestModuleHealthCheckOversized:
    """Tests for oversized package detection."""

    def test_flags_oversized_package(self, tmp_path):
        """Flags a package with 20 lines when threshold=5 as oversized."""
        state_file = tmp_path / "STATE.yaml"
        state_file.write_text(
            "project_name: test\nphase: 1\nepoch: 1\nnext_action: do something unrelated\nblockers: []\n"
        )
        # Create packages/my-module/src/ with a file exceeding threshold
        pkg_src = tmp_path / "packages" / "my-module" / "src"
        pkg_src.mkdir(parents=True)
        # Write a file with 20 lines
        large_file = pkg_src / "index.ts"
        large_file.write_text("\n".join(f"const line{i} = {i};" for i in range(20)))

        result = run_script(SCRIPT, str(state_file), str(tmp_path), "5")
        assert result.returncode == 0
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "output should be a JSON object"
        assert data["health"] in (
            "needs-refactoring",
            "warn-oversized",
        ), f"Expected oversized status, got: {data['health']}"
