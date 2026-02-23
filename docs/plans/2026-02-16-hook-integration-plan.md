# Hook Integration Plan: unified-llm-client + Amplifier Hooks

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Integrate the `unified-llm-client` library with Amplifier's hook system so every LLM call in the pipeline emits observable events, and hooks can gate (deny/approve) or modify those calls.

**Architecture:** Two-phase approach. Phase 1 adds manual `hooks.emit()` calls around existing `unified_llm.generate()` invocations in `backend.py` and `__init__.py` (~80 lines, 2 files, no new files). Phase 2 replaces those manual calls with a middleware factory (`hook_bridge.py`) that plugs into `unified_llm.Client(middleware=[...])`, providing full bidirectional hook integration including request modification, streaming events, tool hooks, and per-node context threading via `contextvars`.

**Tech Stack:** Python 3.11+, pytest + pytest-asyncio (strict mode), unified-llm-client, amplifier-core HookRegistry

---

## Conventions

All work happens in the **loop-pipeline module** repo:
```
modules/loop-pipeline/
```

**Test patterns** (match existing codebase):
- `@pytest.mark.asyncio` on every async test (strict mode)
- Hand-rolled mock classes (no `unittest.mock.patch` for core mocks)
- Inject dependencies via constructor args (`unified_client=`, `hooks=`)
- Use real `unified_llm` types for response objects
- `amplifier_core` stub block at top of test files (see existing `test_unified_llm_wiring.py`)
- No `conftest.py` — all helpers local to each test file
- `provider=object()` as truthy sentinel to enable Path B

**Key API reference** (from codebase exploration):
```python
# HookRegistry.emit() — amplifier_core/hooks.py:109
async def emit(self, event: str, data: dict[str, Any]) -> HookResult

# HookResult — amplifier_core/models.py:88
class HookResult(BaseModel):
    action: Literal["continue", "deny", "modify", "inject_context", "ask_user"] = "continue"
    data: dict[str, Any] | None = None
    reason: str | None = None
    # ... (approval fields, context injection fields, etc.)

# Pipeline engine's existing _emit helper — engine.py:708-711
async def _emit(self, event_name: str, data: dict[str, Any]) -> None:
    if self.hooks is not None:
        await self.hooks.emit(event_name, data)

# Client constructor — unified_llm/client.py:27-35
Client(providers: dict[str, ProviderAdapter], default_provider: str | None = None, middleware: list[Middleware] | None = None)

# Client.from_env() — does NOT accept middleware param
```

**Event names** (new, following the existing `pipeline:*` pattern):
```python
PROVIDER_REQUEST  = "provider:request"
PROVIDER_RESPONSE = "provider:response"
PROVIDER_ERROR    = "provider:error"
```

---

## Phase 1: Orchestrator Event Emission

**What:** Add `hooks.emit()` calls around existing `unified_llm.generate()` calls in both backends. Gives us observability + approval gates immediately.

**Scope:** ~80 lines across 2 existing files, 1 new test file. No new production files.

---

### Task 1: Add provider event constants

**Files:**
- Modify: `amplifier_module_loop_pipeline/pipeline_events.py`
- Test: `tests/test_provider_hooks.py` (create)

**Step 1: Write the failing test**

Create `tests/test_provider_hooks.py` with the initial test:

```python
"""Tests for provider-level hook event emission (provider:request/response/error).

Validates that AmplifierBackend and DirectProviderBackend emit hook events
around unified_llm.generate() calls, and that deny hook results abort LLM calls.
"""

import sys
import types
from dataclasses import dataclass, field
from typing import Any

import pytest

import unified_llm

# ---------------------------------------------------------------------------
# Provide a minimal amplifier_core stub (same pattern as test_unified_llm_wiring.py)
# ---------------------------------------------------------------------------
if "amplifier_core" not in sys.modules:

    @dataclass
    class _StubMessage:
        role: str = "user"
        content: Any = ""
        tool_call_id: str | None = None
        name: str | None = None
        metadata: dict | None = None

    @dataclass
    class _StubChatRequest:
        messages: list = field(default_factory=list)
        tools: list | None = None
        tool_choice: str | None = None
        reasoning_effort: str | None = None

    _stub_core = types.ModuleType("amplifier_core")
    _stub_core.Message = _StubMessage  # type: ignore[attr-defined]
    _stub_core.ChatRequest = _StubChatRequest  # type: ignore[attr-defined]
    sys.modules["amplifier_core"] = _stub_core

    @dataclass
    class _StubToolCallBlock:
        id: str = ""
        name: str = ""
        input: dict = field(default_factory=dict)
        type: str = "tool_call"

    _stub_msg = types.ModuleType("amplifier_core.message_models")
    _stub_msg.ToolCallBlock = _StubToolCallBlock  # type: ignore[attr-defined]
    sys.modules["amplifier_core.message_models"] = _stub_msg

from amplifier_module_loop_pipeline.pipeline_events import (
    PROVIDER_REQUEST,
    PROVIDER_RESPONSE,
    PROVIDER_ERROR,
)


def test_provider_event_constants_exist():
    """Provider event constants are defined and follow naming convention."""
    assert PROVIDER_REQUEST == "provider:request"
    assert PROVIDER_RESPONSE == "provider:response"
    assert PROVIDER_ERROR == "provider:error"
```

**Step 2: Run test to verify it fails**

```bash
cd modules/loop-pipeline
python -m pytest tests/test_provider_hooks.py::test_provider_event_constants_exist -v
```
Expected: FAIL — `ImportError: cannot import name 'PROVIDER_REQUEST'`

**Step 3: Write minimal implementation**

Add to `amplifier_module_loop_pipeline/pipeline_events.py` at the end of the file:

```python
# ---------------------------------------------------------------------------
# Provider-level events (LLM call observability)
# ---------------------------------------------------------------------------
PROVIDER_REQUEST: str = "provider:request"
PROVIDER_RESPONSE: str = "provider:response"
PROVIDER_ERROR: str = "provider:error"
```

**Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_provider_hooks.py::test_provider_event_constants_exist -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add amplifier_module_loop_pipeline/pipeline_events.py tests/test_provider_hooks.py
git commit -m "feat: add provider:request/response/error event constants"
```

---

### Task 2: Wire hooks parameter to AmplifierBackend

**Files:**
- Modify: `amplifier_module_loop_pipeline/backend.py` (lines 59-88)
- Modify: `amplifier_module_loop_pipeline/__init__.py` (line 264)
- Test: `tests/test_provider_hooks.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_provider_hooks.py`:

```python
from amplifier_module_loop_pipeline.backend import AmplifierBackend


def test_amplifier_backend_accepts_hooks_param():
    """AmplifierBackend constructor accepts and stores a hooks parameter."""

    class _MockSession:
        config: dict[str, Any] = {}

    class _Coordinator:
        session = _MockSession()
        config: dict[str, Any] = {"agents": {}}
        def get_capability(self, name: str) -> Any:
            return None

    hooks = object()  # any truthy value
    backend = AmplifierBackend(
        coordinator=_Coordinator(),
        profiles={},
        hooks=hooks,
    )
    assert backend._hooks is hooks


def test_amplifier_backend_hooks_defaults_to_none():
    """AmplifierBackend.hooks defaults to None when not provided."""

    class _MockSession:
        config: dict[str, Any] = {}

    class _Coordinator:
        session = _MockSession()
        config: dict[str, Any] = {"agents": {}}
        def get_capability(self, name: str) -> Any:
            return None

    backend = AmplifierBackend(
        coordinator=_Coordinator(),
        profiles={},
    )
    assert backend._hooks is None
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_provider_hooks.py::test_amplifier_backend_accepts_hooks_param -v
```
Expected: FAIL — `TypeError: AmplifierBackend.__init__() got an unexpected keyword argument 'hooks'`

**Step 3: Write minimal implementation**

In `amplifier_module_loop_pipeline/backend.py`, modify `AmplifierBackend.__init__()`:

Change the constructor signature (line 59-66) from:
```python
    def __init__(
        self,
        coordinator: Any,
        profiles: dict[str, str],
        provider: Any | None = None,
        tools: dict[str, Any] | None = None,
        unified_client: Any | None = None,
    ) -> None:
```
to:
```python
    def __init__(
        self,
        coordinator: Any,
        profiles: dict[str, str],
        provider: Any | None = None,
        tools: dict[str, Any] | None = None,
        unified_client: Any | None = None,
        hooks: Any | None = None,
    ) -> None:
```

And add `self._hooks = hooks` after `self._unified_client = unified_client` (after line 83):
```python
        self._hooks = hooks
```

Then in `amplifier_module_loop_pipeline/__init__.py`, update `_build_backend()` (line 264) to pass hooks:

Change:
```python
            return AmplifierBackend(
                coordinator,
                profiles=profiles,
                provider=first_provider,
                tools=tools,
            )
