"""E2E tests for the Gemini agent (loop-agent, no pipeline).

These tests require a real GOOGLE_API_KEY and are gated behind
a skipif marker. Run with:

    uv run pytest tests/e2e/test_gemini_agent.py -v

Or with explicit timeout:

    uv run pytest tests/e2e/test_gemini_agent.py -v --timeout=300
"""

import os
import subprocess
from pathlib import Path

import pytest

BUNDLE_ROOT = Path(__file__).parent.parent.parent
PROFILE_PATH = BUNDLE_ROOT / "profiles" / "attractor-e2e-gemini.yaml"

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

skip_no_key = pytest.mark.skipif(
    not GOOGLE_API_KEY,
    reason="GOOGLE_API_KEY not set",
)

TIMEOUT = 180  # seconds per test


def run_agent(
    instruction: str,
    cwd: Path,
    timeout: int = TIMEOUT,
) -> subprocess.CompletedProcess:
    """Run the Gemini agent with the given instruction."""
    return subprocess.run(
        [
            "amplifier",
            "run",
            "-B",
            f"file://{PROFILE_PATH}",
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
def test_gemini_agent_basic_invocation(tmp_path):
    """Agent can perform a basic coding task without file I/O."""
    result = run_agent(
        "Write a one-sentence explanation of what a Python list comprehension is. "
        "No file creation needed.",
        cwd=tmp_path,
    )
    assert result.returncode == 0, (
        f"Agent exited non-zero.\nSTDOUT:\n{result.stdout[:1000]}\nSTDERR:\n{result.stderr[:1000]}"
    )


@skip_no_key
def test_gemini_agent_creates_file(tmp_path):
    """Agent uses write_file tool to create a file."""
    result = run_agent(
        "Create a file called hello.py that prints 'Hello from Gemini'. "
        "Use the write_file tool.",
        cwd=tmp_path,
    )
    assert result.returncode == 0, (
        f"Agent exited non-zero.\nSTDOUT:\n{result.stdout[:1000]}\nSTDERR:\n{result.stderr[:1000]}"
    )
    hello_py = tmp_path / "hello.py"
    assert hello_py.exists(), (
        f"hello.py was not created.\nFiles in tmp: {list(tmp_path.iterdir())}"
    )
    content = hello_py.read_text()
    assert "Gemini" in content or "hello" in content.lower(), (
        f"Unexpected content in hello.py:\n{content}"
    )


@skip_no_key
def test_gemini_agent_can_use_web_search(tmp_path):
    """Agent can use the web_search tool (Gemini-unique capability)."""
    result = run_agent(
        "Use the web_search tool to search for 'Python 3.12 release date' "
        "and tell me the year it was released.",
        cwd=tmp_path,
    )
    assert result.returncode == 0, (
        f"Agent exited non-zero.\nSTDOUT:\n{result.stdout[:1000]}\nSTDERR:\n{result.stderr[:1000]}"
    )
    output = result.stdout + result.stderr
    assert "2023" in output or "3.12" in output, (
        f"Expected year/version reference in output:\n{output[:500]}"
    )


@skip_no_key
def test_gemini_agent_read_then_edit(tmp_path):
    """Agent reads an existing file then edits it."""
    existing = tmp_path / "existing.py"
    existing.write_text("print('original content')\n")

    result = run_agent(
        "Read the file existing.py, then edit it to also print 'added line'. "
        "Use read_file then edit_file.",
        cwd=tmp_path,
    )
    assert result.returncode == 0, (
        f"Agent exited non-zero.\nSTDOUT:\n{result.stdout[:1000]}\nSTDERR:\n{result.stderr[:1000]}"
    )
    content = existing.read_text()
    assert "original" in content, (
        f"'original content' missing from edited file:\n{content}"
    )
    assert "added" in content, f"'added line' missing from edited file:\n{content}"
