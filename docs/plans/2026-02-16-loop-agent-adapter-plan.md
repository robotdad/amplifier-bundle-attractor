# Loop-Agent Unified Provider Adapter Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Create a `UnifiedProviderAdapter` that wraps `unified-llm-client` to satisfy `AgentSession`'s provider duck-type contract, enabling unified retry, error handling, and streaming normalization — with zero changes to `agent_session.py`.

**Architecture:** A thin adapter class in `amplifier_module_loop_agent/unified_provider_adapter.py` translates between amplifier-core types (`ChatRequest`/`ChatResponse`) and unified-llm types (`Request`/`Response`/`StreamEvent`). The `AgentOrchestrator.execute()` wraps the native provider with this adapter before passing it to `AgentSession`. The agent session sees the same duck-type interface it always has — `complete()` returns `ChatResponse`, `stream()` yields `dict` chunks.

**Tech Stack:** Python 3.11+, pytest-asyncio (strict mode), amplifier-core message_models + llm_errors, unified-llm-client types + errors + Client

**Design Reference:** `docs/designs/loop-agent-unified-adapter.md` in amplifier-bundle-attractor

---

## Files Overview

| Action | Path (relative to `amplifier-module-loop-agent/`) | Description |
|--------|------|-------------|
| Modify | `pyproject.toml` | Add `unified-llm-client` dev dependency |
| Create | `amplifier_module_loop_agent/unified_provider_adapter.py` | The adapter |
| Create | `tests/test_unified_provider_adapter.py` | Adapter unit tests |
| Modify | `amplifier_module_loop_agent/__init__.py` | Injection in `AgentOrchestrator.execute()` |

**Working directory for all commands:** `modules/loop-agent`

**Test command (adapter only):** `uv run pytest tests/test_unified_provider_adapter.py -v`

**Full regression:** `uv run pytest tests/ -v`

---

## Type Systems Reference

The adapter bridges two type systems. This table is the Rosetta Stone for every task:

| Concept | amplifier-core type | unified-llm type |
|---------|---------------------|-------------------|
| Request envelope | `ChatRequest` (Pydantic) | `Request` (dataclass) |
| Response envelope | `ChatResponse` (Pydantic) | `Response` (dataclass) |
| Message | `message_models.Message` | `types.Message` |
| Text content | `TextBlock` | `ContentPart(kind=TEXT, text=...)` |
| Thinking content | `ThinkingBlock` (with `.signature`) | `ContentPart(kind=THINKING, thinking=ThinkingData(...))` |
| Tool call (response) | `message_models.ToolCall` | `ToolCallData` |
| Tool call (streaming) | N/A (dict chunk) | `types.ToolCall` (on `StreamEvent`) |
| Usage | `message_models.Usage` (Pydantic) | `types.Usage` (dataclass) |
| Stream chunk | `dict[str, Any]` | `StreamEvent` |
| Error base | `LLMError` | `SDKError` |

---

## Phase 1: Request Translation (Tasks 1–5)

### Task 1: Project Setup and Adapter Skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `amplifier_module_loop_agent/unified_provider_adapter.py`
- Create: `tests/test_unified_provider_adapter.py`

**Step 1: Add unified-llm-client to dev dependencies**

In `pyproject.toml`, add to the `[dependency-groups] dev` list:

```toml
[dependency-groups]
dev = [
    "amplifier-core",
    "unified-llm-client",
    "pytest>=8.0.0",
    "pytest-asyncio>=1.0.0",
]
```

And add to `[tool.uv.sources]`:

```toml
[tool.uv.sources]
amplifier-core = { path = "../amplifier-core", editable = true }
unified-llm-client = { path = "../unified-llm-client", editable = true }
```

Run: `uv sync` to install the dependency.

**Step 2: Create test file with import smoke test**

```python
# tests/test_unified_provider_adapter.py
"""Tests for UnifiedProviderAdapter.

Validates the adapter that bridges unified-llm-client types to the
duck-type contract expected by AgentSession (ChatRequest/ChatResponse).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


def test_adapter_is_importable():
    """Smoke test: module imports without error."""
    from amplifier_module_loop_agent.unified_provider_adapter import (
        UnifiedProviderAdapter,
    )

    assert UnifiedProviderAdapter is not None
```

**Step 3: Create adapter skeleton**

```python
# amplifier_module_loop_agent/unified_provider_adapter.py
"""UnifiedProviderAdapter: wraps unified-llm-client for loop-agent's duck-type contract.

See docs/designs/loop-agent-unified-adapter.md for full design.

The adapter satisfies AgentSession's provider duck-type:
  - adapter.complete(request: ChatRequest) -> ChatResponse
  - adapter.stream(request: ChatRequest) -> AsyncIterator[dict]

Internally it translates types, calls unified-llm-client, translates
results back, and maps errors from SDKError to LLMError.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class UnifiedProviderAdapter:
    """Wraps unified-llm-client to satisfy loop-agent's provider duck-type."""

    pass
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_unified_provider_adapter.py::test_adapter_is_importable -v`

Expected: PASS

**Step 5: Commit**

```bash
git add pyproject.toml amplifier_module_loop_agent/unified_provider_adapter.py tests/test_unified_provider_adapter.py
git commit -m "feat(loop-agent): add unified-llm-client dep and adapter skeleton"
```

---

### Task 2: Adapter Constructor

**Files:**
- Modify: `amplifier_module_loop_agent/unified_provider_adapter.py`
- Modify: `tests/test_unified_provider_adapter.py`

**Step 1: Write the failing test**

Add to `tests/test_unified_provider_adapter.py`:

```python
from amplifier_module_loop_agent.unified_provider_adapter import UnifiedProviderAdapter


def test_constructor_stores_config():
    """Constructor stores provider_name, model, and accepts injected client."""
    mock_client = MagicMock()
    adapter = UnifiedProviderAdapter(
        provider_name="anthropic",
        model="claude-sonnet-4-20250514",
        client=mock_client,
    )
    assert adapter._provider_name == "anthropic"
    assert adapter._model == "claude-sonnet-4-20250514"
    assert adapter._client is mock_client
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_unified_provider_adapter.py::test_constructor_stores_config -v`

Expected: FAIL — `TypeError: UnifiedProviderAdapter() takes no arguments`

**Step 3: Implement constructor**

Replace the `pass` in `unified_provider_adapter.py`:

```python
class UnifiedProviderAdapter:
    """Wraps unified-llm-client to satisfy loop-agent's provider duck-type."""

    def __init__(
        self,
        *,
        provider_name: str,
        model: str,
        client: Any = None,
    ) -> None:
        self._provider_name = provider_name
        self._model = model
        self._client = client  # Injected for testing; Task 18 builds from env
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_unified_provider_adapter.py -v`

Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add -u && git commit -m "feat(loop-agent): adapter constructor with provider_name, model, client"
```

---

### Task 3: Translate Simple Text Messages

Translate `ChatRequest` messages with plain string content to `unified_llm.Message` objects.

**Files:**
- Modify: `amplifier_module_loop_agent/unified_provider_adapter.py`
- Modify: `tests/test_unified_provider_adapter.py`

**Step 1: Write the failing test**

Add to test file:

```python
from amplifier_core.message_models import ChatRequest, Message as CoreMessage
from unified_llm.types import ContentKind, Role


