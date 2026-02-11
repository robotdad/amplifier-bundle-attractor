# Track 1-1A6: Fix SESSION_END Emission Timing

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Move `SESSION_END` emission to after the follow-up queue is fully drained, so host applications receive the completion signal only when all queued work is truly done.

**Architecture:** Currently, `process_input()` emits `SESSION_END` before calling `_process_follow_ups()`. This means the host gets a premature completion signal while follow-up messages are still being processed. The fix reorders these two operations: process follow-ups first, then emit `SESSION_END` only once at the very end.

**Tech Stack:** Python, asyncio

**Spec Reference:** coding-agent-loop-spec Section 2.5 (lines 295-302): "Process follow-up messages if any are queued... session.state = IDLE... session.emit(SESSION_END)"

**Adversarial Review Reference:** H-1

---

## Problem Statement

The spec pseudocode shows this exact order:

```
    IF session.followup_queue IS NOT EMPTY:
        next_input = session.followup_queue.DEQUEUE()
        process_input(session, next_input)
        RETURN

    session.state = IDLE
    session.emit(SESSION_END)
```

The follow-up queue is drained **before** `SESSION_END` is emitted. But the current implementation does the opposite:

1. Emits `SESSION_END`
2. Then processes follow-ups (which themselves emit more `SESSION_END` events)

This causes multiple premature `SESSION_END` emissions and the host sees "session ended" before the agent is actually done.

## Root Cause

**File:** `modules/loop-agent/amplifier_module_loop_agent/agent_session.py`
**Lines:** 333-362 (two locations in `process_input`)

**Location 1: Natural completion path (lines 333-338)**

```python
# Current code (natural completion)
if not tool_calls:
    self._state_machine.complete()  # PROCESSING -> IDLE
    await self._emit_session_end()              # <-- emits BEFORE follow-ups
    return await self._process_follow_ups(text) # <-- follow-ups happen AFTER
```

**Location 2: Round limit path (lines 357-362)**

```python
# Current code (round limit reached)
await self._hooks.emit(AGENT_TURN_LIMIT, {"round_count": round_count})
self._state_machine.complete()  # PROCESSING -> IDLE
await self._emit_session_end()              # <-- emits BEFORE follow-ups
return await self._process_follow_ups(last_text) # <-- follow-ups happen AFTER
```

Both paths emit `SESSION_END` then call `_process_follow_ups()`. And `_process_follow_ups` calls `process_input()` recursively, which will emit **more** `SESSION_END` events for each follow-up. The result: N+1 `SESSION_END` events for N follow-up messages.

**File:** `modules/loop-agent/amplifier_module_loop_agent/agent_session.py`
**Lines:** 637-649 (`_process_follow_ups`)

```python
async def _process_follow_ups(self, last_result: str) -> str:
    result = last_result
    next_msg = self._follow_up_queue.drain()
    while next_msg is not None:
        result = await self.process_input(next_msg)  # <-- recursive, emits SESSION_END each time
        next_msg = self._follow_up_queue.drain()
    return result
```

## The Fix

### Approach

1. **Remove `_emit_session_end()` from both completion paths** in `process_input()`.
2. **Add `SESSION_END` emission to `_process_follow_ups()`** after the follow-up queue is fully drained.
3. **Add a `_is_recursive` flag** so recursive `process_input()` calls (from follow-ups) don't emit `SESSION_END` -- only the outermost call does.

### Before/After

**Before (natural completion, lines 333-338):**
```python
if not tool_calls:
    self._state_machine.complete()
    await self._emit_session_end()
    return await self._process_follow_ups(text)
```

**After:**
```python
if not tool_calls:
    self._state_machine.complete()
    # SESSION_END emitted after follow-ups are fully drained
    return await self._process_follow_ups(text)
```

**Before (round limit, lines 357-362):**
```python
await self._hooks.emit(AGENT_TURN_LIMIT, {"round_count": round_count})
self._state_machine.complete()
await self._emit_session_end()
return await self._process_follow_ups(last_text)
```

**After:**
```python
await self._hooks.emit(AGENT_TURN_LIMIT, {"round_count": round_count})
self._state_machine.complete()
# SESSION_END emitted after follow-ups are fully drained
return await self._process_follow_ups(last_text)
```

