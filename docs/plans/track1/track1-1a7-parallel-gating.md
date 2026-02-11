# Track 1-1A7: Add Parallel Tool Call Gating

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Add a `supports_parallel_tool_calls` config flag (default `True`). When `False` or when only 1 tool call is returned, execute tool calls sequentially instead of with `asyncio.gather()`. This lets the host control execution strategy per provider.

**Architecture:** Add `supports_parallel_tool_calls` to `SessionConfig`. In `_execute_tool_calls()`, check this flag and the tool call count. When parallel execution is disabled (or only 1 call), iterate sequentially. When enabled and multiple calls exist, use the existing `asyncio.gather()` path. This is a minimal, non-breaking change to a single method.

**Tech Stack:** Python, asyncio

**Spec Reference:** coding-agent-loop-spec Section 3.2 (`ProviderProfile.supports_parallel_tool_calls`), Section 2.5 `execute_tool_calls()` pseudocode (parallel only when profile supports it AND multiple calls)

**Adversarial Review Reference:** H-3

---

## Problem Statement

The spec says tool calls should only be executed in parallel when `provider_profile.supports_parallel_tool_calls` is `True` AND there are multiple tool calls. The current implementation always uses `asyncio.gather()` for all tool calls regardless of the provider or call count:

```python
async def _execute_tool_calls(self, tool_calls: list) -> list[ToolResult]:
    """Execute tool calls in parallel with asyncio.gather."""
    results = await asyncio.gather(
        *[self._execute_single_tool(tc) for tc in tool_calls]
    )
    return list(results)
```

Providers that don't support parallel tool calls (or where order matters) may receive results in unexpected order, causing subtle bugs in tool output interpretation.

## Root Cause

**File:** `modules/loop-agent/amplifier_module_loop_agent/agent_session.py`
**Lines:** 484-489 (`_execute_tool_calls`)

The method unconditionally uses `asyncio.gather()`. There is no check for a parallel execution flag and no sequential fallback path.

**File:** `modules/loop-agent/amplifier_module_loop_agent/config.py`
**Lines:** 17-52 (`SessionConfig`)

No `supports_parallel_tool_calls` field exists in the config.

## The Fix

### Part 1: Add config field

**File:** `modules/loop-agent/amplifier_module_loop_agent/config.py`

Add to `SessionConfig`:

```python
supports_parallel_tool_calls: bool = True  # False = sequential execution
```

### Part 2: Gate parallel execution

**File:** `modules/loop-agent/amplifier_module_loop_agent/agent_session.py`

**Before** (`_execute_tool_calls`, lines 484-489):
```python
async def _execute_tool_calls(self, tool_calls: list) -> list[ToolResult]:
    """Execute tool calls in parallel with asyncio.gather."""
    results = await asyncio.gather(
        *[self._execute_single_tool(tc) for tc in tool_calls]
    )
    return list(results)
```

**After**:
```python
async def _execute_tool_calls(self, tool_calls: list) -> list[ToolResult]:
    """Execute tool calls, parallel or sequential based on config.

    Uses asyncio.gather() when supports_parallel_tool_calls is True
    AND there are multiple tool calls. Otherwise executes sequentially
    to preserve ordering guarantees (spec Section 2.5).
    """
    use_parallel = (
        self._config.supports_parallel_tool_calls
        and len(tool_calls) > 1
    )

    if use_parallel:
        results = await asyncio.gather(
            *[self._execute_single_tool(tc) for tc in tool_calls]
        )
        return list(results)
    else:
        results: list[ToolResult] = []
        for tc in tool_calls:
            result = await self._execute_single_tool(tc)
            results.append(result)
        return results
```

---

## Tasks

### Task 1: Write failing tests for parallel gating

**Files:**
- Create: `modules/loop-agent/tests/test_parallel_gating.py`

**Step 1: Write the failing tests**

