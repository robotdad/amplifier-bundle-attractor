# Track 1-1A2: Add Cancellation Checkpoints to Agent Loop

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Add 3 cancellation checkpoints to the agent loop so the host can stop a runaway agent at any time: top of loop, after provider call, and around tool execution with `register_start`/`register_complete`.

**Architecture:** Follow the `loop-basic` cancellation pattern. The `ModuleCoordinator` exposes `coordinator.cancellation.is_cancelled` (graceful) and `coordinator.cancellation.is_immediate` (force). We check these at 3 points in the loop. Critical invariant: always add tool results to context before returning on cancel, to avoid orphaned `tool_use` blocks that violate provider API contracts.

**Tech Stack:** Python, amplifier-core `CancellationToken` protocol, asyncio

**Spec Reference:** coding-agent-loop-spec Section 2.4 (abort signal), Section 2.8 stop condition #4, Appendix B Graceful Shutdown Sequence

**Adversarial Review Reference:** C-5

---

## Problem Statement

`AgentSession` has a `shutdown()` method but no mechanism for the host to interrupt a running `process_input()` call. There is no `CancellationToken`, no `asyncio.Event`, and no checkpoint in the loop where cancellation is checked. A runaway agent (infinite tool loops, stuck LLM calls) cannot be stopped until it naturally completes.

The `loop-basic` orchestrator already implements this correctly with 3 checkpoints and proper tool result cleanup. The `loop-agent` orchestrator has zero cancellation support.

## Root Cause

**File:** `modules/loop-agent/amplifier_module_loop_agent/agent_session.py`
**Lines:** 244-362 (the entire `process_input` loop body)

The loop has:
- No cancellation check at the top of the while loop
- No cancellation check after `_call_provider()`
- No `register_tool_start`/`register_tool_complete` around tool execution
- No handling of `asyncio.CancelledError` during tool gather

**File:** `modules/loop-agent/amplifier_module_loop_agent/__init__.py`
**Lines:** 71-130 (`AgentOrchestrator.execute()`)

The orchestrator receives a `coordinator` parameter but never passes it to `AgentSession`. The session has no reference to the coordinator's cancellation token.

## The Fix

### Part 1: Pass coordinator to AgentSession

**File:** `modules/loop-agent/amplifier_module_loop_agent/__init__.py`

The `AgentOrchestrator.execute()` method creates an `AgentSession` at line 117 but doesn't pass `coordinator`. Add a `coordinator` parameter to `AgentSession.__init__()` and pass it through.

**File:** `modules/loop-agent/amplifier_module_loop_agent/agent_session.py`

Add `coordinator` parameter to `__init__` (default `None`). Store as `self._coordinator`.

### Part 2: Three Cancellation Checkpoints

**Checkpoint 1: Top of loop** (line 244 area)

```python
while round_count < self._config.max_tool_rounds_per_input:
    # Checkpoint 1: Check cancellation at top of each iteration
    if self._is_cancelled():
        self._state_machine.complete()
        await self._emit_session_end()
        return await self._process_follow_ups(last_text)
```

**Checkpoint 2: After provider call** (line 286 area, after `call_result = await self._call_provider(request)`)

```python
call_result = await self._call_provider(request)

# Checkpoint 2: Check immediate cancellation after provider returns
if self._is_immediate_cancel():
    self._state_machine.complete()
    await self._emit_session_end()
    return await self._process_follow_ups(last_text)
```

**Checkpoint 3: Around tool execution** (line 484-489 area, in `_execute_tool_calls`)

```python
async def _execute_tool_calls(self, tool_calls: list) -> list[ToolResult]:
    """Execute tool calls in parallel with cancellation support."""
    try:
        results = await asyncio.gather(
            *[self._execute_single_tool(tc) for tc in tool_calls]
        )
        return list(results)
    except asyncio.CancelledError:
        # Immediate cancel during tool execution:
        # Synthesize cancelled results for ALL tool calls
        # to maintain tool_use/tool_result pairing
        logger.info("Tool execution cancelled - synthesizing cancelled results")
        return [
            ToolResult(success=False, output="Tool execution was cancelled by user")
            for _ in tool_calls
        ]
```

Plus, check after gather returns:

```python
    results = list(results)

    # Check immediate cancellation after tools complete
    if self._is_immediate_cancel():
        # Still return results -- they'll be added to history
        # before the main loop exits on the next checkpoint
        pass

    return results
```

