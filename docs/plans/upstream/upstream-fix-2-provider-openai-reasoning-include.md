# Upstream Fix 2: Provider-OpenAI Sends `reasoning.encrypted_content` for Non-Reasoning Models

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Guard the `reasoning.encrypted_content` include parameter so it's only sent when reasoning is actually active in the request.
**Architecture:** One-line conditional guard change — add `and "reasoning" in params` to the existing `if not store_enabled:` check. The fix already exists on branch `fix/reasoning-include-guard` (commit `9d91e3a`).
**Tech Stack:** Python, OpenAI Responses API, amplifier-module-provider-openai

---

## Problem Statement

When `store=false` (the default for many configurations), the OpenAI provider unconditionally sends `include: ["reasoning.encrypted_content"]` even for models that don't support reasoning (gpt-4.1-mini, gpt-4o, etc.). The OpenAI API rejects this with: "Encrypted content is not supported with this model."

This was discovered during E2E Test 6 when running a pipeline with `gpt-4.1-mini`.

## Root Cause

**File:** `amplifier-module-provider-openai/amplifier_module_provider_openai/__init__.py`
**Line:** ~737 (on `main` branch)

```python
# BEFORE (broken — on main):
if not store_enabled:
    params["include"] = kwargs.get("include", ["reasoning.encrypted_content"])
```

This sends the `include` parameter on EVERY request when `store=false`, regardless of whether reasoning is active. Non-reasoning models (gpt-4.1-mini, gpt-4o, gpt-3.5-turbo) reject this parameter.

## The Fix

**Already written on branch `fix/reasoning-include-guard` (commit `9d91e3a`):**

```python
# AFTER (fixed):
if not store_enabled and "reasoning" in params:
    params["include"] = kwargs.get("include", ["reasoning.encrypted_content"])
```

The guard `and "reasoning" in params` ensures the `include` parameter is only added when the request actually has reasoning configured. The `"reasoning"` key is set at lines 719-732 only when `reasoning_param` is truthy (either from kwargs, request.reasoning_effort, or config).

### Additional changes on the branch

The branch also includes a reasoning_param precedence fix (committed earlier in Phase 2 review):

```python
# OLD (main): Used `or` which coerces falsy values like "" or 0 to default
reasoning_param = (
    kwargs.get("reasoning", getattr(request, "reasoning", None))
    or self.reasoning
)

# NEW (fix branch): Explicit None checks preserve intentional falsy values
reasoning_param = kwargs.get("reasoning", getattr(request, "reasoning", None))
if reasoning_param is None and request.reasoning_effort:
    reasoning_param = {
        "effort": request.reasoning_effort,
        "summary": self.reasoning_summary,
    }
if reasoning_param is None:
    reasoning_param = self.reasoning
```

---

### Task 1: Verify the fix branch and create PR

**Files:**
- Already modified: `amplifier-module-provider-openai/amplifier_module_provider_openai/__init__.py:737`
- Already modified: `amplifier-module-provider-openai/tests/test_reasoning_effort.py`

**Step 1: Verify the fix is on the branch**

```bash
cd amplifier-module-provider-openai
git log --oneline fix/reasoning-include-guard
# Should show: 9d91e3a fix: only send reasoning.encrypted_content include when reasoning is active
```

**Step 2: Verify the specific line change**

```bash
git diff main..fix/reasoning-include-guard -- amplifier_module_provider_openai/__init__.py | grep -A2 -B2 "store_enabled"
```

Expected diff:
```diff
-        if not store_enabled:
+        if not store_enabled and "reasoning" in params:
```

**Step 3: Run the full test suite**

Run: `cd amplifier-module-provider-openai && git checkout fix/reasoning-include-guard && uv run pytest -v`
Expected: All tests PASS (including Phase 2 tests)

**Step 4: Write an explicit regression test if not already present**

```python
# tests/test_reasoning_include_guard.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_no_reasoning_include_for_non_reasoning_model():
    """When reasoning is NOT active, include parameter should NOT be sent,
    even when store=false."""
    # Setup provider with store=false, no reasoning config
    # Call complete() with a non-reasoning model
    # Verify params dict does NOT contain "include" key


@pytest.mark.asyncio
async def test_reasoning_include_sent_when_reasoning_active():
    """When reasoning IS active and store=false, include parameter SHOULD be sent."""
    # Setup provider with store=false, reasoning enabled
    # Call complete() with a reasoning-capable model
    # Verify params dict contains "include": ["reasoning.encrypted_content"]
```

**Step 5: Push and create PR**

```bash
cd amplifier-module-provider-openai
git push origin fix/reasoning-include-guard
gh pr create --title "fix: guard reasoning.encrypted_content include for non-reasoning models" \
  --body "When store=false, the provider was unconditionally sending include: [\"reasoning.encrypted_content\"] even for non-reasoning models (gpt-4.1-mini, gpt-4o). The API rejects this with 'Encrypted content is not supported with this model.'

Fix: Add \`and \"reasoning\" in params\` guard so the include parameter is only sent when reasoning is actually configured in the request.

Also fixes falsy-value precedence in reasoning_param (uses explicit None checks instead of \`or\` which coerces empty strings/zeros)." \
  --base main
```

---

## Test Plan

| Test Case | What It Validates |
|---|---|
| Non-reasoning model with `store=false` | `include` NOT in params |
| Reasoning model with `store=false` | `include: ["reasoning.encrypted_content"]` in params |
| Reasoning model with `store=true` | `include` NOT in params (not needed when stored) |
| `reasoning_effort=""` (falsy but intentional) | Treated as "not set", reasoning_param falls through to config |
| `reasoning_effort="low"` with `store=false` | `include` IS in params |

## Backward Compatibility

- **Zero risk.** The fix is strictly additive — it only removes the `include` parameter from requests that shouldn't have had it in the first place. Requests that DO have reasoning active are completely unaffected.
- **Non-reasoning models now work** where they previously errored, so this is purely a bug fix with no behavioral change for working code paths.

## PR Details

| Detail | Value |
|---|---|
| **Target repo** | `microsoft/amplifier-module-provider-openai` |
| **Branch** | `fix/reasoning-include-guard` |
| **Commit** | `9d91e3a` (already committed) |
| **Scope** | 1-line guard change + reasoning_param precedence fix |

## Dependencies

- **Blocks:** Any OpenAI usage with non-reasoning models when `store=false` (e.g., gpt-4.1-mini in Attractor pipelines)
- **Blocked by:** Nothing — branch is ready, just needs PR and merge
- **Priority:** P1 — high impact, trivial effort