```python
"""Tests for parallel tool call gating (H-3).

Verifies that:
1. supports_parallel_tool_calls=True (default) uses parallel execution
2. supports_parallel_tool_calls=False uses sequential execution
3. Single tool call always executes sequentially (even when parallel=True)
4. Sequential execution preserves call order
5. Config flag can be set via from_dict()
"""

import asyncio
import time

import pytest
from unittest.mock import AsyncMock, MagicMock

from amplifier_core.message_models import ChatResponse, ToolCall, Usage
from amplifier_core.models import ToolResult

from amplifier_module_loop_agent.agent_session import AgentSession
from amplifier_module_loop_agent.config import SessionConfig


def _text_response(text: str) -> ChatResponse:
    return ChatResponse(
        content=[{"type": "text", "text": text}],
        tool_calls=None,
        usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
    )


def _multi_tool_response(*tool_calls_tuple) -> ChatResponse:
    return ChatResponse(
        content=[],
        tool_calls=[
            ToolCall(id=cid, name=name, arguments=args)
            for cid, name, args in tool_calls_tuple
        ],
        usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
    )


def _make_hooks():
    hooks = MagicMock()
    hooks._emitted = []

    async def _emit(event, data):
        hooks._emitted.append((event, data))
        return MagicMock(action="continue")

    hooks.emit = AsyncMock(side_effect=_emit)
    return hooks


def _make_slow_tool(name: str, delay: float = 0.1, output: str = "ok"):
    """Tool that takes `delay` seconds to execute."""
    tool = MagicMock()
    tool.name = name
    tool.description = f"Mock {name}"
    tool.input_schema = {"type": "object", "properties": {}}

    async def slow_execute(args):
        await asyncio.sleep(delay)
        return ToolResult(success=True, output=output)

    tool.execute = AsyncMock(side_effect=slow_execute)
    return tool


def _make_ordering_tool(name: str, order_tracker: list):
    """Tool that records execution order."""
    tool = MagicMock()
    tool.name = name
    tool.description = f"Mock {name}"
    tool.input_schema = {"type": "object", "properties": {}}

    async def tracking_execute(args):
        order_tracker.append(name)
        return ToolResult(success=True, output=f"{name} done")

    tool.execute = AsyncMock(side_effect=tracking_execute)
    return tool


# --- Config tests ---


class TestConfigFlag:
    """Tests for the supports_parallel_tool_calls config field."""

    def test_default_is_true(self):
        config = SessionConfig()
        assert config.supports_parallel_tool_calls is True

    def test_can_set_false(self):
        config = SessionConfig(supports_parallel_tool_calls=False)
        assert config.supports_parallel_tool_calls is False

    def test_from_dict_sets_flag(self):
        config = SessionConfig.from_dict({"supports_parallel_tool_calls": False})
        assert config.supports_parallel_tool_calls is False

    def test_from_dict_default(self):
        config = SessionConfig.from_dict({})
        assert config.supports_parallel_tool_calls is True


# --- Sequential execution tests ---


@pytest.mark.asyncio
async def test_sequential_when_parallel_disabled():
    """With supports_parallel_tool_calls=False, tools execute sequentially."""
    order: list[str] = []
    tool_a = _make_ordering_tool("tool_a", order)
    tool_b = _make_ordering_tool("tool_b", order)

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=[
        _multi_tool_response(
            ("tc1", "tool_a", {}),
            ("tc2", "tool_b", {}),
        ),
        _text_response("done."),
    ])
    hooks = _make_hooks()

    session = AgentSession(
        config=SessionConfig(supports_parallel_tool_calls=False),
        provider=provider,
        tools={"tool_a": tool_a, "tool_b": tool_b},
        hooks=hooks,
    )
    await session.process_input("do both")

    # Both tools executed
    assert tool_a.execute.call_count == 1
    assert tool_b.execute.call_count == 1

    # Sequential means order is deterministic: a then b
    assert order == ["tool_a", "tool_b"]


@pytest.mark.asyncio
async def test_sequential_preserves_order():
    """Sequential execution preserves the order tools were returned by the LLM."""
    order: list[str] = []
    tools = {}
    for name in ["first", "second", "third"]:
        tools[name] = _make_ordering_tool(name, order)

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=[
        _multi_tool_response(
            ("tc1", "first", {}),
            ("tc2", "second", {}),
            ("tc3", "third", {}),
        ),
        _text_response("done."),
    ])
    hooks = _make_hooks()

    session = AgentSession(
        config=SessionConfig(supports_parallel_tool_calls=False),
        provider=provider,
        tools=tools,
        hooks=hooks,
    )
    await session.process_input("do all three")

    assert order == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_sequential_timing():
    """Sequential execution takes longer than parallel (proves no gather)."""
    delay = 0.05  # 50ms per tool
    tool_a = _make_slow_tool("tool_a", delay=delay)
    tool_b = _make_slow_tool("tool_b", delay=delay)

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=[
        _multi_tool_response(
            ("tc1", "tool_a", {}),
            ("tc2", "tool_b", {}),
        ),
        _text_response("done."),
    ])
    hooks = _make_hooks()

    session = AgentSession(
        config=SessionConfig(supports_parallel_tool_calls=False),
        provider=provider,
        tools={"tool_a": tool_a, "tool_b": tool_b},
        hooks=hooks,
    )

    start = time.monotonic()
    await session.process_input("do both")
    elapsed = time.monotonic() - start

    # Sequential: should take at least 2x the delay (100ms)
    # With parallel it would take ~50ms
    assert elapsed >= delay * 1.5, (
        f"Expected sequential timing (>={delay * 1.5:.3f}s), got {elapsed:.3f}s"
    )


# --- Parallel execution tests ---


@pytest.mark.asyncio
async def test_parallel_when_enabled_and_multiple():
    """With supports_parallel_tool_calls=True and multiple calls, runs in parallel."""
    delay = 0.05
    tool_a = _make_slow_tool("tool_a", delay=delay)
    tool_b = _make_slow_tool("tool_b", delay=delay)

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=[
        _multi_tool_response(
            ("tc1", "tool_a", {}),
            ("tc2", "tool_b", {}),
        ),
        _text_response("done."),
    ])
    hooks = _make_hooks()

    session = AgentSession(
        config=SessionConfig(supports_parallel_tool_calls=True),
        provider=provider,
        tools={"tool_a": tool_a, "tool_b": tool_b},
        hooks=hooks,
    )

    start = time.monotonic()
    await session.process_input("do both")
    elapsed = time.monotonic() - start

    # Parallel: should complete in roughly delay time, not 2x
    # Use generous bound to avoid flaky CI
    assert elapsed < delay * 1.8, (
        f"Expected parallel timing (<{delay * 1.8:.3f}s), got {elapsed:.3f}s"
    )


@pytest.mark.asyncio
async def test_single_tool_always_sequential():
    """A single tool call is sequential even with parallel=True."""
    order: list[str] = []
    tool_a = _make_ordering_tool("tool_a", order)

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=[
        _multi_tool_response(("tc1", "tool_a", {})),
        _text_response("done."),
    ])
    hooks = _make_hooks()

    session = AgentSession(
        config=SessionConfig(supports_parallel_tool_calls=True),
        provider=provider,
        tools={"tool_a": tool_a},
        hooks=hooks,
    )
    await session.process_input("do one")

    assert tool_a.execute.call_count == 1
    assert order == ["tool_a"]
```

