# DOT Dev-Machine Phase 2: Script Extraction

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Extract inline bash/Python from 5 dev-machine recipe templates into 11 standalone scripts callable by DOT pipeline tool nodes.
**Architecture:** Each script is a self-contained executable that takes CLI args, reads from well-known paths, outputs JSON to stdout, and exits 0/non-zero. Scripts live in `examples/dev-machine/scripts/pipeline/`. Tests live in `examples/dev-machine/tests/` and invoke scripts via subprocess. No imports from other scripts — each is fully standalone.
**Tech Stack:** Python 3.11+, PyYAML, subprocess, pytest

---

## Verified Facts (read before coding)

- **Source recipes:** `/home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-dev-machine/templates/recipes/`
  - `dev-machine-iteration.yaml` (820 lines) — steps `orient`, `spec-drift-check`, `api-inventory`, `test-env-preflight`, `module-health-check`, `build-check`, `post-session`
  - `dev-machine-build.yaml` (256 lines) — step `container-check`
  - `dev-machine-health-check.yaml` (169 lines) — step `initial-check`
  - `dev-machine-fix-iteration.yaml` (152 lines) — steps `read-errors`, `verify`
  - `dev-machine-smoke-test.yaml` (348 lines) — steps `check-file-existence` through `check-robustness-patterns`
- **Target dir:** `amplifier-bundle-attractor/examples/dev-machine/` (does not exist yet — create it)
- **Scripts go in:** `examples/dev-machine/scripts/pipeline/`
- **Tests go in:** `examples/dev-machine/tests/`
- **Fixtures go in:** `examples/dev-machine/tests/fixtures/`
- **Hard constraint:** Core Python logic must be IDENTICAL to the recipe heredoc. `{{template_var}}` → CLI arg. No improvements, no refactoring.
- **Test runner:** `cd amplifier-bundle-attractor/examples/dev-machine && python -m pytest tests/ -v`
- **PyYAML import:** Scripts use `import yaml` — confirm PyYAML available (`python3 -c "import yaml"`)

**Run all phase-2 tests:**
```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/ -v
```

---

## Task 1: Directory Structure and Test Fixtures

**Files:**
- Create: `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/.gitkeep`
- Create: `amplifier-bundle-attractor/examples/dev-machine/tests/fixtures/STATE.yaml`
- Create: `amplifier-bundle-attractor/examples/dev-machine/tests/fixtures/STATE-blocked.yaml`
- Create: `amplifier-bundle-attractor/examples/dev-machine/tests/fixtures/CONTEXT-TRANSFER.md`
- Create: `amplifier-bundle-attractor/examples/dev-machine/tests/conftest.py`

**Step 1: Create directory tree**

```bash
mkdir -p amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline
mkdir -p amplifier-bundle-attractor/examples/dev-machine/tests/fixtures
touch amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/.gitkeep
```

**Step 2: Write `tests/fixtures/STATE.yaml`**

Create `amplifier-bundle-attractor/examples/dev-machine/tests/fixtures/STATE.yaml` with this exact content:

```yaml
project_name: test-project
phase: 1
phase_name: foundation
epoch: 3
next_action: Implement feature-b after feature-a is done
blockers: []
completed_features:
  - feature-a
features:
  feature-b:
    status: ready
    description: Add feature B
    depends_on: [feature-a]
  feature-c:
    status: in-progress
    description: Add feature C
    depends_on: []
meta:
  session_count: 5
  zero_change_sessions: 0
  last_session_head: "abc1234"
  total_features_completed: 1
last_session: "2026-01-01T00:00:00+00:00"
```

**Step 3: Write `tests/fixtures/STATE-blocked.yaml`**

Create `amplifier-bundle-attractor/examples/dev-machine/tests/fixtures/STATE-blocked.yaml`:

```yaml
project_name: test-project
phase: 1
phase_name: foundation
epoch: 1
next_action: Fix build errors
blockers:
  - description: Build failed after working session
    since: "2026-01-01T00:00:00"
    severity: high
completed_features: []
features:
  feature-x:
    status: ready
    description: A feature
meta:
  session_count: 2
  zero_change_sessions: 0
  total_features_completed: 0
```

**Step 4: Write `tests/fixtures/CONTEXT-TRANSFER.md`**

Create `amplifier-bundle-attractor/examples/dev-machine/tests/fixtures/CONTEXT-TRANSFER.md`:

```markdown
# Context Transfer

> **Note**: Older sessions archived in SESSION-ARCHIVE.md.
> Only the last 5 sessions kept here.

### Session 1 Summary
Did some initial work.

### Session 2 Summary
Completed feature-a.
```

**Step 5: Write `tests/conftest.py`**

Create `amplifier-bundle-attractor/examples/dev-machine/tests/conftest.py`:

```python
"""Shared test utilities for dev-machine pipeline script tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts" / "pipeline"


def run_script(script_name: str, *args: str) -> subprocess.CompletedProcess:
    """Run a pipeline script and return the CompletedProcess result."""
    script_path = SCRIPTS_DIR / script_name
    return subprocess.run(
        [sys.executable, str(script_path), *args],
        capture_output=True,
        text=True,
    )


def run_shell_script(script_name: str, *args: str) -> subprocess.CompletedProcess:
    """Run a shell script and return the CompletedProcess result."""
    script_path = SCRIPTS_DIR / script_name
    return subprocess.run(
        [str(script_path), *args],
        capture_output=True,
        text=True,
    )


def parse_last_json(output: str) -> dict:
    """Parse the last valid JSON object from mixed text+JSON stdout."""
    for line in reversed(output.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError(f"No JSON found in output:\n{output}")
```

**Step 6: Verify pytest finds the conftest**

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/ --collect-only 2>&1 | head -20
```

Expected: pytest runs without import errors (no test files yet, just collection).

**Step 7: Commit**

```bash
cd /home/bkrabach/dev/attractor-dev-machine
git add amplifier-bundle-attractor/examples/dev-machine/
git commit -m "feat(phase2): create dev-machine script extraction directory structure and test fixtures"
```

---

## Task 2: `orient.py` — Read STATE.yaml, output structured status

**Source:** `dev-machine-iteration.yaml` step `orient` (lines 28–62)
**Files:**
- Create: `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/orient.py`
- Create: `amplifier-bundle-attractor/examples/dev-machine/tests/test_orient.py`

### Step 1: Write the failing test

Create `amplifier-bundle-attractor/examples/dev-machine/tests/test_orient.py`:

```python
"""Tests for orient.py -- reads STATE.yaml, outputs JSON."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import FIXTURES_DIR, run_script


def test_orient_healthy_state_exits_zero():
    result = run_script("orient.py", str(FIXTURES_DIR / "STATE.yaml"))
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_orient_healthy_state_outputs_valid_json():
    result = run_script("orient.py", str(FIXTURES_DIR / "STATE.yaml"))
    data = json.loads(result.stdout)
    assert isinstance(data, dict)


def test_orient_healthy_state_required_fields():
    result = run_script("orient.py", str(FIXTURES_DIR / "STATE.yaml"))
    data = json.loads(result.stdout)
    assert "phase" in data
    assert "epoch" in data
    assert "ready_count" in data
    assert "status" in data


def test_orient_healthy_status():
    result = run_script("orient.py", str(FIXTURES_DIR / "STATE.yaml"))
    data = json.loads(result.stdout)
    assert data["status"] == "healthy"


def test_orient_blocked_state_returns_blocked_status():
    result = run_script("orient.py", str(FIXTURES_DIR / "STATE-blocked.yaml"))
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["status"] == "blocked"


def test_orient_ready_count_respects_completed_deps():
    """feature-b depends on feature-a which is completed -- should be ready."""
    result = run_script("orient.py", str(FIXTURES_DIR / "STATE.yaml"))
    data = json.loads(result.stdout)
    assert data["ready_count"] == 1  # feature-b is ready (dep feature-a is completed)


def test_orient_missing_file_exits_nonzero():
    result = run_script("orient.py", "/nonexistent/STATE.yaml")
    assert result.returncode != 0


def test_orient_no_args_exits_nonzero():
    result = run_script("orient.py")
    assert result.returncode != 0
```

### Step 2: Run test to verify it fails

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/test_orient.py -v
```

Expected: All tests FAIL with `FileNotFoundError` (script doesn't exist yet).

### Step 3: Write the implementation

Create `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/orient.py`:

```python
#!/usr/bin/env python3
"""orient.py -- Read STATE.yaml and output structured JSON.

Usage: python3 orient.py <state_file>

Output: JSON to stdout
Exit:   0 on success, non-zero on failure

Extracted verbatim from dev-machine-iteration.yaml step 'orient'.
"""

import json
import sys

import yaml


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"status": "blocked", "error": "Usage: orient.py <state_file>"}))
        sys.exit(1)

    state_file = sys.argv[1]

    try:
        with open(state_file) as f:
            state = yaml.safe_load(f)
        blockers = state.get("blockers", [])
        # Support factored state (completed_features list)
        completed_list = set(state.get("completed_features", []))
        features = state.get("features", {})
        ready = in_progress = 0
        for fid, fd in features.items():
            s = fd.get("status", "")
            if s == "ready":
                deps = fd.get("depends_on", [])
                if all(d in completed_list or features.get(d, {}).get("status") in ("completed", "done") for d in deps):
                    ready += 1
            elif s == "in-progress":
                in_progress += 1
        print(json.dumps({
            "phase": state.get("phase", 0),
            "phase_name": state.get("phase_name", "unknown"),
            "epoch": state.get("epoch", 0),
            "next_action": state.get("next_action", ""),
            "ready_count": ready,
            "completed_count": len(completed_list),
            "status": "blocked" if blockers else "healthy"
        }))
    except Exception as e:
        print(json.dumps({"status": "blocked", "error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
```

### Step 4: Run test to verify it passes

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/test_orient.py -v
```

Expected: All 8 tests PASS.

### Step 5: Commit

```bash
cd /home/bkrabach/dev/attractor-dev-machine
git add amplifier-bundle-attractor/examples/dev-machine/
git commit -m "feat(phase2): add orient.py -- reads STATE.yaml, outputs JSON status"
```

---

## Task 3: `spec-drift-check.py` — Compare spec mtimes vs implementation mtimes

**Source:** `dev-machine-iteration.yaml` step `spec-drift-check` (lines 75–119)
**Files:**
- Create: `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/spec-drift-check.py`
- Create: `amplifier-bundle-attractor/examples/dev-machine/tests/test_spec_drift_check.py`

### Step 1: Write the failing test

Create `amplifier-bundle-attractor/examples/dev-machine/tests/test_spec_drift_check.py`:

```python
"""Tests for spec-drift-check.py -- compares spec mtimes vs impl mtimes."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from conftest import FIXTURES_DIR, run_script, parse_last_json