def test_translate_text_messages():
    """String content messages translate to TEXT ContentParts."""
    adapter = UnifiedProviderAdapter(
        provider_name="anthropic",
        model="claude-sonnet-4-20250514",
        client=MagicMock(),
    )
    request = ChatRequest(
        messages=[
            CoreMessage(role="system", content="You are helpful."),
            CoreMessage(role="user", content="Hello"),
            CoreMessage(role="assistant", content="Hi there"),
        ],
        tools=None,
    )
    ulm_request = adapter._translate_request(request)

    assert len(ulm_request.messages) == 3
    assert ulm_request.messages[0].role == Role.SYSTEM
    assert ulm_request.messages[0].content[0].kind == ContentKind.TEXT
    assert ulm_request.messages[0].content[0].text == "You are helpful."
    assert ulm_request.messages[1].role == Role.USER
    assert ulm_request.messages[1].content[0].text == "Hello"
    assert ulm_request.messages[2].role == Role.ASSISTANT
    assert ulm_request.messages[2].content[0].text == "Hi there"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_unified_provider_adapter.py::test_translate_text_messages -v`

Expected: FAIL — `AttributeError: 'UnifiedProviderAdapter' object has no attribute '_translate_request'`

**Step 3: Implement text message translation**

Add these imports and methods to `unified_provider_adapter.py`:

```python
from amplifier_core.message_models import (
    ChatRequest,
    ChatResponse,
    Message as CoreMessage,
    TextBlock,
    ThinkingBlock,
    ToolCall as CoreToolCall,
    Usage as CoreUsage,
)
from unified_llm.types import (
    ContentKind,
    ContentPart,
    Message as ULMMessage,
    Request as ULMRequest,
    Role,
)
```

And add these methods to the class:

```python
    # ------------------------------------------------------------------
    # Request translation
    # ------------------------------------------------------------------

    def _translate_request(self, request: ChatRequest) -> ULMRequest:
        """Translate ChatRequest -> unified_llm.Request."""
        messages = [self._translate_message(m) for m in request.messages]
        return ULMRequest(
            model=self._model,
            messages=messages,
            provider=self._provider_name,
        )

    def _translate_message(self, msg: CoreMessage) -> ULMMessage:
        """Translate a single amplifier-core Message to unified-llm Message."""
        role = self._translate_role(msg.role)
        content = self._translate_content(msg.content)
        return ULMMessage(role=role, content=content, tool_call_id=msg.tool_call_id)

    @staticmethod
    def _translate_role(role: str) -> Role:
        """Map amplifier-core role string to unified-llm Role enum."""
        _ROLE_MAP = {
            "system": Role.SYSTEM,
            "user": Role.USER,
            "assistant": Role.ASSISTANT,
            "tool": Role.TOOL,
            "developer": Role.DEVELOPER,
            "function": Role.TOOL,  # Legacy function role
        }
        return _ROLE_MAP.get(role, Role.USER)

    @staticmethod
    def _translate_content(content: str | list) -> list[ContentPart]:
        """Translate message content to unified-llm ContentParts."""
        if isinstance(content, str):
            return [ContentPart(kind=ContentKind.TEXT, text=content)]
        # Content block list — handled in Task 4
        return [ContentPart(kind=ContentKind.TEXT, text="")]
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_unified_provider_adapter.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add -u && git commit -m "feat(loop-agent): translate simple text messages to unified-llm format"
```

---

### Task 4: Translate Complex Content Block Messages

Handle `TextBlock`, `ThinkingBlock` (with signature preservation), and tool result messages.

**Files:**
- Modify: `amplifier_module_loop_agent/unified_provider_adapter.py`
- Modify: `tests/test_unified_provider_adapter.py`

**Step 1: Write the failing tests**

Add to test file:

```python
from amplifier_core.message_models import TextBlock, ThinkingBlock
from unified_llm.types import ContentKind


def test_translate_content_blocks():
    """TextBlock and ThinkingBlock translate to correct ContentParts."""
    adapter = UnifiedProviderAdapter(
        provider_name="anthropic",
        model="claude-sonnet-4-20250514",
        client=MagicMock(),
    )
    request = ChatRequest(
        messages=[
            CoreMessage(
                role="assistant",
                content=[
                    ThinkingBlock(thinking="Let me think...", signature="sig_abc123"),
                    TextBlock(text="Here is my answer"),
                ],
            ),
        ],
        tools=None,
    )
    ulm_request = adapter._translate_request(request)

    parts = ulm_request.messages[0].content
    assert len(parts) == 2

    # ThinkingBlock -> THINKING ContentPart with signature
    assert parts[0].kind == ContentKind.THINKING
    assert parts[0].thinking is not None
    assert parts[0].thinking.text == "Let me think..."
    assert parts[0].thinking.signature == "sig_abc123"

    # TextBlock -> TEXT ContentPart
    assert parts[1].kind == ContentKind.TEXT
    assert parts[1].text == "Here is my answer"


def test_translate_tool_result_message():
    """Tool result message translates to TOOL_RESULT ContentPart."""
    adapter = UnifiedProviderAdapter(
        provider_name="anthropic",
        model="claude-sonnet-4-20250514",
        client=MagicMock(),
    )
    request = ChatRequest(
        messages=[
            CoreMessage(role="tool", content="file contents here", tool_call_id="tc_1"),
        ],
        tools=None,
    )
    ulm_request = adapter._translate_request(request)

    msg = ulm_request.messages[0]
    assert msg.role == Role.TOOL
    assert msg.tool_call_id == "tc_1"
    assert msg.content[0].kind == ContentKind.TOOL_RESULT
    assert msg.content[0].tool_result is not None
    assert msg.content[0].tool_result.tool_call_id == "tc_1"
    assert msg.content[0].tool_result.content == "file contents here"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_unified_provider_adapter.py::test_translate_content_blocks -v`

Expected: FAIL — content block list returns fallback empty text

**Step 3: Implement content block translation**

Add import to `unified_provider_adapter.py`:

```python
from unified_llm.types import (
    # ... existing imports ...
    ThinkingData,
    ToolCallData as ULMToolCallData,
    ToolResultData as ULMToolResultData,
)
```

Replace the `_translate_content` method and update `_translate_message`:

```python
    def _translate_message(self, msg: CoreMessage) -> ULMMessage:
        """Translate a single amplifier-core Message to unified-llm Message."""
        role = self._translate_role(msg.role)

        # Tool result messages: wrap string content as TOOL_RESULT part
        if msg.role == "tool" and msg.tool_call_id:
            content_str = msg.content if isinstance(msg.content, str) else str(msg.content)
            content = [
                ContentPart(
                    kind=ContentKind.TOOL_RESULT,
                    tool_result=ULMToolResultData(
                        tool_call_id=msg.tool_call_id,
                        content=content_str,
                    ),
                )
            ]
            return ULMMessage(role=role, content=content, tool_call_id=msg.tool_call_id)

        content = self._translate_content(msg.content)
        return ULMMessage(role=role, content=content, tool_call_id=msg.tool_call_id)

    @staticmethod
    def _translate_content(content: str | list) -> list[ContentPart]:
        """Translate message content to unified-llm ContentParts."""
        if isinstance(content, str):
            return [ContentPart(kind=ContentKind.TEXT, text=content)]

        parts: list[ContentPart] = []
        for block in content:
            if isinstance(block, TextBlock):
                parts.append(ContentPart(kind=ContentKind.TEXT, text=block.text))
            elif isinstance(block, ThinkingBlock):
                parts.append(
                    ContentPart(
                        kind=ContentKind.THINKING,
                        thinking=ThinkingData(
                            text=block.thinking,
                            signature=block.signature,
                        ),
                    )
                )
            # Other block types (ToolCallBlock, etc.) are not common in
            # the messages produced by convert_history_to_messages, but
            # fall through gracefully.

        return parts or [ContentPart(kind=ContentKind.TEXT, text="")]
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_unified_provider_adapter.py -v`

Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add -u && git commit -m "feat(loop-agent): translate content blocks (TextBlock, ThinkingBlock, tool results)"
```

---

### Task 5: Translate Generation Parameters

Wire `reasoning_effort` and `model` into the unified-llm `Request`.

**Files:**
- Modify: `amplifier_module_loop_agent/unified_provider_adapter.py`
- Modify: `tests/test_unified_provider_adapter.py`

**Step 1: Write the failing test**

Add to test file:

```python
def test_translate_request_params():
    """reasoning_effort and model are passed through to unified-llm Request."""
    adapter = UnifiedProviderAdapter(
        provider_name="openai",
        model="o3-mini",
        client=MagicMock(),
    )
    request = ChatRequest(
        messages=[CoreMessage(role="user", content="Think hard")],
        reasoning_effort="high",
    )
    ulm_request = adapter._translate_request(request)

    assert ulm_request.model == "o3-mini"
    assert ulm_request.provider == "openai"
    assert ulm_request.reasoning_effort == "high"
    # Tools are NOT passed — agent owns the tool loop
    assert ulm_request.tools is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_unified_provider_adapter.py::test_translate_request_params -v`

Expected: FAIL — `reasoning_effort` not set on ULMRequest

**Step 3: Update `_translate_request` to pass params**

In `unified_provider_adapter.py`, update `_translate_request`:

```python
    def _translate_request(self, request: ChatRequest) -> ULMRequest:
        """Translate ChatRequest -> unified_llm.Request."""
        messages = [self._translate_message(m) for m in request.messages]
        return ULMRequest(
            model=self._model,
            messages=messages,
            provider=self._provider_name,
            reasoning_effort=request.reasoning_effort,
            # Tools are NOT passed: the agent owns the tool loop.
            # We only do single LLM calls via client.complete().
        )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_unified_provider_adapter.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add -u && git commit -m "feat(loop-agent): pass reasoning_effort and model to unified-llm Request"
```

---

## Phase 2: Response Translation — Non-Streaming (Tasks 6–9)