**Step 2: Run tests to verify they fail**

Run: `cd modules/loop-agent && python -m pytest tests/test_parallel_gating.py -v`
Expected: FAIL -- `SessionConfig` has no `supports_parallel_tool_calls` attribute. Config tests fail first, then integration tests.

### Task 2: Add `supports_parallel_tool_calls` to SessionConfig

**Files:**
- Modify: `modules/loop-agent/amplifier_module_loop_agent/config.py:17-52`

**Step 1: Add the field**

Add after `context_window_size` (around line 36):

```python
supports_parallel_tool_calls: bool = True  # False = sequential tool execution
```

**Step 2: Run config unit tests**

Run: `cd modules/loop-agent && python -m pytest tests/test_parallel_gating.py::TestConfigFlag -v`
Expected: All 4 config tests PASS.

**Step 3: Commit**

```
git add modules/loop-agent/amplifier_module_loop_agent/config.py
git commit -m "feat(loop-agent): add supports_parallel_tool_calls config flag"
```

### Task 3: Gate `_execute_tool_calls` on config flag

**Files:**
- Modify: `modules/loop-agent/amplifier_module_loop_agent/agent_session.py:484-489`

**Step 1: Replace the method**

Replace `_execute_tool_calls` with the gated version from the "After" section above:

```python
async def _execute_tool_calls(self, tool_calls: list) -> list[ToolResult]:
    """Execute tool calls, parallel or sequential based on config.

    Uses asyncio.gather() when supports_parallel_tool_calls is True
    AND there are multiple tool calls. Otherwise executes sequentially
    to preserve ordering guarantees (spec Section 2.5).
    """
    use_parallel = (
        self._config.supports_parallel_tool_calls
        and len(tool_calls) > 1
    )

    if use_parallel:
        results = await asyncio.gather(
            *[self._execute_single_tool(tc) for tc in tool_calls]
        )
        return list(results)
    else:
        results: list[ToolResult] = []
        for tc in tool_calls:
            result = await self._execute_single_tool(tc)
            results.append(result)
        return results
```

