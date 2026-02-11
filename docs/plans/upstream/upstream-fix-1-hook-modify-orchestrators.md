# Upstream Fix 1: Hook `modify` Action Not Read by Any Orchestrator

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Fix all 3 existing orchestrators to read `HookResult(action="modify")` data from `tool:post` events, enabling any hook to modify tool output before it reaches the LLM.
**Architecture:** After emitting `tool:post`, each orchestrator checks if the returned `HookResult` has `action="modify"` with non-null `data`. If so, the modified result replaces the original `get_serialized_output()` content. This unlocks the truncation hook, redaction hooks, and any future tool-output-transforming hook.
**Tech Stack:** Python, amplifier-core HookResult protocol, 3 orchestrator modules

---

### Task 1: Fix `loop-basic` to read `modify` action from `tool:post`

**Files:**
- Modify: `amplifier-module-loop-basic/amplifier_module_loop_basic/__init__.py:434-470`
- Test: `amplifier-module-loop-basic/tests/test_hook_modify.py`

**Step 1: Write the failing test**

```python
# tests/test_hook_modify.py
import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from amplifier_core.models import HookResult


@pytest.mark.asyncio
async def test_tool_post_modify_replaces_result():
    """When a hook returns action='modify' on tool:post, the modified data
    should be used instead of the original get_serialized_output()."""
    from amplifier_module_loop_basic import BasicOrchestrator

    # Create a mock tool whose execute returns original content
    mock_tool = MagicMock()
    mock_tool.name = "test_tool"
    mock_tool.description = "A test tool"
    mock_tool.input_schema = {"type": "object", "properties": {}}
    original_result = MagicMock()
    original_result.get_serialized_output.return_value = '{"original": true}'
    original_result.to_dict.return_value = {"original": True}
    mock_tool.execute = AsyncMock(return_value=original_result)

    # Create a mock hooks registry that returns action="modify" with new data
    modified_data = {"result": {"modified": True, "truncated": True}}
    mock_hooks = AsyncMock()
    mock_hooks.emit = AsyncMock(return_value=HookResult(action="modify", data=modified_data))

    # Create a mock provider that returns a response with a tool call
    mock_response = MagicMock()
    mock_response.content = []
    mock_response.tool_calls = [
        MagicMock(id="tc_1", name="test_tool", arguments={"key": "value"})
    ]
    mock_response.usage = None
    mock_response.model = "test-model"

    # Second call returns text (no tool calls) to end the loop
    text_response = MagicMock()
    text_response.content = [MagicMock(type="text", text="Done")]
    text_response.tool_calls = []
    text_response.usage = None
    text_response.model = "test-model"

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(side_effect=[mock_response, text_response])
    mock_provider.parse_tool_calls = MagicMock(side_effect=[
        [MagicMock(id="tc_1", name="test_tool", arguments={"key": "value"})],
        [],
    ])

    # Run the orchestrator and capture what gets added to context
    # The tool result message content should contain the MODIFIED data, not the original
    orchestrator = BasicOrchestrator(MagicMock(), {"max_iterations": 5})
    # ... (wire up tools, providers, hooks, context, run execute)
    # Assert that the tool result added to context contains modified data
    # The key assertion: result.get_serialized_output() should NOT have been used
    # Instead, the modified data from the hook should appear in the tool result message
```

**Step 2: Run test to verify it fails**

Run: `cd amplifier-module-loop-basic && uv run pytest tests/test_hook_modify.py -v`
Expected: FAIL — the test will show the original data is used, not the modified data

**Step 3: Write minimal implementation**

In `amplifier_module_loop_basic/__init__.py`, find line ~467 where `result.get_serialized_output()` is called after `tool:post` emission. The current code is:

```python
# BEFORE (line ~449-467):
# ... ephemeral injection handling for inject_context ...

result_content = result.get_serialized_output()
return (tool_call_id, result_content)
```

Change to:

```python
# AFTER:
# ... ephemeral injection handling for inject_context ...

# Check if a hook modified the tool result via action="modify"
if post_result and post_result.action == "modify" and post_result.data is not None:
    modified_result = post_result.data.get("result", None)
    if modified_result is not None:
        if isinstance(modified_result, (dict, list)):
            result_content = json.dumps(modified_result)
        else:
            result_content = str(modified_result)
    else:
        result_content = result.get_serialized_output()
else:
    result_content = result.get_serialized_output()
return (tool_call_id, result_content)
```

Also add `import json` at the top of the file if not already present.

**Step 4: Run test to verify it passes**

Run: `cd amplifier-module-loop-basic && uv run pytest tests/test_hook_modify.py -v`
Expected: PASS

**Step 5: Run full test suite to verify no regressions**

Run: `cd amplifier-module-loop-basic && uv run pytest -v`
Expected: All existing tests PASS

**Step 6: Commit**

```bash
cd amplifier-module-loop-basic
git checkout -b fix/hook-modify-tool-post
git add amplifier_module_loop_basic/__init__.py tests/test_hook_modify.py
git commit -m "fix: read HookResult modify action from tool:post events

When a hook returns action='modify' on tool:post, the orchestrator now
uses the modified data instead of the original get_serialized_output().
This enables tool output truncation, sanitization, and transformation
hooks to work correctly."
```