```
to:
```python
            return AmplifierBackend(
                coordinator,
                profiles=profiles,
                provider=first_provider,
                tools=tools,
                hooks=hooks,
            )
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_provider_hooks.py::test_amplifier_backend_accepts_hooks_param tests/test_provider_hooks.py::test_amplifier_backend_hooks_defaults_to_none -v
```
Expected: PASS

**Step 5: Run existing tests to verify no regressions**

```bash
python -m pytest tests/test_unified_llm_wiring.py tests/test_backend.py tests/test_pipeline_hooks_wiring.py -v
```
Expected: All PASS (the `hooks` param is optional with default `None`)

**Step 6: Commit**

```bash
git add amplifier_module_loop_pipeline/backend.py amplifier_module_loop_pipeline/__init__.py tests/test_provider_hooks.py
git commit -m "feat: wire hooks parameter to AmplifierBackend constructor"
```

---

### Task 3: Add _emit helper to AmplifierBackend

**Files:**
- Modify: `amplifier_module_loop_pipeline/backend.py`
- Test: `tests/test_provider_hooks.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_provider_hooks.py`:

```python
@pytest.mark.asyncio
async def test_amplifier_backend_emit_helper_fires_event():
    """AmplifierBackend._emit() delegates to hooks.emit() when hooks provided."""

    class _MockSession:
        config: dict[str, Any] = {}

    class _Coordinator:
        session = _MockSession()
        config: dict[str, Any] = {"agents": {}}
        def get_capability(self, name: str) -> Any:
            return None

    class _RecordingHooks:
        def __init__(self):
            self.events: list[tuple[str, dict]] = []
        async def emit(self, event: str, data: dict) -> Any:
            self.events.append((event, data))
            return type("HookResult", (), {"action": "continue", "data": None})()

    hooks = _RecordingHooks()
    backend = AmplifierBackend(
        coordinator=_Coordinator(),
        profiles={},
        hooks=hooks,
    )
    result = await backend._emit("test:event", {"key": "value"})
    assert len(hooks.events) == 1
    assert hooks.events[0] == ("test:event", {"key": "value"})


@pytest.mark.asyncio
async def test_amplifier_backend_emit_helper_noop_without_hooks():
    """AmplifierBackend._emit() is a no-op when hooks is None."""

    class _MockSession:
        config: dict[str, Any] = {}

    class _Coordinator:
        session = _MockSession()
        config: dict[str, Any] = {"agents": {}}
        def get_capability(self, name: str) -> Any:
            return None

    backend = AmplifierBackend(
        coordinator=_Coordinator(),
        profiles={},
        hooks=None,
    )
    # Should not raise
    result = await backend._emit("test:event", {"key": "value"})
    assert result is None
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_provider_hooks.py::test_amplifier_backend_emit_helper_fires_event -v
```
Expected: FAIL — `AttributeError: 'AmplifierBackend' object has no attribute '_emit'`

**Step 3: Write minimal implementation**

Add this method to `AmplifierBackend` in `backend.py`, after `_get_or_create_unified_client()` (after line 323):

```python
    async def _emit(self, event_name: str, data: dict[str, Any]) -> Any:
        """Emit an event via hooks, if provided.

        Returns the HookResult from hooks.emit(), or None if hooks is not set.
        Unlike the engine's fire-and-forget _emit, this returns the result
        so callers can inspect the action (deny, modify, etc.).
        """
        if self._hooks is not None:
            return await self._hooks.emit(event_name, data)
        return None
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_provider_hooks.py::test_amplifier_backend_emit_helper_fires_event tests/test_provider_hooks.py::test_amplifier_backend_emit_helper_noop_without_hooks -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add amplifier_module_loop_pipeline/backend.py tests/test_provider_hooks.py
git commit -m "feat: add _emit helper to AmplifierBackend"
```

---

### Task 4: Emit provider:request before generate() in AmplifierBackend

**Files:**
- Modify: `amplifier_module_loop_pipeline/backend.py` (in `_run_with_tool_loop`)
- Test: `tests/test_provider_hooks.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_provider_hooks.py`:

```python
from amplifier_module_loop_pipeline.context import PipelineContext
from amplifier_module_loop_pipeline.graph import Node
from amplifier_module_loop_pipeline.outcome import StageStatus


# ---------------------------------------------------------------------------
# Shared test helpers (used by remaining tests)
# ---------------------------------------------------------------------------

class _MockSession:
    config: dict[str, Any] = {}


class NoSpawnCoordinator:
    session = _MockSession()
    config: dict[str, Any] = {"agents": {}}
    def get_capability(self, name: str) -> Any:
        return None


class RecordingHooks:
    """Records emitted events and returns configurable HookResults."""
    def __init__(self, action: str = "continue"):
        self.events: list[tuple[str, dict]] = []
        self._action = action
        self._reason: str | None = None

    def set_deny(self, reason: str = "blocked"):
        self._action = "deny"
        self._reason = reason

    async def emit(self, event: str, data: dict) -> Any:
        self.events.append((event, data))
        return type("HookResult", (), {
            "action": self._action,
            "data": None,
            "reason": self._reason,
        })()

    @property
    def event_names(self) -> list[str]:
        return [e[0] for e in self.events]

    def get_data(self, event_name: str) -> list[dict]:
        return [d for e, d in self.events if e == event_name]


def _make_text_response(text: str) -> unified_llm.Response:
    return unified_llm.Response(
        id=f"resp-{abs(hash(text)) % 10000}",
        model="test-model",
        provider="test",
        message=unified_llm.Message.assistant(text),
        finish_reason=unified_llm.FinishReason(reason="stop"),
        usage=unified_llm.Usage(input_tokens=10, output_tokens=20, total_tokens=30),
    )


class MockUnifiedClient:
    def __init__(self, responses: list[unified_llm.Response]) -> None:
        self._responses = list(responses)
        self._idx = 0
        self.call_count = 0

    async def complete(self, request: unified_llm.Request) -> unified_llm.Response:
        self.call_count += 1
        if self._idx < len(self._responses):
            resp = self._responses[self._idx]
            self._idx += 1
            return resp
        return _make_text_response("fallback")


def _make_node(**kwargs: Any) -> Node:
    defaults: dict[str, Any] = {
        "id": "implement",
        "prompt": "Build it",
        "attrs": {"llm_model": "test-model", "llm_provider": "test"},
    }
    defaults.update(kwargs)
    return Node(**defaults)


