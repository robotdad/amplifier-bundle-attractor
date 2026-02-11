# Track 1-1A5: Fix Streaming to Capture Reasoning Content

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Fix `_call_provider_streaming()` to capture `ThinkingBlock` content from stream chunks alongside text, and pass the assembled reasoning to `AssistantTurn` so it is preserved in conversation history and emitted in events.

**Architecture:** The streaming path currently hardcodes `"reasoning": None` in its return dict. We need to accumulate reasoning chunks (keyed by `"thinking"` or `"reasoning"` in stream chunks) the same way we accumulate `"content"` text chunks. The non-streaming path already works correctly via `_extract_reasoning()`.

**Tech Stack:** Python, asyncio async generators, amplifier-core `ChatResponse` / `ThinkingBlock`

**Spec Reference:** coding-agent-loop-spec Section 2.4 (`AssistantTurn.reasoning`), Section 2.5 step 4 (record assistant turn with reasoning)

**Adversarial Review Reference:** C-8

---

## Problem Statement

The streaming path (`_call_provider_streaming`) assembles text from chunks but does not capture `ThinkingBlock` content. The `_extract_reasoning()` helper is only called in the non-streaming path (`_call_provider_complete`). For thinking-enabled models (Claude with extended thinking, OpenAI o-series), reasoning content is silently lost during streaming.

This means:
1. `AssistantTurn.reasoning` is always `None` for streaming responses
2. The `AGENT_ASSISTANT_TEXT_END` event never includes reasoning data from streaming
3. Multi-turn Anthropic conversations lose the `reasoning_signature` needed for thinking block preservation

## Root Cause

**File:** `modules/loop-agent/amplifier_module_loop_agent/agent_session.py`
**Lines:** 162-212 (`_call_provider_streaming` method)

```python
async def _call_provider_streaming(self, request: ChatRequest) -> dict[str, Any]:
    await self._hooks.emit(AGENT_ASSISTANT_TEXT_START, {})

    full_text = ""
    tool_calls: list[dict[str, Any]] = []
    usage_data: dict[str, Any] = {}

    async for chunk in self._provider.stream(request):
        content = chunk.get("content")        # <-- only captures text
        if content:
            full_text += content
            await self._hooks.emit(AGENT_ASSISTANT_TEXT_DELTA, {"delta": content})
        chunk_tool_calls = chunk.get("tool_calls")
        if chunk_tool_calls:
            tool_calls.extend(chunk_tool_calls)
        chunk_usage = chunk.get("usage")
        if chunk_usage:
            usage_data = chunk_usage

    await self._hooks.emit(AGENT_ASSISTANT_TEXT_END, {"text": full_text})

    # ... build raw_tool_calls ...

    return {
        "text": full_text,
        "reasoning": None,              # <-- ALWAYS None
        "reasoning_signature": None,    # <-- ALWAYS None
        "tool_calls": tool_calls,
        "raw_tool_calls": raw_tool_calls,
        "usage": None,
        "usage_data": usage_data,
    }
```

The chunk processing loop only looks for `chunk.get("content")`. It never checks for `chunk.get("thinking")`, `chunk.get("reasoning")`, or `chunk.get("reasoning_signature")`.

## The Fix

### Before (`agent_session.py:162-212`)

```python
async def _call_provider_streaming(self, request: ChatRequest) -> dict[str, Any]:
    await self._hooks.emit(AGENT_ASSISTANT_TEXT_START, {})

    full_text = ""
    tool_calls: list[dict[str, Any]] = []
    usage_data: dict[str, Any] = {}

    async for chunk in self._provider.stream(request):
        content = chunk.get("content")
        if content:
            full_text += content
            await self._hooks.emit(AGENT_ASSISTANT_TEXT_DELTA, {"delta": content})
        chunk_tool_calls = chunk.get("tool_calls")
        if chunk_tool_calls:
            tool_calls.extend(chunk_tool_calls)
        chunk_usage = chunk.get("usage")
        if chunk_usage:
            usage_data = chunk_usage

    await self._hooks.emit(AGENT_ASSISTANT_TEXT_END, {"text": full_text})

    raw_tool_calls: list[Any] = []
    if tool_calls:
        from types import SimpleNamespace
        raw_tool_calls = [
            SimpleNamespace(id=tc["id"], name=tc["name"], arguments=tc["arguments"])
            for tc in tool_calls
        ]

    return {
        "text": full_text,
        "reasoning": None,
        "reasoning_signature": None,
        "tool_calls": tool_calls,
        "raw_tool_calls": raw_tool_calls,
        "usage": None,
        "usage_data": usage_data,
    }
```