**Before (`_process_follow_ups`, lines 637-649):**
```python
async def _process_follow_ups(self, last_result: str) -> str:
    result = last_result
    next_msg = self._follow_up_queue.drain()
    while next_msg is not None:
        result = await self.process_input(next_msg)
        next_msg = self._follow_up_queue.drain()
    return result
```

**After:**
```python
async def _process_follow_ups(self, last_result: str, *, _emit_end: bool = True) -> str:
    """Process queued follow-up messages after the loop completes.

    Recursively calls process_input() for each follow-up message.
    Emits SESSION_END only after the entire queue is drained (spec
    Section 2.5: SESSION_END after follow-ups complete).

    Args:
        last_result: Result from the just-completed loop iteration.
        _emit_end: If True (default), emit SESSION_END after queue
            is drained. Internal recursive calls pass False.
    """
    result = last_result
    next_msg = self._follow_up_queue.drain()
    while next_msg is not None:
        # Set _processing_follow_up so nested process_input calls
        # don't emit their own SESSION_END
        self._processing_follow_up = True
        result = await self.process_input(next_msg)
        next_msg = self._follow_up_queue.drain()
    self._processing_follow_up = False

    # Emit SESSION_END exactly once, after all follow-ups are done
    if _emit_end:
        await self._emit_session_end()
    return result
```

**And guard the recursive calls:** In `process_input()`, when calling `_process_follow_ups`, pass `_emit_end=not self._processing_follow_up`:

Actually, the cleaner approach is simpler. Remove `SESSION_END` from the two completion points. In `_process_follow_ups`, always emit `SESSION_END` at the end. During recursive calls from `process_input` -> `_process_follow_ups` -> `process_input`, the inner `process_input` will call `_process_follow_ups` again, but if the queue is empty it just emits `SESSION_END` and returns. This means we get one `SESSION_END` per `process_input` call. To get exactly one, we use a depth flag:

```python
# In __init__:
self._follow_up_depth = 0
```

**Revised `_process_follow_ups`:**
```python
async def _process_follow_ups(self, last_result: str) -> str:
    """Process queued follow-up messages after the loop completes.

    Calls process_input() for each follow-up. Emits SESSION_END
    only from the outermost call (spec: SESSION_END after all
    follow-ups fully drained).
    """
    result = last_result
    self._follow_up_depth += 1
    try:
        next_msg = self._follow_up_queue.drain()
        while next_msg is not None:
            result = await self.process_input(next_msg)
            next_msg = self._follow_up_queue.drain()
    finally:
        self._follow_up_depth -= 1

    # Emit SESSION_END only from the outermost follow-up call
    if self._follow_up_depth == 0:
        await self._emit_session_end()

    return result
```

---

## Tasks

### Task 1: Write failing tests for SESSION_END timing

**Files:**
- Create: `modules/loop-agent/tests/test_session_end_timing.py`

**Step 1: Write the failing tests**