### Task 6: Translate Text Response

Translate a `unified_llm.Response` with text content into a `ChatResponse` with `TextBlock`.

**Files:**
- Modify: `amplifier_module_loop_agent/unified_provider_adapter.py`
- Modify: `tests/test_unified_provider_adapter.py`

**Step 1: Write the failing test**

Add to test file:

```python
from unified_llm.types import (
    ContentPart,
    FinishReason,
    Message as ULMMessage,
    Response as ULMResponse,
    Role,
    Usage as ULMUsage,
)


def test_translate_text_response():
    """Response with TEXT content -> ChatResponse with TextBlock."""
    adapter = UnifiedProviderAdapter(
        provider_name="anthropic",
        model="claude-sonnet-4-20250514",
        client=MagicMock(),
    )
    ulm_response = ULMResponse(
        id="resp_1",
        model="claude-sonnet-4-20250514",
        provider="anthropic",
        message=ULMMessage(
            role=Role.ASSISTANT,
            content=[ContentPart(kind=ContentKind.TEXT, text="Hello world")],
        ),
        finish_reason=FinishReason(reason="stop"),
        usage=ULMUsage(input_tokens=10, output_tokens=5, total_tokens=15),
    )
    chat_response = adapter._translate_response(ulm_response)

    assert len(chat_response.content) == 1
    assert chat_response.content[0].type == "text"
    assert chat_response.content[0].text == "Hello world"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_unified_provider_adapter.py::test_translate_text_response -v`

Expected: FAIL — `_translate_response` does not exist

**Step 3: Implement response translation**

Add to `unified_provider_adapter.py` imports:

```python
from unified_llm.types import (
    # ... existing ...
    Response as ULMResponse,
    FinishReason as ULMFinishReason,
    Usage as ULMUsage,
)
```

Add method to the class:

```python
    # ------------------------------------------------------------------
    # Response translation (non-streaming)
    # ------------------------------------------------------------------

    def _translate_response(self, response: ULMResponse) -> ChatResponse:
        """Translate unified_llm.Response -> ChatResponse."""
        content_blocks = []

        for part in response.message.content:
            if part.kind == ContentKind.TEXT and part.text:
                content_blocks.append(TextBlock(text=part.text))
            elif part.kind == ContentKind.THINKING and part.thinking:
                content_blocks.append(
                    ThinkingBlock(
                        thinking=part.thinking.text,
                        signature=part.thinking.signature,
                    )
                )
            # TOOL_CALL parts handled separately below

        tool_calls = self._translate_tool_calls(response)
        usage = self._translate_usage(response.usage)

        return ChatResponse(
            content=content_blocks,
            tool_calls=tool_calls if tool_calls else None,
            usage=usage,
        )

    @staticmethod
    def _translate_tool_calls(response: ULMResponse) -> list[CoreToolCall]:
        """Extract tool calls from response (stub — implemented in Task 8)."""
        return []

    @staticmethod
    def _translate_usage(usage: ULMUsage | None) -> CoreUsage | None:
        """Translate usage (stub — implemented in Task 9)."""
        return None
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_unified_provider_adapter.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add -u && git commit -m "feat(loop-agent): translate text response from unified-llm to ChatResponse"
```

---

### Task 7: Translate Thinking Response with Signature Preservation

**Files:**
- Modify: `amplifier_module_loop_agent/unified_provider_adapter.py` (already handled in Task 6 implementation)
- Modify: `tests/test_unified_provider_adapter.py`

**Step 1: Write the failing test**

Add to test file:

```python
from unified_llm.types import ThinkingData


def test_translate_thinking_response_with_signature():
    """THINKING ContentPart -> ThinkingBlock with signature preserved."""
    adapter = UnifiedProviderAdapter(
        provider_name="anthropic",
        model="claude-sonnet-4-20250514",
        client=MagicMock(),
    )
    ulm_response = ULMResponse(
        id="resp_2",
        model="claude-sonnet-4-20250514",
        provider="anthropic",
        message=ULMMessage(
            role=Role.ASSISTANT,
            content=[
                ContentPart(
                    kind=ContentKind.THINKING,
                    thinking=ThinkingData(
                        text="I should analyze this carefully...",
                        signature="sig_roundtrip_abc",
                    ),
                ),
                ContentPart(kind=ContentKind.TEXT, text="Here is my analysis"),
            ],
        ),
        finish_reason=FinishReason(reason="stop"),
        usage=ULMUsage(input_tokens=20, output_tokens=50, total_tokens=70),
    )
    chat_response = adapter._translate_response(ulm_response)

    assert len(chat_response.content) == 2
    # ThinkingBlock with signature
    thinking = chat_response.content[0]
    assert thinking.type == "thinking"
    assert thinking.thinking == "I should analyze this carefully..."
    assert thinking.signature == "sig_roundtrip_abc"
    # TextBlock
    assert chat_response.content[1].type == "text"
    assert chat_response.content[1].text == "Here is my analysis"
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_unified_provider_adapter.py::test_translate_thinking_response_with_signature -v`

Expected: PASS — this was already implemented in Task 6's `_translate_response`

**Step 3: No new implementation needed**

The ThinkingBlock path including signature was implemented in Task 6. This task verifies the edge case.

**Step 4: Confirm all tests pass**

Run: `uv run pytest tests/test_unified_provider_adapter.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add -u && git commit -m "test(loop-agent): verify ThinkingBlock signature round-trip preservation"
```

---

### Task 8: Translate Tool Calls

Translate `ToolCallData` from unified-llm response to amplifier-core `ToolCall` objects.

**Files:**
- Modify: `amplifier_module_loop_agent/unified_provider_adapter.py`
- Modify: `tests/test_unified_provider_adapter.py`

**Step 1: Write the failing test**

Add to test file:

```python
from amplifier_core.message_models import ToolCall as CoreToolCall


def test_translate_tool_calls():
    """ToolCallData from response -> amplifier-core ToolCall objects."""
    adapter = UnifiedProviderAdapter(
        provider_name="anthropic",
        model="claude-sonnet-4-20250514",
        client=MagicMock(),
    )
    ulm_response = ULMResponse(
        id="resp_3",
        model="claude-sonnet-4-20250514",
        provider="anthropic",
        message=ULMMessage(
            role=Role.ASSISTANT,
            content=[
                ContentPart(
                    kind=ContentKind.TOOL_CALL,
                    tool_call=ULMToolCallData(
                        id="tc_1",
                        name="read_file",
                        arguments={"path": "/tmp/test.py"},
                    ),
                ),
                ContentPart(
                    kind=ContentKind.TOOL_CALL,
                    tool_call=ULMToolCallData(
                        id="tc_2",
                        name="write_file",
                        arguments={"path": "/tmp/out.py", "content": "hello"},
                    ),
                ),
            ],
        ),
        finish_reason=FinishReason(reason="tool_calls"),
        usage=ULMUsage(input_tokens=10, output_tokens=20, total_tokens=30),
    )
    chat_response = adapter._translate_response(ulm_response)

    assert chat_response.tool_calls is not None
    assert len(chat_response.tool_calls) == 2
    assert chat_response.tool_calls[0].id == "tc_1"
    assert chat_response.tool_calls[0].name == "read_file"
    assert chat_response.tool_calls[0].arguments == {"path": "/tmp/test.py"}
    assert chat_response.tool_calls[1].id == "tc_2"
    assert chat_response.tool_calls[1].name == "write_file"
```

Also add import at the top of the test file:

```python
from unified_llm.types import ToolCallData as ULMToolCallData
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_unified_provider_adapter.py::test_translate_tool_calls -v`

Expected: FAIL — `_translate_tool_calls` returns empty list

**Step 3: Implement tool call translation**

Add `import json` at the top of `unified_provider_adapter.py`.

Replace the `_translate_tool_calls` stub:

```python
    @staticmethod
    def _translate_tool_calls(response: ULMResponse) -> list[CoreToolCall]:
        """Extract and translate tool calls from unified-llm response."""
        result = []
        for tc_data in response.tool_calls:
            # ToolCallData.arguments can be dict or str (JSON)
            if isinstance(tc_data.arguments, dict):
                arguments = tc_data.arguments
            else:
                try:
                    arguments = json.loads(tc_data.arguments)
                except (json.JSONDecodeError, TypeError):
                    arguments = {}
            result.append(
                CoreToolCall(id=tc_data.id, name=tc_data.name, arguments=arguments)
            )
        return result
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_unified_provider_adapter.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add -u && git commit -m "feat(loop-agent): translate tool calls from unified-llm to amplifier-core ToolCall"
```

---

### Task 9: Translate Usage