**Step 2: Run all parallel gating tests**

Run: `cd modules/loop-agent && python -m pytest tests/test_parallel_gating.py -v`
Expected: All 8 tests PASS (4 config + 4 integration).

**Step 3: Run existing tests for regression**

Run: `cd modules/loop-agent && python -m pytest tests/test_agent_session.py -v`
Expected: All existing tests PASS. Default is `True` so existing parallel behavior is unchanged.

**Step 4: Commit**

```
git add modules/loop-agent/amplifier_module_loop_agent/agent_session.py
git commit -m "feat(loop-agent): gate parallel tool execution on config flag (H-3)

When supports_parallel_tool_calls=False (or only 1 tool call),
execute tool calls sequentially in the order the LLM returned them.
When True and multiple calls, use asyncio.gather() (existing behavior).

Default is True (backward compatible). Providers that don't support
parallel tool calls can set this to False in their config.

Spec: Section 3.2 (ProviderProfile.supports_parallel_tool_calls),
      Section 2.5 (execute_tool_calls conditional on profile flag)
Fixes: H-3 from adversarial review"
```

---

## Backward Compatibility

- **No breaking changes.** The default value is `True`, preserving the existing `asyncio.gather()` behavior for all current users.
- The config field is added to `SessionConfig` with a default, so `from_dict({})` (no config) produces the existing parallel behavior.
- Existing tests all use the default config and will continue to work unchanged.
- The sequential path produces the same `list[ToolResult]` as the parallel path, just in guaranteed order.

## Dependencies on Upstream Fixes

- **None.** This is a self-contained change to `config.py` and `agent_session.py`.
- **Note on interaction with Track 1-1A2 (cancellation):** If cancellation checkpoints are added to `_execute_tool_calls`, the sequential path also needs a cancellation check between tool executions:

```python
# Future enhancement if 1A2 lands first:
else:
    results: list[ToolResult] = []
    for tc in tool_calls:
        if self._is_immediate_cancel():
            # Synthesize cancelled results for remaining tools
            results.extend(
                ToolResult(success=False, output="Cancelled")
                for _ in tool_calls[len(results):]
            )
            break
        result = await self._execute_single_tool(tc)
        results.append(result)
    return results
```

This is called out for the implementer's awareness but is NOT part of this plan. It would be addressed during 1A2 implementation if 1A7 lands first.

## PR Details

**Branch:** `track1/1a7-parallel-gating`
**Title:** `feat(loop-agent): add supports_parallel_tool_calls config flag for sequential execution (H-3)`
**Labels:** `track1`, `agent-loop`, `spec-compliance`
**Reviewers:** @bkrabach