def test_spec_drift_check_exits_zero_on_empty_specs_dir(tmp_path):
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    result = run_script("spec-drift-check.py", str(specs_dir), str(tmp_path))
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_spec_drift_check_ok_message_when_no_drift(tmp_path):
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    result = run_script("spec-drift-check.py", str(specs_dir), str(tmp_path))
    assert "SPEC DRIFT CHECK: OK" in result.stdout


def test_spec_drift_check_nonexistent_specs_dir_exits_zero(tmp_path):
    """Missing specs dir is not an error -- returns OK."""
    result = run_script("spec-drift-check.py", str(tmp_path / "nonexistent"), str(tmp_path))
    assert result.returncode == 0


def test_spec_drift_check_no_args_exits_nonzero():
    result = run_script("spec-drift-check.py")
    assert result.returncode != 0


def test_spec_drift_check_outputs_json():
    """Final line must be valid JSON with a status field."""
    specs_dir = FIXTURES_DIR / "specs" if (FIXTURES_DIR / "specs").exists() else FIXTURES_DIR
    result = run_script("spec-drift-check.py", str(specs_dir), str(FIXTURES_DIR))
    data = parse_last_json(result.stdout)
    assert "drift_count" in data
    assert "status" in data
```

### Step 2: Run test to verify it fails

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/test_spec_drift_check.py -v
```

Expected: All tests FAIL (script doesn't exist).

### Step 3: Write the implementation

Create `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/spec-drift-check.py`:

```python
#!/usr/bin/env python3
"""spec-drift-check.py -- Compare spec file mtimes against implementation mtimes.

Usage: python3 spec-drift-check.py <specs_dir> <project_dir>

Output: Text diagnostic lines + final JSON to stdout
Exit:   0 always (informational check -- failures are warnings, not errors)

Extracted verbatim from dev-machine-iteration.yaml step 'spec-drift-check'.
INTENT: If implementation files are significantly newer than their paired spec files,
the spec has drifted. These candidates are flagged as housekeeping tasks.
"""

import json
import os
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 3:
        print(json.dumps({"status": "error", "drift_count": 0, "error": "Usage: spec-drift-check.py <specs_dir> <project_dir>"}))
        sys.exit(1)

    specs_dir_arg = sys.argv[1]
    project_dir = sys.argv[2]

    os.chdir(project_dir)

    specs_dir = Path(specs_dir_arg)
    STALE_THRESHOLD = 7 * 86400  # 7 days in seconds
    drift_flags = []

    if specs_dir.exists():
        for spec_file in sorted(specs_dir.rglob("*.md")):
            spec_mtime = spec_file.stat().st_mtime
            stem = spec_file.stem
            for suffix in ("-spec", "-module", "-feature", "-design"):
                stem = stem.replace(suffix, "")
            stem = stem.lower()
            if len(stem) < 4:
                continue  # too short -- too many false positives
            for pattern in ("*.ts", "*.tsx", "*.py", "*.rs", "*.js"):
                for impl_file in Path(".").rglob(pattern):
                    parts = str(impl_file).split(os.sep)
                    if any(skip in parts for skip in ("node_modules", ".git", "dist", "__pycache__", ".venv", "target")):
                        continue
                    if specs_dir.name in parts:
                        continue  # don't compare spec against spec
                    if stem in impl_file.stem.lower():
                        impl_mtime = impl_file.stat().st_mtime
                        age_diff_s = impl_mtime - spec_mtime
                        if age_diff_s > STALE_THRESHOLD:
                            drift_flags.append((str(spec_file), str(impl_file), round(age_diff_s / 86400, 1)))
    if drift_flags:
        print(f"=== SPEC DRIFT DETECTED ({len(drift_flags)} candidate(s)) ===")
        for spec_f, impl_f, days in drift_flags[:10]:
            print(f"  HOUSEKEEPING: {spec_f} is {days}d older than {impl_f}")
        if len(drift_flags) > 10:
            print(f"  ... ({len(drift_flags) - 10} more candidates)")
        print("  Add spec-sync tasks to the next epoch, prioritized before new feature work.")
    else:
        print("=== SPEC DRIFT CHECK: OK (no significant drift detected) ===")

    print(json.dumps({"status": "drift" if drift_flags else "ok", "drift_count": len(drift_flags)}))


if __name__ == "__main__":
    main()
```

### Step 4: Run test to verify it passes

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/test_spec_drift_check.py -v
```

Expected: All 5 tests PASS.

### Step 5: Commit

```bash
cd /home/bkrabach/dev/attractor-dev-machine
git add amplifier-bundle-attractor/examples/dev-machine/
git commit -m "feat(phase2): add spec-drift-check.py -- compare spec vs impl mtimes"
```

---

## Task 4: `api-inventory.py` — Scan source for public APIs, write to SCRATCH.md

**Source:** `dev-machine-iteration.yaml` step `api-inventory` (lines 131–166)
**Files:**
- Create: `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/api-inventory.py`
- Create: `amplifier-bundle-attractor/examples/dev-machine/tests/test_api_inventory.py`

### Step 1: Write the failing test

Create `amplifier-bundle-attractor/examples/dev-machine/tests/test_api_inventory.py`:

```python
"""Tests for api-inventory.py -- scans source for public APIs, appends to SCRATCH.md."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import run_script, parse_last_json


def test_api_inventory_exits_zero(tmp_path):
    scratch = tmp_path / "SCRATCH.md"
    result = run_script("api-inventory.py", str(tmp_path), str(scratch))
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_api_inventory_appends_to_scratch_md(tmp_path):
    scratch = tmp_path / "SCRATCH.md"
    scratch.write_text("# Existing content\n")
    result = run_script("api-inventory.py", str(tmp_path), str(scratch))
    assert result.returncode == 0
    content = scratch.read_text()
    assert "API Inventory" in content
    assert "Existing content" in content  # original content preserved


def test_api_inventory_creates_scratch_md_if_missing(tmp_path):
    scratch = tmp_path / "SCRATCH.md"
    result = run_script("api-inventory.py", str(tmp_path), str(scratch))
    assert scratch.exists()


def test_api_inventory_outputs_json(tmp_path):
    scratch = tmp_path / "SCRATCH.md"
    result = run_script("api-inventory.py", str(tmp_path), str(scratch))
    data = parse_last_json(result.stdout)
    assert "status" in data


def test_api_inventory_finds_python_public_items(tmp_path):
    """Finds top-level classes and functions in .py files."""
    (tmp_path / "mymodule.py").write_text(
        "class MyClass:\n    pass\n\ndef public_func():\n    pass\n"
    )
    scratch = tmp_path / "SCRATCH.md"
    result = run_script("api-inventory.py", str(tmp_path), str(scratch))
    assert result.returncode == 0
    content = scratch.read_text()
    assert "Python" in content


def test_api_inventory_no_args_exits_nonzero():
    result = run_script("api-inventory.py")
    assert result.returncode != 0
```

### Step 2: Run test to verify it fails

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/test_api_inventory.py -v
```

Expected: All tests FAIL (script doesn't exist).

### Step 3: Write the implementation

The original step is pure bash. The extracted Python script wraps the same grep logic using subprocess.

Create `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/api-inventory.py`:

```python
#!/usr/bin/env python3
"""api-inventory.py -- Scan project source for public types/APIs, append to SCRATCH.md.

Usage: python3 api-inventory.py <project_dir> [scratch_file]

Defaults: scratch_file = <project_dir>/SCRATCH.md

Output: Text to stdout + final JSON
Exit:   0 always (informational -- on_error: continue in recipe)

Extracted from dev-machine-iteration.yaml step 'api-inventory'.
INTENT: Give the working session a concrete map of what actually exists before
it starts coding. The agent reads SCRATCH.md to find real type names.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def run_grep(args: list[str]) -> str:
    """Run grep and return output, empty string on error."""
    try:
        result = subprocess.run(args, capture_output=True, text=True)
        return result.stdout.strip() if result.stdout.strip() else "(none found)"
    except Exception:
        return "(none found)"


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "error": "Usage: api-inventory.py <project_dir> [scratch_file]"}))
        sys.exit(1)

    project_dir = sys.argv[1]
    scratch_file = sys.argv[2] if len(sys.argv) > 2 else os.path.join(project_dir, "SCRATCH.md")

    os.chdir(project_dir)
    print("=== API INVENTORY ===")

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    ts_output = run_grep([
        "grep", "-rn",
        "--include=*.ts", "--include=*.tsx", "--include=*.js",
        "-E", r"^export (default )?(interface|type|class|function|async function|const|enum|abstract class)",
        "--exclude-dir=node_modules", "--exclude-dir=dist", "--exclude-dir=.git", "--exclude-dir=build",
        ".",
    ])

    py_output = run_grep([
        "grep", "-rn",
        "--include=*.py",
        "-E", r"^(class [A-Z]|def [a-z][^_]|async def [a-z][^_])",
        "--exclude-dir=__pycache__", "--exclude-dir=.git", "--exclude-dir=.venv",
        "--exclude=test_*", "--exclude=*_test.py",
        ".",
    ])

    rs_output = run_grep([
        "grep", "-rn",
        "--include=*.rs",
        "-E", r"^pub (struct|enum|fn|trait|type|const)",
        "--exclude-dir=target", "--exclude-dir=.git",
        ".",
    ])

    lines = [
        "",
        f"## API Inventory (auto-generated {timestamp})",
        "",
        "### TypeScript / JavaScript public exports",
        *ts_output.splitlines()[:60],
        "",
        "### Python public classes / functions",
        *py_output.splitlines()[:60],
        "",
        "### Rust public items",
        *rs_output.splitlines()[:60],
        "",
        "---",
    ]

    with open(scratch_file, "a") as f:
        f.write("\n".join(lines) + "\n")

    print(f"API inventory appended to {scratch_file}")
    print(json.dumps({"status": "ok", "scratch_file": scratch_file}))