### Part 3: Helper methods

```python
def _is_cancelled(self) -> bool:
    """Check if graceful cancellation has been requested."""
    if self._coordinator is None:
        return False
    cancellation = getattr(self._coordinator, "cancellation", None)
    if cancellation is None:
        return False
    return getattr(cancellation, "is_cancelled", False)

def _is_immediate_cancel(self) -> bool:
    """Check if immediate (force) cancellation has been requested."""
    if self._coordinator is None:
        return False
    cancellation = getattr(self._coordinator, "cancellation", None)
    if cancellation is None:
        return False
    return getattr(cancellation, "is_immediate", False)
```

### Part 4: Tool registration for visibility

In `_execute_single_tool`, register/complete with cancellation token:

```python
async def _execute_single_tool(self, tool_call: Any) -> ToolResult:
    # Register tool with cancellation token for visibility
    if self._coordinator:
        cancellation = getattr(self._coordinator, "cancellation", None)
        if cancellation and hasattr(cancellation, "register_tool_start"):
            cancellation.register_tool_start(tool_call.id, tool_call.name)

    try:
        # ... existing execution logic ...
    finally:
        # Unregister tool from cancellation token
        if self._coordinator:
            cancellation = getattr(self._coordinator, "cancellation", None)
            if cancellation and hasattr(cancellation, "register_tool_complete"):
                cancellation.register_tool_complete(tool_call.id)
```

---

## Tasks

### Task 1: Write failing tests for cancellation checkpoints

**Files:**
- Create: `modules/loop-agent/tests/test_cancellation.py`

**Step 1: Write the failing tests**