```python
"""Tests for SESSION_END emission timing (H-1).

Verifies that:
1. SESSION_END is emitted exactly once per process_input() call
2. SESSION_END is emitted AFTER follow-ups are fully drained
3. No premature SESSION_END before follow-up processing
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from amplifier_core.message_models import ChatResponse, Usage

from amplifier_module_loop_agent.agent_session import AgentSession
from amplifier_module_loop_agent.config import SessionConfig
from amplifier_module_loop_agent.steering import FollowUpQueue


def _text_response(text: str) -> ChatResponse:
    return ChatResponse(
        content=[{"type": "text", "text": text}],
        tool_calls=None,
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


def _make_mock_tool(name: str) -> MagicMock:
    from amplifier_core.models import ToolResult

    tool = MagicMock()
    tool.name = name
    tool.description = f"Mock {name}"
    tool.input_schema = {"type": "object", "properties": {}}
    tool.execute = AsyncMock(return_value=ToolResult(success=True, output="ok"))
    return tool


@pytest.mark.asyncio
async def test_session_end_emitted_exactly_once_no_followups():
    """Without follow-ups, SESSION_END is emitted exactly once."""
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=_text_response("done."))
    hooks = _make_hooks()

    session = AgentSession(
        config=SessionConfig(),
        provider=provider,
        tools={"read_file": _make_mock_tool("read_file")},
        hooks=hooks,
    )
    await session.process_input("do it")

    session_end_events = [
        e for e, _ in hooks._emitted if e == "agent:session_end"
    ]
    assert len(session_end_events) == 1


@pytest.mark.asyncio
async def test_session_end_after_followups_drained():
    """SESSION_END comes AFTER all follow-ups are processed."""
    follow_up_queue = FollowUpQueue()
    follow_up_queue.follow_up("follow-up message")

    call_count = 0

    async def provider_side_effect(request):
        nonlocal call_count
        call_count += 1
        return _text_response(f"Response {call_count}.")

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=provider_side_effect)
    hooks = _make_hooks()

    session = AgentSession(
        config=SessionConfig(),
        provider=provider,
        tools={"read_file": _make_mock_tool("read_file")},
        hooks=hooks,
        follow_up_queue=follow_up_queue,
    )
    result = await session.process_input("start")

    # Both the original and follow-up were processed
    assert provider.complete.call_count == 2

    # SESSION_END should be emitted exactly ONCE
    session_end_events = [
        e for e, _ in hooks._emitted if e == "agent:session_end"
    ]
    assert len(session_end_events) == 1


@pytest.mark.asyncio
async def test_session_end_is_last_lifecycle_event():
    """SESSION_END is the last lifecycle event emitted."""
    follow_up_queue = FollowUpQueue()
    follow_up_queue.follow_up("followup 1")

    call_count = 0

    async def provider_side_effect(request):
        nonlocal call_count
        call_count += 1
        return _text_response(f"Response {call_count}.")

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=provider_side_effect)
    hooks = _make_hooks()

    session = AgentSession(
        config=SessionConfig(),
        provider=provider,
        tools={},
        hooks=hooks,
        follow_up_queue=follow_up_queue,
    )
    await session.process_input("go")

    # Find the index of SESSION_END
    events = [e for e, _ in hooks._emitted]
    session_end_indices = [
        i for i, e in enumerate(events) if e == "agent:session_end"
    ]
    assert len(session_end_indices) == 1

    session_end_idx = session_end_indices[0]

    # No agent:user_input or agent:assistant_text_end events AFTER session_end
    for i in range(session_end_idx + 1, len(events)):
        assert events[i] not in (
            "agent:user_input",
            "agent:assistant_text_end",
        ), f"Event {events[i]} emitted after SESSION_END at index {i}"


@pytest.mark.asyncio
async def test_multiple_followups_single_session_end():
    """Multiple follow-ups in queue -> still exactly one SESSION_END."""
    follow_up_queue = FollowUpQueue()
    follow_up_queue.follow_up("followup 1")
    follow_up_queue.follow_up("followup 2")
    follow_up_queue.follow_up("followup 3")

    call_count = 0

    async def provider_side_effect(request):
        nonlocal call_count
        call_count += 1
        return _text_response(f"Response {call_count}.")

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=provider_side_effect)
    hooks = _make_hooks()

    session = AgentSession(
        config=SessionConfig(),
        provider=provider,
        tools={},
        hooks=hooks,
        follow_up_queue=follow_up_queue,
    )
    await session.process_input("go")

    # 1 original + 3 follow-ups = 4 provider calls
    assert provider.complete.call_count == 4

    # Exactly one SESSION_END
    session_end_events = [
        e for e, _ in hooks._emitted if e == "agent:session_end"
    ]
    assert len(session_end_events) == 1
```

**Step 2: Run tests to verify they fail**

Run: `cd modules/loop-agent && python -m pytest tests/test_session_end_timing.py -v`
Expected: FAIL -- `test_session_end_after_followups_drained` and `test_multiple_followups_single_session_end` fail because multiple SESSION_END events are emitted.

### Task 2: Add `_follow_up_depth` tracking to `__init__`

**Files:**
- Modify: `modules/loop-agent/amplifier_module_loop_agent/agent_session.py:76-101`

**Step 1: Add the depth counter**

In `AgentSession.__init__()`, add after `self._loop_detector` initialization (around line 97):

```python
self._follow_up_depth = 0  # Tracks follow-up recursion depth for SESSION_END timing
```

**Step 2: Commit**

```
git add modules/loop-agent/amplifier_module_loop_agent/agent_session.py
git commit -m "feat(loop-agent): add follow-up depth counter for SESSION_END timing"
```