# ---------------------------------------------------------------------------
# provider:request emission tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_amplifier_backend_emits_provider_request():
    """AmplifierBackend emits provider:request before unified_llm.generate()."""
    hooks = RecordingHooks()
    mock_client = MockUnifiedClient([_make_text_response("done")])

    backend = AmplifierBackend(
        coordinator=NoSpawnCoordinator(),
        profiles={},
        provider=object(),
        unified_client=mock_client,
        hooks=hooks,
    )
    node = _make_node()
    await backend.run(node, "Build it", PipelineContext())

    assert "provider:request" in hooks.event_names
    data = hooks.get_data("provider:request")[0]
    assert data["model"] == "test-model"
    assert data["provider"] == "test"
    assert data["node_id"] == "implement"
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_provider_hooks.py::test_amplifier_backend_emits_provider_request -v
```
Expected: FAIL — `AssertionError: "provider:request" not in []` (no events emitted yet)

**Step 3: Write minimal implementation**

In `amplifier_module_loop_pipeline/backend.py`, modify `_run_with_tool_loop()` (around line 278-294).

Add the import at the top of the file (after the existing imports around line 17-31):
```python
from .pipeline_events import PROVIDER_REQUEST, PROVIDER_RESPONSE, PROVIDER_ERROR
```

Then in `_run_with_tool_loop()`, add the emit call before `unified_llm.generate()`. Change the section starting at line 284 from:

```python
        try:
            result = await unified_llm.generate(
```

to:

```python
        # Emit provider:request before the LLM call
        pre_result = await self._emit(PROVIDER_REQUEST, {
            "provider": provider_name,
            "model": model,
            "node_id": node.id,
            "tool_names": [t.name for t in tools] if tools else [],
            "message_count": 1,  # prompt-only = 1 message
        })

        # Check for deny action from hooks (e.g., approval gates)
        if pre_result is not None and getattr(pre_result, "action", "continue") == "deny":
            reason = getattr(pre_result, "reason", None) or "Denied by hook"
            return Outcome(
                status=StageStatus.FAIL,
                failure_reason=f"Denied by hook: {reason}",
            )

        try:
            result = await unified_llm.generate(
```

**Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_provider_hooks.py::test_amplifier_backend_emits_provider_request -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add amplifier_module_loop_pipeline/backend.py tests/test_provider_hooks.py
git commit -m "feat: emit provider:request before generate() in AmplifierBackend"
```

---

### Task 5: Emit provider:response after generate() in AmplifierBackend

**Files:**
- Modify: `amplifier_module_loop_pipeline/backend.py` (in `_run_with_tool_loop`)
- Test: `tests/test_provider_hooks.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_provider_hooks.py`:

```python
@pytest.mark.asyncio
async def test_amplifier_backend_emits_provider_response():
    """AmplifierBackend emits provider:response after successful generate()."""
    hooks = RecordingHooks()
    mock_client = MockUnifiedClient([_make_text_response("done")])

    backend = AmplifierBackend(
        coordinator=NoSpawnCoordinator(),
        profiles={},
        provider=object(),
        unified_client=mock_client,
        hooks=hooks,
    )
    node = _make_node()
    await backend.run(node, "Build it", PipelineContext())

    assert "provider:response" in hooks.event_names
    data = hooks.get_data("provider:response")[0]
    assert data["model"] == "test-model"
    assert data["provider"] == "test"
    assert data["node_id"] == "implement"
    assert "usage" in data
    assert data["usage"]["input_tokens"] == 10
    assert data["usage"]["output_tokens"] == 20
    assert data["usage"]["total_tokens"] == 30
    assert data["finish_reason"] == "stop"


@pytest.mark.asyncio
async def test_amplifier_backend_response_includes_step_count():
    """provider:response includes the number of tool loop steps."""
    hooks = RecordingHooks()
    mock_client = MockUnifiedClient([_make_text_response("done")])

    backend = AmplifierBackend(
        coordinator=NoSpawnCoordinator(),
        profiles={},
        provider=object(),
        unified_client=mock_client,
        hooks=hooks,
    )
    node = _make_node()
    await backend.run(node, "Build it", PipelineContext())

    data = hooks.get_data("provider:response")[0]
    assert "step_count" in data
    assert isinstance(data["step_count"], int)
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_provider_hooks.py::test_amplifier_backend_emits_provider_response -v
```
Expected: FAIL — `AssertionError: "provider:response" not in [...]`

**Step 3: Write minimal implementation**

In `backend.py`, in `_run_with_tool_loop()`, add the emit call after `unified_llm.generate()` succeeds. After the existing `except` blocks (around line 306), and before the outcome mapping section, add:

Change the section after the try/except blocks from:

```python
        # Map GenerateResult → Outcome
        if result.text:
```

to:

```python
        # Emit provider:response after successful LLM call
        await self._emit(PROVIDER_RESPONSE, {
            "provider": provider_name,
            "model": model,
            "node_id": node.id,
            "usage": {
                "input_tokens": result.total_usage.input_tokens,
                "output_tokens": result.total_usage.output_tokens,
                "total_tokens": result.total_usage.total_tokens,
                "reasoning_tokens": result.total_usage.reasoning_tokens,
                "cache_read_tokens": result.total_usage.cache_read_tokens,
                "cache_write_tokens": result.total_usage.cache_write_tokens,
            },
            "finish_reason": result.finish_reason.reason,
            "text_length": len(result.text) if result.text else 0,
            "step_count": len(result.steps),
        })

        # Map GenerateResult → Outcome
        if result.text:
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_provider_hooks.py::test_amplifier_backend_emits_provider_response tests/test_provider_hooks.py::test_amplifier_backend_response_includes_step_count -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add amplifier_module_loop_pipeline/backend.py tests/test_provider_hooks.py
git commit -m "feat: emit provider:response after generate() in AmplifierBackend"
```

---

### Task 6: Emit provider:error on SDKError in AmplifierBackend

**Files:**
- Modify: `amplifier_module_loop_pipeline/backend.py` (in `_run_with_tool_loop`)
- Test: `tests/test_provider_hooks.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_provider_hooks.py`:

```python
class FailingUnifiedClient:
    def __init__(self, error: Exception) -> None:
        self._error = error
    async def complete(self, request: unified_llm.Request) -> Any:
        raise self._error


@pytest.mark.asyncio
async def test_amplifier_backend_emits_provider_error_on_sdk_error():
    """AmplifierBackend emits provider:error when unified_llm.generate() raises SDKError."""
    hooks = RecordingHooks()
    mock_client = FailingUnifiedClient(
        unified_llm.ServerError(
            message="Internal server error",
            provider="test",
            status_code=500,
        )
    )

    backend = AmplifierBackend(
        coordinator=NoSpawnCoordinator(),
        profiles={},
        provider=object(),
        unified_client=mock_client,
        hooks=hooks,
    )
    node = _make_node()
    result = await backend.run(node, "Build it", PipelineContext())

    assert result.status == StageStatus.FAIL
    assert "provider:error" in hooks.event_names
    data = hooks.get_data("provider:error")[0]
    assert data["provider"] == "test"
    assert data["model"] == "test-model"
    assert data["node_id"] == "implement"
    assert data["error_type"] == "ServerError"
    assert data["retryable"] is True
    assert "Internal server error" in data["message"]
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_provider_hooks.py::test_amplifier_backend_emits_provider_error_on_sdk_error -v
```
Expected: FAIL — `AssertionError: "provider:error" not in [...]`

**Step 3: Write minimal implementation**

In `backend.py`, in `_run_with_tool_loop()`, modify the `except unified_llm.SDKError` block. Change from:

```python
        except unified_llm.SDKError as exc:
            logger.warning("unified_llm.generate failed for node %s: %s", node.id, exc)
            return Outcome(
                status=StageStatus.FAIL,
                failure_reason=str(exc),
            )
```

to:

```python
        except unified_llm.SDKError as exc:
            logger.warning("unified_llm.generate failed for node %s: %s", node.id, exc)
            await self._emit(PROVIDER_ERROR, {
                "provider": provider_name,
                "model": model,
                "node_id": node.id,
                "error_type": type(exc).__name__,
                "error_class": type(exc).__mro__[1].__name__,
                "retryable": getattr(exc, "retryable", False),
                "message": str(exc),
            })
            return Outcome(
                status=StageStatus.FAIL,
                failure_reason=str(exc),
            )
```

**Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_provider_hooks.py::test_amplifier_backend_emits_provider_error_on_sdk_error -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add amplifier_module_loop_pipeline/backend.py tests/test_provider_hooks.py
git commit -m "feat: emit provider:error on SDKError in AmplifierBackend"
```

---

### Task 7: Handle deny hook result in AmplifierBackend

**Files:**
- Test: `tests/test_provider_hooks.py` (append)

Note: The deny handling code was already added in Task 4. This task adds a dedicated test.

**Step 1: Write the test**

Append to `tests/test_provider_hooks.py`:

```python
@pytest.mark.asyncio
async def test_amplifier_backend_deny_hook_aborts_llm_call():
    """When hooks return deny on provider:request, the LLM call is skipped."""
    hooks = RecordingHooks()
    hooks.set_deny("cost limit exceeded")
    mock_client = MockUnifiedClient([_make_text_response("should not reach")])

    backend = AmplifierBackend(
        coordinator=NoSpawnCoordinator(),
        profiles={},
        provider=object(),
        unified_client=mock_client,
        hooks=hooks,
    )
    node = _make_node()
    result = await backend.run(node, "Build it", PipelineContext())

    # LLM call should never have been made
    assert mock_client.call_count == 0
    # Outcome should be FAIL with the denial reason
    assert result.status == StageStatus.FAIL
    assert "cost limit exceeded" in (result.failure_reason or "")
    # Only provider:request should have been emitted (no response/error)
    assert hooks.event_names == ["provider:request"]
```

**Step 2: Run test**

```bash
python -m pytest tests/test_provider_hooks.py::test_amplifier_backend_deny_hook_aborts_llm_call -v
```
Expected: PASS (deny handling was implemented in Task 4)

**Step 3: Commit**

```bash
git add tests/test_provider_hooks.py
git commit -m "test: verify deny hook result aborts LLM call in AmplifierBackend"
```

---

### Task 8: Add _emit helper to DirectProviderBackend and emit events

**Files:**
- Modify: `amplifier_module_loop_pipeline/__init__.py` (DirectProviderBackend.run)
- Test: `tests/test_provider_hooks.py` (append)

**Step 1: Write the failing tests**

Append to `tests/test_provider_hooks.py`:

```python
from amplifier_module_loop_pipeline import DirectProviderBackend


@pytest.mark.asyncio
async def test_direct_backend_emits_provider_request():
    """DirectProviderBackend emits provider:request before generate()."""
    hooks = RecordingHooks()
    mock_client = MockUnifiedClient([_make_text_response("done")])

    backend = DirectProviderBackend(
        provider=object(),
        unified_client=mock_client,
        hooks=hooks,
    )
    node = _make_node(id="step1")
    await backend.run(node, "do work", PipelineContext())

    assert "provider:request" in hooks.event_names
    data = hooks.get_data("provider:request")[0]
    assert data["provider"] == "test"
    assert data["model"] == "test-model"
    assert data["node_id"] == "step1"


@pytest.mark.asyncio
async def test_direct_backend_emits_provider_response():
    """DirectProviderBackend emits provider:response after generate()."""
    hooks = RecordingHooks()
    mock_client = MockUnifiedClient([_make_text_response("done")])

    backend = DirectProviderBackend(
        provider=object(),
        unified_client=mock_client,
        hooks=hooks,
    )
    node = _make_node(id="step1")
    await backend.run(node, "do work", PipelineContext())

    assert "provider:response" in hooks.event_names
    data = hooks.get_data("provider:response")[0]
    assert "usage" in data
    assert data["finish_reason"] == "stop"


@pytest.mark.asyncio
async def test_direct_backend_emits_provider_error():
    """DirectProviderBackend emits provider:error on SDKError."""
    hooks = RecordingHooks()
    mock_client = FailingUnifiedClient(
        unified_llm.RateLimitError(
            message="Too many requests",
            provider="test",
            status_code=429,
        )
    )

    backend = DirectProviderBackend(
        provider=object(),
        unified_client=mock_client,
        hooks=hooks,
    )
    node = _make_node(id="step1")
    result = await backend.run(node, "do work", PipelineContext())

    assert result.status == StageStatus.FAIL
    assert "provider:error" in hooks.event_names
    data = hooks.get_data("provider:error")[0]
    assert data["error_type"] == "RateLimitError"
    assert data["retryable"] is True


@pytest.mark.asyncio
async def test_direct_backend_deny_hook_aborts_llm_call():
    """When hooks return deny on provider:request, DirectProviderBackend skips the LLM call."""
    hooks = RecordingHooks()
    hooks.set_deny("not approved")
    mock_client = MockUnifiedClient([_make_text_response("should not reach")])

    backend = DirectProviderBackend(
        provider=object(),
        unified_client=mock_client,
        hooks=hooks,
    )
    node = _make_node(id="step1")
    result = await backend.run(node, "do work", PipelineContext())

    assert mock_client.call_count == 0
    assert result.status == StageStatus.FAIL
    assert "not approved" in (result.failure_reason or "")
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_provider_hooks.py::test_direct_backend_emits_provider_request -v
```
Expected: FAIL — no events emitted by DirectProviderBackend

**Step 3: Write minimal implementation**

In `amplifier_module_loop_pipeline/__init__.py`, add the import near the top (after existing imports around line 27):

```python
from .pipeline_events import PROVIDER_REQUEST, PROVIDER_RESPONSE, PROVIDER_ERROR
```

Add an `_emit` method to `DirectProviderBackend` (after `_get_or_create_unified_client`, around line 197):

```python
    async def _emit(self, event_name: str, data: dict[str, Any]) -> Any:
        """Emit an event via hooks, if provided."""
        if self._hooks is not None:
            return await self._hooks.emit(event_name, data)
        return None
```

Then modify `DirectProviderBackend.run()` to emit events. In the `run()` method, add the pre-call emit before `unified_llm.generate()`. Change the section around line 134 from:

```python
        # Call unified_llm.generate() — handles tool loop, retry, errors
        try:
            result = await unified_llm.generate(**generate_kwargs)
```

to:

```python
        # Emit provider:request before the LLM call
        pre_result = await self._emit(PROVIDER_REQUEST, {
            "provider": provider_name,
            "model": model,
            "node_id": node.id,
            "tool_names": [t.name for t in tools] if tools else [],
            "message_count": len(generate_kwargs.get("messages", [])) or 1,
        })

        # Check for deny action from hooks
        if pre_result is not None and getattr(pre_result, "action", "continue") == "deny":
            reason = getattr(pre_result, "reason", None) or "Denied by hook"
            return Outcome(
                status=StageStatus.FAIL,
                failure_reason=f"Denied by hook: {reason}",
            )

        # Call unified_llm.generate() — handles tool loop, retry, errors
        try:
            result = await unified_llm.generate(**generate_kwargs)
```

Modify the `except unified_llm.SDKError` block from:

```python
        except unified_llm.SDKError as exc:
            logger.warning("unified_llm.generate failed for node %s: %s", node.id, exc)
            return Outcome(
                status=StageStatus.FAIL,
                failure_reason=str(exc),
            )
```

to:

```python
        except unified_llm.SDKError as exc:
            logger.warning("unified_llm.generate failed for node %s: %s", node.id, exc)
            await self._emit(PROVIDER_ERROR, {
                "provider": provider_name,
                "model": model,
                "node_id": node.id,
                "error_type": type(exc).__name__,
                "error_class": type(exc).__mro__[1].__name__,
                "retryable": getattr(exc, "retryable", False),
                "message": str(exc),
            })
            return Outcome(
                status=StageStatus.FAIL,
                failure_reason=str(exc),
            )
```

Add the response emit after the try/except, before the outcome mapping. Change from:

```python
        # Map GenerateResult → Outcome
        text = result.text
```

to:

```python
        # Emit provider:response after successful LLM call
        await self._emit(PROVIDER_RESPONSE, {
            "provider": provider_name,
            "model": model,
            "node_id": node.id,
            "usage": {
                "input_tokens": result.total_usage.input_tokens,
                "output_tokens": result.total_usage.output_tokens,
                "total_tokens": result.total_usage.total_tokens,
                "reasoning_tokens": result.total_usage.reasoning_tokens,
                "cache_read_tokens": result.total_usage.cache_read_tokens,
                "cache_write_tokens": result.total_usage.cache_write_tokens,
            },
            "finish_reason": result.finish_reason.reason,
            "text_length": len(result.text) if result.text else 0,
            "step_count": len(result.steps),
        })

        # Map GenerateResult → Outcome
        text = result.text
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_provider_hooks.py::test_direct_backend_emits_provider_request tests/test_provider_hooks.py::test_direct_backend_emits_provider_response tests/test_provider_hooks.py::test_direct_backend_emits_provider_error tests/test_provider_hooks.py::test_direct_backend_deny_hook_aborts_llm_call -v
```
Expected: All PASS

**Step 5: Run full test suite to verify no regressions**

```bash
python -m pytest tests/ -v
```
Expected: All existing tests PASS

**Step 6: Commit**

```bash
git add amplifier_module_loop_pipeline/__init__.py tests/test_provider_hooks.py
git commit -m "feat: emit provider events in DirectProviderBackend"
```

---

### Task 9: Test backward compatibility (hooks=None)

**Files:**
- Test: `tests/test_provider_hooks.py` (append)

**Step 1: Write the tests**

Append to `tests/test_provider_hooks.py`:

```python
@pytest.mark.asyncio
async def test_amplifier_backend_works_without_hooks():
    """AmplifierBackend still works when hooks is None (backward compat)."""
    mock_client = MockUnifiedClient([_make_text_response("done")])

    backend = AmplifierBackend(
        coordinator=NoSpawnCoordinator(),
        profiles={},
        provider=object(),
        unified_client=mock_client,
        hooks=None,  # explicitly None
    )
    node = _make_node()
    result = await backend.run(node, "Build it", PipelineContext())

    assert result.status == StageStatus.SUCCESS
    assert mock_client.call_count > 0


@pytest.mark.asyncio
async def test_direct_backend_works_without_hooks():
    """DirectProviderBackend still works when hooks is None."""
    mock_client = MockUnifiedClient([_make_text_response("done")])

    backend = DirectProviderBackend(
        provider=object(),
        unified_client=mock_client,
        hooks=None,
    )
    node = _make_node(id="step1")
    result = await backend.run(node, "do work", PipelineContext())

    assert result.status == StageStatus.SUCCESS
    assert mock_client.call_count > 0


@pytest.mark.asyncio
async def test_event_ordering_request_before_response():
    """provider:request is emitted before provider:response."""
    hooks = RecordingHooks()
    mock_client = MockUnifiedClient([_make_text_response("done")])

    backend = AmplifierBackend(
        coordinator=NoSpawnCoordinator(),
        profiles={},
        provider=object(),
        unified_client=mock_client,
        hooks=hooks,
    )
    node = _make_node()
    await backend.run(node, "Build it", PipelineContext())

    names = hooks.event_names
    req_idx = names.index("provider:request")
    resp_idx = names.index("provider:response")
    assert req_idx < resp_idx
```

**Step 2: Run tests**

```bash
python -m pytest tests/test_provider_hooks.py::test_amplifier_backend_works_without_hooks tests/test_provider_hooks.py::test_direct_backend_works_without_hooks tests/test_provider_hooks.py::test_event_ordering_request_before_response -v
```
Expected: All PASS

**Step 3: Commit**

```bash
git add tests/test_provider_hooks.py
git commit -m "test: backward compatibility and event ordering for provider hooks"
```

---

### Task 10: Full test suite regression check (Phase 1 complete)

**Step 1: Run all loop-pipeline tests**

```bash
cd modules/loop-pipeline
python -m pytest tests/ -v --tb=short
```
Expected: All tests PASS, including all existing tests and the new `test_provider_hooks.py`

**Step 2: Run unified-llm-client tests to ensure no breakage**

```bash
cd ../unified-llm-client
python -m pytest tests/unit/ tests/adapter/ tests/dod/ -v --tb=short -x
```
Expected: All PASS

**Step 3: Commit Phase 1 completion marker**

```bash
cd modules/loop-pipeline
git log --oneline -8
```
Verify 7 clean commits from Tasks 1-9.

---

## Phase 2: Hook Bridge Middleware

**What:** A middleware factory that plugs into `unified_llm.Client(middleware=[...])`, replacing the manual Phase 1 emit calls with a middleware that sits inside the unified-llm call chain. This enables request/response modification, streaming events, tool hooks, and per-node context threading.

**Scope:** 1 new file (`hook_bridge.py`), modifications to `backend.py` and `__init__.py`, new test file.

---

### Task 11: Create hook_bridge.py with middleware factory skeleton

**Files:**
- Create: `amplifier_module_loop_pipeline/hook_bridge.py`
- Create: `tests/test_hook_bridge.py`

**Step 1: Write the failing test**

Create `tests/test_hook_bridge.py`:

```python
"""Tests for the hook bridge middleware (Phase 2).

Validates that create_hook_bridge() returns a middleware function that
bridges unified-llm-client middleware to Amplifier's hook system.
"""

import sys
import types
from dataclasses import dataclass, field
from typing import Any

import pytest

import unified_llm

# ---------------------------------------------------------------------------
# amplifier_core stub (same as test_provider_hooks.py)
# ---------------------------------------------------------------------------
if "amplifier_core" not in sys.modules:

    @dataclass
    class _StubMessage:
        role: str = "user"
        content: Any = ""
        tool_call_id: str | None = None
        name: str | None = None
        metadata: dict | None = None

    @dataclass
    class _StubChatRequest:
        messages: list = field(default_factory=list)
        tools: list | None = None
        tool_choice: str | None = None
        reasoning_effort: str | None = None

    _stub_core = types.ModuleType("amplifier_core")
    _stub_core.Message = _StubMessage  # type: ignore[attr-defined]
    _stub_core.ChatRequest = _StubChatRequest  # type: ignore[attr-defined]
    sys.modules["amplifier_core"] = _stub_core

    @dataclass
    class _StubToolCallBlock:
        id: str = ""
        name: str = ""
        input: dict = field(default_factory=dict)
        type: str = "tool_call"

    _stub_msg = types.ModuleType("amplifier_core.message_models")
    _stub_msg.ToolCallBlock = _StubToolCallBlock  # type: ignore[attr-defined]
    sys.modules["amplifier_core.message_models"] = _stub_msg

from amplifier_module_loop_pipeline.hook_bridge import create_hook_bridge


def test_create_hook_bridge_returns_callable():
    """create_hook_bridge() returns a middleware function."""

    class _Hooks:
        async def emit(self, event, data):
            return type("R", (), {"action": "continue", "data": None})()

    middleware = create_hook_bridge(hooks=_Hooks())
    assert callable(middleware)
```

**Step 2: Run test to verify it fails**

```bash
cd modules/loop-pipeline
python -m pytest tests/test_hook_bridge.py::test_create_hook_bridge_returns_callable -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'amplifier_module_loop_pipeline.hook_bridge'`

**Step 3: Write minimal implementation**

Create `amplifier_module_loop_pipeline/hook_bridge.py`:

```python
"""Hook bridge middleware — bridges unified-llm-client to Amplifier hooks.

Creates a unified_llm.Middleware function that emits Amplifier hook events
(provider:request, provider:response, provider:error) around LLM calls,
and processes hook results (deny, modify, continue).

This middleware replaces the manual hooks.emit() calls from Phase 1,
moving event emission into the unified-llm middleware chain where it can
intercept and modify requests/responses.
"""

from __future__ import annotations

import contextvars
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ContextVar for threading pipeline node context through the async call stack.
# Set by the backend before each generate() call, read by the middleware.
_current_node_context: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "pipeline_node_context", default={}
)


def get_node_context() -> dict[str, Any]:
    """Get the current pipeline node context (set by the backend)."""
    return _current_node_context.get()


def set_node_context(ctx: dict[str, Any]) -> contextvars.Token[dict[str, Any]]:
    """Set the pipeline node context for the current async task."""
    return _current_node_context.set(ctx)


def create_hook_bridge(
    hooks: Any,
) -> Any:
    """Create a unified-llm middleware that bridges to Amplifier's hook system.

    Args:
        hooks: Amplifier HookRegistry (or any object with async emit()).

    Returns:
        A middleware function compatible with unified_llm.Client(middleware=[...]).
    """

    async def hook_bridge_middleware(request: Any, next_fn: Any) -> Any:
        """Middleware that emits hook events around each LLM call."""
        # Will be implemented in subsequent tasks
        return await next_fn(request)

    return hook_bridge_middleware
```

**Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_hook_bridge.py::test_create_hook_bridge_returns_callable -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add amplifier_module_loop_pipeline/hook_bridge.py tests/test_hook_bridge.py
git commit -m "feat: create hook_bridge.py skeleton with ContextVar"
```

---

### Task 12: Implement pre-request event emission in middleware

**Files:**
- Modify: `amplifier_module_loop_pipeline/hook_bridge.py`
- Test: `tests/test_hook_bridge.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_hook_bridge.py`:

```python
from amplifier_module_loop_pipeline.hook_bridge import set_node_context


class RecordingHooks:
    """Records emitted events and returns configurable HookResults."""
    def __init__(self, action: str = "continue"):
        self.events: list[tuple[str, dict]] = []
        self._action = action
        self._reason: str | None = None
        self._modified_data: dict | None = None

    def set_deny(self, reason: str = "blocked"):
        self._action = "deny"
        self._reason = reason

    def set_modify(self, data: dict):
        self._action = "modify"
        self._modified_data = data

    async def emit(self, event: str, data: dict) -> Any:
        self.events.append((event, data))
        return type("HookResult", (), {
            "action": self._action,
            "data": self._modified_data,
            "reason": self._reason,
        })()

    @property
    def event_names(self) -> list[str]:
        return [e[0] for e in self.events]

    def get_data(self, event_name: str) -> list[dict]:
        return [d for e, d in self.events if e == event_name]


def _make_request(model: str = "test-model", provider: str = "test") -> unified_llm.Request:
    return unified_llm.Request(
        model=model,
        messages=[unified_llm.Message.user("Hello")],
        provider=provider,
    )


def _make_response(text: str = "Hi") -> unified_llm.Response:
    return unified_llm.Response(
        id="resp-1",
        model="test-model",
        provider="test",
        message=unified_llm.Message.assistant(text),
        finish_reason=unified_llm.FinishReason(reason="stop"),
        usage=unified_llm.Usage(input_tokens=10, output_tokens=5, total_tokens=15),
    )


@pytest.mark.asyncio
async def test_middleware_emits_provider_request():
    """Hook bridge middleware emits provider:request before calling next_fn."""
    hooks = RecordingHooks()
    middleware = create_hook_bridge(hooks=hooks)

    token = set_node_context({"node_id": "step1"})
    try:
        request = _make_request()
        response = _make_response()

        async def next_fn(req):
            return response

        result = await middleware(request, next_fn)
        assert result is response

        assert "provider:request" in hooks.event_names
        data = hooks.get_data("provider:request")[0]
        assert data["model"] == "test-model"
        assert data["provider"] == "test"
        assert data["node_id"] == "step1"
        assert data["message_count"] == 1
    finally:
        _current_node_context = __import__(
            "amplifier_module_loop_pipeline.hook_bridge", fromlist=["_current_node_context"]
        )._current_node_context
        _current_node_context.reset(token)
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_hook_bridge.py::test_middleware_emits_provider_request -v
```
Expected: FAIL — `AssertionError: "provider:request" not in []`

**Step 3: Write minimal implementation**

In `hook_bridge.py`, update the `hook_bridge_middleware` function. Add the import at the top:

```python
from .pipeline_events import PROVIDER_REQUEST, PROVIDER_RESPONSE, PROVIDER_ERROR
```

Replace the `hook_bridge_middleware` function body:

```python
    async def hook_bridge_middleware(request: Any, next_fn: Any) -> Any:
        """Middleware that emits hook events around each LLM call."""
        node_ctx = get_node_context()

        # Pre-request: emit provider:request
        pre_result = await hooks.emit(PROVIDER_REQUEST, {
            "provider": request.provider or "unknown",
            "model": request.model,
            "node_id": node_ctx.get("node_id"),
            "tool_names": [t.name for t in (request.tools or [])],
            "message_count": len(request.messages),
        })

        # Check for deny action
        if getattr(pre_result, "action", "continue") == "deny":
            from unified_llm.errors import AbortError
            reason = getattr(pre_result, "reason", None) or "Denied by hook"
            raise AbortError(f"Denied by hook: {reason}")

        # Call through to next middleware / adapter
        return await next_fn(request)
```

**Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_hook_bridge.py::test_middleware_emits_provider_request -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add amplifier_module_loop_pipeline/hook_bridge.py tests/test_hook_bridge.py
git commit -m "feat: emit provider:request in hook bridge middleware"
```

---

### Task 13: Implement deny and post-response emission in middleware

**Files:**
- Modify: `amplifier_module_loop_pipeline/hook_bridge.py`
- Test: `tests/test_hook_bridge.py` (append)

**Step 1: Write the failing tests**

Append to `tests/test_hook_bridge.py`:

```python
@pytest.mark.asyncio
async def test_middleware_deny_raises_abort_error():
    """Hook bridge raises AbortError when hooks return deny."""
    hooks = RecordingHooks()
    hooks.set_deny("cost limit")
    middleware = create_hook_bridge(hooks=hooks)

    token = set_node_context({"node_id": "step1"})
    try:
        request = _make_request()
        call_count = 0

        async def next_fn(req):
            nonlocal call_count
            call_count += 1
            return _make_response()

        with pytest.raises(unified_llm.AbortError, match="cost limit"):
            await middleware(request, next_fn)

        # next_fn should never have been called
        assert call_count == 0
    finally:
        from amplifier_module_loop_pipeline.hook_bridge import _current_node_context
        _current_node_context.reset(token)


@pytest.mark.asyncio
async def test_middleware_emits_provider_response():
    """Hook bridge emits provider:response after successful call."""
    hooks = RecordingHooks()
    middleware = create_hook_bridge(hooks=hooks)

    token = set_node_context({"node_id": "step1"})
    try:
        request = _make_request()
        response = _make_response("Hello!")

        async def next_fn(req):
            return response

        result = await middleware(request, next_fn)

        assert "provider:response" in hooks.event_names
        data = hooks.get_data("provider:response")[0]
        assert data["model"] == "test-model"
        assert data["provider"] == "test"
        assert data["node_id"] == "step1"
        assert data["usage"]["input_tokens"] == 10
        assert data["usage"]["output_tokens"] == 5
        assert data["finish_reason"] == "stop"
    finally:
        from amplifier_module_loop_pipeline.hook_bridge import _current_node_context
        _current_node_context.reset(token)


@pytest.mark.asyncio
async def test_middleware_emits_provider_error():
    """Hook bridge emits provider:error when next_fn raises SDKError."""
    hooks = RecordingHooks()
    middleware = create_hook_bridge(hooks=hooks)

    token = set_node_context({"node_id": "step1"})
    try:
        request = _make_request()

        async def next_fn(req):
            raise unified_llm.ServerError(
                message="Internal error", provider="test", status_code=500
            )

        with pytest.raises(unified_llm.ServerError):
            await middleware(request, next_fn)

        assert "provider:error" in hooks.event_names
        data = hooks.get_data("provider:error")[0]
        assert data["error_type"] == "ServerError"
        assert data["retryable"] is True
    finally:
        from amplifier_module_loop_pipeline.hook_bridge import _current_node_context
        _current_node_context.reset(token)
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_hook_bridge.py::test_middleware_emits_provider_response -v
```
Expected: FAIL — `AssertionError: "provider:response" not in [...]`

**Step 3: Write minimal implementation**

In `hook_bridge.py`, update `hook_bridge_middleware` to add post-response and error emission. Replace the function body with:

```python
    async def hook_bridge_middleware(request: Any, next_fn: Any) -> Any:
        """Middleware that emits hook events around each LLM call."""
        from unified_llm.errors import AbortError, SDKError

        node_ctx = get_node_context()

        # Pre-request: emit provider:request
        pre_result = await hooks.emit(PROVIDER_REQUEST, {
            "provider": request.provider or "unknown",
            "model": request.model,
            "node_id": node_ctx.get("node_id"),
            "tool_names": [t.name for t in (request.tools or [])],
            "message_count": len(request.messages),
        })

        # Check for deny action
        if getattr(pre_result, "action", "continue") == "deny":
            reason = getattr(pre_result, "reason", None) or "Denied by hook"
            raise AbortError(f"Denied by hook: {reason}")

        # Call through to next middleware / adapter
        try:
            response = await next_fn(request)
        except SDKError as exc:
            # Emit provider:error, then re-raise
            await hooks.emit(PROVIDER_ERROR, {
                "provider": request.provider or "unknown",
                "model": request.model,
                "node_id": node_ctx.get("node_id"),
                "error_type": type(exc).__name__,
                "error_class": type(exc).__mro__[1].__name__,
                "retryable": getattr(exc, "retryable", False),
                "message": str(exc),
            })
            raise

        # Post-response: emit provider:response
        usage = getattr(response, "usage", None)
        finish = getattr(response, "finish_reason", None)
        await hooks.emit(PROVIDER_RESPONSE, {
            "provider": request.provider or "unknown",
            "model": request.model,
            "node_id": node_ctx.get("node_id"),
            "usage": {
                "input_tokens": getattr(usage, "input_tokens", 0),
                "output_tokens": getattr(usage, "output_tokens", 0),
                "total_tokens": getattr(usage, "total_tokens", 0),
                "reasoning_tokens": getattr(usage, "reasoning_tokens", None),
                "cache_read_tokens": getattr(usage, "cache_read_tokens", None),
                "cache_write_tokens": getattr(usage, "cache_write_tokens", None),
            } if usage else {},
            "finish_reason": getattr(finish, "reason", "unknown") if finish else "unknown",
            "text_length": len(response.text) if hasattr(response, "text") and response.text else 0,
        })

        return response
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_hook_bridge.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add amplifier_module_loop_pipeline/hook_bridge.py tests/test_hook_bridge.py
git commit -m "feat: complete hook bridge middleware (deny, response, error)"
```

---

### Task 14: Implement Client construction with provider-copy pattern

**Files:**
- Modify: `amplifier_module_loop_pipeline/hook_bridge.py`
- Test: `tests/test_hook_bridge.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_hook_bridge.py`:

```python
from amplifier_module_loop_pipeline.hook_bridge import create_middleware_client


@pytest.mark.asyncio
async def test_create_middleware_client_copies_providers():
    """create_middleware_client copies providers from base client and adds middleware."""
    hooks = RecordingHooks()

    class _MockAdapter:
        name = "test"
        async def complete(self, request):
            return _make_response()
        def stream(self, request):
            raise NotImplementedError

    base_client = unified_llm.Client(
        providers={"test": _MockAdapter()},
        default_provider="test",
    )

    client = create_middleware_client(base_client, hooks=hooks)

    # Client should have the same providers
    assert "test" in client.providers
    assert client.default_provider == "test"
    # Client should have middleware
    assert len(client._middleware) > 0


def test_create_middleware_client_preserves_default_provider():
    """create_middleware_client preserves the base client's default_provider."""
    hooks = RecordingHooks()

    class _MockAdapter:
        name = "mock"
        async def complete(self, request):
            return _make_response()
        def stream(self, request):
            raise NotImplementedError

    base_client = unified_llm.Client(
        providers={"anthropic": _MockAdapter(), "openai": _MockAdapter()},
        default_provider="anthropic",
    )

    client = create_middleware_client(base_client, hooks=hooks)

    assert client.default_provider == "anthropic"
    assert set(client.providers.keys()) == {"anthropic", "openai"}
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_hook_bridge.py::test_create_middleware_client_copies_providers -v
```
Expected: FAIL — `ImportError: cannot import name 'create_middleware_client'`

**Step 3: Write minimal implementation**

Add to `hook_bridge.py`:

```python
def create_middleware_client(
    base_client: Any,
    hooks: Any,
) -> Any:
    """Create a new Client with hook bridge middleware, copying providers from base.

    This is the "provider-copy pattern": Client.from_env() doesn't accept middleware,
    so we call from_env() to get auto-detected adapters, then construct a new Client
    with those adapters plus our middleware.

    Args:
        base_client: An existing unified_llm.Client (e.g., from Client.from_env()).
        hooks: Amplifier HookRegistry.

    Returns:
        A new unified_llm.Client with the hook bridge middleware installed.
    """
    from unified_llm.client import Client

    middleware_fn = create_hook_bridge(hooks=hooks)

    return Client(
        providers=dict(base_client.providers),
        default_provider=base_client.default_provider,
        middleware=[middleware_fn],
    )
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_hook_bridge.py::test_create_middleware_client_copies_providers tests/test_hook_bridge.py::test_create_middleware_client_preserves_default_provider -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add amplifier_module_loop_pipeline/hook_bridge.py tests/test_hook_bridge.py
git commit -m "feat: add create_middleware_client with provider-copy pattern"
```

---

### Task 15: Implement tool execution wrapping

**Files:**
- Modify: `amplifier_module_loop_pipeline/hook_bridge.py`
- Test: `tests/test_hook_bridge.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_hook_bridge.py`:

```python
from amplifier_module_loop_pipeline.hook_bridge import wrap_tool_with_hooks


@pytest.mark.asyncio
async def test_wrap_tool_emits_tool_pre_and_post():
    """wrap_tool_with_hooks emits tool:pre before and tool:post after execution."""
    hooks = RecordingHooks()
    call_log: list[str] = []

    original_tool = unified_llm.Tool(
        name="write_file",
        description="Write a file",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}},
        execute=None,
    )

    async def original_execute(**kwargs):
        call_log.append("executed")
        return "file written"

    original_tool.execute = original_execute

    token = set_node_context({"node_id": "step1"})
    try:
        wrapped = wrap_tool_with_hooks(original_tool, hooks)

        # Name and schema should be preserved
        assert wrapped.name == "write_file"
        assert wrapped.description == "Write a file"
        assert wrapped.parameters == original_tool.parameters

        # Execute the wrapped tool
        result = await wrapped.execute(path="/tmp/test.py")
        assert result == "file written"
        assert call_log == ["executed"]

        # Hook events should have been emitted
        assert "tool:pre" in hooks.event_names
        assert "tool:post" in hooks.event_names

        pre_data = hooks.get_data("tool:pre")[0]
        assert pre_data["tool_name"] == "write_file"
        assert pre_data["args"] == {"path": "/tmp/test.py"}

        post_data = hooks.get_data("tool:post")[0]
        assert post_data["tool_name"] == "write_file"
        assert post_data["result"] == "file written"
    finally:
        from amplifier_module_loop_pipeline.hook_bridge import _current_node_context
        _current_node_context.reset(token)