```python
"""Tests for cancellation checkpoints in the agent loop (C-5).

Verifies 3 cancellation checkpoints:
1. Top of loop -- graceful cancel before LLM call
2. After provider call -- immediate cancel before processing response
3. Around tool execution -- cancel during gather, results still added
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, PropertyMock

from amplifier_core.message_models import ChatResponse, ToolCall, Usage
from amplifier_core.models import ToolResult

from amplifier_module_loop_agent.agent_session import AgentSession
from amplifier_module_loop_agent.config import SessionConfig
from amplifier_module_loop_agent.state import SessionState


def _text_response(text: str) -> ChatResponse:
    return ChatResponse(
        content=[{"type": "text", "text": text}],
        tool_calls=None,
        usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
    )


def _tool_response(call_id: str, tool_name: str, args: dict) -> ChatResponse:
    return ChatResponse(
        content=[],
        tool_calls=[ToolCall(id=call_id, name=tool_name, arguments=args)],
        usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
    )


def _make_mock_tool(name: str, output: str = "ok") -> MagicMock:
    tool = MagicMock()
    tool.name = name
    tool.description = f"Mock {name}"
    tool.input_schema = {"type": "object", "properties": {}}
    tool.execute = AsyncMock(return_value=ToolResult(success=True, output=output))
    return tool


def _make_cancellation_mock(is_cancelled: bool = False, is_immediate: bool = False):
    """Create a mock cancellation token."""
    cancel = MagicMock()
    type(cancel).is_cancelled = PropertyMock(return_value=is_cancelled)
    type(cancel).is_immediate = PropertyMock(return_value=is_immediate)
    cancel.register_tool_start = MagicMock()
    cancel.register_tool_complete = MagicMock()
    return cancel


def _make_coordinator(is_cancelled=False, is_immediate=False):
    coord = MagicMock()
    coord.cancellation = _make_cancellation_mock(is_cancelled, is_immediate)
    return coord


def _make_hooks():
    hooks = MagicMock()
    hooks._emitted = []

    async def _recording_emit(event, data):
        hooks._emitted.append((event, data))
        return MagicMock(action="continue")

    hooks.emit = AsyncMock(side_effect=_recording_emit)
    return hooks


@pytest.mark.asyncio
async def test_checkpoint1_graceful_cancel_at_loop_top():
    """Graceful cancel at top of loop exits without calling provider."""
    coordinator = _make_coordinator(is_cancelled=True)
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=_text_response("should not reach"))
    tools = {"read_file": _make_mock_tool("read_file")}
    hooks = _make_hooks()

    session = AgentSession(
        config=SessionConfig(),
        provider=provider,
        tools=tools,
        hooks=hooks,
        coordinator=coordinator,
    )
    result = await session.process_input("do stuff")

    # Provider should NOT be called -- we cancelled before the LLM call
    provider.complete.assert_not_called()
    # Session should end cleanly
    assert session._state_machine.state == SessionState.IDLE


@pytest.mark.asyncio
async def test_checkpoint2_immediate_cancel_after_provider():
    """Immediate cancel after provider call exits before tool execution."""
    # Cancel flag starts False, becomes True after first provider call
    coordinator = _make_coordinator(is_cancelled=False, is_immediate=False)
    call_count = 0

    original_response = _tool_response("tc1", "read_file", {"path": "x.py"})

    async def provider_side_effect(request):
        nonlocal call_count
        call_count += 1
        # After first call, set immediate cancel
        type(coordinator.cancellation).is_immediate = PropertyMock(return_value=True)
        return original_response

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=provider_side_effect)
    tools = {"read_file": _make_mock_tool("read_file")}
    hooks = _make_hooks()

    session = AgentSession(
        config=SessionConfig(),
        provider=provider,
        tools=tools,
        hooks=hooks,
        coordinator=coordinator,
    )
    result = await session.process_input("read x.py")

    # Provider called once, then immediate cancel kicks in
    assert provider.complete.call_count == 1
    # Tool should NOT be executed
    tools["read_file"].execute.assert_not_called()


@pytest.mark.asyncio
async def test_checkpoint3_tool_results_added_on_cancel():
    """When cancelled after tool execution, tool results are still in history."""
    coordinator = _make_coordinator(is_cancelled=False, is_immediate=False)

    async def tool_side_effect(args):
        # Set cancel during tool execution
        type(coordinator.cancellation).is_cancelled = PropertyMock(return_value=True)
        return ToolResult(success=True, output="file contents")

    tool = _make_mock_tool("read_file")
    tool.execute = AsyncMock(side_effect=tool_side_effect)

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=[
        _tool_response("tc1", "read_file", {"path": "x.py"}),
        _text_response("should not reach"),
    ])
    hooks = _make_hooks()

    session = AgentSession(
        config=SessionConfig(),
        provider=provider,
        tools={"read_file": tool},
        hooks=hooks,
        coordinator=coordinator,
    )
    await session.process_input("read x.py")

    # Tool was executed
    tool.execute.assert_called_once()
    # Provider called only once (cancelled before second call)
    assert provider.complete.call_count == 1
    # Tool results were added to history (not orphaned)
    from amplifier_module_loop_agent.turns import ToolResultsTurn
    tool_result_turns = [
        t for t in session._history if isinstance(t, ToolResultsTurn)
    ]
    assert len(tool_result_turns) == 1


@pytest.mark.asyncio
async def test_tool_register_start_complete_called():
    """Tool execution registers with cancellation token for visibility."""
    coordinator = _make_coordinator()
    tool = _make_mock_tool("read_file")
    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=[
        _tool_response("tc1", "read_file", {}),
        _text_response("done"),
    ])
    hooks = _make_hooks()

    session = AgentSession(
        config=SessionConfig(),
        provider=provider,
        tools={"read_file": tool},
        hooks=hooks,
        coordinator=coordinator,
    )
    await session.process_input("read")

    coordinator.cancellation.register_tool_start.assert_called_once_with(
        "tc1", "read_file"
    )
    coordinator.cancellation.register_tool_complete.assert_called_once_with("tc1")


@pytest.mark.asyncio
async def test_no_coordinator_no_crash():
    """Without a coordinator, cancellation checks are no-ops."""
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=_text_response("ok"))
    hooks = _make_hooks()

    session = AgentSession(
        config=SessionConfig(),
        provider=provider,
        tools={"read_file": _make_mock_tool("read_file")},
        hooks=hooks,
        coordinator=None,
    )
    result = await session.process_input("hi")
    assert result == "ok"
```

**Step 2: Run tests to verify they fail**

Run: `cd modules/loop-agent && python -m pytest tests/test_cancellation.py -v`
Expected: FAIL -- `AgentSession.__init__()` does not accept `coordinator` parameter.

### Task 2: Add coordinator parameter to AgentSession

**Files:**
- Modify: `modules/loop-agent/amplifier_module_loop_agent/agent_session.py:76-101`

**Step 1: Add coordinator to `__init__`**

Add `coordinator: Any = None` parameter after `follow_up_queue` in `AgentSession.__init__()`. Store as `self._coordinator = coordinator`.

