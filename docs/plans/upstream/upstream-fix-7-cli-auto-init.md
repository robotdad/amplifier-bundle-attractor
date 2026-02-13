# Upstream Fix 7: CLI Should Auto-Init in Non-Interactive Contexts

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** When `check_first_run()` returns True and stdin is not a TTY (shadow containers, CI pipelines, automation), the CLI should auto-configure from environment variables instead of showing an interactive prompt that can't be answered.
**Architecture:** In the run command's first-run check, detect non-TTY and invoke the `init --yes` logic automatically. The `init --yes` path already exists and works correctly (it was used successfully in shadow testing with `amplifier init --yes`).
**Tech Stack:** Python, Click CLI, amplifier-app-cli

---

## Problem Statement

When `check_first_run()` returns True and stdin is not a TTY:

1. The CLI calls `prompt_first_run_init(console)` (in `session_runner.py:135-146`)
2. `prompt_first_run_init()` shows the "No provider configured!" message
3. Then the `init` command attempts interactive prompts
4. The init command at line 193 detects non-TTY: `if not non_interactive and not sys.stdin.isatty()`
5. It prints "Error: Interactive mode requires a TTY" and exits

This means **any non-interactive context** (Docker containers, CI pipelines, shadow environments, cron jobs) that has API keys in the environment but no `settings.yaml` file will fail on first run. The workaround is to run `amplifier init --yes` first, but this shouldn't be necessary when API keys are clearly available.

## Root Cause

**File 1:** `amplifier-app-cli/amplifier_app_cli/session_runner.py`
**Lines:** 135-146

```python
from .commands.init import check_first_run
from .commands.init import prompt_first_run_init

# ... in the session runner setup:
if check_first_run():
    if not config.is_resume:
        prompt_first_run_init(console)  # <-- always calls interactive prompt
```

There's no TTY check before calling `prompt_first_run_init()`. The function unconditionally tries interactive mode.

**File 2:** `amplifier-app-cli/amplifier_app_cli/commands/init.py`
**Line:** 193

```python
if not non_interactive and not sys.stdin.isatty():
    console.print("[red]Error:[/red] Interactive mode requires a TTY. "
                  "Use --yes flag for non-interactive setup.")
    raise SystemExit(1)
```

The TTY detection exists in the init command, but it errors out instead of falling back to non-interactive mode.

## The Fix

Add a TTY check in the session runner's first-run handling. When not interactive, invoke the init command's non-interactive logic directly.

---

### Task 1: Add non-TTY detection to session_runner first-run check

**Files:**
- Modify: `amplifier-app-cli/amplifier_app_cli/session_runner.py:135-146`
- Test: `amplifier-app-cli/tests/test_auto_init.py`

**Step 1: Write the failing test**

```python
# tests/test_auto_init.py
import pytest
import sys
from unittest.mock import patch, MagicMock, AsyncMock


def test_non_tty_auto_inits_from_env():
    """When check_first_run() is True and stdin is not a TTY,
    the session runner should auto-init from env vars instead of
    showing an interactive prompt."""
    with patch("amplifier_app_cli.session_runner.check_first_run", return_value=True), \
         patch("sys.stdin") as mock_stdin, \
         patch("amplifier_app_cli.session_runner.auto_init_from_env") as mock_auto_init:
        mock_stdin.isatty.return_value = False
        mock_auto_init.return_value = True  # Success
        # ... invoke the session runner ...
        mock_auto_init.assert_called_once()


def test_tty_shows_interactive_prompt():
    """When check_first_run() is True and stdin IS a TTY,
    the session runner should show the interactive prompt as before."""
    with patch("amplifier_app_cli.session_runner.check_first_run", return_value=True), \
         patch("sys.stdin") as mock_stdin, \
         patch("amplifier_app_cli.session_runner.prompt_first_run_init") as mock_prompt:
        mock_stdin.isatty.return_value = True
        # ... invoke the session runner ...
        mock_prompt.assert_called_once()


def test_auto_init_detects_api_keys():
    """auto_init_from_env should detect available API keys and configure."""
    import os
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-123"}):
        from amplifier_app_cli.session_runner import auto_init_from_env
        # Should succeed and create settings
        result = auto_init_from_env()
        assert result is True
```

**Step 2: Run test to verify it fails**

Run: `cd amplifier-app-cli && python -m pytest tests/test_auto_init.py -v`
Expected: FAIL — `auto_init_from_env` doesn't exist yet

**Step 3: Implement the auto-init logic**

In `session_runner.py`, modify the first-run check:

```python
# BEFORE (lines 135-146):
from .commands.init import check_first_run
from .commands.init import prompt_first_run_init

if check_first_run():
    if not config.is_resume:
        prompt_first_run_init(console)

# AFTER:
import sys
from .commands.init import check_first_run
from .commands.init import prompt_first_run_init

if check_first_run():
    if not config.is_resume:
        if sys.stdin.isatty():
            prompt_first_run_init(console)
        else:
            # Non-interactive context (CI, Docker, shadow env)
            # Auto-init from environment variables
            auto_init_from_env(console)
```

Then add the `auto_init_from_env` function:

```python
def auto_init_from_env(console=None) -> bool:
    """Auto-configure from environment variables in non-interactive contexts.

    Equivalent to 'amplifier init --yes' but called programmatically.
    Returns True if a provider was configured, False otherwise.
    """
    import os
    from .commands.init import init_cmd
    from click.testing import CliRunner

    # Check if any API keys are available
    api_keys = {
        "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY"),
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
        "AZURE_OPENAI_API_KEY": os.environ.get("AZURE_OPENAI_API_KEY"),
        "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY"),
        "GOOGLE_API_KEY": os.environ.get("GOOGLE_API_KEY"),
    }

    available = {k: v for k, v in api_keys.items() if v}

    if not available:
        if console:
            console.print(
                "[yellow]No API keys found in environment. "
                "Set ANTHROPIC_API_KEY, OPENAI_API_KEY, etc. "
                "or run 'amplifier init' interactively.[/yellow]"
            )
        return False

    # Invoke init in non-interactive mode
    runner = CliRunner()
    result = runner.invoke(init_cmd, ["--yes"])

    if result.exit_code == 0:
        if console:
            providers = ", ".join(k.replace("_API_KEY", "").lower() for k in available)
            console.print(
                f"[green]Auto-configured from environment: {providers}[/green]"
            )
        return True
    else:
        if console:
            console.print(
                "[yellow]Auto-init failed. Run 'amplifier init' manually.[/yellow]"
            )
        return False
```

**Step 4: Run test to verify it passes**

Run: `cd amplifier-app-cli && python -m pytest tests/test_auto_init.py -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `cd amplifier-app-cli && python -m pytest -v`
Expected: All existing tests PASS

**Step 6: Commit**

```bash
cd amplifier-app-cli
git checkout -b feat/auto-init-non-tty
git add amplifier_app_cli/session_runner.py tests/test_auto_init.py
git commit -m "feat: auto-init from env vars in non-interactive contexts

When check_first_run() returns True and stdin is not a TTY (Docker,
CI, shadow environments), the CLI now auto-configures from environment
variables instead of showing an interactive prompt that can't be
answered.

Equivalent to running 'amplifier init --yes' automatically. Falls back
to a helpful error message if no API keys are found in the environment.

This eliminates the need to manually run 'amplifier init --yes' before
'amplifier run' in non-interactive contexts."
```

---

### Task 2: Also fix the init command's TTY error to suggest auto-init

**Files:**
- Modify: `amplifier-app-cli/amplifier_app_cli/commands/init.py:193-196`

**Step 1: Update the error message**

```python
# BEFORE (line 193-196):
if not non_interactive and not sys.stdin.isatty():
    console.print("[red]Error:[/red] Interactive mode requires a TTY. "
                  "Use --yes flag for non-interactive setup.")
    raise SystemExit(1)

# AFTER:
if not non_interactive and not sys.stdin.isatty():
    # Auto-upgrade to non-interactive mode instead of erroring
    console.print(
        "[yellow]Non-interactive context detected. "
        "Auto-configuring from environment variables...[/yellow]"
    )
    non_interactive = True  # Fall through to non-interactive path
```

This changes the init command from erroring in non-TTY to automatically switching to non-interactive mode. This is a better UX — if someone explicitly runs `amplifier init` in a CI pipeline, they probably want it to work, not error.

**Step 2: Commit**

```bash
cd amplifier-app-cli
git add amplifier_app_cli/commands/init.py
git commit -m "fix: auto-upgrade to non-interactive mode when no TTY available

Instead of erroring with 'Interactive mode requires a TTY', the init
command now automatically switches to non-interactive mode and configures
from environment variables. This is the expected behavior when running
in CI, Docker, or other non-TTY contexts."
```

---

## Test Plan

| Test Case | What It Validates |
|---|---|
| Non-TTY + API keys in env → auto-configures | Core fix |
| Non-TTY + no API keys → helpful message, no crash | Graceful degradation |
| TTY + first run → interactive prompt (unchanged) | Backward compatibility |
| `amplifier init` without TTY → auto non-interactive | Init command fix |
| `amplifier init --yes` → unchanged behavior | Existing flag still works |
| Shadow container first run → auto-configures | Real-world scenario |

## Backward Compatibility

- **TTY behavior is completely unchanged.** The new code path only activates when `sys.stdin.isatty()` returns False.
- **`amplifier init --yes` is unchanged.** The explicit flag continues to work as before.
- **Non-TTY behavior improves.** Instead of an error exit, users get auto-configuration. This is strictly better — no valid use case prefers the error.
- **Idempotent.** If init has already been run, `check_first_run()` returns False and the new code never activates.

## PR Details

| Detail | Value |
|---|---|
| **Target repo** | `microsoft/amplifier-app-cli` (or wherever the canonical CLI lives) |
| **Branch** | `feat/auto-init-non-tty` |
| **Commit messages** | 2 commits: auto-init in session_runner, init command TTY fix |
| **Scope** | ~40 lines in 2 files + tests |
| **Location note** | CLI source found at `/path/to/amplifier-app-cli/` |

## Dependencies

- **Blocks:** Shadow/CI/automation workflows — they currently require a manual `amplifier init --yes` before any `amplifier run`
- **Blocked by:** Nothing — can start immediately
- **Related:** Fix 6 (tip message) addresses the misleading UX text; can be combined into one PR
- **Priority:** P2 — medium impact (affects all non-interactive contexts), moderate effort