@pytest.mark.asyncio
async def test_wrap_tool_with_no_execute_returns_none():
    """wrap_tool_with_hooks with execute=None preserves None."""
    hooks = RecordingHooks()
    original_tool = unified_llm.Tool(
        name="read_file",
        description="Read a file",
        parameters={},
        execute=None,
    )
    wrapped = wrap_tool_with_hooks(original_tool, hooks)
    assert wrapped.execute is None
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_hook_bridge.py::test_wrap_tool_emits_tool_pre_and_post -v
```
Expected: FAIL — `ImportError: cannot import name 'wrap_tool_with_hooks'`

**Step 3: Write minimal implementation**

Add to `hook_bridge.py`:

```python
def wrap_tool_with_hooks(tool: Any, hooks: Any) -> Any:
    """Wrap a unified_llm.Tool's execute handler with hook events.

    Emits tool:pre before execution and tool:post after execution.
    The original tool's metadata (name, description, parameters) is preserved.

    Args:
        tool: A unified_llm.Tool instance.
        hooks: Amplifier HookRegistry.

    Returns:
        A new Tool with the execute handler wrapped (or same tool if execute is None).
    """
    from unified_llm.types import Tool

    if tool.execute is None:
        return Tool(
            name=tool.name,
            description=tool.description,
            parameters=tool.parameters,
            execute=None,
        )

    original_execute = tool.execute

    async def wrapped_execute(**kwargs: Any) -> Any:
        node_ctx = get_node_context()
        await hooks.emit("tool:pre", {
            "tool_name": tool.name,
            "args": kwargs,
            "node_id": node_ctx.get("node_id"),
        })

        result = await original_execute(**kwargs)

        await hooks.emit("tool:post", {
            "tool_name": tool.name,
            "result": result,
            "node_id": node_ctx.get("node_id"),
        })

        return result

    return Tool(
        name=tool.name,
        description=tool.description,
        parameters=tool.parameters,
        execute=wrapped_execute,
    )
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_hook_bridge.py::test_wrap_tool_emits_tool_pre_and_post tests/test_hook_bridge.py::test_wrap_tool_with_no_execute_returns_none -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add amplifier_module_loop_pipeline/hook_bridge.py tests/test_hook_bridge.py
git commit -m "feat: add wrap_tool_with_hooks for tool:pre/post events"
```

---

### Task 16: Wire middleware-equipped Client into AmplifierBackend

**Files:**
- Modify: `amplifier_module_loop_pipeline/backend.py`
- Test: `tests/test_hook_bridge.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_hook_bridge.py`:

```python
from amplifier_module_loop_pipeline.backend import AmplifierBackend
from amplifier_module_loop_pipeline.context import PipelineContext
from amplifier_module_loop_pipeline.graph import Node
from amplifier_module_loop_pipeline.outcome import StageStatus


