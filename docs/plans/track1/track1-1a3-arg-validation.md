# Track 1-1A3: Add Tool Argument Validation

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Validate tool call arguments against the tool's `get_spec().input_schema` (JSON Schema) before calling `tool.execute()`. Return `ToolResult(success=False)` with a clear error message when required fields are missing, so the LLM can self-correct.

**Architecture:** Add a validation step in `_execute_single_tool()` between tool lookup and `tool.execute()`. The validation checks `"required"` fields from the tool's `input_schema`. We use a lightweight check (no jsonschema library dependency) that validates required field presence and basic type conformance. This matches spec Section 3.8 step 2: LOOKUP -> **VALIDATE** -> EXECUTE -> TRUNCATE -> EMIT -> RETURN.

**Tech Stack:** Python, JSON Schema (subset: `required` fields + `type` checks), no new dependencies

**Spec Reference:** coding-agent-loop-spec Section 3.8 (Tool execution pipeline, step 2: VALIDATE), Section 4.1 step 2, Appendix B (ValidationError)

**Adversarial Review Reference:** C-6

---

## Problem Statement

Tool arguments from the LLM are passed directly to `tool.execute()` without any schema validation. When the LLM omits a required field (e.g., `file_path` for `read_file`), the error surfaces as an unpredictable Python exception deep inside the tool's implementation rather than a clean validation error that tells the LLM exactly which field is missing and what the schema expects.

## Root Cause

**File:** `modules/loop-agent/amplifier_module_loop_agent/agent_session.py`
**Lines:** 491-538 (`_execute_single_tool`)

After looking up the tool (line 500-512), the code immediately calls `tool.execute(tool_call.arguments)` at line 515. There is no validation step between lookup and execute:

```python
# Current code: lookup then execute, no validation
tool = self._tools.get(tool_call.name)
if tool is None:
    # ... error handling for unknown tool ...

try:
    result = await tool.execute(tool_call.arguments)  # <-- no validation
```

The tool's `input_schema` property (a JSON Schema dict with `"required"`, `"properties"`, `"type"` fields) is available on every tool but never consulted during execution.

## The Fix

### Approach

Add a `_validate_tool_arguments()` method that:
1. Reads `tool.input_schema` (the JSON Schema dict)
2. Checks that all fields listed in `"required"` are present in `tool_call.arguments`
3. Optionally checks basic type conformance for present fields
4. Returns `None` on success or an error message string on failure

Call this method after tool lookup, before `tool.execute()`. On validation failure, emit `AGENT_TOOL_CALL_END` with the error and return `ToolResult(success=False, output=error_msg)`.

### Before/After

**Before** (`agent_session.py:500-515`):
```python
tool = self._tools.get(tool_call.name)
if tool is None:
    # ... error handling ...
    return ToolResult(success=False, output=error_msg)

try:
    result = await tool.execute(tool_call.arguments)
```

**After**:
```python
tool = self._tools.get(tool_call.name)
if tool is None:
    # ... error handling (unchanged) ...
    return ToolResult(success=False, output=error_msg)

# Validate arguments against tool's JSON Schema (spec Section 3.8 step 2)
validation_error = self._validate_tool_arguments(tool, tool_call.arguments)
if validation_error is not None:
    duration_ms = (time.monotonic() - start_time) * 1000
    await self._hooks.emit(
        AGENT_TOOL_CALL_END,
        {
            "call_id": tool_call.id,
            "error": validation_error,
            "duration_ms": duration_ms,
        },
    )
    return ToolResult(success=False, output=validation_error)

try:
    result = await tool.execute(tool_call.arguments)
```

### New Method

```python
@staticmethod
def _validate_tool_arguments(
    tool: Any, arguments: dict[str, Any] | None
) -> str | None:
    """Validate tool arguments against the tool's input_schema.

    Checks required field presence. Returns None on success or an
    error message string describing all validation failures.

    This is a lightweight validator (no jsonschema dependency).
    It covers the most common LLM mistakes: missing required fields
    and wrong argument types.
    """
    schema = getattr(tool, "input_schema", None)
    if not schema or not isinstance(schema, dict):
        return None  # No schema to validate against

    args = arguments or {}

    errors: list[str] = []

    # Check required fields
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    for field_name in required:
        if field_name not in args:
            field_schema = properties.get(field_name, {})
            field_type = field_schema.get("type", "any")
            field_desc = field_schema.get("description", "")
            hint = f" ({field_desc})" if field_desc else ""
            errors.append(
                f"Missing required field '{field_name}' (type: {field_type}){hint}"
            )

    # Basic type checking for present fields
    _JSON_SCHEMA_TYPE_MAP = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    for field_name, value in args.items():
        if field_name in properties:
            expected_type_str = properties[field_name].get("type")
            if expected_type_str and expected_type_str in _JSON_SCHEMA_TYPE_MAP:
                expected_type = _JSON_SCHEMA_TYPE_MAP[expected_type_str]
                if not isinstance(value, expected_type):
                    errors.append(
                        f"Field '{field_name}' expected type "
                        f"'{expected_type_str}', got '{type(value).__name__}'"
                    )

    if errors:
        error_list = "; ".join(errors)
        return (
            f"Validation error for tool '{tool.name}': {error_list}. "
            f"Please fix the arguments and try again."
        )

    return None
```