### After

```python
async def _call_provider_streaming(self, request: ChatRequest) -> dict[str, Any]:
    """Streaming path: consume provider.stream(), emitting delta events.

    Emits ASSISTANT_TEXT_START before any deltas, ASSISTANT_TEXT_DELTA
    for each content chunk, and ASSISTANT_TEXT_END with the full text
    and reasoning when the stream completes.

    Captures both text content and reasoning/thinking content from
    stream chunks to preserve reasoning for thinking-enabled models
    (Claude extended thinking, OpenAI o-series).
    """
    await self._hooks.emit(AGENT_ASSISTANT_TEXT_START, {})

    full_text = ""
    full_reasoning = ""
    reasoning_signature: str | None = None
    tool_calls: list[dict[str, Any]] = []
    usage_data: dict[str, Any] = {}

    async for chunk in self._provider.stream(request):
        # Accumulate text content
        content = chunk.get("content")
        if content:
            full_text += content
            await self._hooks.emit(AGENT_ASSISTANT_TEXT_DELTA, {"delta": content})

        # Accumulate reasoning/thinking content
        thinking = chunk.get("thinking") or chunk.get("reasoning")
        if thinking:
            full_reasoning += thinking

        # Capture reasoning signature (for multi-turn Anthropic thinking)
        chunk_sig = chunk.get("reasoning_signature") or chunk.get("signature")
        if chunk_sig:
            reasoning_signature = chunk_sig

        # Accumulate tool calls
        chunk_tool_calls = chunk.get("tool_calls")
        if chunk_tool_calls:
            tool_calls.extend(chunk_tool_calls)

        # Capture usage data
        chunk_usage = chunk.get("usage")
        if chunk_usage:
            usage_data = chunk_usage

    # Emit text end with full assembled text and reasoning
    text_end_data: dict[str, Any] = {"text": full_text}
    if full_reasoning:
        text_end_data["reasoning"] = full_reasoning
    await self._hooks.emit(AGENT_ASSISTANT_TEXT_END, text_end_data)

    # Build ToolCall-like objects for the execution path
    raw_tool_calls: list[Any] = []
    if tool_calls:
        from types import SimpleNamespace

        raw_tool_calls = [
            SimpleNamespace(
                id=tc["id"],
                name=tc["name"],
                arguments=tc["arguments"],
            )
            for tc in tool_calls
        ]

    return {
        "text": full_text,
        "reasoning": full_reasoning if full_reasoning else None,
        "reasoning_signature": reasoning_signature,
        "tool_calls": tool_calls,
        "raw_tool_calls": raw_tool_calls,
        "usage": None,
        "usage_data": usage_data,
    }
```

### Key Changes

1. **Added `full_reasoning` accumulator** (line-level: new variable initialized to `""`)
2. **Added `reasoning_signature` capture** (new variable initialized to `None`)
3. **Check `chunk.get("thinking")` and `chunk.get("reasoning")`** in the stream loop
4. **Check `chunk.get("reasoning_signature")` and `chunk.get("signature")`** for multi-turn
5. **Include reasoning in `AGENT_ASSISTANT_TEXT_END` event data**
6. **Return actual reasoning values** instead of hardcoded `None`

---

## Tasks

### Task 1: Write failing tests for streaming reasoning capture

**Files:**
- Create: `modules/loop-agent/tests/test_streaming_reasoning.py`

**Step 1: Write the failing tests**