### Task 3: Remove SESSION_END from completion paths, fix `_process_follow_ups`

**Files:**
- Modify: `modules/loop-agent/amplifier_module_loop_agent/agent_session.py:333-362`
- Modify: `modules/loop-agent/amplifier_module_loop_agent/agent_session.py:637-649`

**Step 1: Remove `_emit_session_end()` from natural completion path**

Change lines 333-338 from:

```python
if not tool_calls:
    self._state_machine.complete()
    await self._emit_session_end()
    return await self._process_follow_ups(text)
```

To:

```python
if not tool_calls:
    self._state_machine.complete()
    return await self._process_follow_ups(text)
```

**Step 2: Remove `_emit_session_end()` from round limit path**

Change lines 357-362 from:

```python
await self._hooks.emit(AGENT_TURN_LIMIT, {"round_count": round_count})
self._state_machine.complete()
await self._emit_session_end()
return await self._process_follow_ups(last_text)
```

To:

```python
await self._hooks.emit(AGENT_TURN_LIMIT, {"round_count": round_count})
self._state_machine.complete()
return await self._process_follow_ups(last_text)
```

**Step 3: Rewrite `_process_follow_ups` with depth tracking**

Replace lines 637-649 with:

```python
async def _process_follow_ups(self, last_result: str) -> str:
    """Process queued follow-up messages after the loop completes.

    Calls process_input() for each follow-up message. Emits
    SESSION_END only from the outermost call, after the entire
    follow-up queue is fully drained (spec Section 2.5).
    """
    result = last_result
    self._follow_up_depth += 1
    try:
        next_msg = self._follow_up_queue.drain()
        while next_msg is not None:
            result = await self.process_input(next_msg)
            next_msg = self._follow_up_queue.drain()
    finally:
        self._follow_up_depth -= 1

    # Emit SESSION_END only from the outermost follow-up call
    if self._follow_up_depth == 0:
        await self._emit_session_end()

    return result
```

**Step 4: Run all SESSION_END timing tests**

Run: `cd modules/loop-agent && python -m pytest tests/test_session_end_timing.py -v`
Expected: All 4 tests PASS.

**Step 5: Run existing tests for regression**

Run: `cd modules/loop-agent && python -m pytest tests/test_agent_session.py -v`
Expected: All existing tests PASS. (No existing tests use follow-ups, so the behavioral change is transparent. SESSION_END still emits exactly once for simple cases.)

**Step 6: Commit**

```
git add modules/loop-agent/amplifier_module_loop_agent/agent_session.py
git commit -m "fix(loop-agent): emit SESSION_END after follow-up queue fully drained (H-1)

Previously SESSION_END was emitted before processing follow-ups,
causing premature completion signals and N+1 SESSION_END events
when N follow-up messages were queued.

Now SESSION_END is emitted exactly once, from the outermost
_process_follow_ups() call, after the entire queue is drained.
Uses a depth counter to prevent nested process_input() calls from
emitting their own SESSION_END events.

Spec: Section 2.5 (follow-up processing before SESSION_END)
Fixes: H-1 from adversarial review"
```

---

## Backward Compatibility

- **Behavioral change:** `SESSION_END` is now emitted once instead of N+1 times when follow-ups are queued. This is the **correct** behavior per spec.
- **Host applications** that relied on the first `SESSION_END` emission to detect completion of the initial input will now see it later (after follow-ups). This is the intended behavior -- the session isn't done until all work is done.
- **No API changes.** The event name, data structure, and public method signatures are unchanged.

## Dependencies on Upstream Fixes

- **None.** This is a pure reordering of existing operations within `agent_session.py`.
- **Note:** If track1-1a4 (AWAITING_INPUT) is implemented first, the natural completion branch will have an additional `if/else` for question detection. The `SESSION_END` removal applies to the `else` branch (the non-question path). The AWAITING_INPUT path already correctly does NOT emit SESSION_END.

## PR Details

**Branch:** `track1/1a6-session-end-timing`
**Title:** `fix(loop-agent): emit SESSION_END after follow-up queue fully drained (H-1)`
**Labels:** `track1`, `agent-loop`, `spec-compliance`
**Reviewers:** @bkrabach