---

## Tasks

### Task 1: Write failing tests for argument validation

**Files:**
- Create: `modules/loop-agent/tests/test_arg_validation.py`

**Step 1: Write the failing tests**

```python
"""Tests for tool argument validation in the agent loop (C-6).

Verifies that:
1. Missing required fields produce a clean error result
2. Type mismatches produce a clean error result
3. Valid arguments pass through to execution
4. Tools with no schema are not validated
5. The LLM receives the error and can self-correct
"""

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


def _tool_response(*tool_calls_tuple) -> ChatResponse:
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


def _make_tool_with_schema(name: str, schema: dict, output: str = "ok"):
    tool = MagicMock()
    tool.name = name
    tool.description = f"Mock {name}"
    tool.input_schema = schema
    tool.execute = AsyncMock(return_value=ToolResult(success=True, output=output))
    return tool


# --- Validation method unit tests ---


class TestValidateToolArguments:
    """Unit tests for the static _validate_tool_arguments method."""

    def test_missing_required_field(self):
        tool = _make_tool_with_schema("read_file", {
            "type": "object",
            "required": ["file_path"],
            "properties": {
                "file_path": {"type": "string", "description": "Path to the file"},
                "offset": {"type": "integer"},
            },
        })
        result = AgentSession._validate_tool_arguments(tool, {})
        assert result is not None
        assert "file_path" in result
        assert "Missing required field" in result

    def test_all_required_fields_present(self):
        tool = _make_tool_with_schema("read_file", {
            "type": "object",
            "required": ["file_path"],
            "properties": {
                "file_path": {"type": "string"},
            },
        })
        result = AgentSession._validate_tool_arguments(
            tool, {"file_path": "/tmp/test.py"}
        )
        assert result is None

    def test_type_mismatch(self):
        tool = _make_tool_with_schema("read_file", {
            "type": "object",
            "required": ["file_path"],
            "properties": {
                "file_path": {"type": "string"},
                "offset": {"type": "integer"},
            },
        })
        result = AgentSession._validate_tool_arguments(
            tool, {"file_path": "/tmp/test.py", "offset": "not_a_number"}
        )
        assert result is not None
        assert "offset" in result
        assert "integer" in result

    def test_no_schema_passes(self):
        tool = MagicMock()
        tool.name = "custom_tool"
        tool.input_schema = None
        result = AgentSession._validate_tool_arguments(tool, {"anything": "goes"})
        assert result is None

    def test_empty_schema_passes(self):
        tool = _make_tool_with_schema("custom", {})
        result = AgentSession._validate_tool_arguments(tool, {"anything": "goes"})
        assert result is None

    def test_none_arguments_fails_required(self):
        tool = _make_tool_with_schema("write_file", {
            "type": "object",
            "required": ["file_path", "content"],
            "properties": {
                "file_path": {"type": "string"},
                "content": {"type": "string"},
            },
        })
        result = AgentSession._validate_tool_arguments(tool, None)
        assert result is not None
        assert "file_path" in result
        assert "content" in result

    def test_multiple_missing_fields(self):
        tool = _make_tool_with_schema("write_file", {
            "type": "object",
            "required": ["file_path", "content"],
            "properties": {
                "file_path": {"type": "string"},
                "content": {"type": "string"},
            },
        })
        result = AgentSession._validate_tool_arguments(tool, {})
        assert result is not None
        assert "file_path" in result
        assert "content" in result


# --- Integration tests ---


@pytest.mark.asyncio
async def test_validation_error_sent_to_llm():
    """Missing required field -> error result fed back to LLM for self-correction."""
    tool = _make_tool_with_schema("read_file", {
        "type": "object",
        "required": ["file_path"],
        "properties": {
            "file_path": {"type": "string", "description": "Path to the file"},
        },
    })

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=[
        # First call: LLM calls read_file without file_path
        _tool_response(("tc1", "read_file", {})),
        # Second call: LLM corrects and provides file_path
        _tool_response(("tc2", "read_file", {"file_path": "/tmp/test.py"})),
        # Third call: LLM responds with text
        _text_response("Read complete"),
    ])
    hooks = _make_hooks()

    session = AgentSession(
        config=SessionConfig(),
        provider=provider,
        tools={"read_file": tool},
        hooks=hooks,
    )
    result = await session.process_input("read test.py")

    assert result == "Read complete"
    # First tool call should NOT have executed (validation failed)
    # Second tool call should have executed (validation passed)
    assert tool.execute.call_count == 1
    tool.execute.assert_called_once_with({"file_path": "/tmp/test.py"})


@pytest.mark.asyncio
async def test_validation_error_emits_tool_call_end():
    """Validation failure emits agent:tool_call_end with error."""
    tool = _make_tool_with_schema("write_file", {
        "type": "object",
        "required": ["file_path", "content"],
        "properties": {
            "file_path": {"type": "string"},
            "content": {"type": "string"},
        },
    })

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=[
        _tool_response(("tc1", "write_file", {"content": "hello"})),  # missing file_path
        _text_response("ok"),
    ])
    hooks = _make_hooks()

    session = AgentSession(
        config=SessionConfig(),
        provider=provider,
        tools={"write_file": tool},
        hooks=hooks,
    )
    await session.process_input("write hello")

    # Find the tool_call_end event
    end_events = [
        (e, d) for e, d in hooks._emitted if e == "agent:tool_call_end"
    ]
    assert len(end_events) == 1
    assert "error" in end_events[0][1]
    assert "file_path" in end_events[0][1]["error"]
```

