# Track 1-1A1: Wire Tool Truncation Into Agent Loop

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** After the `hooks-tool-truncation` hook fires on `tool:post`, read back its modified data and use the truncated output as the `ToolResult` sent to the LLM, while preserving full output in the event stream.

**Architecture:** The `hooks-tool-truncation` module already registers on `tool:post` and returns `HookResult(action="modify", data={"result": truncated, "full_output": original})`. The loop-agent's `_execute_single_tool()` currently emits `AGENT_TOOL_CALL_END` but never reads back modified data from `tool:post`. We need to emit the `tool:post` event, check the returned `HookResult`, and if `action="modify"`, use `data["result"]` as the content fed to the LLM.

**Tech Stack:** Python, amplifier-core HookResult protocol, asyncio

**Spec Reference:** coding-agent-loop-spec Section 5 (Tool Output and Context Management), Section 3.8 (Tool execution pipeline steps: EXECUTE -> TRUNCATE -> EMIT -> RETURN)

**Adversarial Review Reference:** C-4

---

## Problem Statement

The `hooks-tool-truncation` module exists with 34 tests, but no code in the agent loop reads the `HookResult` returned by the `tool:post` emission. When a tool returns 100KB of output, the full untruncated content is stored as the `ToolResult` and sent to the LLM, blowing out the context window. The truncation hook fires but its output is ignored.

## Root Cause

**File:** `modules/loop-agent/amplifier_module_loop_agent/agent_session.py`
**Lines:** 514-525 (the success path in `_execute_single_tool`)

Current code emits `AGENT_TOOL_CALL_END` but does NOT emit `tool:post` (the Amplifier hook event that truncation registers on), and does NOT read back any `HookResult`:

```python
# Current code (lines 514-525)
try:
    result = await tool.execute(tool_call.arguments)
    duration_ms = (time.monotonic() - start_time) * 1000
    await self._hooks.emit(
        AGENT_TOOL_CALL_END,
        {
            "call_id": tool_call.id,
            "output": str(result.output) if result.output else "",
            "duration_ms": duration_ms,
        },
    )
    return result
```

The `AGENT_TOOL_CALL_END` event is an agent-level event. The truncation hook listens on Amplifier's `tool:post` event (from `amplifier_core.events.TOOL_POST`). There is no `tool:post` emission in the agent loop at all.

## The Fix

### Approach

1. Import `TOOL_POST` from `amplifier_core.events` into `agent_session.py`.
2. After tool execution succeeds, emit `tool:post` with the result data.
3. Check the returned `HookResult` -- if `action="modify"` and `data` contains a `"result"` key, use the modified (truncated) result for the `ToolResult` sent to the LLM.
4. Continue emitting `AGENT_TOOL_CALL_END` with the **full** untruncated output (for the event stream / host UI).

### Before/After

**Before** (`agent_session.py:514-525`):
```python
try:
    result = await tool.execute(tool_call.arguments)
    duration_ms = (time.monotonic() - start_time) * 1000
    await self._hooks.emit(
        AGENT_TOOL_CALL_END,
        {
            "call_id": tool_call.id,
            "output": str(result.output) if result.output else "",
            "duration_ms": duration_ms,
        },
    )
    return result
```

**After**:
```python
try:
    result = await tool.execute(tool_call.arguments)
    duration_ms = (time.monotonic() - start_time) * 1000

    # Serialize result for the tool:post hook
    raw_output = result.get_serialized_output()

    # Emit tool:post for hooks (truncation, logging, etc.)
    post_result = await self._hooks.emit(
        TOOL_POST,
        {
            "tool_name": tool_call.name,
            "tool_input": tool_call.arguments,
            "result": raw_output,
            "call_id": tool_call.id,
        },
    )

    # If a hook modified the result (e.g. truncation), use the
    # modified output for the LLM while preserving full output
    # in the event stream.
    llm_output = raw_output
    if (
        hasattr(post_result, "action")
        and post_result.action == "modify"
        and hasattr(post_result, "data")
        and post_result.data
        and "result" in post_result.data
    ):
        llm_output = post_result.data["result"]

    # Emit agent:tool_call_end with FULL untruncated output
    # (spec: TOOL_CALL_END carries full output for host/UI)
    await self._hooks.emit(
        AGENT_TOOL_CALL_END,
        {
            "call_id": tool_call.id,
            "output": raw_output,
            "duration_ms": duration_ms,
        },
    )

    # Return result with potentially truncated output for LLM
    return ToolResult(success=result.success, output=llm_output)
```

### Import Change

Add to imports at top of `agent_session.py` (line 36 area, in the events import block):