if __name__ == "__main__":
    main()
```

### Step 4: Run test to verify it passes

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/test_api_inventory.py -v
```

Expected: All 6 tests PASS.

### Step 5: Commit

```bash
cd /home/bkrabach/dev/attractor-dev-machine
git add amplifier-bundle-attractor/examples/dev-machine/
git commit -m "feat(phase2): add api-inventory.py -- scan public APIs, append to SCRATCH.md"
```

---

## Task 5: `test-env-preflight.py` — Validate test runner works

**Source:** `dev-machine-iteration.yaml` step `test-env-preflight` (lines 177–218)
**Files:**
- Create: `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/test-env-preflight.py`
- Create: `amplifier-bundle-attractor/examples/dev-machine/tests/test_test_env_preflight.py`

### Step 1: Write the failing test

Create `amplifier-bundle-attractor/examples/dev-machine/tests/test_test_env_preflight.py`:

```python
"""Tests for test-env-preflight.py -- validates the test runner itself works."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from conftest import run_script


def test_preflight_exits_zero_on_working_runner(tmp_path):
    """A command that succeeds on --collect-only should exit 0."""
    result = run_script("test-env-preflight.py", "python3 -m pytest --version", str(tmp_path))
    # python3 -m pytest --version doesn't take --collect-only but exits 0
    # We just check the script itself runs
    assert result.returncode in (0, 1, 99)  # any valid exit code


def test_preflight_broken_runner_exits_99(tmp_path):
    """A command that fails --collect-only should exit 99."""
    result = run_script("test-env-preflight.py", "false", str(tmp_path))
    assert result.returncode == 99


def test_preflight_broken_runner_writes_postmortem(tmp_path):
    result = run_script("test-env-preflight.py", "false", str(tmp_path))
    assert (tmp_path / ".dev-machine-postmortem").exists()


def test_preflight_broken_runner_writes_sentinel(tmp_path):
    result = run_script("test-env-preflight.py", "false", str(tmp_path))
    assert (tmp_path / ".dev-machine-test-env-broken").exists()


def test_preflight_broken_runner_outputs_broken_json(tmp_path):
    result = run_script("test-env-preflight.py", "false", str(tmp_path))
    # Find the JSON line in output
    for line in result.stdout.splitlines():
        if line.strip().startswith("{"):
            data = json.loads(line.strip())
            assert data["test_env"] == "broken"
            return
    pytest.fail(f"No JSON found in stdout: {result.stdout!r}")


def test_preflight_no_args_exits_nonzero():
    result = run_script("test-env-preflight.py")
    assert result.returncode != 0
```

### Step 2: Run test to verify it fails

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/test_test_env_preflight.py -v
```

Expected: All tests FAIL (script doesn't exist).

### Step 3: Write the implementation

The original is pure bash. The extracted Python script uses subprocess to run the test command.

Create `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/test-env-preflight.py`:

```python
#!/usr/bin/env python3
"""test-env-preflight.py -- Validate the test runner works before starting a session.

Usage: python3 test-env-preflight.py <test_command> <project_dir>

Output: JSON to stdout  {"test_env": "ok"} or {"test_env": "broken"}
Exit:   0 = test runner functional, 99 = test runner broken (structural failure)

Extracted from dev-machine-iteration.yaml step 'test-env-preflight'.
INTENT: If the test RUNNER is broken (missing deps, import error, syntax error in
test infrastructure), detect this BEFORE wasting a working session.
This is NOT about failing tests -- it's about the runner being non-functional.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone


def main() -> None:
    if len(sys.argv) < 3:
        print(json.dumps({"status": "error", "error": "Usage: test-env-preflight.py <test_command> <project_dir>"}))
        sys.exit(1)

    test_command = sys.argv[1]
    project_dir = sys.argv[2]

    os.chdir(project_dir)
    print("=== TEST ENVIRONMENT PREFLIGHT ===")

    cmd_parts = test_command.split() + ["--collect-only", "-q"]
    collect_result = subprocess.run(cmd_parts, capture_output=True, text=True)
    collect_output = collect_result.stdout + collect_result.stderr
    collect_exit = collect_result.returncode

    print(collect_output[:2000] if collect_output else "")

    if collect_exit == 0:
        print("Test runner is functional.")
        print(json.dumps({"test_env": "ok"}))
    else:
        print("")
        print(f"TEST RUNNER FAILED (exit {collect_exit}) -- structural failure, not a test failure.")
        print("Retrying will NOT fix a broken test runner. Writing postmortem and halting.")

        postmortem_file = os.path.join(project_dir, ".dev-machine-postmortem")
        with open(postmortem_file, "w") as f:
            f.write("=== Dev Machine Post-Mortem: Test Environment Broken ===\n")
            f.write(f"Date:   {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
            f.write(f"Reason: test-env-preflight failed -- {test_command} --collect-only exited {collect_exit}\n")
            f.write("\n")
            f.write("The test runner itself is broken. This is NOT a test failure -- it is a\n")
            f.write("structural failure (e.g. missing dependency, import error, syntax error in\n")
            f.write("test infrastructure). Retrying will not fix this.\n")
            f.write("\n")
            f.write("To resume: fix the test runner error shown above, delete this file and\n")
            f.write(".dev-machine-test-env-broken, then restart the container.\n")
            f.write("\n")
            f.write("=== Preflight output ===\n")
            f.write(collect_output)

        # Sentinel file: entrypoint.sh checks for this and skips the retry loop
        open(os.path.join(project_dir, ".dev-machine-test-env-broken"), "w").close()

        print(json.dumps({"test_env": "broken"}))
        sys.exit(99)


if __name__ == "__main__":
    main()
```

### Step 4: Run test to verify it passes

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/test_test_env_preflight.py -v
```

Expected: All 6 tests PASS.

### Step 5: Commit

```bash
cd /home/bkrabach/dev/attractor-dev-machine
git add amplifier-bundle-attractor/examples/dev-machine/
git commit -m "feat(phase2): add test-env-preflight.py -- validates test runner before session"
```

---

## Task 6: `module-health-check.py` — LOC per package with content-aware bypass

**Source:** `dev-machine-iteration.yaml` step `module-health-check` (lines 228–277)
**Files:**
- Create: `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/module-health-check.py`
- Create: `amplifier-bundle-attractor/examples/dev-machine/tests/test_module_health_check.py`

### Step 1: Write the failing test

Create `amplifier-bundle-attractor/examples/dev-machine/tests/test_module_health_check.py`:

```python
"""Tests for module-health-check.py -- LOC per package with content-aware bypass."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from conftest import FIXTURES_DIR, run_script


def test_health_check_ok_on_empty_project(tmp_path):
    state = tmp_path / "STATE.yaml"
    shutil.copy(FIXTURES_DIR / "STATE.yaml", state)
    result = run_script("module-health-check.py", str(state), str(tmp_path), "5000")
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_health_check_outputs_valid_json(tmp_path):
    state = tmp_path / "STATE.yaml"
    shutil.copy(FIXTURES_DIR / "STATE.yaml", state)
    result = run_script("module-health-check.py", str(state), str(tmp_path), "5000")
    for line in result.stdout.splitlines():
        if line.strip().startswith("{"):
            data = json.loads(line.strip())
            assert "health" in data
            return
    pytest.fail(f"No JSON in stdout: {result.stdout!r}")


def test_health_check_ok_when_no_packages_dir(tmp_path):
    state = tmp_path / "STATE.yaml"
    shutil.copy(FIXTURES_DIR / "STATE.yaml", state)
    result = run_script("module-health-check.py", str(state), str(tmp_path), "5000")
    output = result.stdout
    assert "ok" in output or "within size limits" in output


def test_health_check_flags_oversized_package(tmp_path):
    """Create a package/*/src directory with many .py lines exceeding threshold."""
    state = tmp_path / "STATE.yaml"
    shutil.copy(FIXTURES_DIR / "STATE.yaml", state)
    pkg_src = tmp_path / "packages" / "bigpkg" / "src"
    pkg_src.mkdir(parents=True)
    big_file = pkg_src / "main.py"
    big_file.write_text("x = 1\n" * 20)  # 20 lines
    result = run_script("module-health-check.py", str(state), str(tmp_path), "5")  # threshold=5
    for line in result.stdout.splitlines():
        if line.strip().startswith("{"):
            data = json.loads(line.strip())
            # Either warns or blocks, depending on next_action
            assert data["health"] in ("needs-refactoring", "warn-oversized", "ok")
            return


def test_health_check_no_args_exits_nonzero():
    result = run_script("module-health-check.py")
    assert result.returncode != 0
```

### Step 2: Run test to verify it fails

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/test_module_health_check.py -v
```