---

### Task 2: Fix `loop-streaming` to read `modify` action from `tool:post` (2 sites)

**Files:**
- Modify: `amplifier-module-loop-streaming/amplifier_module_loop_streaming/__init__.py:958-991` and `1078-1115`
- Test: `amplifier-module-loop-streaming/tests/test_hook_modify.py`

**Step 1: Write the failing test**

```python
# tests/test_hook_modify.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from amplifier_core.models import HookResult


@pytest.mark.asyncio
async def test_execute_tool_call_modify_replaces_result():
    """_execute_tool_call should use modified data when hook returns modify."""
    # Similar structure to loop-basic test, targeting _execute_tool_call method
    # Assert that the returned content tuple uses modified data


@pytest.mark.asyncio
async def test_execute_tool_with_result_modify_replaces_context():
    """_execute_tool_with_result should use modified data in context message."""
    # Target the second method that adds tool result directly to context
    # Assert that context.add_message receives modified content
```

**Step 2: Run test to verify it fails**

Run: `cd amplifier-module-loop-streaming && uv run pytest tests/test_hook_modify.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

**Site 1** — `_execute_tool_call` method (around line 991):

```python
# BEFORE (line ~991):
content = result.get_serialized_output()
return (tool_call.id, tool_call.name, content)

# AFTER:
if post_result and post_result.action == "modify" and post_result.data is not None:
    modified_result = post_result.data.get("result", None)
    if modified_result is not None:
        if isinstance(modified_result, (dict, list)):
            content = json.dumps(modified_result)
        else:
            content = str(modified_result)
    else:
        content = result.get_serialized_output()
else:
    content = result.get_serialized_output()
return (tool_call.id, tool_call.name, content)
```

**Site 2** — `_execute_tool_with_result` method (around line 1115):

```python
# BEFORE (line ~1115):
await context.add_message({
    "role": "tool", "name": tool_call.name, "tool_call_id": tool_call.id,
    "content": result.get_serialized_output(),
})

# AFTER:
if post_result and post_result.action == "modify" and post_result.data is not None:
    modified_result = post_result.data.get("result", None)
    if modified_result is not None:
        if isinstance(modified_result, (dict, list)):
            tool_content = json.dumps(modified_result)
        else:
            tool_content = str(modified_result)
    else:
        tool_content = result.get_serialized_output()
else:
    tool_content = result.get_serialized_output()

await context.add_message({
    "role": "tool", "name": tool_call.name, "tool_call_id": tool_call.id,
    "content": tool_content,
})
```

**Step 4: Run test to verify it passes**

Run: `cd amplifier-module-loop-streaming && uv run pytest tests/test_hook_modify.py -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `cd amplifier-module-loop-streaming && uv run pytest -v`
Expected: All existing tests PASS

**Step 6: Commit**

```bash
cd amplifier-module-loop-streaming
git checkout -b fix/hook-modify-tool-post
git add amplifier_module_loop_streaming/__init__.py tests/test_hook_modify.py
git commit -m "fix: read HookResult modify action from tool:post events (2 sites)

Both _execute_tool_call and _execute_tool_with_result now check for
action='modify' on tool:post hook results and use modified data when
available. Enables truncation and transformation hooks to work."
```

---

### Task 3: Fix `loop-events` to read `modify` action from `tool:post`

**Files:**
- Modify: `amplifier-module-loop-events/amplifier_module_loop_events/__init__.py:440-476`
- Test: `amplifier-module-loop-events/tests/test_hook_modify.py`

**Step 1: Write the failing test**

```python
# tests/test_hook_modify.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from amplifier_core.models import HookResult


@pytest.mark.asyncio
async def test_tool_post_modify_replaces_context_message():
    """When hook returns modify on tool:post, context message uses modified data."""
    # Target the context.add_message call that uses result.get_serialized_output()
    # Assert that context.add_message receives the modified content
```

**Step 2: Run test to verify it fails**

Run: `cd amplifier-module-loop-events && uv run pytest tests/test_hook_modify.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

In `amplifier_module_loop_events/__init__.py`, find line ~476:

```python
# BEFORE (line ~476):
await context.add_message({
    "role": "tool", "name": tool_name, "tool_call_id": tool_call.id,
    "content": result.get_serialized_output(),
})

# AFTER:
if post_result and post_result.action == "modify" and post_result.data is not None:
    modified_result = post_result.data.get("result", None)
    if modified_result is not None:
        if isinstance(modified_result, (dict, list)):
            tool_content = json.dumps(modified_result)
        else:
            tool_content = str(modified_result)
    else:
        tool_content = result.get_serialized_output()
else:
    tool_content = result.get_serialized_output()

await context.add_message({
    "role": "tool", "name": tool_name, "tool_call_id": tool_call.id,
    "content": tool_content,
})
```

**Step 4: Run test to verify it passes**

Run: `cd amplifier-module-loop-events && uv run pytest tests/test_hook_modify.py -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `cd amplifier-module-loop-events && uv run pytest -v`
Expected: All existing tests PASS

