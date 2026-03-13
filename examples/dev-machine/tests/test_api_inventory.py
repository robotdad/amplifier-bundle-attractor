"""Tests for api-inventory.py — scan source for public APIs, write to SCRATCH.md."""

from conftest import SCRIPTS_DIR, parse_last_json, run_script

SCRIPT = SCRIPTS_DIR / "api-inventory.py"


class TestApiInventoryArgs:
    """Tests for argument handling."""

    def test_no_args_exits_nonzero(self):
        """api-inventory.py exits non-zero when called with no arguments."""
        result = run_script(SCRIPT)
        assert result.returncode != 0

    def test_exits_zero_with_project_dir(self, tmp_path):
        """api-inventory.py exits 0 when given a valid project_dir."""
        result = run_script(SCRIPT, str(tmp_path))
        assert result.returncode == 0


class TestApiInventoryScratchFile:
    """Tests for SCRATCH.md creation and appending."""

    def test_creates_scratch_md_if_missing(self, tmp_path):
        """Creates SCRATCH.md when it does not exist."""
        scratch = tmp_path / "SCRATCH.md"
        assert not scratch.exists()
        run_script(SCRIPT, str(tmp_path))
        assert scratch.exists()

    def test_appends_to_existing_scratch_md_preserving_content(self, tmp_path):
        """Appends API inventory section to existing SCRATCH.md without overwriting content."""
        scratch = tmp_path / "SCRATCH.md"
        existing_content = "# My Project\n\nSome existing notes here.\n"
        scratch.write_text(existing_content)
        run_script(SCRIPT, str(tmp_path))
        content = scratch.read_text()
        # Original content must be preserved
        assert "Some existing notes here." in content
        # New inventory section must be appended
        assert "## API Inventory" in content


class TestApiInventoryOutput:
    """Tests for output format and content."""

    def test_outputs_json_with_status_and_scratch_file(self, tmp_path):
        """Output includes final JSON line with status and scratch_file fields."""
        result = run_script(SCRIPT, str(tmp_path))
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "output should be a JSON object"
        assert "status" in data
        assert "scratch_file" in data

    def test_finds_python_public_items_in_py_files(self, tmp_path):
        """Finds Python public classes and functions in .py files."""
        # Create a .py file with public items
        src_file = tmp_path / "mymodule.py"
        src_file.write_text(
            "class MyClass:\n"
            "    pass\n"
            "\n"
            "def public_function():\n"
            "    pass\n"
            "\n"
            "def _private():\n"
            "    pass\n"
        )
        scratch = tmp_path / "SCRATCH.md"
        run_script(SCRIPT, str(tmp_path))
        content = scratch.read_text()
        # Public class and function should appear in the inventory
        assert "MyClass" in content or "mymodule.py" in content
        assert "## API Inventory" in content