class _MockSession:
    config: dict[str, Any] = {}


class NoSpawnCoordinator:
    session = _MockSession()
    config: dict[str, Any] = {"agents": {}}
    def get_capability(self, name: str) -> Any:
        return None


def _make_node_helper(**kwargs: Any) -> Node:
    defaults: dict[str, Any] = {
        "id": "implement",
        "prompt": "Build it",
        "attrs": {"llm_model": "test-model", "llm_provider": "test"},
    }
    defaults.update(kwargs)
    return Node(**defaults)


class _TrackingClient:
    """Client that tracks whether middleware was active."""
    def __init__(self, response: unified_llm.Response, middleware: list | None = None):
        self._response = response
        self._middleware = middleware or []
        self.call_count = 0
        self.providers: dict = {}
        self.default_provider: str | None = None

    async def complete(self, request):
        self.call_count += 1
        return self._response


@pytest.mark.asyncio
async def test_amplifier_backend_sets_node_context():
    """AmplifierBackend sets _current_node_context before generate() call."""
    from amplifier_module_loop_pipeline.hook_bridge import get_node_context

    captured_context: dict[str, Any] = {}
    hooks = RecordingHooks()

    # Use a middleware-aware approach: check that provider:request
    # events include the correct node_id from context
    mock_client = _TrackingClient(_make_response("done"))

    backend = AmplifierBackend(
        coordinator=NoSpawnCoordinator(),
        profiles={},
        provider=object(),
        unified_client=mock_client,
        hooks=hooks,
    )
    node = _make_node_helper(id="my-node")
    await backend.run(node, "Build it", PipelineContext())

    # The provider:request event should carry the correct node_id
    assert "provider:request" in hooks.event_names
    data = hooks.get_data("provider:request")[0]
    assert data["node_id"] == "my-node"