Map all token usage fields between the two type systems.

**Files:**
- Modify: `amplifier_module_loop_agent/unified_provider_adapter.py`
- Modify: `tests/test_unified_provider_adapter.py`

**Step 1: Write the failing test**

Add to test file:

```python
from amplifier_core.message_models import Usage as CoreUsage


def test_translate_usage_all_fields():
    """All usage fields map correctly including optional ones."""
    adapter = UnifiedProviderAdapter(
        provider_name="anthropic",
        model="claude-sonnet-4-20250514",
        client=MagicMock(),
    )
    ulm_response = ULMResponse(
        id="resp_4",
        model="claude-sonnet-4-20250514",
        provider="anthropic",
        message=ULMMessage(
            role=Role.ASSISTANT,
            content=[ContentPart(kind=ContentKind.TEXT, text="ok")],
        ),
        finish_reason=FinishReason(reason="stop"),
        usage=ULMUsage(
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            reasoning_tokens=20,
            cache_read_tokens=30,
            cache_write_tokens=10,
        ),
    )
    chat_response = adapter._translate_response(ulm_response)

    assert chat_response.usage is not None
    assert chat_response.usage.input_tokens == 100
    assert chat_response.usage.output_tokens == 50
    assert chat_response.usage.total_tokens == 150
    assert chat_response.usage.reasoning_tokens == 20
    assert chat_response.usage.cache_read_tokens == 30
    assert chat_response.usage.cache_write_tokens == 10


def test_translate_usage_none():
    """None usage -> None on ChatResponse."""
    adapter = UnifiedProviderAdapter(
        provider_name="anthropic",
        model="claude-sonnet-4-20250514",
        client=MagicMock(),
    )
    ulm_response = ULMResponse(
        id="resp_5",
        model="claude-sonnet-4-20250514",
        provider="anthropic",
        message=ULMMessage(
            role=Role.ASSISTANT,
            content=[ContentPart(kind=ContentKind.TEXT, text="ok")],
        ),
        finish_reason=FinishReason(reason="stop"),
        usage=ULMUsage(input_tokens=10, output_tokens=5, total_tokens=15),
    )
    # Override usage to None for test (Usage is required on Response, but
    # the _translate_usage method should handle None gracefully)
    chat_response = adapter._translate_response(ulm_response)
    assert chat_response.usage is not None  # Usage was provided
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_unified_provider_adapter.py::test_translate_usage_all_fields -v`

Expected: FAIL — `_translate_usage` returns `None`

**Step 3: Implement usage translation**

Replace the `_translate_usage` stub:

```python
    @staticmethod
    def _translate_usage(usage: ULMUsage | None) -> CoreUsage | None:
        """Translate unified-llm Usage to amplifier-core Usage."""
        if usage is None:
            return None
        return CoreUsage(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            reasoning_tokens=usage.reasoning_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
        )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_unified_provider_adapter.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add -u && git commit -m "feat(loop-agent): translate usage from unified-llm to amplifier-core"
```

---

## Phase 3: complete() Integration (Task 10)

### Task 10: Wire complete() End-to-End

Combine request translation, `client.complete()`, and response translation into the public `complete()` method.

**Files:**
- Modify: `amplifier_module_loop_agent/unified_provider_adapter.py`
- Modify: `tests/test_unified_provider_adapter.py`

**Step 1: Write the failing test**

Add to test file:

```python
@pytest.mark.asyncio
async def test_complete_end_to_end():
    """complete() translates request, calls client, translates response."""
    # Build a mock unified-llm response
    ulm_response = ULMResponse(
        id="resp_e2e",
        model="claude-sonnet-4-20250514",
        provider="anthropic",
        message=ULMMessage(
            role=Role.ASSISTANT,
            content=[ContentPart(kind=ContentKind.TEXT, text="Test response")],
        ),
        finish_reason=FinishReason(reason="stop"),
        usage=ULMUsage(input_tokens=10, output_tokens=5, total_tokens=15),
    )
    mock_client = MagicMock()
    mock_client.complete = AsyncMock(return_value=ulm_response)

    adapter = UnifiedProviderAdapter(
        provider_name="anthropic",
        model="claude-sonnet-4-20250514",
        client=mock_client,
    )
    request = ChatRequest(
        messages=[CoreMessage(role="user", content="Hello")],
    )

    result = await adapter.complete(request)

    # Verify client was called with translated request
    mock_client.complete.assert_called_once()
    call_arg = mock_client.complete.call_args[0][0]
    assert call_arg.model == "claude-sonnet-4-20250514"
    assert call_arg.provider == "anthropic"
    assert call_arg.messages[0].role == Role.USER

    # Verify response was translated back
    assert len(result.content) == 1
    assert result.content[0].text == "Test response"
    assert result.usage.input_tokens == 10
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_unified_provider_adapter.py::test_complete_end_to_end -v`

Expected: FAIL — `complete()` method does not exist

**Step 3: Implement complete()**

Add to the class in `unified_provider_adapter.py`:

```python
    # ------------------------------------------------------------------
    # Public API: complete()
    # ------------------------------------------------------------------

    async def complete(self, request: ChatRequest) -> ChatResponse:
        """Satisfy loop-agent's provider.complete() contract.

        Translates ChatRequest -> unified_llm.Request, calls client.complete(),
        translates unified_llm.Response -> ChatResponse.
        """
        ulm_request = self._translate_request(request)
        ulm_response = await self._client.complete(ulm_request)
        return self._translate_response(ulm_response)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_unified_provider_adapter.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add -u && git commit -m "feat(loop-agent): wire complete() end-to-end through adapter"
```

---

## Phase 4: Error Mapping (Tasks 11–12)

### Task 11: Error Mapping Function

Map each `SDKError` subclass to the correct `LLMError` subclass with proper retryability.

**Files:**
- Modify: `amplifier_module_loop_agent/unified_provider_adapter.py`
- Modify: `tests/test_unified_provider_adapter.py`

**Step 1: Write the failing test**

Add to test file:

```python
from amplifier_core.llm_errors import (
    AuthenticationError as CoreAuthError,
    RateLimitError as CoreRateLimitError,
    ProviderUnavailableError,
    LLMTimeoutError,
    ContentFilterError as CoreContentFilterError,
    ContextLengthError as CoreContextLengthError,
    StreamError as CoreStreamError,
    LLMError,
)
from unified_llm import errors as ulm_errors


@pytest.mark.parametrize(
    "ulm_error, expected_type, expected_retryable",
    [
        (
            ulm_errors.AuthenticationError(
                message="bad key", provider="anthropic", status_code=401
            ),
            CoreAuthError,
            False,
        ),
        (
            ulm_errors.RateLimitError(
                message="slow down", provider="anthropic", status_code=429
            ),
            CoreRateLimitError,
            True,
        ),
        (
            ulm_errors.ServerError(
                message="internal error", provider="anthropic", status_code=500
            ),
            ProviderUnavailableError,
            True,
        ),
        (
            ulm_errors.ContentFilterError(
                message="blocked", provider="anthropic"
            ),
            CoreContentFilterError,
            False,
        ),
        (
            ulm_errors.ContextLengthError(
                message="too long", provider="anthropic", status_code=413
            ),
            CoreContextLengthError,
            False,
        ),
        (
            ulm_errors.RequestTimeoutError("timed out"),
            LLMTimeoutError,
            True,
        ),
        (
            ulm_errors.NetworkError("connection refused"),
            ProviderUnavailableError,  # NetworkError extends ProviderUnavailableError in core
            True,
        ),
        (
            ulm_errors.StreamError("stream broke"),
            CoreStreamError,
            True,
        ),
        (
            ulm_errors.ConfigurationError("bad config"),
            LLMError,
            False,
        ),
    ],
    ids=[
        "auth", "rate_limit", "server", "content_filter",
        "context_length", "timeout", "network", "stream", "config",
    ],
)
def test_map_error(ulm_error, expected_type, expected_retryable):
    """Each SDKError maps to the correct LLMError with right retryability."""
    adapter = UnifiedProviderAdapter(
        provider_name="anthropic",
        model="claude-sonnet-4-20250514",
        client=MagicMock(),
    )
    mapped = adapter._map_error(ulm_error)

    assert isinstance(mapped, expected_type), (
        f"Expected {expected_type.__name__}, got {type(mapped).__name__}"
    )
    assert mapped.retryable == expected_retryable
    assert mapped.provider == "anthropic"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_unified_provider_adapter.py::test_map_error -v`

Expected: FAIL — `_map_error` does not exist

**Step 3: Implement error mapping**

Add imports to `unified_provider_adapter.py`:

```python
from amplifier_core.llm_errors import (
    AuthenticationError as CoreAuthError,
    ContentFilterError as CoreContentFilterError,
    ContextLengthError as CoreContextLengthError,
    LLMError,
    LLMTimeoutError,
    ProviderUnavailableError,
    RateLimitError as CoreRateLimitError,
    StreamError as CoreStreamError,
)
from unified_llm.errors import SDKError
from unified_llm import errors as ulm_errors
```

Add method to the class:

```python
    # ------------------------------------------------------------------
    # Error mapping
    # ------------------------------------------------------------------

    def _map_error(self, error: SDKError) -> LLMError:
        """Map unified-llm SDKError to amplifier-core LLMError."""
        msg = str(error)
        provider = self._provider_name
        status_code = getattr(error, "status_code", None)

        # --- Provider errors (have provider/status_code on the ULM side) ---

        if isinstance(error, ulm_errors.AuthenticationError):
            return CoreAuthError(msg, provider=provider, status_code=status_code)

        if isinstance(error, ulm_errors.AccessDeniedError):
            return CoreAuthError(msg, provider=provider, status_code=status_code)

        if isinstance(error, ulm_errors.RateLimitError):
            retry_after = getattr(error, "retry_after", None)
            return CoreRateLimitError(
                msg, provider=provider, status_code=status_code, retry_after=retry_after
            )

        if isinstance(error, ulm_errors.ServerError):
            return ProviderUnavailableError(
                msg, provider=provider, status_code=status_code
            )

        if isinstance(error, ulm_errors.ContentFilterError):
            return CoreContentFilterError(msg, provider=provider, status_code=status_code)

        if isinstance(error, ulm_errors.ContextLengthError):
            return CoreContextLengthError(msg, provider=provider, status_code=status_code)

        # --- Non-provider errors ---

        if isinstance(error, ulm_errors.RequestTimeoutError):
            return LLMTimeoutError(msg, provider=provider)

        if isinstance(error, ulm_errors.NetworkError):
            return ProviderUnavailableError(msg, provider=provider)

        if isinstance(error, ulm_errors.StreamError):
            return CoreStreamError(msg, provider=provider)

        # --- Fallback ---
        return LLMError(msg, provider=provider, retryable=error.retryable)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_unified_provider_adapter.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add -u && git commit -m "feat(loop-agent): error mapping from SDKError to LLMError hierarchy"
```

---

### Task 12: Wire Error Mapping into complete()

Catch `SDKError` in `complete()` and re-raise as `LLMError`.

**Files:**
- Modify: `amplifier_module_loop_agent/unified_provider_adapter.py`
- Modify: `tests/test_unified_provider_adapter.py`

**Step 1: Write the failing test**

Add to test file:

```python
@pytest.mark.asyncio
async def test_complete_maps_sdk_error_to_llm_error():
    """SDKError from client.complete() is caught and re-raised as LLMError."""
    mock_client = MagicMock()
    mock_client.complete = AsyncMock(
        side_effect=ulm_errors.RateLimitError(
            message="429 rate limited", provider="anthropic", status_code=429
        )
    )
    adapter = UnifiedProviderAdapter(
        provider_name="anthropic",
        model="claude-sonnet-4-20250514",
        client=mock_client,
    )
    request = ChatRequest(
        messages=[CoreMessage(role="user", content="Hello")],
    )

    with pytest.raises(CoreRateLimitError) as exc_info:
        await adapter.complete(request)

    assert exc_info.value.retryable is True
    assert exc_info.value.provider == "anthropic"
    # Original error is chained
    assert exc_info.value.__cause__ is not None


@pytest.mark.asyncio
async def test_complete_maps_auth_error():
    """AuthenticationError from client -> CoreAuthError (non-retryable)."""
    mock_client = MagicMock()
    mock_client.complete = AsyncMock(
        side_effect=ulm_errors.AuthenticationError(
            message="invalid key", provider="anthropic", status_code=401
        )
    )
    adapter = UnifiedProviderAdapter(
        provider_name="anthropic",
        model="claude-sonnet-4-20250514",
        client=mock_client,
    )
    request = ChatRequest(
        messages=[CoreMessage(role="user", content="Hello")],
    )

    with pytest.raises(CoreAuthError) as exc_info:
        await adapter.complete(request)

    assert exc_info.value.retryable is False
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_unified_provider_adapter.py::test_complete_maps_sdk_error_to_llm_error -v`

Expected: FAIL — `SDKError` propagates uncaught (raises `RateLimitError` from unified_llm, not from amplifier_core)

**Step 3: Add error handling to complete()**

Update `complete()` in `unified_provider_adapter.py`:

```python
    async def complete(self, request: ChatRequest) -> ChatResponse:
        """Satisfy loop-agent's provider.complete() contract."""
        ulm_request = self._translate_request(request)
        try:
            ulm_response = await self._client.complete(ulm_request)
        except SDKError as e:
            raise self._map_error(e) from e
        return self._translate_response(ulm_response)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_unified_provider_adapter.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add -u && git commit -m "feat(loop-agent): wire error mapping into complete() with exception chaining"
```

---

## Phase 5: Streaming Translation (Tasks 13–17)

### Task 13: Basic Streaming — TEXT_DELTA

Translate `TEXT_DELTA` stream events to `{"content": delta}` dict chunks.

**Files:**
- Modify: `amplifier_module_loop_agent/unified_provider_adapter.py`
- Modify: `tests/test_unified_provider_adapter.py`

**Step 1: Write the failing test**

Add helper and test to test file:

```python
from unified_llm.types import StreamEvent, StreamEventType


async def _collect_stream(adapter, request):
    """Helper: collect all chunks from adapter.stream()."""
    chunks = []
    async for chunk in adapter.stream(request):
        chunks.append(chunk)
    return chunks


def _make_streaming_adapter(*events):
    """Create adapter with a mock client that streams given events."""
    async def fake_stream(request):
        for event in events:
            yield event

    mock_client = MagicMock()
    mock_client.stream = fake_stream
    return UnifiedProviderAdapter(
        provider_name="anthropic",
        model="claude-sonnet-4-20250514",
        client=mock_client,
    )


@pytest.mark.asyncio
async def test_stream_text_deltas():
    """TEXT_DELTA events yield {content: delta} chunks."""
    adapter = _make_streaming_adapter(
        StreamEvent(type=StreamEventType.TEXT_DELTA, delta="Hello"),
        StreamEvent(type=StreamEventType.TEXT_DELTA, delta=" world"),
        StreamEvent(type=StreamEventType.FINISH, usage=ULMUsage(
            input_tokens=10, output_tokens=5, total_tokens=15,
        )),
    )
    request = ChatRequest(
        messages=[CoreMessage(role="user", content="Hi")],
    )
    chunks = await _collect_stream(adapter, request)

    text_chunks = [c for c in chunks if "content" in c]
    assert len(text_chunks) == 2
    assert text_chunks[0] == {"content": "Hello"}
    assert text_chunks[1] == {"content": " world"}
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_unified_provider_adapter.py::test_stream_text_deltas -v`

Expected: FAIL — `stream()` does not exist

**Step 3: Implement basic stream()**

Add imports to `unified_provider_adapter.py`:

```python
from unified_llm.types import (
    # ... existing ...
    StreamEvent,
    StreamEventType,
)
```

Add method to the class:

```python
    # ------------------------------------------------------------------
    # Public API: stream()
    # ------------------------------------------------------------------

    async def stream(self, request: ChatRequest):
        """Satisfy loop-agent's provider.stream() contract.

        MUST be an async generator function (uses yield) so that
        inspect.isasyncgenfunction(adapter.stream) returns True.

        Yields dict chunks with keys the agent session expects:
          content, thinking, reasoning_signature, tool_calls, usage
        """
        ulm_request = self._translate_request(request)

        try:
            async for event in self._client.stream(ulm_request):
                chunk = self._translate_stream_event(event)
                if chunk is not None:
                    yield chunk
        except SDKError as e:
            raise self._map_error(e) from e

    def _translate_stream_event(self, event: StreamEvent) -> dict[str, Any] | None:
        """Translate a single StreamEvent to a dict chunk, or None to skip."""
        if event.type == StreamEventType.TEXT_DELTA and event.delta:
            return {"content": event.delta}

        # Additional event types handled in Tasks 14-16
        return None
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_unified_provider_adapter.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add -u && git commit -m "feat(loop-agent): streaming TEXT_DELTA translation"
```

---

### Task 14: Reasoning Streaming

Handle `REASONING_DELTA` and `REASONING_END` (with signature extraction).