```python
from amplifier_core.events import TOOL_POST
```

---

## Tasks

### Task 1: Write failing integration test for truncation wiring

**Files:**
- Create: `modules/loop-agent/tests/test_truncation_wiring.py`

**Step 1: Write the failing test**

```python
"""Tests for tool output truncation wiring in the agent loop (C-4).

Verifies that when hooks-tool-truncation is active, the agent loop:
1. Emits tool:post after tool execution
2. Reads back HookResult(action="modify") data
3. Uses truncated output for the ToolResult sent to LLM
4. Preserves full output in agent:tool_call_end event
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from amplifier_core.events import TOOL_POST
from amplifier_core.message_models import ChatResponse, ToolCall, Usage
from amplifier_core.models import HookResult, ToolResult

from amplifier_module_loop_agent import AgentOrchestrator
from amplifier_module_loop_agent.events import AGENT_TOOL_CALL_END


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


@pytest.mark.asyncio
async def test_tool_post_emitted_after_execution():
    """tool:post event is emitted after each tool execution."""
    big_output = "x" * 100_000
    tool = _make_mock_tool("read_file", output=big_output)

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=[
        _tool_response("tc1", "read_file", {"path": "big.txt"}),
        _text_response("done"),
    ])

    emitted_events: list[tuple[str, dict]] = []

    async def recording_emit(event: str, data: dict):
        emitted_events.append((event, data))
        # Simulate truncation hook on tool:post
        if event == "tool:post":
            return HookResult(
                action="modify",
                data={
                    "result": "truncated_output",
                    "full_output": data.get("result"),
                },
            )
        return MagicMock(action="continue")

    hooks = MagicMock()
    hooks.emit = AsyncMock(side_effect=recording_emit)

    orch = AgentOrchestrator(coordinator=MagicMock(), config={})
    await orch.execute("read big.txt", MagicMock(), {"test": provider},
                       {"read_file": tool}, hooks)

    # Verify tool:post was emitted
    post_events = [(e, d) for e, d in emitted_events if e == "tool:post"]
    assert len(post_events) == 1
    assert post_events[0][1]["tool_name"] == "read_file"
    assert post_events[0][1]["result"] == big_output


@pytest.mark.asyncio
async def test_truncated_output_sent_to_llm():
    """When tool:post returns modify, the LLM sees truncated output."""
    big_output = "x" * 100_000
    truncated = "truncated_version"
    tool = _make_mock_tool("read_file", output=big_output)

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=[
        _tool_response("tc1", "read_file", {"path": "big.txt"}),
        _text_response("done"),
    ])

    async def truncating_emit(event: str, data: dict):
        if event == "tool:post":
            return HookResult(
                action="modify",
                data={"result": truncated, "full_output": data.get("result")},
            )
        return MagicMock(action="continue")

    hooks = MagicMock()
    hooks.emit = AsyncMock(side_effect=truncating_emit)

    orch = AgentOrchestrator(coordinator=MagicMock(), config={})
    await orch.execute("read big.txt", MagicMock(), {"test": provider},
                       {"read_file": tool}, hooks)

    # The second LLM call should contain the truncated tool result
    second_request = provider.complete.call_args_list[1][0][0]
    tool_messages = [m for m in second_request.messages if m.role == "tool"]
    assert len(tool_messages) == 1
    # The tool result content sent to LLM should be the truncated version
    assert tool_messages[0].content == truncated


@pytest.mark.asyncio
async def test_full_output_in_tool_call_end_event():
    """agent:tool_call_end event carries full untruncated output."""
    big_output = "x" * 100_000
    tool = _make_mock_tool("read_file", output=big_output)

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=[
        _tool_response("tc1", "read_file", {"path": "big.txt"}),
        _text_response("done"),
    ])

    emitted_events: list[tuple[str, dict]] = []

    async def recording_emit(event: str, data: dict):
        emitted_events.append((event, data))
        if event == "tool:post":
            return HookResult(
                action="modify",
                data={"result": "short", "full_output": data.get("result")},
            )
        return MagicMock(action="continue")

    hooks = MagicMock()
    hooks.emit = AsyncMock(side_effect=recording_emit)

    orch = AgentOrchestrator(coordinator=MagicMock(), config={})
    await orch.execute("read big.txt", MagicMock(), {"test": provider},
                       {"read_file": tool}, hooks)

    # agent:tool_call_end should have the FULL output
    end_events = [(e, d) for e, d in emitted_events
                  if e == "agent:tool_call_end"]
    assert len(end_events) == 1
    assert end_events[0][1]["output"] == big_output


@pytest.mark.asyncio
async def test_no_truncation_when_hook_continues():
    """When tool:post returns action=continue, output is unchanged."""
    tool = _make_mock_tool("read_file", output="small output")

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=[
        _tool_response("tc1", "read_file", {}),
        _text_response("done"),
    ])

    async def passthrough_emit(event: str, data: dict):
        return MagicMock(action="continue")

    hooks = MagicMock()
    hooks.emit = AsyncMock(side_effect=passthrough_emit)

    orch = AgentOrchestrator(coordinator=MagicMock(), config={})
    await orch.execute("read", MagicMock(), {"test": provider},
                       {"read_file": tool}, hooks)

    second_request = provider.complete.call_args_list[1][0][0]
    tool_messages = [m for m in second_request.messages if m.role == "tool"]
    assert len(tool_messages) == 1
    assert "small output" in tool_messages[0].content
```