```python
def __init__(
    self,
    config: SessionConfig,
    provider: Any,
    tools: dict[str, Any],
    hooks: Any,
    steering_queue: SteeringQueue | None = None,
    follow_up_queue: FollowUpQueue | None = None,
    coordinator: Any = None,
    provider_name: str = "",
    model: str = "",
) -> None:
    self._config = config
    self._provider = provider
    self._tools = tools
    self._hooks = hooks
    self._coordinator = coordinator
    # ... rest unchanged
```

**Step 2: Add cancellation helper methods**

Add these methods to `AgentSession` (after the `shutdown` method, around line 593):

```python
# ------------------------------------------------------------------
# Cancellation checks (spec Section 2.4, 2.8)
# ------------------------------------------------------------------

def _is_cancelled(self) -> bool:
    """Check if graceful cancellation has been requested."""
    if self._coordinator is None:
        return False
    cancellation = getattr(self._coordinator, "cancellation", None)
    if cancellation is None:
        return False
    return getattr(cancellation, "is_cancelled", False)

def _is_immediate_cancel(self) -> bool:
    """Check if immediate (force) cancellation has been requested."""
    if self._coordinator is None:
        return False
    cancellation = getattr(self._coordinator, "cancellation", None)
    if cancellation is None:
        return False
    return getattr(cancellation, "is_immediate", False)
```

**Step 3: Verify import**

Run: `cd modules/loop-agent && python -c "from amplifier_module_loop_agent.agent_session import AgentSession; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```
git add modules/loop-agent/amplifier_module_loop_agent/agent_session.py
git commit -m "feat(loop-agent): add coordinator parameter and cancellation helpers"
```

### Task 3: Wire coordinator through from AgentOrchestrator

**Files:**
- Modify: `modules/loop-agent/amplifier_module_loop_agent/__init__.py:117-125`

**Step 1: Pass coordinator to AgentSession constructor**

In `AgentOrchestrator.execute()`, add `coordinator=self._coordinator` to the `AgentSession(...)` constructor call at line 117:

```python
self._session = AgentSession(
    config=config,
    provider=provider,
    tools=all_tools,
    hooks=hooks,
    steering_queue=self._steering_queue,
    follow_up_queue=self._follow_up_queue,
    coordinator=self._coordinator,
    provider_name=provider_name,
)
```

**Step 2: Verify no regression**

Run: `cd modules/loop-agent && python -m pytest tests/test_agent_session.py -v`
Expected: All existing tests PASS.

**Step 3: Commit**

```
git add modules/loop-agent/amplifier_module_loop_agent/__init__.py
git commit -m "feat(loop-agent): pass coordinator to AgentSession for cancellation"
```

### Task 4: Add 3 cancellation checkpoints to process_input

**Files:**
- Modify: `modules/loop-agent/amplifier_module_loop_agent/agent_session.py:244-362`

**Step 1: Add Checkpoint 1 at top of while loop (after line 244)**

Insert after `while round_count < self._config.max_tool_rounds_per_input:`:

```python
    # Checkpoint 1: Graceful cancellation at top of loop
    if self._is_cancelled():
        self._state_machine.complete()
        await self._emit_session_end()
        return await self._process_follow_ups(last_text)
```

**Step 2: Add Checkpoint 2 after provider call (after line 271)**

Insert after the `call_result = await self._call_provider(request)` try/except block (after the except blocks, around line 286):

```python
    # Checkpoint 2: Immediate cancellation after provider call
    if self._is_immediate_cancel():
        self._state_machine.complete()
        await self._emit_session_end()
        return await self._process_follow_ups(last_text)
