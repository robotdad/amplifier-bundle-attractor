"""Tests for post-session-reconcile.py — Stale metadata, wiring audit, periodic checks."""

import yaml

from conftest import SCRIPTS_DIR, parse_last_json, run_script

SCRIPT = SCRIPTS_DIR / "post-session-reconcile.py"


def _make_state(
    tmp_path,
    completed_features=None,
    total_features_completed=None,
    session_count=5,
    epoch=3,
    features=None,
    next_action="implement next feature",
):
    """Create a STATE.yaml for reconcile tests."""
    if completed_features is None:
        completed_features = ["feature-a", "feature-b"]
    if total_features_completed is None:
        total_features_completed = len(completed_features)
    if features is None:
        features = {}

    state = {
        "project_name": "test-project",
        "phase": 1,
        "phase_name": "foundation",
        "epoch": epoch,
        "next_action": next_action,
        "blockers": [],
        "completed_features": completed_features,
        "features": features,
        "meta": {
            "session_count": session_count,
            "zero_change_sessions": 0,
            "last_session_head": "abc1234",
            "total_features_completed": total_features_completed,
        },
    }
    state_file = tmp_path / "STATE.yaml"
    with open(state_file, "w") as f:
        yaml.dump(state, f, default_flow_style=False, sort_keys=False)
    return state_file


class TestPostSessionReconcileExitCodes:
    """Tests for exit code behaviour."""

    def test_exits_zero_with_valid_args(self, tmp_path):
        """Script exits 0 when given valid STATE.yaml and directories."""
        state_file = _make_state(tmp_path)
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        result = run_script(
            SCRIPT,
            str(state_file),
            str(specs_dir),
            str(project_dir),
            "echo install",
            "echo test",
        )
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}. stderr: {result.stderr}"
        )

    def test_no_args_exits_nonzero(self):
        """Script exits non-zero when called with no arguments."""
        result = run_script(SCRIPT)
        assert result.returncode != 0


class TestPostSessionReconcileOutput:
    """Tests for JSON output format."""

    def test_outputs_valid_json_with_reconciled_field(self, tmp_path):
        """Script outputs valid JSON containing reconciled field."""
        state_file = _make_state(tmp_path)
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        result = run_script(
            SCRIPT,
            str(state_file),
            str(specs_dir),
            str(project_dir),
            "echo install",
            "echo test",
        )
        assert result.returncode == 0
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "Output should be a JSON object"
        assert "reconciled" in data, "JSON output must contain 'reconciled' field"
        assert "wiring_issues" in data, "JSON output must contain 'wiring_issues' field"


class TestPostSessionReconcileStaleMetadata:
    """Tests for stale metadata reconciliation."""

    def test_fixes_stale_total_features_completed(self, tmp_path):
        """Reconciles meta.total_features_completed from stale 99 to actual 2."""
        # completed_features has 2 items but total_features_completed is 99 (stale)
        state_file = _make_state(
            tmp_path,
            completed_features=["feature-a", "feature-b"],
            total_features_completed=99,
        )
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        result = run_script(
            SCRIPT,
            str(state_file),
            str(specs_dir),
            str(project_dir),
            "echo install",
            "echo test",
        )
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}. stderr: {result.stderr}"
        )

        # Verify JSON output indicates reconciliation happened
        data = parse_last_json(result.stdout)
        assert isinstance(data, dict), "Output should be a JSON object"
        assert data.get("reconciled") is True, (
            f"reconciled should be True when stale metadata was fixed, got {data}"
        )

        # Verify STATE.yaml was updated on disk
        with open(state_file) as f:
            updated_state = yaml.safe_load(f)
        actual_total = updated_state["meta"]["total_features_completed"]
        assert actual_total == 2, (
            f"meta.total_features_completed should be fixed to 2 (actual count), got {actual_total}"
        )