**Step 6: Commit**

```bash
cd amplifier-module-loop-events
git checkout -b fix/hook-modify-tool-post
git add amplifier_module_loop_events/__init__.py tests/test_hook_modify.py
git commit -m "fix: read HookResult modify action from tool:post events

The orchestrator now checks for action='modify' on tool:post hook results
and uses modified data for the context message when available."
```

---

### Task 4: Add an integration test with `hooks-tool-truncation` to verify end-to-end

**Files:**
- Test: `amplifier-module-loop-basic/tests/test_hook_modify_integration.py`

**Step 1: Write the integration test**

```python
# tests/test_hook_modify_integration.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from amplifier_core.hooks import HookRegistry
from amplifier_core.models import HookResult


async def truncation_hook(event: str, data: dict) -> HookResult:
    """Simulates what hooks-tool-truncation does: modifies tool output."""
    result = data.get("result", {})
    if isinstance(result, dict):
        output = result.get("output", "")
    elif isinstance(result, str):
        output = result
    else:
        return HookResult()

    if len(str(output)) > 100:
        truncated = str(output)[:100] + "\n[WARNING: Tool output was truncated...]"
        modified = dict(result) if isinstance(result, dict) else {"output": result}
        modified["output" if isinstance(result, dict) else "result"] = truncated
        return HookResult(action="modify", data={"result": modified})
    return HookResult()


@pytest.mark.asyncio
async def test_truncation_hook_modifies_tool_output_in_orchestrator():
    """End-to-end: a truncation hook registered on tool:post actually
    affects what the LLM sees as the tool result."""
    hooks = HookRegistry()
    hooks.register("tool:post", truncation_hook, priority=50, name="truncation")

    # Emit tool:post with a large result
    large_output = "x" * 500
    result = await hooks.emit("tool:post", {
        "tool_name": "read_file",
        "result": {"output": large_output},
    })

    # Verify the hook returned modify with truncated data
    assert result.action == "modify"
    assert result.data is not None
    assert "[WARNING: Tool output was truncated...]" in str(result.data["result"])
    assert len(str(result.data["result"]["output"])) < 500
```

**Step 2: Run test**

Run: `cd amplifier-module-loop-basic && uv run pytest tests/test_hook_modify_integration.py -v`
Expected: PASS (this validates the hook protocol independently)

**Step 3: Commit**

```bash
cd amplifier-module-loop-basic
git add tests/test_hook_modify_integration.py
git commit -m "test: add integration test for hook modify protocol with truncation"
```

---

## Problem Statement

When a hook returns `HookResult(action="modify", data=modified_data)` on a `tool:post` event, every orchestrator ignores the modified data and uses the original `result.get_serialized_output()` instead. The `modify` action protocol works correctly inside `hooks.emit()` (the data is chained through handlers and returned in the `HookResult`), but no orchestrator reads the returned data.

## Root Cause

In all 3 orchestrators, the code pattern is:

```python
post_result = await hooks.emit(TOOL_POST, {"tool_name": ..., "result": result_data, ...})
# ... check for inject_context (lines vary) ...
result_content = result.get_serialized_output()  # <-- ORIGINAL result, ignores post_result
```

Locations:
- `loop-basic/__init__.py:467` — `result.get_serialized_output()`
- `loop-streaming/__init__.py:991` — `result.get_serialized_output()` in `_execute_tool_call`
- `loop-streaming/__init__.py:1115` — `result.get_serialized_output()` in `_execute_tool_with_result`
- `loop-events/__init__.py:476` — `result.get_serialized_output()`

## Backward Compatibility

- **Zero risk of breaking existing hooks.** Hooks that return `action="continue"` (the default) will not trigger the new `if` branch. The `result.get_serialized_output()` path remains the default.
- **Hooks that return `action="inject_context"` are unaffected.** The action precedence in `emit()` means `inject_context` takes priority over `modify` — the returned HookResult will have `action="inject_context"`, not `action="modify"`, so the new branch won't trigger.
- **Hooks that use in-place mutation (like `hooks-redaction`) continue to work.** In-place mutation modifies the `result` object directly, so `get_serialized_output()` already sees the mutation. The new code path is additive.

## PR Details

| Orchestrator | Target Repo | Branch | Sites |
|---|---|---|---|
| loop-basic | `microsoft/amplifier-module-loop-basic` | `fix/hook-modify-tool-post` | 1 site |
| loop-streaming | `microsoft/amplifier-module-loop-streaming` | `fix/hook-modify-tool-post` | 2 sites |
| loop-events | `microsoft/amplifier-module-loop-events` | `fix/hook-modify-tool-post` | 1 site |

## Dependencies

- **Blocks:** Attractor truncation hook wiring (adversarial review C-4), any future tool-output-modifying hooks
- **Blocked by:** Nothing — can start immediately
- **Priority:** P0 — this is the most impactful upstream fix