**Step 2: Run tests to verify they fail**

Run: `cd modules/loop-agent && python -m pytest tests/test_truncation_wiring.py -v`
Expected: FAIL -- `tool:post` is never emitted, truncated output never read back.

### Task 2: Import TOOL_POST event constant

**Files:**
- Modify: `modules/loop-agent/amplifier_module_loop_agent/agent_session.py:36-53`

**Step 1: Add the import**

In the events import block (line 36), add `TOOL_POST` to the imports from `amplifier_core.events`. The existing import block at lines 36-53 currently imports agent events. Add:

```python
from amplifier_core.events import TOOL_POST
```

This can go right after the existing `amplifier_core.events` imports or alongside the existing re-exports in `events.py`.

**Step 2: Verify import resolves**

Run: `cd modules/loop-agent && python -c "from amplifier_module_loop_agent.agent_session import AgentSession; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```
git add modules/loop-agent/amplifier_module_loop_agent/agent_session.py
git commit -m "feat(loop-agent): import TOOL_POST event for truncation wiring"
```

### Task 3: Wire tool:post emission and read back HookResult

**Files:**
- Modify: `modules/loop-agent/amplifier_module_loop_agent/agent_session.py:514-525`

**Step 1: Replace the success path in `_execute_single_tool`**

Replace lines 514-525 (the `try` block's success path) with the new code from the "After" section above. The key changes:

1. Call `result.get_serialized_output()` to get the raw string output.
2. Emit `TOOL_POST` with `tool_name`, `tool_input`, `result`, and `call_id`.
3. Check `post_result.action == "modify"` and read `post_result.data["result"]`.
4. Emit `AGENT_TOOL_CALL_END` with the **full** raw output.
5. Return `ToolResult(success=result.success, output=llm_output)` with potentially truncated output.

**Step 2: Run the new tests to verify they pass**

Run: `cd modules/loop-agent && python -m pytest tests/test_truncation_wiring.py -v`
Expected: All 4 tests PASS.

**Step 3: Run existing tests to verify no regressions**

Run: `cd modules/loop-agent && python -m pytest tests/test_agent_session.py -v`
Expected: All existing tests PASS.

**Step 4: Commit**

```
git add modules/loop-agent/amplifier_module_loop_agent/agent_session.py
git commit -m "feat(loop-agent): wire tool:post emission and read truncated output (C-4)

After tool execution, emit tool:post event so hooks like
hooks-tool-truncation can modify the result. If a hook returns
action='modify' with truncated data, the LLM receives the truncated
version while agent:tool_call_end preserves full output for the
host/UI event stream.

Spec: Section 5 (Tool Output and Context Management)
Fixes: C-4 from adversarial review"
```

---

## Backward Compatibility

- **No breaking changes.** If no `tool:post` hook is registered, `hooks.emit()` returns `HookResult(action="continue")` and the code falls through to the original behavior (full output sent to LLM).
- The `AGENT_TOOL_CALL_END` event now always carries the full raw output string rather than `str(result.output)`. This is actually closer to spec (TOOL_CALL_END should carry full untruncated output).
- Existing tests that use `MagicMock(action="continue")` as the emit return value will continue to work unchanged.

## Dependencies on Upstream Fixes

- **None.** The `hooks-tool-truncation` module already exists and works. The `TOOL_POST` event constant exists in `amplifier_core.events`. This fix only wires the existing pieces together.
- The truncation hook only needs to be mounted in the bundle config to activate. Without it, this change is a no-op (emit fires, nobody listens, `action="continue"` returned).

## PR Details

**Branch:** `track1/1a1-wire-truncation`
**Title:** `feat(loop-agent): wire tool output truncation into agent loop (C-4)`
**Labels:** `track1`, `agent-loop`, `spec-compliance`
**Reviewers:** @bkrabach
