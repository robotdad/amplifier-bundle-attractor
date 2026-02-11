# Upstream Fix 3: Enrich `PreparedBundle.spawn()` with `orchestrator:complete` Metadata

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Capture structured metadata from the child session's `orchestrator:complete` event and include it in spawn()'s return dict, eliminating the need for JSON-in-string hacking.
**Architecture:** Before calling `child_session.execute()`, register a temporary hook on the child session's HookRegistry to capture the `orchestrator:complete` event data. After execute() returns, include the captured metadata in the return dict alongside the existing `output` and `session_id` keys.
**Tech Stack:** Python, amplifier-core HookRegistry, amplifier-foundation PreparedBundle

---

## Problem Statement

`PreparedBundle.spawn()` returns `{"output": str, "session_id": str}` where `output` is the raw string from `execute()`. Callers that need structured metadata (status, routing labels, context updates) must parse JSON out of the string — a fragile heuristic that the pipeline backend currently does with `json.loads()` wrapped in try/except.

The `orchestrator:complete` event already carries `status` and `turn_count` per the kernel contract, and orchestrators can emit additional metadata. But `spawn()` doesn't capture this event from the child session.

Both the core-expert and amplifier-expert independently concluded the kernel `execute() → str` protocol should NOT change. The event system was designed for exactly this sideband data flow pattern.

## Root Cause

**File:** `amplifier-foundation/amplifier_foundation/bundle.py`
**Lines:** 1302-1308

```python
# Current implementation:
try:
    response = await child_session.execute(instruction)
finally:
    await child_session.cleanup()

return {"output": response, "session_id": child_session.session_id}
```

The method calls `execute()`, gets a string back, and wraps it. There's no mechanism to capture the `orchestrator:complete` event that fires during execution.

## The Fix

Register a temporary hook on the child session's HookRegistry before calling execute(), capture the orchestrator:complete event data, and include it in the return dict.

---

### Task 1: Write the failing test

**Files:**
- Test: `amplifier-foundation/tests/test_spawn_enrichment.py`

**Step 1: Write the failing test**

```python
# tests/test_spawn_enrichment.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from amplifier_core.hooks import HookRegistry
from amplifier_core.models import HookResult


@pytest.mark.asyncio
async def test_spawn_returns_status_from_orchestrator_complete():
    """spawn() should include status from orchestrator:complete event."""
    from amplifier_foundation.bundle import PreparedBundle

    # Create a mock child session that:
    # 1. Has a HookRegistry where we can register hooks
    # 2. During execute(), emits orchestrator:complete with status and turn_count
    hooks = HookRegistry()

    mock_session = AsyncMock()
    mock_session.session_id = "test-child-123"
    mock_session.coordinator = MagicMock()
    mock_session.coordinator.hooks = hooks

    async def mock_execute(instruction):
        # Simulate what an orchestrator does: emit orchestrator:complete
        await hooks.emit("orchestrator:complete", {
            "status": "success",
            "turn_count": 3,
            "metadata": {"routing_label": "tests_pass"},
        })
        return "The task completed successfully."

    mock_session.execute = mock_execute
    mock_session.initialize = AsyncMock()
    mock_session.cleanup = AsyncMock()

    # ... setup PreparedBundle to use mock_session ...
    # Call spawn()
    # result = await prepared.spawn(child_bundle, "Do something")

    # Assert enriched return
    # assert result["output"] == "The task completed successfully."
    # assert result["session_id"] == "test-child-123"
    # assert result["status"] == "success"
    # assert result["turn_count"] == 3
    # assert result["metadata"] == {"routing_label": "tests_pass"}


@pytest.mark.asyncio
async def test_spawn_returns_defaults_when_no_orchestrator_complete():
    """spawn() should return sensible defaults when no orchestrator:complete fires."""
    # ... setup where execute() does NOT emit orchestrator:complete ...
    # result = await prepared.spawn(child_bundle, "Do something")

    # Assert defaults
    # assert result["output"] == "Some response"
    # assert result["session_id"] == "test-child-456"
    # assert result.get("status") == "success"  # default assumption
    # assert result.get("turn_count") is None
    # assert result.get("metadata") == {}


@pytest.mark.asyncio
async def test_spawn_returns_error_status_on_failed_execution():
    """spawn() should capture error status from orchestrator:complete on failure."""
    # ... setup where orchestrator emits status="error" ...
    # result = await prepared.spawn(child_bundle, "Do something")
    # assert result.get("status") == "error"
```

**Step 2: Run test to verify it fails**

Run: `cd amplifier-foundation && uv run pytest tests/test_spawn_enrichment.py -v`
Expected: FAIL — current spawn() doesn't return `status`, `turn_count`, or `metadata`