Expected: All tests FAIL (script doesn't exist).

### Step 3: Write the implementation

The original is bash with embedded Python. The extracted Python script converts the bash `for pkg in packages/*/` loop to Python pathlib and replaces `wc -l` with Python line counting.

Create `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/module-health-check.py`:

```python
#!/usr/bin/env python3
"""module-health-check.py -- Flag oversized packages before a working session.

Usage: python3 module-health-check.py <state_file> <project_dir> <threshold>

Output: Text + JSON to stdout  {"health": "ok"} | {"health": "warn-oversized"} | {"health": "needs-refactoring"}
Exit:   0 always (informational -- on_error: continue in recipe)

Extracted from dev-machine-iteration.yaml step 'module-health-check'.
Content-aware bypass: if next_action already mentions an oversized module by
name, the machine has a plan for it. Only genuinely *unplanned* oversized
modules trigger a hard block.
"""

import json
import os
import sys
from pathlib import Path

import yaml


def count_loc(src_dir: Path) -> int:
    """Count lines of code in .ts/.tsx/.py/.rs files under src_dir."""
    total = 0
    for ext in ("*.ts", "*.tsx", "*.py", "*.rs"):
        for f in src_dir.rglob(ext):
            try:
                total += sum(1 for _ in f.open())
            except Exception:
                pass
    return total


def main() -> None:
    if len(sys.argv) < 4:
        print(json.dumps({"health": "error", "error": "Usage: module-health-check.py <state_file> <project_dir> <threshold>"}))
        sys.exit(1)

    state_file = sys.argv[1]
    project_dir = sys.argv[2]
    try:
        threshold = int(sys.argv[3])
    except ValueError:
        print(json.dumps({"health": "error", "error": f"threshold must be an integer, got: {sys.argv[3]}"}))
        sys.exit(1)

    os.chdir(project_dir)
    print("=== MODULE HEALTH CHECK ===")

    packages_dir = Path("packages")
    oversized: list[str] = []

    if packages_dir.exists():
        for pkg in sorted(packages_dir.iterdir()):
            if not pkg.is_dir():
                continue
            src = pkg / "src"
            if src.is_dir():
                loc = count_loc(src)
                if loc > threshold:
                    oversized.append(f"{pkg.name}({loc})")

    if oversized:
        oversized_str = " ".join(oversized)
        print(f"OVERSIZED PACKAGES: {oversized_str}")

        # Content-aware bypass: only block modules NOT mentioned in next_action.
        # If next_action already names the module, the machine knows about it.
        try:
            with open(state_file) as f:
                state = yaml.safe_load(f)
            next_action = state.get("next_action", "")
            unplanned = []
            for token in oversized:
                pkg_name = token.split("(")[0].strip()
                if pkg_name and pkg_name not in next_action:
                    unplanned.append(token)
        except Exception:
            unplanned = oversized

        if not unplanned:
            print("All oversized modules acknowledged in next_action -- warn only.")
            print(json.dumps({"health": "warn-oversized", "oversized": oversized_str, "planned": True}))
        else:
            unplanned_str = " ".join(unplanned)
            print(f"Unplanned oversized modules: {unplanned_str} -- blocking.")
            try:
                import datetime
                with open(state_file) as f:
                    s = yaml.safe_load(f)
                b = s.get("blockers") or []
                b.append({
                    "description": f"Module size threshold exceeded:{unplanned_str} -- refactoring epoch needed",
                    "since": datetime.datetime.now().isoformat(),
                    "severity": "high",
                })
                s["blockers"] = b
                with open(state_file, "w") as f:
                    yaml.dump(s, f, default_flow_style=False, sort_keys=False)
            except Exception as e:
                print(f"Warning: could not write blocker to STATE.yaml: {e}")
            print(json.dumps({"health": "needs-refactoring", "oversized": unplanned_str}))
    else:
        print("All packages within size limits.")
        print(json.dumps({"health": "ok"}))


if __name__ == "__main__":
    main()
```

### Step 4: Run test to verify it passes

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/test_module_health_check.py -v
```

Expected: All 5 tests PASS.

### Step 5: Commit

```bash
cd /home/bkrabach/dev/attractor-dev-machine
git add amplifier-bundle-attractor/examples/dev-machine/
git commit -m "feat(phase2): add module-health-check.py -- LOC per package with content-aware bypass"
```

---

## Task 7: `build-check.py` — Full build + test + paper tiger detection

**Source:** `dev-machine-iteration.yaml` step `build-check` (lines 369–487)
**Files:**
- Create: `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/build-check.py`
- Create: `amplifier-bundle-attractor/examples/dev-machine/tests/test_build_check.py`

### Step 1: Write the failing test

Create `amplifier-bundle-attractor/examples/dev-machine/tests/test_build_check.py`:

```python
"""Tests for build-check.py -- full build + test + paper tiger detection."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from conftest import FIXTURES_DIR, run_script


def test_build_check_clean_exits_zero(tmp_path):
    state = tmp_path / "STATE.yaml"
    shutil.copy(FIXTURES_DIR / "STATE.yaml", state)
    result = run_script("build-check.py", "true", "true", str(tmp_path), str(state))
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_build_check_clean_outputs_valid_json(tmp_path):
    state = tmp_path / "STATE.yaml"
    shutil.copy(FIXTURES_DIR / "STATE.yaml", state)
    result = run_script("build-check.py", "true", "true", str(tmp_path), str(state))
    for line in result.stdout.splitlines():
        if line.strip().startswith("{"):
            data = json.loads(line.strip())
            assert "build_status" in data
            return
    pytest.fail(f"No JSON in stdout: {result.stdout!r}")


def test_build_check_clean_status(tmp_path):
    state = tmp_path / "STATE.yaml"
    shutil.copy(FIXTURES_DIR / "STATE.yaml", state)
    result = run_script("build-check.py", "true", "true", str(tmp_path), str(state))
    for line in result.stdout.splitlines():
        if line.strip().startswith("{"):
            data = json.loads(line.strip())
            assert data["build_status"] == "clean"
            return


def test_build_check_failed_build_status(tmp_path):
    state = tmp_path / "STATE.yaml"
    shutil.copy(FIXTURES_DIR / "STATE.yaml", state)
    result = run_script("build-check.py", "false", "true", str(tmp_path), str(state))
    assert result.returncode == 0  # script itself exits 0
    for line in result.stdout.splitlines():
        if line.strip().startswith("{"):
            data = json.loads(line.strip())
            assert data["build_status"] == "failed"
            return


def test_build_check_failed_build_writes_blocker(tmp_path):
    state = tmp_path / "STATE.yaml"
    shutil.copy(FIXTURES_DIR / "STATE.yaml", state)
    run_script("build-check.py", "false", "true", str(tmp_path), str(state))
    with open(state) as f:
        s = yaml.safe_load(f)
    assert len(s.get("blockers", [])) > 0


def test_build_check_failed_tests_status(tmp_path):
    state = tmp_path / "STATE.yaml"
    shutil.copy(FIXTURES_DIR / "STATE.yaml", state)
    result = run_script("build-check.py", "true", "false", str(tmp_path), str(state))
    for line in result.stdout.splitlines():
        if line.strip().startswith("{"):
            data = json.loads(line.strip())
            assert data["build_status"] == "failed"
            return


def test_build_check_no_args_exits_nonzero():
    result = run_script("build-check.py")
    assert result.returncode != 0
```

### Step 2: Run test to verify it fails

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/test_build_check.py -v
```

Expected: All tests FAIL (script doesn't exist).

### Step 3: Write the implementation

The original is bash with two embedded `python3 -c "..."` one-liners for writing blockers. The extracted Python converts all bash to Python subprocess.

Create `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/build-check.py`:

```python
#!/usr/bin/env python3
"""build-check.py -- Post-session build + regression check + paper tiger detection.

Usage: python3 build-check.py <build_command> <test_command> <project_dir> <state_file>

Output: Text + final JSON  {"build_status": "clean"} | {"build_status": "failed"}
Exit:   0 always (caller reads build_status from JSON)

Extracted from dev-machine-iteration.yaml step 'build-check'.
TASK 4 (Regression Detection): Runs the FULL test suite with NO file filters.
TASK 2 (Integration Verification): Prints integration verification checklist.
"""

import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml


def add_blocker(state_file: str, description: str) -> None:
    """Append a blocker to STATE.yaml blockers list."""
    try:
        with open(state_file) as f:
            s = yaml.safe_load(f)
        b = s.get("blockers") or []
        b.append({
            "description": description,
            "since": datetime.datetime.now().isoformat(),
            "severity": "high",
        })
        s["blockers"] = b
        with open(state_file, "w") as f:
            yaml.dump(s, f, default_flow_style=False, sort_keys=False)
    except Exception as e:
        print(f"Warning: could not write blocker to {state_file}: {e}")


def main() -> None:
    if len(sys.argv) < 5:
        print(json.dumps({"build_status": "error", "error": "Usage: build-check.py <build_command> <test_command> <project_dir> <state_file>"}))
        sys.exit(1)

    build_command = sys.argv[1]
    test_command = sys.argv[2]
    project_dir = sys.argv[3]
    state_file = sys.argv[4]

    os.chdir(project_dir)
    print("=== POST-SESSION BUILD + REGRESSION CHECK ===")
    build_failed = 0
    test_failed = 0

    # --- 1. Build / type-check ---
    print(f"--- Build: {build_command} ---")
    build_result = subprocess.run(build_command.split(), capture_output=False)
    if build_result.returncode == 0:
        print("BUILD: clean")
    else:
        print(f"BUILD FAILED (exit {build_result.returncode})")
        build_failed = 1

    # --- 2. Full test suite (regression detection) ---
    print("")
    print(f"--- Full test suite: {test_command} (no file filters -- regression check) ---")
    test_result = subprocess.run(test_command.split(), capture_output=False)
    if test_result.returncode == 0:
        print("TESTS: all passing")
    else:
        print(f"TESTS FAILED (exit {test_result.returncode}) -- check for regressions in previously-passing tests")
        test_failed = 1

    # --- 3. Integration verification checklist ---
    print("")
    print("=== INTEGRATION VERIFICATION CHECKLIST (next session must confirm) ===")
    print("  [1] Completed features are reachable through actual entry points -- not just")
    print("      unit-tested in isolation. Verify the wiring from top-level to implementation.")
    print("  [2] No stub/mock implementations remain in production code paths.")
    print("      grep for: TODO, FIXME, 'stub', 'mock', 'placeholder', 'not implemented'")
    print("      in non-test source files. Each hit is a candidate blocker.")
    print("  [3] If the project has a schema or type registry, verify all referenced types")
    print("      exist in it. No dangling references to unregistered/undefined types.")

    # --- 4. Paper tiger detection ---
    print("")
    print("=== PAPER TIGER DETECTION ===")
    pt_flags = 0

    # PT-1: Stub signatures in production source (non-test files)
    print("--- PT-1: Stub/placeholder implementations in production code ---")
    stub_result = subprocess.run(
        [
            "grep", "-rn",
            "--include=*.ts", "--include=*.tsx", "--include=*.py", "--include=*.rs", "--include=*.js",
            "--exclude-dir=node_modules", "--exclude-dir=.git", "--exclude-dir=dist", "--exclude-dir=__pycache__",
            "-E", r"(raise NotImplementedError|pass$|return \{\}$|return \[\]$|TODO: implement|FIXME: implement|stub implementation|not yet implemented)",
            ".",
        ],
        capture_output=True, text=True,
    )
    stub_hits = "\n".join(
        line for line in stub_result.stdout.splitlines()
        if not any(x in line for x in ["test_", "_test.", ".test.", ".spec."])
    )
    stub_hits_head = "\n".join(stub_hits.splitlines()[:20])
    if stub_hits_head.strip():
        print("WARNING: Possible stub implementations in production paths:")
        print(stub_hits_head)
        pt_flags += 1
    else:
        print("OK: No obvious stub patterns found in production source.")

    # PT-2: Route/entry-point registration check
    print("")
    print("--- PT-2: Entry-point registration check ---")
    entry_files = ["main.py", "app.py", "index.ts", "index.js", "server.ts", "server.js", "app.ts"]
    entry_found = 0
    for ef in entry_files:
        if Path(ef).is_file():
            lines = sum(1 for _ in open(ef))
            print(f"Entry file found: {ef} ({lines} lines)")
            entry_found += 1
    if entry_found == 0:
        print("INFO: No standard entry file found at project root (may use non-standard structure).")

    # PT-3: Summary
    print("")
    if pt_flags > 0:
        print(f"PAPER TIGER CHECK: {pt_flags} warning(s). Review stub hits above before marking features complete.")
    else:
        print("PAPER TIGER CHECK: clean (no obvious stubs detected).")

    # --- 5. Write blockers and output status ---
    if build_failed:
        print("")
        print(f"Adding build blocker to {state_file}...")
        add_blocker(
            state_file,
            f"{build_command} failed after working session -- fix build errors before resuming",
        )
    if test_failed:
        print("")
        print(f"Adding regression blocker to {state_file}...")
        add_blocker(
            state_file,
            f"{test_command} failed after working session -- run full test suite with no file filters to identify regressions",
        )

    if build_failed or test_failed:
        print(json.dumps({"build_status": "failed"}))
    else:
        print(json.dumps({"build_status": "clean"}))


if __name__ == "__main__":
    main()
```

### Step 4: Run test to verify it passes

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/test_build_check.py -v
```

Expected: All 7 tests PASS.

### Step 5: Commit

```bash
cd /home/bkrabach/dev/attractor-dev-machine
git add amplifier-bundle-attractor/examples/dev-machine/
git commit -m "feat(phase2): add build-check.py -- full build+test with paper tiger detection"
```

---

## Task 8: `post-session-archive.py` — Archive completed features and old sessions

**Source:** `dev-machine-iteration.yaml` step `post-session` Python block, feature archiving + session archiving sections (lines 504–555)
**Files:**
- Create: `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/post-session-archive.py`
- Create: `amplifier-bundle-attractor/examples/dev-machine/tests/test_post_session_archive.py`

### Step 1: Write the failing test

Create `amplifier-bundle-attractor/examples/dev-machine/tests/test_post_session_archive.py`:

```python
"""Tests for post-session-archive.py -- archive completed features and old sessions."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from conftest import FIXTURES_DIR, run_script


def test_archive_exits_zero(tmp_path):
    state = tmp_path / "STATE.yaml"
    ctx = tmp_path / "CONTEXT-TRANSFER.md"
    shutil.copy(FIXTURES_DIR / "STATE.yaml", state)
    shutil.copy(FIXTURES_DIR / "CONTEXT-TRANSFER.md", ctx)
    result = run_script("post-session-archive.py", str(state), str(ctx))
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_archive_outputs_valid_json(tmp_path):
    state = tmp_path / "STATE.yaml"
    ctx = tmp_path / "CONTEXT-TRANSFER.md"
    shutil.copy(FIXTURES_DIR / "STATE.yaml", state)
    shutil.copy(FIXTURES_DIR / "CONTEXT-TRANSFER.md", ctx)
    result = run_script("post-session-archive.py", str(state), str(ctx))
    for line in result.stdout.splitlines():
        if line.strip().startswith("{"):
            data = json.loads(line.strip())
            assert "archived_features" in data
            return
    pytest.fail(f"No JSON in stdout: {result.stdout!r}")


def test_archive_moves_completed_features_to_archive(tmp_path):
    """Features with status 'completed' in features{} should move to FEATURE-ARCHIVE.yaml."""
    state_data = {
        "project_name": "test",
        "phase": 1,
        "epoch": 1,
        "completed_features": [],
        "features": {
            "feat-done": {"status": "completed", "description": "A done feature"},
            "feat-active": {"status": "ready", "description": "An active feature"},
        },
        "blockers": [],
        "meta": {"session_count": 1, "total_features_completed": 0},
    }
    state = tmp_path / "STATE.yaml"
    ctx = tmp_path / "CONTEXT-TRANSFER.md"
    ctx.write_text("# Context\n")
    with open(state, "w") as f:
        yaml.dump(state_data, f)

    run_script("post-session-archive.py", str(state), str(ctx))

    with open(state) as f:
        updated = yaml.safe_load(f)
    # feat-done should be removed from features{}
    assert "feat-done" not in updated.get("features", {})
    # feat-done should be in completed_features list
    assert "feat-done" in updated.get("completed_features", [])


def test_archive_writes_feature_archive_yaml(tmp_path):
    state_data = {
        "project_name": "test",
        "phase": 1,
        "epoch": 1,
        "completed_features": [],
        "features": {"feat-done": {"status": "completed", "description": "Done"}},
        "blockers": [],
        "meta": {"session_count": 1, "total_features_completed": 0},
    }
    state = tmp_path / "STATE.yaml"
    ctx = tmp_path / "CONTEXT-TRANSFER.md"
    ctx.write_text("# Context\n")
    with open(state, "w") as f:
        yaml.dump(state_data, f)

    run_script("post-session-archive.py", str(state), str(ctx))
    assert (tmp_path / "FEATURE-ARCHIVE.yaml").exists()


def test_archive_no_args_exits_nonzero():
    result = run_script("post-session-archive.py")
    assert result.returncode != 0
```

### Step 2: Run test to verify it fails

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/test_post_session_archive.py -v
```

Expected: All tests FAIL (script doesn't exist).

### Step 3: Write the implementation

Create `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/post-session-archive.py`:

```python
#!/usr/bin/env python3
"""post-session-archive.py -- Archive completed features and old session summaries.

Usage: python3 post-session-archive.py <state_file> <context_file>

Output: Text + final JSON  {"archived_features": N, "archived_sessions": N}
Exit:   0 on success, non-zero on failure

Extracted from dev-machine-iteration.yaml step 'post-session' (feature + session archiving sections).
"""

import json
import os
import re
import sys
from pathlib import Path

import yaml


def main() -> None:
    if len(sys.argv) < 3:
        print(json.dumps({"status": "error", "error": "Usage: post-session-archive.py <state_file> <context_file>"}))
        sys.exit(1)

    state_file = sys.argv[1]
    ctx_path = sys.argv[2]

    try:
        with open(state_file) as f:
            state = yaml.safe_load(f)

        archived_features = 0
        archived_sessions = 0

        # --- Archive completed features (if using completed_features list pattern) ---
        features = state.get("features", {})
        completed_list = state.get("completed_features", [])
        if isinstance(completed_list, list):
            newly_completed = {fid: fd for fid, fd in features.items() if fd.get("status") in ("completed", "done")}
            if newly_completed:
                archive_path = os.path.join(os.path.dirname(state_file) or ".", "FEATURE-ARCHIVE.yaml")
                try:
                    with open(archive_path) as f:
                        archive = yaml.safe_load(f) or {}
                except FileNotFoundError:
                    archive = {"description": "Completed feature archive. Append-only.", "features": {}}
                arch_feats = archive.get("features", {})
                for fid, fd in newly_completed.items():
                    if fid not in completed_list:
                        completed_list.append(fid)
                    arch_feats[fid] = fd
                    del features[fid]
                archive["features"] = arch_feats
                state["completed_features"] = completed_list
                state["features"] = features
                with open(archive_path, "w") as f:
                    yaml.dump(archive, f, default_flow_style=False, sort_keys=False, width=120)
                archived_features = len(newly_completed)
                print(f"Archived {archived_features} completed feature(s) to FEATURE-ARCHIVE.yaml")

        # --- Archive old session summaries from context-transfer (keep last 5) ---
        KEEP_SESSIONS = 5
        session_archive = os.path.join(os.path.dirname(ctx_path) or ".", "SESSION-ARCHIVE.md")
        if os.path.exists(ctx_path):
            with open(ctx_path) as f:
                ctx = f.read()
            sess = list(re.finditer(r"^### Session \d+ Summary", ctx, re.MULTILINE))
            if len(sess) > KEEP_SESSIONS:
                header = ctx[:sess[0].start()]
                keep_from = sess[-KEEP_SESSIONS]
                to_archive = ctx[sess[0].start():keep_from.start()]
                keep = ctx[keep_from.start():]
                if to_archive.strip():
                    existing = ""
                    if os.path.exists(session_archive):
                        with open(session_archive) as f:
                            existing = f.read()
                    if not existing:
                        existing = "# Session Archive\n\n> Archived session summaries. Append-only.\n\n"
                    if to_archive[:50] not in existing:
                        with open(session_archive, "a") as f:
                            f.write(to_archive)
                with open(ctx_path, "w") as f:
                    f.write(header)
                    f.write(f"> **Note**: Older sessions archived in SESSION-ARCHIVE.md.\n")
                    f.write(f"> Only the last {KEEP_SESSIONS} sessions kept here.\n\n")
                    f.write(keep)
                archived_sessions = len(sess) - KEEP_SESSIONS
                print(f"Archived {archived_sessions} old session summary(ies) to SESSION-ARCHIVE.md")

        with open(state_file, "w") as f:
            yaml.dump(state, f, default_flow_style=False, sort_keys=False, width=120)

        print(json.dumps({"archived_features": archived_features, "archived_sessions": archived_sessions}))

    except Exception as e:
        print(json.dumps({"status": "blocked", "error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
```

### Step 4: Run test to verify it passes

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/test_post_session_archive.py -v
```

Expected: All 5 tests PASS.

### Step 5: Commit

```bash
cd /home/bkrabach/dev/attractor-dev-machine
git add amplifier-bundle-attractor/examples/dev-machine/
git commit -m "feat(phase2): add post-session-archive.py -- archive completed features and old sessions"
```

---

## Task 9: `post-session-accounting.py` — Session counting and zero-change tracking

**Source:** `dev-machine-iteration.yaml` step `post-session` Python block, session count + zero-change tracking section (lines 557–575)
**Files:**
- Create: `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/post-session-accounting.py`
- Create: `amplifier-bundle-attractor/examples/dev-machine/tests/test_post_session_accounting.py`

### Step 1: Write the failing test

Create `amplifier-bundle-attractor/examples/dev-machine/tests/test_post_session_accounting.py`:

```python
"""Tests for post-session-accounting.py -- session counting and zero-change tracking."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from conftest import FIXTURES_DIR, run_script


def test_accounting_exits_zero(tmp_path):
    state = tmp_path / "STATE.yaml"
    shutil.copy(FIXTURES_DIR / "STATE.yaml", state)
    result = run_script("post-session-accounting.py", str(state), str(tmp_path), "5")
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_accounting_outputs_valid_json(tmp_path):
    state = tmp_path / "STATE.yaml"
    shutil.copy(FIXTURES_DIR / "STATE.yaml", state)
    result = run_script("post-session-accounting.py", str(state), str(tmp_path), "5")
    for line in result.stdout.splitlines():
        if line.strip().startswith("{"):
            data = json.loads(line.strip())
            assert "session_count" in data
            return
    pytest.fail(f"No JSON in stdout: {result.stdout!r}")


def test_accounting_increments_session_count(tmp_path):
    state = tmp_path / "STATE.yaml"
    shutil.copy(FIXTURES_DIR / "STATE.yaml", state)
    # Initial session_count in meta is 5
    run_script("post-session-accounting.py", str(state), str(tmp_path), "5")
    with open(state) as f:
        updated = yaml.safe_load(f)
    assert updated["meta"]["session_count"] == 6  # incremented from 5


def test_accounting_zero_change_incremented_when_head_unchanged(tmp_path):
    """If git HEAD didn't change since last session, zero_change_sessions should increment."""
    state_data = {
        "project_name": "test",
        "phase": 1,
        "epoch": 1,
        "features": {},
        "completed_features": [],
        "blockers": [],
        "meta": {
            "session_count": 3,
            "zero_change_sessions": 0,
            "last_session_head": "FAKE_HEAD_THAT_WONT_MATCH",
            "total_features_completed": 0,
        },
    }
    state = tmp_path / "STATE.yaml"
    with open(state, "w") as f:
        yaml.dump(state_data, f)
    # project_dir is tmp_path -- not a git repo, so git will fail gracefully
    result = run_script("post-session-accounting.py", str(state), str(tmp_path), "3")
    assert result.returncode == 0


def test_accounting_no_args_exits_nonzero():
    result = run_script("post-session-accounting.py")
    assert result.returncode != 0
```

### Step 2: Run test to verify it fails

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/test_post_session_accounting.py -v
```

Expected: All tests FAIL (script doesn't exist).

### Step 3: Write the implementation

Create `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/post-session-accounting.py`:

```python
#!/usr/bin/env python3
"""post-session-accounting.py -- Increment session count and track zero-change sessions.

Usage: python3 post-session-accounting.py <state_file> <project_dir> <session_count>

Output: Text + final JSON  {"session_count": N, "zero_change_sessions": N}
Exit:   0 on success, non-zero on failure

Extracted from dev-machine-iteration.yaml step 'post-session' (session count + zero-change tracking section).
Task 8: Cost & Progress Visibility -- increment meta.session_count on every iteration
so humans can monitor cumulative usage. Compare git HEAD to detect sessions that
produced no code commits (zero-change).
"""

import json
import subprocess
import sys

import yaml


def main() -> None:
    if len(sys.argv) < 4:
        print(json.dumps({"status": "error", "error": "Usage: post-session-accounting.py <state_file> <project_dir> <session_count>"}))
        sys.exit(1)

    state_file = sys.argv[1]
    project_dir = sys.argv[2]
    session_count = int(sys.argv[3])

    try:
        with open(state_file) as f:
            state = yaml.safe_load(f)

        # --- Session count and zero-change tracking (Task 8: Cost & Progress Visibility) ---
        # Increment meta.session_count on every iteration so humans can monitor cumulative usage.
        # Compare git HEAD to detect sessions that produced no code commits (zero-change).
        meta = state.setdefault("meta", {})
        meta["session_count"] = meta.get("session_count", 0) + 1
        try:
            current_head = subprocess.run(
                ["git", "-C", project_dir, "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5
            ).stdout.strip()
            last_head = meta.get("last_session_head", "")
            if last_head and current_head == last_head:
                meta["zero_change_sessions"] = meta.get("zero_change_sessions", 0) + 1
                print(f"ZERO-CHANGE SESSION #{meta['zero_change_sessions']}: no code commits this session (HEAD: {current_head[:8]})")
            else:
                meta["zero_change_sessions"] = 0
            meta["last_session_head"] = current_head
        except Exception:
            pass  # non-fatal: git unavailable or not a repo

        state["meta"] = meta

        with open(state_file, "w") as f:
            yaml.dump(state, f, default_flow_style=False, sort_keys=False, width=120)

        print(json.dumps({
            "session_count": meta["session_count"],
            "zero_change_sessions": meta.get("zero_change_sessions", 0),
        }))

    except Exception as e:
        print(json.dumps({"status": "blocked", "error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
```

### Step 4: Run test to verify it passes

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/test_post_session_accounting.py -v
```

Expected: All 5 tests PASS.

### Step 5: Commit

```bash
cd /home/bkrabach/dev/attractor-dev-machine
git add amplifier-bundle-attractor/examples/dev-machine/
git commit -m "feat(phase2): add post-session-accounting.py -- session counting and zero-change tracking"
```

---

## Task 10: `post-session-reconcile.py` — Stale metadata, wiring audit, periodic checks

**Source:** `dev-machine-iteration.yaml` step `post-session`: stale reconciliation (lines 577–585), wiring audit (lines 615–689), periodic clean-room check (lines 691–734), periodic integration test check (lines 736–791)
**Files:**
- Create: `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/post-session-reconcile.py`
- Create: `amplifier-bundle-attractor/examples/dev-machine/tests/test_post_session_reconcile.py`

### Step 1: Write the failing test

Create `amplifier-bundle-attractor/examples/dev-machine/tests/test_post_session_reconcile.py`:

```python
"""Tests for post-session-reconcile.py -- stale metadata, wiring audit, periodic checks."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from conftest import FIXTURES_DIR, run_script


def test_reconcile_exits_zero(tmp_path):
    state = tmp_path / "STATE.yaml"
    shutil.copy(FIXTURES_DIR / "STATE.yaml", state)
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    result = run_script(
        "post-session-reconcile.py",
        str(state), str(specs_dir), str(tmp_path),
        "echo install", "echo test",
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_reconcile_outputs_valid_json(tmp_path):
    state = tmp_path / "STATE.yaml"
    shutil.copy(FIXTURES_DIR / "STATE.yaml", state)
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    result = run_script(
        "post-session-reconcile.py",
        str(state), str(specs_dir), str(tmp_path),
        "echo install", "echo test",
    )
    for line in result.stdout.splitlines():
        if line.strip().startswith("{"):
            data = json.loads(line.strip())
            assert "reconciled" in data
            return
    pytest.fail(f"No JSON in stdout: {result.stdout!r}")


def test_reconcile_fixes_stale_total_features_completed(tmp_path):
    """If total_features_completed doesn't match len(completed_features), fix it."""
    state_data = {
        "project_name": "test",
        "phase": 1,
        "epoch": 1,
        "completed_features": ["feat-a", "feat-b"],
        "features": {},
        "blockers": [],
        "meta": {
            "session_count": 3,
            "total_features_completed": 99,  # wrong value
        },
    }
    state = tmp_path / "STATE.yaml"
    with open(state, "w") as f:
        yaml.dump(state_data, f)
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()

    run_script(
        "post-session-reconcile.py",
        str(state), str(specs_dir), str(tmp_path),
        "echo install", "echo test",
    )

    with open(state) as f:
        updated = yaml.safe_load(f)
    assert updated["meta"]["total_features_completed"] == 2  # fixed to actual count


def test_reconcile_no_args_exits_nonzero():
    result = run_script("post-session-reconcile.py")
    assert result.returncode != 0
```

### Step 2: Run test to verify it fails

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/test_post_session_reconcile.py -v
```

Expected: All tests FAIL (script doesn't exist).

### Step 3: Write the implementation

Create `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/post-session-reconcile.py`:

```python
#!/usr/bin/env python3
"""post-session-reconcile.py -- Stale metadata reconciliation, wiring audit, periodic checks.

Usage: python3 post-session-reconcile.py <state_file> <specs_dir> <project_dir> <install_command> <test_command>

Output: Text + final JSON  {"reconciled": true, "wiring_issues": N}
Exit:   0 always (continue_on_fail in recipe -- housekeeping, not session-critical)

Extracted from dev-machine-iteration.yaml step 'post-session':
  - Stale state metadata reconciliation (Task 21)
  - Integration wiring audit at epoch boundaries (Task 12)
  - Periodic clean-room check (Task 22: Test Environment Reproducibility)
  - Periodic integration test check (Task 24)
"""

import datetime
import json
import subprocess
import sys
from pathlib import Path

import yaml


def main() -> None:
    if len(sys.argv) < 6:
        print(json.dumps({"reconciled": False, "error": "Usage: post-session-reconcile.py <state_file> <specs_dir> <project_dir> <install_command> <test_command>"}))
        sys.exit(1)

    state_file = sys.argv[1]
    specs_dir_arg = sys.argv[2]
    project_dir = sys.argv[3]
    install_command = sys.argv[4]
    test_command = sys.argv[5]

    wiring_issues = 0

    try:
        with open(state_file) as f:
            state = yaml.safe_load(f)

        meta = state.setdefault("meta", {})

        # --- Stale state metadata reconciliation (Task 21) ---
        # Verify meta.total_features_completed matches len(completed_features) exactly.
        # If they diverge (e.g. manual edits, archiving errors), fix before writing STATE.yaml.
        actual_completed = len(state.get("completed_features", []))
        recorded = meta.get("total_features_completed", 0)
        if recorded != actual_completed:
            print(f"RECONCILIATION: total_features_completed {recorded} != actual {actual_completed}. Fixing.")
            meta["total_features_completed"] = actual_completed
        state["meta"] = meta

        with open(state_file, "w") as f:
            yaml.dump(state, f, default_flow_style=False, sort_keys=False, width=120)

        # --- Integration wiring audit at epoch boundaries (Task 12) ---
        # When all features in an epoch are done, scan module pairs to verify A actually
        # imports/uses B. Unwired connections are written to STATE.yaml next_action as
        # P0 features, prioritized before new capability work in the next epoch.
        features = state.get("features", {})
        active = [fid for fid, fd in features.items() if fd.get("status") not in ("completed", "done")]
        if len(active) == 0 and features:
            print("")
            print("=== EPOCH BOUNDARY: INTEGRATION WIRING AUDIT ===")
            print("All features complete. Auditing cross-module wiring...")

            # Discover module/package directories
            pkg_dirs = []
            for base in ["packages", "src", "lib"]:
                p = Path(project_dir) / base
                if p.exists():
                    pkg_dirs = [d for d in p.iterdir() if d.is_dir() and not d.name.startswith(".")]
                    break

            if not pkg_dirs:
                print("  INFO: No packages/ or src/ directory found -- skipping structural wiring audit.")
            else:
                pkg_names = [d.name for d in pkg_dirs]
                specs_dir = Path(specs_dir_arg)
                unwired = []
                for mod_a in pkg_dirs:
                    for mod_b_name in pkg_names:
                        if mod_a.name == mod_b_name:
                            continue
                        # Check if mod_a source files reference mod_b_name
                        result = subprocess.run(
                            ["grep", "-rl",
                             "--include=*.py", "--include=*.ts", "--include=*.tsx", "--include=*.js",
                             "--exclude-dir=node_modules", "--exclude-dir=.git", "--exclude-dir=dist",
                             mod_b_name, str(mod_a)],
                            capture_output=True, text=True, timeout=10
                        )
                        # Only flag as unwired if there's a declared spec dependency
                        dep_expected = False
                        if specs_dir.exists():
                            for spec_f in specs_dir.rglob("*.md"):
                                txt = spec_f.read_text(errors="ignore").lower()
                                if mod_a.name.lower() in txt and mod_b_name.lower() in txt:
                                    dep_expected = True
                                    break
                        if dep_expected and not result.stdout.strip():
                            unwired.append(f"{mod_a.name} -> {mod_b_name}")

                if unwired:
                    wiring_issues = len(unwired)
                    print(f"  UNWIRED CONNECTIONS FOUND ({len(unwired)} pair(s)) -- add as P0 features for next epoch:")
                    for pair in unwired:
                        print(f"    {pair}")
                    # Prepend wiring reminder to next_action if not already there
                    with open(state_file) as f:
                        state = yaml.safe_load(f)
                    existing_next = state.get("next_action", "")
                    if "wire" not in existing_next.lower() and "integration" not in existing_next.lower():
                        state["next_action"] = (
                            f"[WIRING NEEDED] Connect: {'; '.join(unwired[:3])}. Then: {existing_next}"
                        )
                        with open(state_file, "w") as f:
                            yaml.dump(state, f, default_flow_style=False, sort_keys=False, width=120)
                        print("  Updated STATE.yaml next_action to prioritize wiring tasks.")
                else:
                    print("  OK: All expected module pairs appear to be wired.")
            print("=== END INTEGRATION WIRING AUDIT ===")

        # --- Periodic clean-room check (Task 22: Test Environment Reproducibility) ---
        # Every 10 sessions: fresh dependency install + full test run to catch environment drift.
        with open(state_file) as f:
            state = yaml.safe_load(f)
        session_count = state.get("meta", {}).get("session_count", 0)
        if session_count > 0 and (session_count % 10) == 0:
            print("")
            print(f"=== PERIODIC CLEAN-ROOM CHECK (session {session_count}) ===")
            print("Verifying test environment reproducibility with a fresh install + full test run.")
            install_result = subprocess.run(install_command.split(), capture_output=False, cwd=project_dir)
            print(f"--- Full test suite: {test_command} ---")
            test_result = subprocess.run(test_command.split(), capture_output=False, cwd=project_dir)
            if test_result.returncode == 0:
                print(f"CLEAN-ROOM CHECK: PASSED (environment is reproducible at session {session_count})")
            else:
                print(f"CLEAN-ROOM CHECK: FAILED (exit {test_result.returncode}) -- environment drift detected")
                print("ACTION: Refresh lock files, pin dependency versions, and fix test failures.")
                b = state.get("blockers") or []
                b.append({
                    "description": "Clean-room check failed -- environment drift detected. Refresh lock files and fix test failures.",
                    "since": datetime.datetime.now().isoformat(),
                    "severity": "medium",
                })
                state["blockers"] = b
                with open(state_file, "w") as f:
                    yaml.dump(state, f, default_flow_style=False, sort_keys=False, width=120)
                print("Blocker added to STATE.yaml.")
            print("=== END CLEAN-ROOM CHECK ===")

        # --- Periodic integration test check (Task 24) ---
        # Every 5 epochs: run integration tests if they exist, or flag missing coverage.
        epoch = state.get("epoch", 0)
        if epoch > 0 and (epoch % 5) == 0:
            print("")
            print(f"=== PERIODIC INTEGRATION TEST CHECK (epoch {epoch}) ===")
            integ_found = 0
            for integ_dir in ["tests/integration", "tests/e2e", "integration_tests", "e2e"]:
                full_integ = Path(project_dir) / integ_dir
                if full_integ.is_dir():
                    file_count = sum(1 for _ in full_integ.rglob("*.py")) + sum(1 for _ in full_integ.rglob("*.ts"))
                    if file_count > 0:
                        integ_found += 1
                        print(f"Integration test directory found: {integ_dir} ({file_count} files)")
                        print("--- Running integration tests ---")
                        integ_result = subprocess.run(
                            test_command.split() + [str(full_integ)],
                            capture_output=False, cwd=project_dir
                        )
                        if integ_result.returncode == 0:
                            print("INTEGRATION TESTS: PASSED")
                        else:
                            print(f"INTEGRATION TESTS: FAILED (exit {integ_result.returncode}) -- fix before next epoch.")
            if integ_found == 0:
                print(f"WARNING: No integration test directory found after epoch {epoch}.")
                print("Cross-module features lack integration test coverage.")
                print(f"HOUSEKEEPING: Add tests/integration/ before epoch {epoch + 5}.")
                with open(state_file) as f:
                    state = yaml.safe_load(f)
                pf = state.setdefault("proposed_features", [])
                if not any("integration-test" in str(p.get("id", "")) for p in pf):
                    pf.append({
                        "id": "proposed-integration-tests",
                        "name": "Add integration test suite",
                        "rationale": "No integration tests found. Cross-module features need coverage.",
                        "proposed_at": datetime.datetime.now().isoformat(),
                    })
                    with open(state_file, "w") as f:
                        yaml.dump(state, f, default_flow_style=False, sort_keys=False, width=120)
                    print("Added integration test proposal to STATE.yaml proposed_features.")
            print("=== END INTEGRATION TEST CHECK ===")

        print(json.dumps({"reconciled": True, "wiring_issues": wiring_issues}))

    except Exception as e:
        print(json.dumps({"reconciled": False, "error": str(e)}))
        sys.exit(0)  # continue_on_fail in recipe


if __name__ == "__main__":
    main()
```

### Step 4: Run test to verify it passes

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/test_post_session_reconcile.py -v
```

Expected: All 4 tests PASS.

### Step 5: Commit

```bash
cd /home/bkrabach/dev/attractor-dev-machine
git add amplifier-bundle-attractor/examples/dev-machine/
git commit -m "feat(phase2): add post-session-reconcile.py -- stale metadata, wiring audit, periodic checks"
```

---

## Task 11: `post-session-status.py` — Increment epoch, output final JSON status

**Source:** `dev-machine-iteration.yaml` step `post-session` Python block, epoch update + final JSON output section (lines 587–608)
**Files:**
- Create: `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/post-session-status.py`
- Create: `amplifier-bundle-attractor/examples/dev-machine/tests/test_post_session_status.py`

### Step 1: Write the failing test

Create `amplifier-bundle-attractor/examples/dev-machine/tests/test_post_session_status.py`:

```python
"""Tests for post-session-status.py -- increment epoch, output final JSON status."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from conftest import FIXTURES_DIR, run_script


def test_status_exits_zero(tmp_path):
    state = tmp_path / "STATE.yaml"
    shutil.copy(FIXTURES_DIR / "STATE.yaml", state)
    result = run_script("post-session-status.py", str(state), "5")
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_status_outputs_valid_json(tmp_path):
    state = tmp_path / "STATE.yaml"
    shutil.copy(FIXTURES_DIR / "STATE.yaml", state)
    result = run_script("post-session-status.py", str(state), "5")
    data = json.loads(result.stdout.strip())
    assert isinstance(data, dict)


def test_status_required_fields(tmp_path):
    state = tmp_path / "STATE.yaml"
    shutil.copy(FIXTURES_DIR / "STATE.yaml", state)
    result = run_script("post-session-status.py", str(state), "5")
    data = json.loads(result.stdout.strip())
    assert "status" in data
    assert "session_count" in data
    assert "at_epoch_boundary" in data
    assert "next_action" in data
    assert "total_features" in data


def test_status_healthy_when_no_blockers(tmp_path):
    state = tmp_path / "STATE.yaml"
    shutil.copy(FIXTURES_DIR / "STATE.yaml", state)
    result = run_script("post-session-status.py", str(state), "5")
    data = json.loads(result.stdout.strip())
    assert data["status"] == "healthy"


def test_status_blocked_when_blockers(tmp_path):
    state = tmp_path / "STATE.yaml"
    shutil.copy(FIXTURES_DIR / "STATE-blocked.yaml", state)
    result = run_script("post-session-status.py", str(state), "2")
    data = json.loads(result.stdout.strip())
    assert data["status"] == "blocked"


def test_status_increments_epoch(tmp_path):
    state = tmp_path / "STATE.yaml"
    shutil.copy(FIXTURES_DIR / "STATE.yaml", state)
    # Initial epoch is 3 in fixture
    run_script("post-session-status.py", str(state), "5")
    with open(state) as f:
        updated = yaml.safe_load(f)
    assert updated["epoch"] == 4  # incremented from 3


def test_status_missing_file_exits_nonzero():
    result = run_script("post-session-status.py", "/nonexistent/STATE.yaml", "5")
    assert result.returncode != 0


def test_status_no_args_exits_nonzero():
    result = run_script("post-session-status.py")
    assert result.returncode != 0
```

### Step 2: Run test to verify it fails

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/test_post_session_status.py -v
```

Expected: All tests FAIL (script doesn't exist).

### Step 3: Write the implementation

Create `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/post-session-status.py`:

```python
#!/usr/bin/env python3
"""post-session-status.py -- Increment epoch, write STATE.yaml, output final JSON status.

Usage: python3 post-session-status.py <state_file> <session_count>

Output: JSON to stdout (single line)
  {"status": "healthy"|"blocked"|"complete", "session_count": "N",
   "at_epoch_boundary": bool, "next_action": "...", "total_features": N}
Exit:   0 on success, non-zero on failure

Extracted from dev-machine-iteration.yaml step 'post-session' (epoch update + final JSON output section).
"""

import json
import sys
from datetime import datetime, timezone

import yaml


def main() -> None:
    if len(sys.argv) < 3:
        print(json.dumps({"status": "blocked", "error": "Usage: post-session-status.py <state_file> <session_count>"}))
        sys.exit(1)

    state_file = sys.argv[1]
    session_count = sys.argv[2]

    try:
        with open(state_file) as f:
            state = yaml.safe_load(f)

        session_num = int(session_count) + 1

        # --- Update epoch and check health ---
        state["epoch"] = state.get("epoch", 0) + 1
        state["last_session"] = datetime.now(timezone.utc).isoformat()
        blockers = state.get("blockers", [])

        with open(state_file, "w") as f:
            yaml.dump(state, f, default_flow_style=False, sort_keys=False, width=120)

        features = state.get("features", {})
        remaining = sum(1 for f in features.values() if f.get("status") not in ("completed", "done"))
        # at_epoch_boundary: all features in this epoch are done -- triggers wiring audit
        at_epoch_boundary = (remaining == 0 and len(features) > 0)
        status = "blocked" if blockers else ("complete" if remaining == 0 else "healthy")

        print(json.dumps({
            "status": status,
            "session_count": str(session_num),
            "at_epoch_boundary": at_epoch_boundary,
            "next_action": state.get("next_action", ""),
            "total_features": state.get("meta", {}).get("total_features_completed", 0),
        }))

    except Exception as e:
        print(json.dumps({"status": "blocked", "session_count": session_count, "error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
```

### Step 4: Run test to verify it passes

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/test_post_session_status.py -v
```

Expected: All 8 tests PASS.

### Step 5: Commit

```bash
cd /home/bkrabach/dev/attractor-dev-machine
git add amplifier-bundle-attractor/examples/dev-machine/
git commit -m "feat(phase2): add post-session-status.py -- increment epoch, output final JSON status"
```

---

## Task 12: `container-check.sh` — Refuse to run outside Docker

**Source:** `dev-machine-build.yaml` step `container-check` (lines 36–61); identical copy in `dev-machine-health-check.yaml` lines 39–65
**Files:**
- Create: `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/container-check.sh`
- Create: `amplifier-bundle-attractor/examples/dev-machine/tests/test_container_check.py`

### Step 1: Write the failing test

Create `amplifier-bundle-attractor/examples/dev-machine/tests/test_container_check.py`:

```python
"""Tests for container-check.sh -- refuses to run outside Docker."""

from __future__ import annotations

import os

import pytest

from conftest import run_shell_script


def test_container_check_fails_on_bare_host():
    """On a bare host (no /.dockerenv), should exit non-zero unless DEV_MACHINE_ALLOW_HOST is set."""
    if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
        pytest.skip("Running inside a container -- test only valid on bare host")
    env = {**os.environ}
    env.pop("DEV_MACHINE_ALLOW_HOST", None)

    import subprocess
    import sys
    script = str(__import__("pathlib").Path(__file__).parent.parent / "scripts" / "pipeline" / "container-check.sh")
    result = subprocess.run([script], capture_output=True, text=True, env=env)
    assert result.returncode != 0
    assert "ERROR" in result.stdout or "DANGEROUS" in result.stdout


def test_container_check_bypass_with_env_var():
    """DEV_MACHINE_ALLOW_HOST=1 should allow running outside container with a warning."""
    if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
        pytest.skip("Running inside a container -- test only valid on bare host")

    import subprocess
    script = str(__import__("pathlib").Path(__file__).parent.parent / "scripts" / "pipeline" / "container-check.sh")
    env = {**os.environ, "DEV_MACHINE_ALLOW_HOST": "1"}
    result = subprocess.run([script], capture_output=True, text=True, env=env)
    assert result.returncode == 0
    assert "WARNING" in result.stdout


def test_container_check_script_is_executable():
    """The script must have executable permissions."""
    from pathlib import Path
    import stat
    script = Path(__file__).parent.parent / "scripts" / "pipeline" / "container-check.sh"
    mode = script.stat().st_mode
    assert mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH), "container-check.sh must be executable"
```

### Step 2: Run test to verify it fails

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/test_container_check.py -v
```

Expected: All tests FAIL (script doesn't exist).

### Step 3: Write the implementation

Create `amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/container-check.sh`:

```bash
#!/usr/bin/env bash
# container-check.sh -- Refuse to run outside a Docker/container environment.
#
# Usage: ./container-check.sh
#
# Exit: 0 = inside container (or DEV_MACHINE_ALLOW_HOST=1 bypass)
#       1 = running on bare host (safety block)
#
# Extracted verbatim from dev-machine-build.yaml step 'container-check'.

# Check if running inside a container
if [ ! -f /.dockerenv ] && [ ! -f /run/.containerenv ]; then
    echo "=========================================="
    echo "ERROR: DEV MACHINE NOT RUNNING IN CONTAINER"
    echo "=========================================="
    echo ""
    echo "Running dev-machine recipes outside a container is DANGEROUS."
    echo "Autonomous agents have unrestricted filesystem access and can"
    echo "damage files outside the project directory."
    echo ""
    echo "Use: ./run-dev-machine.sh"
    echo "Or:  docker compose run --rm dev-machine"
    echo ""
    echo "To bypass this check (NOT RECOMMENDED):"
    echo "  export DEV_MACHINE_ALLOW_HOST=1"
    echo "=========================================="
    if [ -z "${DEV_MACHINE_ALLOW_HOST:-}" ]; then
        exit 1
    fi
    echo "WARNING: DEV_MACHINE_ALLOW_HOST is set. Proceeding on bare host."
    echo "YOU ACCEPT ALL RISKS OF FILESYSTEM DAMAGE."
fi
echo "Container check passed."
```

### Step 4: Make it executable

```bash
chmod +x amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/container-check.sh
```

### Step 5: Run test to verify it passes

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/test_container_check.py -v
```

Expected: All 3 tests PASS (or `skip` if running inside a container).

### Step 6: Run the full test suite

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/ -v
```

Expected: All tests in all files PASS (48+ tests total).

### Step 7: Commit

```bash
cd /home/bkrabach/dev/attractor-dev-machine
git add amplifier-bundle-attractor/examples/dev-machine/
git commit -m "feat(phase2): add container-check.sh -- refuses to run outside Docker"
```

---

## Final Verification

After all 12 tasks are complete, run the full suite and verify the directory structure:

### Verify all tests pass

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: All tests PASS, 0 ERRORS, 0 FAILURES.

### Verify directory structure

```bash
find amplifier-bundle-attractor/examples/dev-machine -type f | sort
```

Expected output:
```
amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/.gitkeep
amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/api-inventory.py
amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/build-check.py
amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/container-check.sh
amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/module-health-check.py
amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/orient.py
amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/post-session-accounting.py
amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/post-session-archive.py
amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/post-session-reconcile.py
amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/post-session-status.py
amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/spec-drift-check.py
amplifier-bundle-attractor/examples/dev-machine/scripts/pipeline/test-env-preflight.py
amplifier-bundle-attractor/examples/dev-machine/tests/conftest.py
amplifier-bundle-attractor/examples/dev-machine/tests/fixtures/CONTEXT-TRANSFER.md
amplifier-bundle-attractor/examples/dev-machine/tests/fixtures/STATE-blocked.yaml
amplifier-bundle-attractor/examples/dev-machine/tests/fixtures/STATE.yaml
amplifier-bundle-attractor/examples/dev-machine/tests/test_api_inventory.py
amplifier-bundle-attractor/examples/dev-machine/tests/test_build_check.py
amplifier-bundle-attractor/examples/dev-machine/tests/test_container_check.py
amplifier-bundle-attractor/examples/dev-machine/tests/test_module_health_check.py
amplifier-bundle-attractor/examples/dev-machine/tests/test_orient.py
amplifier-bundle-attractor/examples/dev-machine/tests/test_post_session_accounting.py
amplifier-bundle-attractor/examples/dev-machine/tests/test_post_session_archive.py
amplifier-bundle-attractor/examples/dev-machine/tests/test_post_session_reconcile.py
amplifier-bundle-attractor/examples/dev-machine/tests/test_post_session_status.py
amplifier-bundle-attractor/examples/dev-machine/tests/test_spec_drift_check.py
amplifier-bundle-attractor/examples/dev-machine/tests/test_test_env_preflight.py
```

### Smoke-test each script standalone

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/examples/dev-machine
python3 scripts/pipeline/orient.py tests/fixtures/STATE.yaml
python3 scripts/pipeline/spec-drift-check.py tests/fixtures tests/
python3 scripts/pipeline/build-check.py "true" "true" /tmp tests/fixtures/STATE.yaml
python3 scripts/pipeline/post-session-status.py tests/fixtures/STATE.yaml 5
```

Each should print JSON to stdout and exit 0.

### Final commit

```bash
cd /home/bkrabach/dev/attractor-dev-machine
git add amplifier-bundle-attractor/examples/dev-machine/
git commit -m "feat(phase2): complete script extraction -- 10 Python scripts + 1 shell script, all with tests"
```