```

**Step 3: Run tests**

Run: `cd modules/loop-agent && python -m pytest tests/test_cancellation.py::test_checkpoint1_graceful_cancel_at_loop_top tests/test_cancellation.py::test_checkpoint2_immediate_cancel_after_provider -v`
Expected: Both PASS.

**Step 4: Commit**

```
git add modules/loop-agent/amplifier_module_loop_agent/agent_session.py
git commit -m "feat(loop-agent): add cancellation checkpoints 1 and 2 to main loop"
```

### Task 5: Add Checkpoint 3 around tool execution

**Files:**
- Modify: `modules/loop-agent/amplifier_module_loop_agent/agent_session.py:484-489` (`_execute_tool_calls`)
- Modify: `modules/loop-agent/amplifier_module_loop_agent/agent_session.py:491-538` (`_execute_single_tool`)

**Step 1: Add CancelledError handling to `_execute_tool_calls`**

Replace the method:

```python
async def _execute_tool_calls(self, tool_calls: list) -> list[ToolResult]:
    """Execute tool calls in parallel with cancellation support."""
    try:
        results = await asyncio.gather(
            *[self._execute_single_tool(tc) for tc in tool_calls]
        )
        return list(results)
    except asyncio.CancelledError:
        # Immediate cancel during tool execution:
        # Synthesize cancelled results for ALL tool calls to maintain
        # tool_use/tool_result pairing (provider API contract)
        logger.info("Tool execution cancelled - synthesizing cancelled results")
        return [
            ToolResult(
                success=False,
                output="Tool execution was cancelled by user",
            )
            for _ in tool_calls
        ]
```

**Step 2: Add register_tool_start/complete to `_execute_single_tool`**

Wrap the existing body in a try/finally to register/unregister:

```python
async def _execute_single_tool(self, tool_call: Any) -> ToolResult:
    """Execute a single tool call. Never raises -- errors become results."""
    # Register tool with cancellation token for visibility
    if self._coordinator:
        cancellation = getattr(self._coordinator, "cancellation", None)
        if cancellation and hasattr(cancellation, "register_tool_start"):
            cancellation.register_tool_start(tool_call.id, tool_call.name)

    try:
        # ... existing emit, lookup, execute, return logic unchanged ...
        await self._hooks.emit(
            AGENT_TOOL_CALL_START,
            {"tool_name": tool_call.name, "call_id": tool_call.id},
        )
        # ... rest of existing implementation ...
    finally:
        # Unregister tool from cancellation token
        if self._coordinator:
            cancellation = getattr(self._coordinator, "cancellation", None)
            if cancellation and hasattr(cancellation, "register_tool_complete"):
                cancellation.register_tool_complete(tool_call.id)
```

**Step 3: Run all cancellation tests**

Run: `cd modules/loop-agent && python -m pytest tests/test_cancellation.py -v`
Expected: All 5 tests PASS.

**Step 4: Run full test suite**

Run: `cd modules/loop-agent && python -m pytest tests/ -v`
Expected: All tests PASS (existing + new).

**Step 5: Commit**

```
git add modules/loop-agent/amplifier_module_loop_agent/agent_session.py
git commit -m "feat(loop-agent): add cancellation checkpoint 3 with tool registration (C-5)

Three cancellation checkpoints following loop-basic pattern:
1. Top of loop: graceful cancel before LLM call
2. After provider call: immediate cancel before tool execution
3. Around tool execution: CancelledError handling + register_start/complete

Critical invariant preserved: tool results are always added to context
before returning on cancel, preventing orphaned tool_use blocks that
violate provider API contracts.

Spec: Section 2.4, 2.8 (abort signal / stop conditions)
Fixes: C-5 from adversarial review"
```

---

## Backward Compatibility

- **No breaking changes.** The `coordinator` parameter defaults to `None`. When `None`, all `_is_cancelled()` and `_is_immediate_cancel()` calls return `False`, matching pre-fix behavior.
- Existing tests use `MagicMock()` as the coordinator passed to `AgentOrchestrator`. Since the mock's `.cancellation.is_cancelled` attribute defaults to a MagicMock (truthy), we need to verify existing tests still pass. The `getattr(..., "is_cancelled", False)` pattern handles this safely since it checks the actual attribute.
- The `register_tool_start`/`register_tool_complete` calls are guarded by `hasattr` checks, so they're no-ops if the cancellation object doesn't support them.

## Dependencies on Upstream Fixes

- **amplifier-core `CancellationToken`**: The `coordinator.cancellation` object with `is_cancelled`, `is_immediate`, `register_tool_start`, and `register_tool_complete` must exist. This is already implemented in amplifier-core as used by loop-basic.
- **No blocking dependencies.** The implementation is defensive (checks for `None`, uses `getattr` with defaults) so it works even if the cancellation API evolves.

## PR Details

**Branch:** `track1/1a2-cancellation`
**Title:** `feat(loop-agent): add 3 cancellation checkpoints to agent loop (C-5)`
**Labels:** `track1`, `agent-loop`, `spec-compliance`, `critical`
**Reviewers:** @bkrabach
