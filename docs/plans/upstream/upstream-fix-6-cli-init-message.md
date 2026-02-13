# Upstream Fix 6: Fix Misleading `amplifier init` Tip Message

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Fix the misleading tip message in the CLI that tells users to set API keys to skip init, when in reality setting API keys does NOT skip init.
**Architecture:** Single text change in the `prompt_first_run_init()` function.
**Tech Stack:** Python, Click CLI, amplifier-app-cli

---

## Problem Statement

When a user runs `amplifier run` for the first time without `~/.amplifier/settings.yaml`, the CLI shows:

```
⚠️  No provider configured!

Tip: Set ANTHROPIC_API_KEY, OPENAI_API_KEY, etc. to skip this.
```

This message is **actively misleading**. The `check_first_run()` function at `commands/init.py:64-137` checks ONLY whether a provider is configured in `~/.amplifier/settings.yaml`. It does NOT check environment variables. Setting API keys does NOT skip the init prompt.

This was discovered when shadow environment testing consistently failed — the containers had API keys in the environment but still hit the init prompt, which blocks in non-TTY contexts.

## Root Cause

**File:** `amplifier-app-cli/amplifier_app_cli/commands/init.py`
**Line:** 151 (inside `prompt_first_run_init()`)

```python
# Line 147:
console.print("[yellow]⚠️  No provider configured![/yellow]")
# Line 148-150:
console.print(
    "Run [bold]amplifier init[/bold] to set up your provider, "
    "or add configuration to ~/.amplifier/settings.yaml"
)
# Line 151:
console.print("Tip: Set ANTHROPIC_API_KEY, OPENAI_API_KEY, etc. to skip this.")
```

The `check_first_run()` function at line 64-137 works by:
1. Loading `AppSettings` from `~/.amplifier/settings.yaml` (line 86-87)
2. Calling `ProviderManager(config).get_current_provider()` (line 87)
3. Which reads `settings.get("config", {}).get("providers", [])` (line 324-325 in `lib/settings.py`)
4. If the providers list is empty → returns `None` → `check_first_run()` returns `True`

**Environment variables are explicitly NOT checked.** There's even a design comment at `init.py:69-78` explaining this is intentional (not all providers use env-var auth).

## The Fix

Change the tip message to accurately describe how to skip the prompt:

---

### Task 1: Fix the tip message

**Files:**
- Modify: `amplifier-app-cli/amplifier_app_cli/commands/init.py:151`

**Step 1: Write the failing test**

```python
# tests/test_init_message.py
def test_init_tip_message_does_not_say_skip():
    """The tip message should NOT claim that setting API keys skips init."""
    import amplifier_app_cli.commands.init as init_module
    import inspect
    source = inspect.getsource(init_module.prompt_first_run_init)
    assert "to skip this" not in source, \
        "Tip message still says 'to skip this' — misleading"
    assert "amplifier init --yes" in source, \
        "Tip should mention 'amplifier init --yes'"
```

**Step 2: Run test to verify it fails**

Run: `cd amplifier-app-cli && python -m pytest tests/test_init_message.py -v`
Expected: FAIL — "to skip this" found in source

**Step 3: Apply the fix**

```python
# BEFORE (line 151):
console.print("Tip: Set ANTHROPIC_API_KEY, OPENAI_API_KEY, etc. to skip this.")

# AFTER:
console.print(
    "Tip: Run [bold]amplifier init --yes[/bold] to auto-configure "
    "from environment variables (ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.)"
)
```

**Step 4: Run test to verify it passes**

Run: `cd amplifier-app-cli && python -m pytest tests/test_init_message.py -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `cd amplifier-app-cli && python -m pytest -v`
Expected: All existing tests PASS

**Step 6: Commit**

```bash
cd amplifier-app-cli
git checkout -b fix/init-tip-message
git add amplifier_app_cli/commands/init.py tests/test_init_message.py
git commit -m "fix: correct misleading 'set API keys to skip this' tip message

The tip previously said 'Set ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.
to skip this' but setting API keys does NOT skip init. The
check_first_run() function only checks ~/.amplifier/settings.yaml,
not environment variables.

Changed to accurately recommend 'amplifier init --yes' which does
auto-configure from environment variables."
```

---

## Test Plan

| Test Case | What It Validates |
|---|---|
| Tip message does not contain "to skip this" | Misleading text removed |
| Tip message contains "amplifier init --yes" | Accurate guidance present |
| Existing init flow unchanged | No behavioral change |

## Backward Compatibility

- **Zero risk.** This is a text-only change. No behavioral change whatsoever. The init flow, API key detection, and settings file handling are all untouched.

## PR Details

| Detail | Value |
|---|---|
| **Target repo** | `microsoft/amplifier-app-cli` (or wherever the canonical CLI lives) |
| **Branch** | `fix/init-tip-message` |
| **Commit message** | `fix: correct misleading 'set API keys to skip this' tip message` |
| **Scope** | 1-line text change + 1 test |
| **Location note** | CLI source found at `/path/to/amplifier-app-cli/` |

## Dependencies

- **Blocks:** Nothing — workaround (`amplifier init --yes`) exists
- **Blocked by:** Nothing — can be done immediately
- **Related:** Fix 7 (CLI auto-init) addresses the deeper issue of non-interactive contexts
- **Can combine with Fix 7** into a single CLI PR
- **Priority:** P3 — low severity, trivial effort, pure UX improvement
