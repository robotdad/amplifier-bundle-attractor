"""Tests for container-check.sh — Refuse to run outside Docker."""

import os
import subprocess
from pathlib import Path

import pytest

from conftest import SCRIPTS_DIR

SCRIPT = SCRIPTS_DIR / "container-check.sh"

# Detect if the test runner itself is inside a container
IN_CONTAINER = Path("/.dockerenv").exists() or Path("/run/.containerenv").exists()

skip_if_in_container = pytest.mark.skipif(
    IN_CONTAINER,
    reason="Container check tests only run on bare host (skip when inside container)",
)


def run_container_check(
    env_overrides: dict | None = None,
) -> subprocess.CompletedProcess:
    """Run container-check.sh with optional environment variable overrides.

    Strips DEV_MACHINE_ALLOW_HOST from the environment unless explicitly set
    in env_overrides, ensuring a clean test environment.

    Args:
        env_overrides: Dict of environment variables to set or override.

    Returns:
        subprocess.CompletedProcess with stdout, stderr, and returncode.
    """
    env = os.environ.copy()
    # Remove DEV_MACHINE_ALLOW_HOST by default so tests start clean
    env.pop("DEV_MACHINE_ALLOW_HOST", None)
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )


class TestContainerCheckExecutable:
    """Tests for container-check.sh file existence and permissions."""

    def test_script_is_executable(self):
        """container-check.sh must have executable permissions (+x)."""
        assert SCRIPT.exists(), f"Script not found: {SCRIPT}"
        assert os.access(SCRIPT, os.X_OK), f"Script is not executable: {SCRIPT}"


class TestContainerCheckBareHost:
    """Tests for behavior when running on a bare host (outside container)."""

    @skip_if_in_container
    def test_fails_on_bare_host_without_allow_env(self):
        """Script exits 1 on bare host when DEV_MACHINE_ALLOW_HOST is not set."""
        result = run_container_check()
        assert result.returncode == 1, (
            f"Expected exit 1 on bare host without DEV_MACHINE_ALLOW_HOST, "
            f"got {result.returncode}.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    @skip_if_in_container
    def test_bypass_with_allow_env_exits_zero(self):
        """Script exits 0 when DEV_MACHINE_ALLOW_HOST=1, printing WARNING."""
        result = run_container_check(env_overrides={"DEV_MACHINE_ALLOW_HOST": "1"})
        assert result.returncode == 0, (
            f"Expected exit 0 when DEV_MACHINE_ALLOW_HOST=1, "
            f"got {result.returncode}.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        combined = result.stdout + result.stderr
        assert "WARNING" in combined or "YOU ACCEPT ALL RISKS" in combined, (
            f"Expected WARNING in output when bypassing with DEV_MACHINE_ALLOW_HOST=1.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