```python
"""Tests for streaming reasoning capture (C-8).

Verifies that _call_provider_streaming() captures:
1. ThinkingBlock content from stream chunks
2. Reasoning signature for multi-turn Anthropic conversations
3. Both text and reasoning when present together
4. Reasoning is included in AGENT_ASSISTANT_TEXT_END event
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from amplifier_core.message_models import ChatResponse, Usage

from amplifier_module_loop_agent.agent_session import AgentSession
from amplifier_module_loop_agent.config import SessionConfig


def _make_hooks():
    hooks = MagicMock()
    hooks._emitted = []

    async def _emit(event, data):
        hooks._emitted.append((event, data))
        return MagicMock(action="continue")

    hooks.emit = AsyncMock(side_effect=_emit)
    return hooks


def _make_streaming_provider(chunks: list[dict]):
    """Create a mock provider with a stream() async generator.

    Each dict in chunks is yielded from stream(). Keys:
      content, thinking, reasoning, reasoning_signature, signature,
      tool_calls, usage
    """
    provider = AsyncMock()

    async def _stream(request):
        for chunk in chunks:
            yield chunk

    provider.stream = _stream
    # Mark as async generator so _detect_streaming_support works
    provider.complete = AsyncMock()
    return provider


def _make_session(provider, hooks=None):
    """Create an AgentSession configured for streaming."""
    hooks = hooks or _make_hooks()
    tools = {}
    session = AgentSession(
        config=SessionConfig(),
        provider=provider,
        tools=tools,
        hooks=hooks,
    )
    # Force streaming on (override detection since our mock uses a real async gen)
    session._use_streaming = True
    return session, hooks


@pytest.mark.asyncio
async def test_reasoning_captured_from_thinking_chunks():
    """Stream chunks with 'thinking' key are captured as reasoning."""
    provider = _make_streaming_provider([
        {"thinking": "Let me analyze this..."},
        {"thinking": " The bug is in line 42."},
        {"content": "I found the issue."},
    ])
    session, hooks = _make_session(provider)

    # Call the streaming method directly
    from amplifier_core.message_models import ChatRequest, Message

    request = ChatRequest(messages=[Message(role="user", content="find the bug")])
    result = await session._call_provider_streaming(request)

    assert result["reasoning"] == "Let me analyze this... The bug is in line 42."
    assert result["text"] == "I found the issue."


@pytest.mark.asyncio
async def test_reasoning_captured_from_reasoning_chunks():
    """Stream chunks with 'reasoning' key are also captured."""
    provider = _make_streaming_provider([
        {"reasoning": "Step 1: read the file."},
        {"reasoning": " Step 2: find the error."},
        {"content": "Here's my analysis."},
    ])
    session, hooks = _make_session(provider)

    from amplifier_core.message_models import ChatRequest, Message

    request = ChatRequest(messages=[Message(role="user", content="analyze")])
    result = await session._call_provider_streaming(request)

    assert result["reasoning"] == "Step 1: read the file. Step 2: find the error."


@pytest.mark.asyncio
async def test_reasoning_signature_captured():
    """Reasoning signature is captured for multi-turn thinking."""
    provider = _make_streaming_provider([
        {"thinking": "Deep analysis..."},
        {"reasoning_signature": "sig_abc123"},
        {"content": "Done."},
    ])
    session, hooks = _make_session(provider)

    from amplifier_core.message_models import ChatRequest, Message

    request = ChatRequest(messages=[Message(role="user", content="think")])
    result = await session._call_provider_streaming(request)

    assert result["reasoning"] == "Deep analysis..."
    assert result["reasoning_signature"] == "sig_abc123"


@pytest.mark.asyncio
async def test_signature_key_also_captured():
    """The 'signature' key variant is also captured."""
    provider = _make_streaming_provider([
        {"thinking": "Thinking..."},
        {"signature": "sig_xyz789"},
        {"content": "Result."},
    ])
    session, hooks = _make_session(provider)

    from amplifier_core.message_models import ChatRequest, Message

    request = ChatRequest(messages=[Message(role="user", content="think")])
    result = await session._call_provider_streaming(request)

    assert result["reasoning_signature"] == "sig_xyz789"


@pytest.mark.asyncio
async def test_reasoning_in_text_end_event():
    """AGENT_ASSISTANT_TEXT_END event includes reasoning when present."""
    provider = _make_streaming_provider([
        {"thinking": "My reasoning here."},
        {"content": "The answer."},
    ])
    session, hooks = _make_session(provider)

    from amplifier_core.message_models import ChatRequest, Message

    request = ChatRequest(messages=[Message(role="user", content="q")])
    await session._call_provider_streaming(request)

    # Find the text_end event
    text_end_events = [
        (e, d) for e, d in hooks._emitted if e == "agent:assistant_text_end"
    ]
    assert len(text_end_events) == 1
    event_data = text_end_events[0][1]
    assert event_data["text"] == "The answer."
    assert event_data["reasoning"] == "My reasoning here."


@pytest.mark.asyncio
async def test_no_reasoning_returns_none():
    """When no thinking chunks, reasoning is None (not empty string)."""
    provider = _make_streaming_provider([
        {"content": "Simple response."},
    ])
    session, hooks = _make_session(provider)

    from amplifier_core.message_models import ChatRequest, Message

    request = ChatRequest(messages=[Message(role="user", content="hi")])
    result = await session._call_provider_streaming(request)

    assert result["reasoning"] is None
    assert result["reasoning_signature"] is None


@pytest.mark.asyncio
async def test_reasoning_persisted_in_assistant_turn():
    """Reasoning from streaming is stored in AssistantTurn in history."""
    provider = _make_streaming_provider([
        {"thinking": "Deep thought."},
        {"reasoning_signature": "sig_001"},
        {"content": "Answer."},
    ])

    # Use text-only second response to exit the loop
    text_response = ChatResponse(
        content=[{"type": "text", "text": ""}],
        tool_calls=None,
        usage=Usage(input_tokens=5, output_tokens=5, total_tokens=10),
    )

    session, hooks = _make_session(provider)
    # Override: first call streams, but we test _call_provider_streaming directly
    from amplifier_core.message_models import ChatRequest, Message

    request = ChatRequest(messages=[Message(role="user", content="think hard")])
    result = await session._call_provider_streaming(request)

    # Verify the result dict has reasoning
    assert result["reasoning"] == "Deep thought."
    assert result["reasoning_signature"] == "sig_001"

    # When this result feeds into process_input's AssistantTurn creation
    # (lines 314-322), reasoning and reasoning_signature will be set.
    # We verify the dict keys are correct for that code path.
    from amplifier_module_loop_agent.turns import AssistantTurn

    turn = AssistantTurn(
        content=result["text"],
        reasoning=result["reasoning"],
        reasoning_signature=result["reasoning_signature"],
    )
    assert turn.reasoning == "Deep thought."
    assert turn.reasoning_signature == "sig_001"
```