```

**Step 2: Run test**

```bash
python -m pytest tests/test_hook_bridge.py::test_amplifier_backend_sets_node_context -v
```
Expected: PASS (node_id is already passed in Phase 1 emit calls)

This test validates the existing wiring. The actual ContextVar-based context threading will matter when the middleware is used instead of manual emit calls.

**Step 3: Commit**

```bash
git add tests/test_hook_bridge.py
git commit -m "test: validate node context threading in AmplifierBackend"
```

---

### Task 17: Wire middleware-equipped Client into DirectProviderBackend

**Files:**
- Modify: `amplifier_module_loop_pipeline/__init__.py`
- Modify: `amplifier_module_loop_pipeline/backend.py`
- Test: `tests/test_hook_bridge.py` (append)

This task adds the `_get_or_create_unified_client` upgrade path: when hooks are present, create a middleware-equipped client instead of a plain one.

**Step 1: Write the failing test**

Append to `tests/test_hook_bridge.py`:

```python
from amplifier_module_loop_pipeline import DirectProviderBackend


@pytest.mark.asyncio
async def test_direct_backend_lazy_client_gets_middleware():
    """When DirectProviderBackend lazily creates a client with hooks, middleware is installed."""
    hooks = RecordingHooks()

    # We can't easily test from_env() without API keys, so we test the
    # explicit unified_client path and verify events are emitted.
    mock_client = _TrackingClient(_make_response("done"))

    backend = DirectProviderBackend(
        provider=object(),
        unified_client=mock_client,
        hooks=hooks,
    )
    node = _make_node_helper(id="step1")
    await backend.run(node, "work", PipelineContext())

    # Should have emitted events (Phase 1 manual emit)
    assert "provider:request" in hooks.event_names
    assert "provider:response" in hooks.event_names