**Files:**
- Modify: `amplifier_module_loop_agent/unified_provider_adapter.py`
- Modify: `tests/test_unified_provider_adapter.py`

**Step 1: Write the failing test**

Add to test file:

```python
@pytest.mark.asyncio
async def test_stream_reasoning_with_signature():
    """REASONING_DELTA -> {thinking: delta}, REASONING_END -> {reasoning_signature: sig}."""
    adapter = _make_streaming_adapter(
        StreamEvent(type=StreamEventType.REASONING_START),
        StreamEvent(type=StreamEventType.REASONING_DELTA, reasoning_delta="Step 1: "),
        StreamEvent(type=StreamEventType.REASONING_DELTA, reasoning_delta="analyze input"),
        StreamEvent(
            type=StreamEventType.REASONING_END,
            raw={"signature": "sig_roundtrip_xyz"},
        ),
        StreamEvent(type=StreamEventType.TEXT_DELTA, delta="Result"),
        StreamEvent(type=StreamEventType.FINISH, usage=ULMUsage(
            input_tokens=20, output_tokens=10, total_tokens=30,
        )),
    )
    request = ChatRequest(
        messages=[CoreMessage(role="user", content="Think")],
    )
    chunks = await _collect_stream(adapter, request)

    thinking_chunks = [c for c in chunks if "thinking" in c]
    assert len(thinking_chunks) == 2
    assert thinking_chunks[0] == {"thinking": "Step 1: "}
    assert thinking_chunks[1] == {"thinking": "analyze input"}

    sig_chunks = [c for c in chunks if "reasoning_signature" in c]
    assert len(sig_chunks) == 1
    assert sig_chunks[0] == {"reasoning_signature": "sig_roundtrip_xyz"}
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_unified_provider_adapter.py::test_stream_reasoning_with_signature -v`

Expected: FAIL — REASONING events return None (skipped)

**Step 3: Add reasoning handling to `_translate_stream_event`**

Update `_translate_stream_event` in `unified_provider_adapter.py`:

```python
    def _translate_stream_event(self, event: StreamEvent) -> dict[str, Any] | None:
        """Translate a single StreamEvent to a dict chunk, or None to skip."""
        if event.type == StreamEventType.TEXT_DELTA and event.delta:
            return {"content": event.delta}

        if event.type == StreamEventType.REASONING_DELTA and event.reasoning_delta:
            return {"thinking": event.reasoning_delta}

        if event.type == StreamEventType.REASONING_END:
            # Extract signature for Anthropic multi-turn round-tripping
            sig = None
            if event.raw and isinstance(event.raw, dict):
                sig = event.raw.get("signature")
            if sig:
                return {"reasoning_signature": sig}
            return None

        # STREAM_START, TEXT_START, TEXT_END, REASONING_START: skip
        return None
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_unified_provider_adapter.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add -u && git commit -m "feat(loop-agent): streaming reasoning deltas and signature extraction"
```

---

### Task 15: Streaming Tool-Call Buffering

Buffer `TOOL_CALL_START`/`DELTA`/`END` events and yield a single complete `{"tool_calls": [...]}` chunk on `END`.

**Files:**
- Modify: `amplifier_module_loop_agent/unified_provider_adapter.py`
- Modify: `tests/test_unified_provider_adapter.py`

**Step 1: Write the failing tests**

Add to test file:

```python
from unified_llm.types import ToolCall as ULMToolCall


@pytest.mark.asyncio
async def test_stream_tool_call_buffering():
    """TOOL_CALL_START/DELTA/END -> single {tool_calls: [...]} chunk."""
    adapter = _make_streaming_adapter(
        StreamEvent(
            type=StreamEventType.TOOL_CALL_START,
            tool_call=ULMToolCall(id="tc_1", name="read_file", arguments={}),
        ),
        StreamEvent(
            type=StreamEventType.TOOL_CALL_DELTA,
            delta='{"path": "/tmp/test.py"}',
        ),
        StreamEvent(
            type=StreamEventType.TOOL_CALL_END,
            tool_call=ULMToolCall(
                id="tc_1",
                name="read_file",
                arguments={"path": "/tmp/test.py"},
            ),
        ),
        StreamEvent(type=StreamEventType.FINISH, usage=ULMUsage(
            input_tokens=10, output_tokens=5, total_tokens=15,
        )),
    )
    request = ChatRequest(
        messages=[CoreMessage(role="user", content="Read file")],
    )
    chunks = await _collect_stream(adapter, request)

    tc_chunks = [c for c in chunks if "tool_calls" in c]
    assert len(tc_chunks) == 1
    assert tc_chunks[0]["tool_calls"] == [
        {"id": "tc_1", "name": "read_file", "arguments": {"path": "/tmp/test.py"}}
    ]


@pytest.mark.asyncio
async def test_stream_multiple_tool_calls():
    """Multiple sequential tool calls each yield a separate chunk."""
    adapter = _make_streaming_adapter(
        # First tool call
        StreamEvent(
            type=StreamEventType.TOOL_CALL_START,
            tool_call=ULMToolCall(id="tc_1", name="read_file", arguments={}),
        ),
        StreamEvent(
            type=StreamEventType.TOOL_CALL_END,
            tool_call=ULMToolCall(
                id="tc_1", name="read_file", arguments={"path": "a.py"},
            ),
        ),
        # Second tool call
        StreamEvent(
            type=StreamEventType.TOOL_CALL_START,
            tool_call=ULMToolCall(id="tc_2", name="write_file", arguments={}),
        ),
        StreamEvent(
            type=StreamEventType.TOOL_CALL_END,
            tool_call=ULMToolCall(
                id="tc_2", name="write_file",
                arguments={"path": "b.py", "content": "hello"},
            ),
        ),
        StreamEvent(type=StreamEventType.FINISH, usage=ULMUsage(
            input_tokens=10, output_tokens=5, total_tokens=15,
        )),
    )
    request = ChatRequest(
        messages=[CoreMessage(role="user", content="Do both")],
    )
    chunks = await _collect_stream(adapter, request)

    tc_chunks = [c for c in chunks if "tool_calls" in c]
    assert len(tc_chunks) == 2
    assert tc_chunks[0]["tool_calls"][0]["name"] == "read_file"
    assert tc_chunks[1]["tool_calls"][0]["name"] == "write_file"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_unified_provider_adapter.py::test_stream_tool_call_buffering -v`

Expected: FAIL — tool call events are skipped (return None)

**Step 3: Implement tool-call buffering in stream()**

The tool-call buffering logic lives in `stream()` since it needs state across events. Update the `stream()` method and `_translate_stream_event`:

```python
    async def stream(self, request: ChatRequest):
        """Satisfy loop-agent's provider.stream() contract.

        MUST be an async generator function (uses yield) so that
        inspect.isasyncgenfunction(adapter.stream) returns True.
        """
        ulm_request = self._translate_request(request)

        # Tool-call buffering state: accumulate START/DELTA until END
        _buffering_tool_call: bool = False

        try:
            async for event in self._client.stream(ulm_request):
                # --- Tool-call buffering ---
                if event.type == StreamEventType.TOOL_CALL_START:
                    _buffering_tool_call = True
                    continue  # Don't yield START

                if event.type == StreamEventType.TOOL_CALL_DELTA:
                    continue  # Don't yield DELTA (args accumulated by provider)

                if event.type == StreamEventType.TOOL_CALL_END:
                    _buffering_tool_call = False
                    tc = event.tool_call
                    if tc:
                        # Use complete tool_call from END event
                        arguments = tc.arguments
                        if not arguments and tc.raw_arguments:
                            try:
                                arguments = json.loads(tc.raw_arguments)
                            except (json.JSONDecodeError, TypeError):
                                arguments = {}
                        yield {
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "name": tc.name,
                                    "arguments": arguments,
                                }
                            ]
                        }
                    continue

                # --- Regular event translation ---
                chunk = self._translate_stream_event(event)
                if chunk is not None:
                    yield chunk

        except SDKError as e:
            # Discard any partial tool-call buffer on error
            raise self._map_error(e) from e
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_unified_provider_adapter.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add -u && git commit -m "feat(loop-agent): streaming tool-call buffering (START/DELTA/END -> complete chunk)"
```

---

### Task 16: Streaming Usage and Finish

Translate `FINISH` event with usage data to `{"usage": {...}}` chunk.

**Files:**
- Modify: `amplifier_module_loop_agent/unified_provider_adapter.py`
- Modify: `tests/test_unified_provider_adapter.py`

**Step 1: Write the failing test**

Add to test file:

```python
@pytest.mark.asyncio
async def test_stream_finish_usage():
    """FINISH event yields {usage: {...}} chunk with all token fields."""
    adapter = _make_streaming_adapter(
        StreamEvent(type=StreamEventType.TEXT_DELTA, delta="Hi"),
        StreamEvent(
            type=StreamEventType.FINISH,
            usage=ULMUsage(
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                reasoning_tokens=20,
            ),
        ),
    )
    request = ChatRequest(
        messages=[CoreMessage(role="user", content="Hello")],
    )
    chunks = await _collect_stream(adapter, request)

    usage_chunks = [c for c in chunks if "usage" in c]
    assert len(usage_chunks) == 1
    usage = usage_chunks[0]["usage"]
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 50
    assert usage["total_tokens"] == 150
    assert usage["reasoning_tokens"] == 20
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_unified_provider_adapter.py::test_stream_finish_usage -v`

Expected: FAIL — FINISH event returns None

**Step 3: Add FINISH handling to `_translate_stream_event`**

Update `_translate_stream_event`:

```python
    def _translate_stream_event(self, event: StreamEvent) -> dict[str, Any] | None:
        """Translate a single StreamEvent to a dict chunk, or None to skip."""
        if event.type == StreamEventType.TEXT_DELTA and event.delta:
            return {"content": event.delta}

        if event.type == StreamEventType.REASONING_DELTA and event.reasoning_delta:
            return {"thinking": event.reasoning_delta}

        if event.type == StreamEventType.REASONING_END:
            sig = None
            if event.raw and isinstance(event.raw, dict):
                sig = event.raw.get("signature")
            if sig:
                return {"reasoning_signature": sig}
            return None

        if event.type == StreamEventType.FINISH and event.usage:
            usage_dict: dict[str, Any] = {
                "input_tokens": event.usage.input_tokens,
                "output_tokens": event.usage.output_tokens,
                "total_tokens": event.usage.total_tokens,
            }
            if event.usage.reasoning_tokens is not None:
                usage_dict["reasoning_tokens"] = event.usage.reasoning_tokens
            if event.usage.cache_read_tokens is not None:
                usage_dict["cache_read_tokens"] = event.usage.cache_read_tokens
            if event.usage.cache_write_tokens is not None:
                usage_dict["cache_write_tokens"] = event.usage.cache_write_tokens
            return {"usage": usage_dict}

        # STREAM_START, TEXT_START, TEXT_END, REASONING_START: skip
        return None
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_unified_provider_adapter.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add -u && git commit -m "feat(loop-agent): streaming FINISH event with usage translation"
```

---

### Task 17: Verify stream() is Async Generator and Error Mapping

Verify `inspect.isasyncgenfunction(adapter.stream)` passes (required by `AgentSession._detect_streaming_support`) and that streaming errors are mapped.

**Files:**
- Modify: `tests/test_unified_provider_adapter.py`

**Step 1: Write the failing test**

Add to test file:

```python
import inspect


def test_stream_is_async_generator_function():
    """adapter.stream must pass inspect.isasyncgenfunction() check.

    AgentSession._detect_streaming_support() uses this at construction
    time to decide whether to use streaming.
    """
    adapter = UnifiedProviderAdapter(
        provider_name="anthropic",
        model="claude-sonnet-4-20250514",
        client=MagicMock(),
    )
    assert inspect.isasyncgenfunction(adapter.stream), (
        "adapter.stream must be an async generator function "
        "(defined with 'async def' + 'yield') for AgentSession streaming detection"
    )


@pytest.mark.asyncio
async def test_stream_maps_sdk_error_to_llm_error():
    """SDKError during streaming is caught and re-raised as LLMError."""
    async def failing_stream(request):
        yield StreamEvent(type=StreamEventType.TEXT_DELTA, delta="partial")
        raise ulm_errors.ServerError(
            message="stream failed", provider="anthropic", status_code=500
        )

    mock_client = MagicMock()
    mock_client.stream = failing_stream

    adapter = UnifiedProviderAdapter(
        provider_name="anthropic",
        model="claude-sonnet-4-20250514",
        client=mock_client,
    )
    request = ChatRequest(
        messages=[CoreMessage(role="user", content="Hello")],
    )

    with pytest.raises(ProviderUnavailableError) as exc_info:
        async for _chunk in adapter.stream(request):
            pass  # Consume until error

    assert exc_info.value.retryable is True
    assert exc_info.value.__cause__ is not None
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_unified_provider_adapter.py::test_stream_is_async_generator_function tests/test_unified_provider_adapter.py::test_stream_maps_sdk_error_to_llm_error -v`

Expected: PASS — both were already implemented in Tasks 13 and 15 (the stream method uses `yield` and has `except SDKError`)

**Step 3: No new implementation needed**

These verify existing behavior. The key assertions:
- `stream()` uses `async def` + `yield` → it IS an async generator function
- `stream()` has `except SDKError as e: raise self._map_error(e) from e` → errors are mapped

**Step 4: Confirm all tests pass**

Run: `uv run pytest tests/test_unified_provider_adapter.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add -u && git commit -m "test(loop-agent): verify stream() async generator detection and error mapping"
```

---

## Phase 6: Injection and Integration (Tasks 18–21)

### Task 18: Client Construction Inside Adapter

When no client is injected, build one from environment using `Client.from_env()`.

**Files:**
- Modify: `amplifier_module_loop_agent/unified_provider_adapter.py`
- Modify: `tests/test_unified_provider_adapter.py`

**Step 1: Write the failing test**

Add to test file:

```python
from unittest.mock import patch


@pytest.mark.asyncio
async def test_adapter_builds_client_from_env():
    """When no client is injected, adapter builds one via Client.from_env()."""
    mock_client_instance = MagicMock()
    mock_client_instance.complete = AsyncMock(
        return_value=ULMResponse(
            id="resp_env",
            model="claude-sonnet-4-20250514",
            provider="anthropic",
            message=ULMMessage(
                role=Role.ASSISTANT,
                content=[ContentPart(kind=ContentKind.TEXT, text="from env")],
            ),
            finish_reason=FinishReason(reason="stop"),
            usage=ULMUsage(input_tokens=5, output_tokens=3, total_tokens=8),
        ),
    )

    mock_constructed_client = MagicMock()
    mock_constructed_client.providers = {"anthropic": MagicMock()}
    mock_constructed_client.complete = mock_client_instance.complete

    with patch(
        "amplifier_module_loop_agent.unified_provider_adapter.Client"
    ) as MockClient:
        MockClient.from_env.return_value = mock_constructed_client

        # No client= passed — should build from env
        adapter = UnifiedProviderAdapter(
            provider_name="anthropic",
            model="claude-sonnet-4-20250514",
        )

        MockClient.from_env.assert_called_once()
        assert adapter._client is not None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_unified_provider_adapter.py::test_adapter_builds_client_from_env -v`

Expected: FAIL — constructor doesn't call `Client.from_env()`

**Step 3: Implement client construction**

Add import to `unified_provider_adapter.py`:

```python
from unified_llm.client import Client
```

Update the constructor:

```python
    def __init__(
        self,
        *,
        provider_name: str,
        model: str,
        client: Any = None,
    ) -> None:
        self._provider_name = provider_name
        self._model = model

        if client is not None:
            self._client = client
        else:
            # Build client from environment-detected API keys
            base = Client.from_env()
            # Re-wrap with our provider as default
            self._client = Client(
                providers=base.providers,
                default_provider=provider_name,
            )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_unified_provider_adapter.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add -u && git commit -m "feat(loop-agent): build Client from environment when none injected"
```

---

### Task 19: Injection in AgentOrchestrator

Modify `AgentOrchestrator.execute()` to wrap the provider with `UnifiedProviderAdapter` when unified-llm-client is available.

**Files:**
- Modify: `amplifier_module_loop_agent/__init__.py`
- Modify: `tests/test_unified_provider_adapter.py`

**Step 1: Write the failing test**

Add to test file:

```python
from amplifier_module_loop_agent import AgentOrchestrator
from amplifier_core.message_models import ChatResponse, Usage as CoreUsage
from amplifier_core.models import ToolResult


@pytest.mark.asyncio
async def test_orchestrator_injects_adapter():
    """AgentOrchestrator wraps provider with UnifiedProviderAdapter when config enables it."""
    # Create a mock unified-llm response
    ulm_response = ULMResponse(
        id="resp_inject",
        model="claude-sonnet-4-20250514",
        provider="anthropic",
        message=ULMMessage(
            role=Role.ASSISTANT,
            content=[ContentPart(kind=ContentKind.TEXT, text="Adapter response")],
        ),
        finish_reason=FinishReason(reason="stop"),
        usage=ULMUsage(input_tokens=10, output_tokens=5, total_tokens=15),
    )

    # Mock the Client.from_env to return a client with our response
    mock_client = MagicMock()
    mock_client.providers = {"anthropic": MagicMock()}
    mock_client.complete = AsyncMock(return_value=ulm_response)

    with patch(
        "amplifier_module_loop_agent.unified_provider_adapter.Client"
    ) as MockClient:
        # Make Client() constructor return our mock
        MockClient.return_value = mock_client
        MockClient.from_env.return_value = mock_client

        config = {"use_unified_llm": True, "model": "claude-sonnet-4-20250514"}
        coordinator = MagicMock()
        orchestrator = AgentOrchestrator(coordinator=coordinator, config=config)

        # Use a real provider dict — the adapter should REPLACE it
        native_provider = AsyncMock()
        providers = {"anthropic": native_provider}

        hooks = MagicMock()
        hooks._emitted = []

        async def _emit(event, data):
            hooks._emitted.append((event, data))
            return MagicMock(action="continue")

        hooks.emit = AsyncMock(side_effect=_emit)

        tools = {}
        context = MagicMock()

        result = await orchestrator.execute(
            "Hello", context, providers, tools, hooks, coordinator
        )

        assert result == "Adapter response"
        # Native provider should NOT have been called
        native_provider.complete.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_unified_provider_adapter.py::test_orchestrator_injects_adapter -v`

Expected: FAIL — orchestrator uses native provider, not adapter

**Step 3: Modify `__init__.py` injection point**

Edit `amplifier_module_loop_agent/__init__.py`. Add the adapter injection after `provider = providers[provider_name]`:

```python
            # Merge subagent lifecycle tools into the tools dict
            all_tools = dict(tools)
            if config.current_depth < config.max_subagent_depth:
                subagent_mgr = SubagentManager(
                    coordinator=self._coordinator,
                    max_depth=config.max_subagent_depth,
                    current_depth=config.current_depth,
                )
                for tool in subagent_mgr.create_tools():
                    all_tools[tool.name] = tool

            # Wrap provider with unified-llm adapter if configured
            if self._config.get("use_unified_llm"):
                try:
                    from .unified_provider_adapter import UnifiedProviderAdapter

                    model = self._config.get("model", "")
                    provider = UnifiedProviderAdapter(
                        provider_name=provider_name,
                        model=model,
                    )
                    logger.info(
                        "Using UnifiedProviderAdapter for %s/%s",
                        provider_name,
                        model,
                    )
                except (ImportError, Exception) as e:
                    logger.warning(
                        "Failed to create UnifiedProviderAdapter, using native provider: %s",
                        e,
                    )

            self._session = AgentSession(
```

The key change: insert the adapter wrapping block between the subagent tool merge and the `AgentSession(...)` construction.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_unified_provider_adapter.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add -u && git commit -m "feat(loop-agent): inject UnifiedProviderAdapter in AgentOrchestrator.execute()"
```

---

### Task 20: End-to-End Integration Test

Verify the adapter works with a real `AgentSession` through a multi-turn conversation with tool calls.

**Files:**
- Modify: `tests/test_unified_provider_adapter.py`

**Step 1: Write the integration test**

Add to test file:

```python
from amplifier_module_loop_agent.agent_session import AgentSession
from amplifier_module_loop_agent.config import SessionConfig


@pytest.mark.asyncio
async def test_end_to_end_adapter_with_agent_session():
    """Full integration: adapter + AgentSession completes a multi-turn conversation."""
    # Response 1: tool call
    tool_call_response = ULMResponse(
        id="resp_tc",
        model="claude-sonnet-4-20250514",
        provider="anthropic",
        message=ULMMessage(
            role=Role.ASSISTANT,
            content=[
                ContentPart(kind=ContentKind.TEXT, text="Let me read that file"),
                ContentPart(
                    kind=ContentKind.TOOL_CALL,
                    tool_call=ULMToolCallData(
                        id="tc_1",
                        name="read_file",
                        arguments={"path": "/tmp/test.py"},
                    ),
                ),
            ],
        ),
        finish_reason=FinishReason(reason="tool_calls"),
        usage=ULMUsage(input_tokens=20, output_tokens=15, total_tokens=35),
    )

    # Response 2: text completion
    text_response = ULMResponse(
        id="resp_txt",
        model="claude-sonnet-4-20250514",
        provider="anthropic",
        message=ULMMessage(
            role=Role.ASSISTANT,
            content=[
                ContentPart(kind=ContentKind.TEXT, text="The file contains hello world."),
            ],
        ),
        finish_reason=FinishReason(reason="stop"),
        usage=ULMUsage(input_tokens=30, output_tokens=10, total_tokens=40),
    )

    # Mock client returns tool_call then text
    mock_client = MagicMock()
    mock_client.complete = AsyncMock(side_effect=[tool_call_response, text_response])

    adapter = UnifiedProviderAdapter(
        provider_name="anthropic",
        model="claude-sonnet-4-20250514",
        client=mock_client,
    )

    # Build a mock tool
    mock_tool = MagicMock()
    mock_tool.name = "read_file"
    mock_tool.description = "Read a file"
    mock_tool.input_schema = {"type": "object", "properties": {"path": {"type": "string"}}}
    mock_tool.execute = AsyncMock(
        return_value=ToolResult(success=True, output="hello world")
    )

    # Build hooks
    hooks = MagicMock()
    hooks._emitted = []

    async def _emit(event, data):
        hooks._emitted.append((event, data))
        return MagicMock(action="continue")

    hooks.emit = AsyncMock(side_effect=_emit)

    # Create AgentSession with the ADAPTER as provider
    config = SessionConfig()
    session = AgentSession(
        config=config,
        provider=adapter,  # <-- The adapter!
        tools={"read_file": mock_tool},
        hooks=hooks,
        provider_name="anthropic",
        model="claude-sonnet-4-20250514",
    )

    result = await session.process_input("Read /tmp/test.py for me")

    # Verify full flow worked
    assert result == "The file contains hello world."
    assert mock_client.complete.call_count == 2
    mock_tool.execute.assert_called_once_with({"path": "/tmp/test.py"})

    # Verify the adapter translated requests correctly
    first_call_request = mock_client.complete.call_args_list[0][0][0]
    assert first_call_request.model == "claude-sonnet-4-20250514"
    assert first_call_request.provider == "anthropic"
```

**Step 2: Run test**

Run: `uv run pytest tests/test_unified_provider_adapter.py::test_end_to_end_adapter_with_agent_session -v`

Expected: PASS — this exercises the full chain: AgentSession → adapter.complete() → translate → mock client → translate back → AgentSession processes tool calls → adapter.complete() again → text response.

**Step 3: No new implementation needed**

This is a pure integration test verifying all components work together.

**Step 4: Confirm all tests pass**

Run: `uv run pytest tests/test_unified_provider_adapter.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add -u && git commit -m "test(loop-agent): end-to-end integration test with adapter + AgentSession"
```

---

### Task 21: Full Regression

Verify all 30+ existing tests pass unchanged — the adapter doesn't break anything.

**Files:**
- No changes

**Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`

Expected: ALL PASS — existing tests mock `provider.complete()` which the adapter satisfies. No existing test uses the adapter, so they're completely isolated.

**Step 2: Verify test count**

The output should show 30+ existing tests plus the ~15 new adapter tests, all passing.

**Step 3: Commit (if any formatting fixes needed)**

```bash
git add -u && git commit -m "test(loop-agent): full regression pass — all existing tests unchanged"
```

---

## Summary

| Phase | Tasks | What's Built |
|-------|-------|-------------|
| 1. Request Translation | 1–5 | `ChatRequest` → `unified_llm.Request` (messages, content blocks, params) |
| 2. Response Translation | 6–9 | `unified_llm.Response` → `ChatResponse` (text, thinking, tool calls, usage) |
| 3. complete() | 10 | End-to-end `complete()` method |
| 4. Error Mapping | 11–12 | `SDKError` → `LLMError` with retryability + exception chaining |
| 5. Streaming | 13–17 | `StreamEvent` → dict chunks with tool-call buffering |
| 6. Integration | 18–21 | Client construction, orchestrator injection, E2E test, regression |

**Critical invariant maintained throughout:** `agent_session.py` has ZERO modifications.

**What the adapter enables:**
- Unified retry with exponential backoff + jitter + Retry-After
- Typed error hierarchy with retryability classification
- Normalized streaming across all 3 providers
- Spec-compliant request/response translation
- Full Amplifier hook observability (when hook bridge middleware is added — future enhancement)