**Step 2: Run tests to verify they fail**

Run: `cd modules/loop-agent && python -m pytest tests/test_arg_validation.py -v`
Expected: FAIL -- `AgentSession` has no `_validate_tool_arguments` method.

### Task 2: Add `_validate_tool_arguments` method

**Files:**
- Modify: `modules/loop-agent/amplifier_module_loop_agent/agent_session.py`

**Step 1: Add the static method**

Add the `_validate_tool_arguments` static method from the "New Method" section above. Place it in the "Tool execution" section, after `_execute_tool_calls` and before `_execute_single_tool` (around line 484).

**Step 2: Run unit tests only**

Run: `cd modules/loop-agent && python -m pytest tests/test_arg_validation.py::TestValidateToolArguments -v`
Expected: All 7 unit tests PASS.

**Step 3: Commit**

```
git add modules/loop-agent/amplifier_module_loop_agent/agent_session.py
git commit -m "feat(loop-agent): add _validate_tool_arguments static method"
```

### Task 3: Wire validation into `_execute_single_tool`

**Files:**
- Modify: `modules/loop-agent/amplifier_module_loop_agent/agent_session.py:500-515`

**Step 1: Insert validation check after tool lookup**

After the `tool is None` check (line 512) and before the `try: result = await tool.execute(...)` block (line 514), insert:

```python
# Validate arguments against tool's JSON Schema (spec Section 3.8 step 2)
validation_error = self._validate_tool_arguments(tool, tool_call.arguments)
if validation_error is not None:
    duration_ms = (time.monotonic() - start_time) * 1000
    await self._hooks.emit(
        AGENT_TOOL_CALL_END,
        {
            "call_id": tool_call.id,
            "error": validation_error,
            "duration_ms": duration_ms,
        },
    )
    return ToolResult(success=False, output=validation_error)
```

**Step 2: Run all tests**

Run: `cd modules/loop-agent && python -m pytest tests/test_arg_validation.py -v`
Expected: All tests PASS (unit + integration).

**Step 3: Run existing tests for regression**

Run: `cd modules/loop-agent && python -m pytest tests/test_agent_session.py -v`
Expected: All existing tests PASS. (Existing mock tools have `input_schema = {"type": "object", "properties": {}}` with no `"required"` key, so validation always passes.)

**Step 4: Commit**

```
git add modules/loop-agent/amplifier_module_loop_agent/agent_session.py
git commit -m "feat(loop-agent): validate tool arguments before execution (C-6)

Check required fields from tool's input_schema before calling
tool.execute(). On validation failure, return ToolResult(success=False)
with a descriptive error message so the LLM can self-correct.

Lightweight validator: checks required field presence and basic type
conformance. No jsonschema library dependency.

Spec: Section 3.8 step 2 (VALIDATE), Appendix B (ValidationError)
Fixes: C-6 from adversarial review"
```

---

## Backward Compatibility

- **No breaking changes.** Tools with no `input_schema` or an empty schema pass validation unconditionally.
- Existing mock tools in tests use `{"type": "object", "properties": {}}` without a `"required"` key. Since `required` defaults to `[]`, all existing test tools pass validation.
- The validation is a subset of full JSON Schema validation. It catches the most common LLM mistake (missing required fields) without adding a dependency on `jsonschema`. More sophisticated validation (e.g., `pattern`, `enum`, `oneOf`) can be added later if needed.

## Dependencies on Upstream Fixes

- **None.** The `input_schema` property already exists on all Amplifier tools. No upstream changes required.

## PR Details

**Branch:** `track1/1a3-arg-validation`
**Title:** `feat(loop-agent): validate tool arguments against JSON Schema before execution (C-6)`
**Labels:** `track1`, `agent-loop`, `spec-compliance`, `critical`
**Reviewers:** @bkrabach