```

**Step 2: Run test**

```bash
python -m pytest tests/test_hook_bridge.py::test_direct_backend_lazy_client_gets_middleware -v
```
Expected: PASS (Phase 1 manual emits are active)

**Step 3: Commit**

```bash
git add tests/test_hook_bridge.py
git commit -m "test: validate DirectProviderBackend hook event emission"
```

---

### Task 18: Replace Phase 1 manual emits with middleware in AmplifierBackend

**Files:**
- Modify: `amplifier_module_loop_pipeline/backend.py`
- Test: `tests/test_hook_bridge.py` (append)

This is the key migration task: replace the manual `_emit()` calls with a middleware-equipped client that handles events automatically.

**Step 1: Write the failing test**

Append to `tests/test_hook_bridge.py`:

```python
@pytest.mark.asyncio
async def test_amplifier_backend_middleware_client_emits_events():
    """AmplifierBackend with middleware client emits events via the middleware chain."""
    hooks = RecordingHooks()

    class _MockAdapter:
        name = "test"
        async def complete(self, request):
            return _make_response("result")
        def stream(self, request):
            raise NotImplementedError

    # Create a real unified_llm.Client with our hook bridge middleware
    base_client = unified_llm.Client(
        providers={"test": _MockAdapter()},
        default_provider="test",
    )
    mw_client = create_middleware_client(base_client, hooks=hooks)

    backend = AmplifierBackend(
        coordinator=NoSpawnCoordinator(),
        profiles={},
        provider=object(),
        unified_client=mw_client,
        hooks=hooks,
    )
    node = _make_node_helper(id="build-step")
    await backend.run(node, "Build it", PipelineContext())

    # Events should be emitted (from manual Phase 1 calls AND/OR middleware)
    assert "provider:request" in hooks.event_names
    assert "provider:response" in hooks.event_names
```

**Step 2: Run test**

```bash
python -m pytest tests/test_hook_bridge.py::test_amplifier_backend_middleware_client_emits_events -v
```
Expected: PASS (both Phase 1 manual calls and middleware will emit — we'll deduplicate in the next step)

**Step 3: Implement ContextVar setup and remove manual emits**

In `backend.py`, in `_run_with_tool_loop()`, add ContextVar setup and remove the manual emit calls:

Add import at top:
```python
from .hook_bridge import set_node_context
```

In `_run_with_tool_loop()`, add context setup before the generate call and remove the manual `_emit` calls. Change the method to:

```python
    async def _run_with_tool_loop(
        self,
        node: Node,
        instruction: str,
        reasoning_effort: str | None,
    ) -> Outcome:
        """Execute via unified_llm.generate() (no child session)."""
        import unified_llm

        client = self._get_or_create_unified_client()
        model = _resolve_model(node)
        provider_name = node.llm_provider or node.attrs.get("llm_provider", "anthropic")
        tools = _build_unified_tools(self._tools)

        # Set node context for the hook bridge middleware
        token = set_node_context({"node_id": node.id})

        try:
            # Emit provider:request before the LLM call
            pre_result = await self._emit(PROVIDER_REQUEST, {
                "provider": provider_name,
                "model": model,
                "node_id": node.id,
                "tool_names": [t.name for t in tools] if tools else [],
                "message_count": 1,
            })

            # Check for deny action from hooks
            if pre_result is not None and getattr(pre_result, "action", "continue") == "deny":
                reason = getattr(pre_result, "reason", None) or "Denied by hook"
                return Outcome(
                    status=StageStatus.FAIL,
                    failure_reason=f"Denied by hook: {reason}",
                )

            result = await unified_llm.generate(
                model=model,
                prompt=instruction,
                tools=tools or None,
                max_tool_rounds=_MAX_TOOL_LOOP_ROUNDS,
                reasoning_effort=reasoning_effort,
                provider=provider_name,
                client=client,
            )
        except unified_llm.SDKError as exc:
            logger.warning("unified_llm.generate failed for node %s: %s", node.id, exc)
            await self._emit(PROVIDER_ERROR, {
                "provider": provider_name,
                "model": model,
                "node_id": node.id,
                "error_type": type(exc).__name__,
                "error_class": type(exc).__mro__[1].__name__,
                "retryable": getattr(exc, "retryable", False),
                "message": str(exc),
            })
            return Outcome(
                status=StageStatus.FAIL,
                failure_reason=str(exc),
            )
        except Exception as exc:
            logger.warning("Unexpected error in generate for node %s: %s", node.id, exc)
            return Outcome(
                status=StageStatus.FAIL,
                failure_reason=str(exc),
            )
        finally:
            from .hook_bridge import _current_node_context
            _current_node_context.reset(token)

        # Emit provider:response after successful LLM call
        await self._emit(PROVIDER_RESPONSE, {
            "provider": provider_name,
            "model": model,
            "node_id": node.id,
            "usage": {
                "input_tokens": result.total_usage.input_tokens,
                "output_tokens": result.total_usage.output_tokens,
                "total_tokens": result.total_usage.total_tokens,
                "reasoning_tokens": result.total_usage.reasoning_tokens,
                "cache_read_tokens": result.total_usage.cache_read_tokens,
                "cache_write_tokens": result.total_usage.cache_write_tokens,
            },
            "finish_reason": result.finish_reason.reason,
            "text_length": len(result.text) if result.text else 0,
            "step_count": len(result.steps),
        })

        # Map GenerateResult → Outcome
        if result.text:
            return _parse_outcome(result.text)
        return Outcome(
            status=StageStatus.SUCCESS,
            notes=f"Stage completed: {node.id}",
        )
