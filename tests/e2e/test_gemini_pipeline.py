"""E2E test for the Gemini pipeline (loop-pipeline).

Requires GOOGLE_API_KEY. Run with:

    uv run pytest tests/e2e/test_gemini_pipeline.py -v

Pipeline tests are slower (up to 10 minutes) since they spawn
agent sessions per pipeline node.
"""

import os
import subprocess
from pathlib import Path

import pytest

BUNDLE_ROOT = Path(__file__).parent.parent.parent
PIPELINE_PROFILE_PATH = BUNDLE_ROOT / "profiles" / "attractor-e2e-pipeline-gemini.yaml"

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

skip_no_key = pytest.mark.skipif(
    not GOOGLE_API_KEY,
    reason="GOOGLE_API_KEY not set",
)

PIPELINE_TIMEOUT = 600  # seconds


def run_pipeline(
    instruction: str,
    cwd: Path,
    timeout: int = PIPELINE_TIMEOUT,
) -> subprocess.CompletedProcess:
    """Run the Gemini pipeline with the given instruction."""
    return subprocess.run(
        [
            "amplifier",
            "run",
            "-B",
            f"file://{PIPELINE_PROFILE_PATH}",
            "--mode",
            "single",
            instruction,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@skip_no_key
def test_gemini_pipeline_simple_file_creation(tmp_path):
    """Pipeline executes simple_file_creation.dot with a Gemini agent node.

    Graph: start -> implement -> done
    The DOT fixture's implement node instructs the Gemini agent to create hello.py.
    """
    result = run_pipeline(
        "Run the pipeline",
        cwd=tmp_path,
    )
    assert result.returncode == 0, (
        f"Pipeline failed.\nSTDOUT:\n{result.stdout[:2000]}\nSTDERR:\n{result.stderr[:2000]}"
    )
    hello_py = tmp_path / "hello.py"
    assert hello_py.exists(), (
        f"hello.py was not created by pipeline.\n"
        f"Files in tmp: {list(tmp_path.iterdir())}\n"
        f"Pipeline output:\n{result.stdout[:1000]}"
    )