**Step 2: Run tests to verify they fail**

Run: `cd modules/loop-agent && python -m pytest tests/test_streaming_reasoning.py -v`
Expected: FAIL -- `result["reasoning"]` is `None` because current code hardcodes it.

### Task 2: Fix `_call_provider_streaming` to capture reasoning

**Files:**
- Modify: `modules/loop-agent/amplifier_module_loop_agent/agent_session.py:162-212`

**Step 1: Replace the method**

Replace the entire `_call_provider_streaming` method (lines 162-212) with the "After" code shown above.

**Step 2: Run all streaming reasoning tests**

Run: `cd modules/loop-agent && python -m pytest tests/test_streaming_reasoning.py -v`
Expected: All 8 tests PASS.

**Step 3: Run existing tests for regression**

Run: `cd modules/loop-agent && python -m pytest tests/test_agent_session.py -v`
Expected: All existing tests PASS. (Existing tests don't use streaming -- they mock `provider.complete`, and `_detect_streaming_support()` returns `False` for standard `AsyncMock` objects because `inspect.isasyncgenfunction` is `False`.)

**Step 4: Commit**

```
git add modules/loop-agent/amplifier_module_loop_agent/agent_session.py
git commit -m "fix(loop-agent): capture reasoning content in streaming path (C-8)

_call_provider_streaming() now accumulates thinking/reasoning chunks
from the stream alongside text content. Also captures
reasoning_signature for multi-turn Anthropic thinking preservation.

Previously, reasoning was hardcoded to None in the streaming return
dict, silently discarding all thinking content for Claude extended
thinking and OpenAI o-series models.

Checks both 'thinking' and 'reasoning' chunk keys (provider-agnostic).
Checks both 'reasoning_signature' and 'signature' chunk keys.

Spec: Section 2.4 (AssistantTurn.reasoning)
Fixes: C-8 from adversarial review"
```

---

## Backward Compatibility

- **No breaking changes.** The streaming return dict now has real values for `reasoning` and `reasoning_signature` instead of `None`. All downstream code already handles `None` vs string values for these fields (see `agent_session.py:288-289`, `turns.py:38-39`).
- Providers that don't emit `thinking` or `reasoning` chunks will continue to produce `None` values (the accumulator stays empty and is returned as `None`).
- The `AGENT_ASSISTANT_TEXT_END` event now conditionally includes `reasoning` data. Existing event consumers that don't check for this key are unaffected.

## Dependencies on Upstream Fixes

- **Provider stream format.** The fix assumes providers emit thinking content via `chunk.get("thinking")` or `chunk.get("reasoning")`. This matches the amplifier-core provider contract. If a provider uses a different key, that provider's stream adapter needs to normalize the key.
- **No blocking dependencies.** This is a pure loop-agent fix.

## PR Details

**Branch:** `track1/1a5-streaming-reasoning`
**Title:** `fix(loop-agent): capture reasoning/thinking content in streaming path (C-8)`
**Labels:** `track1`, `agent-loop`, `spec-compliance`, `critical`
**Reviewers:** @bkrabach