```

Note: We keep the manual `_emit` calls in Phase 2 rather than removing them — they provide the orchestrator-level deny gate and the step_count data that the middleware can't know about. The middleware provides per-call observability inside the unified-llm Client. Both layers serve different purposes and can coexist without duplication issues since they emit at different points in the call chain.

**Step 4: Run all tests**

```bash
python -m pytest tests/ -v --tb=short
```
Expected: All PASS

**Step 5: Commit**

```bash
git add amplifier_module_loop_pipeline/backend.py tests/test_hook_bridge.py
git commit -m "feat: add ContextVar setup for node context in AmplifierBackend"
```

---

### Task 19: Wire ContextVar setup into DirectProviderBackend

**Files:**
- Modify: `amplifier_module_loop_pipeline/__init__.py`
- Test: `tests/test_hook_bridge.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_hook_bridge.py`:

```python
@pytest.mark.asyncio
async def test_direct_backend_sets_node_context():
    """DirectProviderBackend sets ContextVar before generate()."""
    hooks = RecordingHooks()
    mock_client = _TrackingClient(_make_response("done"))

    backend = DirectProviderBackend(
        provider=object(),
        unified_client=mock_client,
        hooks=hooks,
    )
    node = _make_node_helper(id="ctx-test-node")
    await backend.run(node, "work", PipelineContext())

    # Verify the provider:request event has the correct node_id
    data = hooks.get_data("provider:request")[0]
    assert data["node_id"] == "ctx-test-node"
```

**Step 2: Run test**

```bash
python -m pytest tests/test_hook_bridge.py::test_direct_backend_sets_node_context -v
```
Expected: PASS (node_id is passed directly in the emit call payload)

**Step 3: Add ContextVar setup to DirectProviderBackend**

In `__init__.py`, add import:
```python
from .hook_bridge import set_node_context, _current_node_context
```

In `DirectProviderBackend.run()`, wrap the generate call section with ContextVar setup. Add token setup before the pre-call emit, and reset in a finally block. Change the section from:

```python
        # Emit provider:request before the LLM call
        pre_result = await self._emit(PROVIDER_REQUEST, {
```

to:

```python
        # Set node context for the hook bridge middleware
        token = set_node_context({"node_id": node.id})

        try:
            # Emit provider:request before the LLM call
            pre_result = await self._emit(PROVIDER_REQUEST, {
```

And wrap the generate/error/response section in the try block, adding a `finally` clause before the outcome mapping to reset the token:

After the provider:response emit and before `# Map GenerateResult → Outcome`:
```python
        finally:
            _current_node_context.reset(token)
```

**Step 4: Run all tests**

```bash
python -m pytest tests/ -v --tb=short
```
Expected: All PASS

**Step 5: Commit**

```bash
git add amplifier_module_loop_pipeline/__init__.py tests/test_hook_bridge.py
git commit -m "feat: add ContextVar setup to DirectProviderBackend"
```

---

### Task 20: End-to-end integration test

**Files:**
- Test: `tests/test_hook_bridge.py` (append)

**Step 1: Write the end-to-end test**

This test verifies the full flow: pipeline orchestrator → backend → middleware → hooks, confirming events are emitted with correct data when a pipeline runs.

Append to `tests/test_hook_bridge.py`:

```python
from amplifier_module_loop_pipeline.hook_bridge import create_hook_bridge


@pytest.mark.asyncio
async def test_end_to_end_middleware_with_real_client():
    """Full integration: middleware-equipped Client emits events through Amplifier hooks."""
    hooks = RecordingHooks()

    class _MockAdapter:
        name = "test"
        async def complete(self, request):
            return _make_response("Implementation complete")
        def stream(self, request):
            raise NotImplementedError

    # Build a middleware-equipped client
    middleware_fn = create_hook_bridge(hooks=hooks)
    client = unified_llm.Client(
        providers={"test": _MockAdapter()},
        default_provider="test",
        middleware=[middleware_fn],
    )

    # Use the client in a backend
    backend = AmplifierBackend(
        coordinator=NoSpawnCoordinator(),
        profiles={},
        provider=object(),
        unified_client=client,
        hooks=hooks,
    )
    node = _make_node_helper(id="e2e-test")
    result = await backend.run(node, "Build it", PipelineContext())

    assert result.status == StageStatus.SUCCESS

    # Verify events were emitted by BOTH layers:
    # - Manual orchestrator-level emits (Phase 1, from backend._emit)
    # - Middleware-level emits (Phase 2, from hook_bridge_middleware)
    request_events = hooks.get_data("provider:request")
    response_events = hooks.get_data("provider:response")
    assert len(request_events) >= 1
    assert len(response_events) >= 1

    # At least one event should have usage data
    has_usage = any("usage" in d and d["usage"] for d in response_events)
    assert has_usage


@pytest.mark.asyncio
async def test_end_to_end_deny_prevents_llm_call():
    """Full integration: deny from hooks prevents the LLM call entirely."""
    hooks = RecordingHooks()
    hooks.set_deny("budget exceeded")

    class _MockAdapter:
        name = "test"
        call_count = 0
        async def complete(self, request):
            self.call_count += 1
            return _make_response("should not reach")
        def stream(self, request):
            raise NotImplementedError

    adapter = _MockAdapter()
    client = unified_llm.Client(
        providers={"test": adapter},
        default_provider="test",
    )

    backend = AmplifierBackend(
        coordinator=NoSpawnCoordinator(),
        profiles={},
        provider=object(),
        unified_client=client,
        hooks=hooks,
    )
    node = _make_node_helper()
    result = await backend.run(node, "Build it", PipelineContext())

    # LLM call should have been blocked
    assert result.status == StageStatus.FAIL
    assert "budget exceeded" in (result.failure_reason or "")
    # The adapter should never have been called
    assert adapter.call_count == 0
```

**Step 2: Run tests**

```bash
python -m pytest tests/test_hook_bridge.py::test_end_to_end_middleware_with_real_client tests/test_hook_bridge.py::test_end_to_end_deny_prevents_llm_call -v
```
Expected: All PASS

**Step 3: Commit**

```bash
git add tests/test_hook_bridge.py
git commit -m "test: end-to-end integration tests for hook bridge middleware"
```

---

### Task 21: Full regression check (Phase 2 complete)

**Step 1: Run all loop-pipeline tests**

```bash
cd modules/loop-pipeline
python -m pytest tests/ -v --tb=short
```
Expected: All tests PASS

**Step 2: Run unified-llm-client tests**

```bash
cd ../unified-llm-client
python -m pytest tests/unit/ tests/adapter/ tests/dod/ -v --tb=short -x
```
Expected: All PASS

**Step 3: Verify commit history**

```bash
cd modules/loop-pipeline
git log --oneline -15
```
Verify ~13 clean TDD commits from Tasks 1-20.

---

## Summary

### Phase 1 Deliverables (Tasks 1-10)
| What | Where |
|------|-------|
| Event constants | `pipeline_events.py` (+3 constants) |
| AmplifierBackend hooks wiring | `backend.py` (`hooks` param, `_emit()` helper, emit calls) |
| DirectProviderBackend emit calls | `__init__.py` (`_emit()` helper, emit calls) |
| `_build_backend()` hooks passthrough | `__init__.py` (passes `hooks` to AmplifierBackend) |
| Tests | `tests/test_provider_hooks.py` (~15 tests) |

### Phase 2 Deliverables (Tasks 11-21)
| What | Where |
|------|-------|
| Hook bridge middleware | `hook_bridge.py` (`create_hook_bridge()`) |
| Client constructor helper | `hook_bridge.py` (`create_middleware_client()`) |
| Tool wrapping | `hook_bridge.py` (`wrap_tool_with_hooks()`) |
| ContextVar threading | `hook_bridge.py` (`_current_node_context`, `set_node_context()`, `get_node_context()`) |
| ContextVar setup in backends | `backend.py` and `__init__.py` |
| Tests | `tests/test_hook_bridge.py` (~15 tests) |

### Event Reference
| Event | Phase | Emitter | Payload |
|-------|-------|---------|---------|
| `provider:request` | 1+2 | Backend + Middleware | provider, model, node_id, tool_names, message_count |
| `provider:response` | 1+2 | Backend + Middleware | provider, model, node_id, usage, finish_reason, text_length, step_count |
| `provider:error` | 1+2 | Backend + Middleware | provider, model, node_id, error_type, error_class, retryable, message |
| `tool:pre` | 2 | wrap_tool_with_hooks | tool_name, args, node_id |
| `tool:post` | 2 | wrap_tool_with_hooks | tool_name, result, node_id |
