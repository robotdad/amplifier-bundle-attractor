"""Shared test utilities and fixtures for dev-machine pipeline script tests."""

import json
import re
import subprocess
import sys
from pathlib import Path

# Path constants
TESTS_DIR = Path(__file__).parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
SCRIPTS_DIR = TESTS_DIR.parent / "scripts" / "pipeline"


def run_script(
    script_path: Path | str, *args: str, input_text: str | None = None
) -> subprocess.CompletedProcess:
    """Run a Python script via subprocess and return the completed process.

    Args:
        script_path: Path to the Python script to run.
        *args: Additional arguments to pass to the script.
        input_text: Optional stdin input for the script.

    Returns:
        subprocess.CompletedProcess with stdout, stderr, and returncode.
    """
    cmd = [sys.executable, str(script_path), *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        input=input_text,
    )


def run_shell_script(
    script_path: Path | str, *args: str, input_text: str | None = None
) -> subprocess.CompletedProcess:
    """Run a shell script via subprocess and return the completed process.

    Args:
        script_path: Path to the shell script to run.
        *args: Additional arguments to pass to the script.
        input_text: Optional stdin input for the script.

    Returns:
        subprocess.CompletedProcess with stdout, stderr, and returncode.
    """
    cmd = [str(script_path), *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        input=input_text,
    )


def parse_last_json(output: str) -> dict | list:
    """Extract and parse the last JSON object or array from mixed text+JSON stdout.

    Useful for scripts that emit log lines followed by a final JSON result.

    Args:
        output: String output that may contain text mixed with JSON.

    Returns:
        Parsed JSON value (dict or list) from the last JSON block found.

    Raises:
        ValueError: If no valid JSON object or array is found in the output.
    """
    # Find all JSON object/array candidates using a pattern that matches
    # top-level { ... } or [ ... ] blocks
    candidates = []

    # Try to find JSON by scanning for { or [ that start a valid JSON block
    # We try each position where a { or [ appears and attempt to parse from there
    for match in re.finditer(r"[{\[]", output):
        start = match.start()
        substring = output[start:]
        # Try increasingly large substrings to find valid JSON
        try:
            parsed = json.loads(substring)
            candidates.append((start, parsed))
            break  # Found one starting here; record it
        except json.JSONDecodeError:
            # Try to find the end of the JSON block by looking at lines
            # Collect lines and try progressive accumulation
            pass

    # More robust approach: split on lines and look for JSON blocks
    lines = output.splitlines()
    json_candidates = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("{") or line.startswith("["):
            # Try accumulating lines until we get valid JSON
            for end in range(i + 1, len(lines) + 1):
                candidate_text = "\n".join(lines[i:end])
                try:
                    parsed = json.loads(candidate_text)
                    json_candidates.append(parsed)
                    i = end
                    break
                except json.JSONDecodeError:
                    continue
            else:
                i += 1
        else:
            # Also try parsing individual lines as JSON
            if line:
                try:
                    parsed = json.loads(line)
                    json_candidates.append(parsed)
                except json.JSONDecodeError:
                    pass
            i += 1

    if not json_candidates:
        raise ValueError(f"No valid JSON found in output:\n{output}")

    return json_candidates[-1]