---

### Task 2: Implement the spawn enrichment

**Files:**
- Modify: `amplifier-foundation/amplifier_foundation/bundle.py:1295-1308`

**Step 1: Implement the fix**

In `bundle.py`, modify the `spawn()` method. Add hook registration before execute() and enrich the return dict:

```python
# BEFORE (lines 1295-1308):
        # System prompt factory registration (lines 1288-1300) ...

        # Execute instruction and cleanup
        try:
            response = await child_session.execute(instruction)
        finally:
            await child_session.cleanup()

        return {"output": response, "session_id": child_session.session_id}


# AFTER:
        # System prompt factory registration (lines 1288-1300) ...

        # Capture orchestrator:complete event data from child session
        completion_data: dict[str, Any] = {}

        async def _capture_orchestrator_complete(
            event: str, data: dict[str, Any]
        ) -> "HookResult":
            completion_data.update(data)
            from amplifier_core.models import HookResult
            return HookResult()

        # Register temporary hook to capture structured metadata
        unregister = child_session.coordinator.hooks.register(
            "orchestrator:complete",
            _capture_orchestrator_complete,
            priority=999,  # Run last — don't interfere with other hooks
            name="_spawn_completion_capture",
        )

        # Execute instruction and cleanup
        try:
            response = await child_session.execute(instruction)
        finally:
            # Unregister the temporary hook before cleanup
            unregister()
            await child_session.cleanup()

        return {
            "output": response,
            "session_id": child_session.session_id,
            # Enriched fields from orchestrator:complete event
            "status": completion_data.get("status", "success"),
            "turn_count": completion_data.get("turn_count"),
            "metadata": completion_data.get("metadata", {}),
        }
```

**Step 2: Add the import if needed**

At the top of the file, ensure `HookResult` is importable. Since the inner function needs it, use a late import or add to the existing imports:

```python
from amplifier_core.models import HookResult  # add to existing imports
```

**Step 3: Run test to verify it passes**

Run: `cd amplifier-foundation && uv run pytest tests/test_spawn_enrichment.py -v`
Expected: PASS

**Step 4: Run full test suite**

Run: `cd amplifier-foundation && uv run pytest -v`
Expected: All existing tests PASS (new keys are additive — no existing code reads them)

**Step 5: Commit**

```bash
cd amplifier-foundation
git checkout -b feat/spawn-enrichment
git add amplifier_foundation/bundle.py tests/test_spawn_enrichment.py
git commit -m "feat: enrich spawn() return with orchestrator:complete metadata

PreparedBundle.spawn() now captures the orchestrator:complete event from
the child session and includes status, turn_count, and metadata in the
return dict. This enables structured data flow from child sessions to
callers (pipeline backends, tool-delegate) without json.dumps/json.loads.

New return keys (all additive, backward compatible):
- status: str (default 'success')
- turn_count: int | None
- metadata: dict (default {})"
```

---

## Test Plan

| Test Case | What It Validates |
|---|---|
| Child emits `orchestrator:complete` with status/turn_count/metadata | All three fields appear in return dict |
| Child does NOT emit `orchestrator:complete` | Defaults: status="success", turn_count=None, metadata={} |
| Child emits status="error" | Error status propagated |
| Child execution raises exception | Exception propagates (existing behavior), hook is cleaned up |
| Existing callers that only read `output` and `session_id` | Unaffected — new keys are additive |

## Backward Compatibility

- **Zero risk for existing callers.** The return dict previously had `{"output": str, "session_id": str}`. New keys (`status`, `turn_count`, `metadata`) are additive. Any code that does `result["output"]` continues to work identically.
- **The temporary hook has priority 999** (lowest) and returns `HookResult()` (continue) — it won't interfere with any existing hooks on the child session.
- **The unregister call in `finally`** ensures the hook is cleaned up even if execute() raises.
- **tool-delegate** currently reads `result["output"]` and `result["session_id"]` — it can optionally start reading `result["status"]` and `result["metadata"]` after this lands, but isn't required to.

## PR Details

| Detail | Value |
|---|---|
| **Target repo** | `microsoft/amplifier-foundation` |
| **Branch** | `feat/spawn-enrichment` |
| **Commit message** | `feat: enrich spawn() return with orchestrator:complete metadata` |
| **Scope** | ~20 lines in `bundle.py`, new test file |

## Dependencies

- **Blocks:** Clean pipeline→agent structured data flow (eliminates json.dumps/json.loads hacks in loop-pipeline backend)
- **Blocked by:** Nothing — can start immediately
- **Related:** Fix 4 (spawn example update) and Fix 5 (delegate spawn kwargs) should be coordinated but are not blocking
- **Priority:** P1 — high value, moderate effort
