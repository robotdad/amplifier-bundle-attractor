# Track 1-1A4: Implement AWAITING_INPUT State Detection

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** When the model responds with text only (no tool calls) and the text looks like a question, transition to `AWAITING_INPUT` instead of `IDLE` and emit an event so the host application can distinguish "agent is asking a question" from "agent completed the task."

**Architecture:** Add a question-detection heuristic in the natural-completion branch of `process_input()`. When text ends with `?` (after stripping whitespace and markdown), transition to `AWAITING_INPUT` and emit a new `AGENT_AWAITING_INPUT` event. The host decides whether to answer (which calls `process_input()` again after `resume_input()`) or close the session. Add a new public `resume_with_input()` method that handles the `AWAITING_INPUT -> PROCESSING` transition.

**Tech Stack:** Python, state machine transitions, regex for question detection

**Spec Reference:** coding-agent-loop-spec Section 2.3 (SessionState), Section 2.5 (state transitions: `PROCESSING -> AWAITING_INPUT`)

**Adversarial Review Reference:** C-7

---

## Problem Statement

`SessionState.AWAITING_INPUT` exists in the enum and the transition table (`state.py:44`), but no code path ever triggers the `await_input()` transition. When the model responds with text only (no tool calls), the session always goes to `IDLE` via `complete()` at `agent_session.py:335`. The host application cannot distinguish between "the agent finished its task" and "the agent is asking for clarification."

## Root Cause

**File:** `modules/loop-agent/amplifier_module_loop_agent/agent_session.py`
**Lines:** 333-338 (natural completion branch)

```python
# Current code: always goes IDLE, never AWAITING_INPUT
if not tool_calls:
    self._state_machine.complete()  # PROCESSING -> IDLE always
    await self._emit_session_end()
    return await self._process_follow_ups(text)
```

**File:** `modules/loop-agent/amplifier_module_loop_agent/state.py`
**Lines:** 42-46 (transition exists but is never triggered)

```python
SessionState.PROCESSING: {
    "complete": SessionState.IDLE,
    "await_input": SessionState.AWAITING_INPUT,  # <-- dead code
    "fatal_error": SessionState.CLOSED,
    "abort": SessionState.CLOSED,
},
```

**File:** `modules/loop-agent/amplifier_module_loop_agent/events.py`

No `AGENT_AWAITING_INPUT` event constant exists.

## The Fix

### Part 1: Add AGENT_AWAITING_INPUT event constant

**File:** `modules/loop-agent/amplifier_module_loop_agent/events.py`

Add after `AGENT_SESSION_END`:

```python
AGENT_AWAITING_INPUT = "agent:awaiting_input"
```

Add to `__all__` list.

### Part 2: Add question detection heuristic

A simple, pragmatic heuristic: strip trailing whitespace, backticks, and markdown formatting. If the remaining text ends with `?`, it's a question. This avoids false positives from question marks in code blocks or middle-of-text questions.

```python
@staticmethod
def _looks_like_question(text: str) -> bool:
    """Detect if model text looks like a question directed at the user.

    Heuristic: strip trailing whitespace, markdown formatting, and
    code fences. If the cleaned text ends with '?', treat it as a
    question. This intentionally errs on the side of caution --
    only text that clearly ends as a question triggers AWAITING_INPUT.
    """
    if not text or not text.strip():
        return False

    # Strip trailing whitespace and common markdown artifacts
    cleaned = text.rstrip()

    # Remove trailing code fences that might follow a question
    # e.g., "What do you think?\n```"
    lines = cleaned.split("\n")

    # Walk backwards past empty lines and code fences
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("```"):
            continue
        # Found the last meaningful line
        return stripped.endswith("?")

    return False
```

### Part 3: Wire into natural completion branch

**Before** (`agent_session.py:333-338`):
```python
if not tool_calls:
    self._state_machine.complete()  # PROCESSING -> IDLE
    await self._emit_session_end()
    return await self._process_follow_ups(text)
```

**After**:
```python
if not tool_calls:
    # Detect if the model is asking the user a question
    if self._looks_like_question(text):
        self._state_machine.await_input()  # PROCESSING -> AWAITING_INPUT
        await self._hooks.emit(
            AGENT_AWAITING_INPUT,
            {"text": text, "session_id": self._session_id},
        )
        # Do NOT emit session_end or process follow-ups.
        # The host decides: answer via resume_with_input() or close.
        return text
    else:
        self._state_machine.complete()  # PROCESSING -> IDLE
        await self._emit_session_end()
        return await self._process_follow_ups(text)
```

### Part 4: Add `resume_with_input()` public method

```python
async def resume_with_input(self, answer: str) -> str:
    """Resume from AWAITING_INPUT state with the user's answer.

    Transitions AWAITING_INPUT -> PROCESSING and calls process_input()
    with the user's answer as the new prompt.

    Args:
        answer: The user's response to the agent's question.

    Returns:
        The agent's response after processing the answer.

    Raises:
        InvalidTransitionError: If not in AWAITING_INPUT state.
    """
    self._state_machine.resume_input()  # AWAITING_INPUT -> PROCESSING
    # Transition back to IDLE first so process_input can submit() again
    self._state_machine.complete()  # PROCESSING -> IDLE
    return await self.process_input(answer)
```

---

## Tasks

### Task 1: Write failing tests for AWAITING_INPUT detection

**Files:**
- Create: `modules/loop-agent/tests/test_awaiting_input.py`

**Step 1: Write the failing tests**

```python
"""Tests for AWAITING_INPUT state detection (C-7).

Verifies that:
1. Question-like text -> AWAITING_INPUT state
2. Non-question text -> IDLE state (existing behavior)
3. The heuristic correctly identifies questions
4. resume_with_input() continues the session
5. AGENT_AWAITING_INPUT event is emitted
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

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


def _make_mock_tool(name: str) -> MagicMock:
    tool = MagicMock()
    tool.name = name
    tool.description = f"Mock {name}"
    tool.input_schema = {"type": "object", "properties": {}}
    tool.execute = AsyncMock(return_value=ToolResult(success=True, output="ok"))
    return tool


def _make_hooks():
    hooks = MagicMock()
    hooks._emitted = []

    async def _emit(event, data):
        hooks._emitted.append((event, data))
        return MagicMock(action="continue")

    hooks.emit = AsyncMock(side_effect=_emit)
    return hooks


# --- Heuristic unit tests ---


class TestLooksLikeQuestion:
    """Unit tests for the question detection heuristic."""

    def test_ends_with_question_mark(self):
        assert AgentSession._looks_like_question("What file should I edit?") is True

    def test_plain_statement(self):
        assert AgentSession._looks_like_question("I've completed the task.") is False

    def test_empty_string(self):
        assert AgentSession._looks_like_question("") is False

    def test_whitespace_only(self):
        assert AgentSession._looks_like_question("   \n  ") is False

    def test_question_with_trailing_whitespace(self):
        assert AgentSession._looks_like_question("What do you think?  \n") is True

    def test_question_before_code_fence(self):
        text = "Should I use this approach?\n```python\nx = 1\n```"
        assert AgentSession._looks_like_question(text) is False

    def test_question_after_code_fence(self):
        text = "```python\nx = 1\n```\nDoes this look correct?"
        assert AgentSession._looks_like_question(text) is True

    def test_question_mark_in_middle_not_at_end(self):
        assert AgentSession._looks_like_question(
            "What? I already did that."
        ) is False

    def test_multiline_question_at_end(self):
        text = "I found two options:\n1. Option A\n2. Option B\nWhich do you prefer?"
        assert AgentSession._looks_like_question(text) is True


# --- Integration tests ---


@pytest.mark.asyncio
async def test_question_response_enters_awaiting_input():
    """Model asking a question -> AWAITING_INPUT state."""
    provider = AsyncMock()
    provider.complete = AsyncMock(
        return_value=_text_response("Which file should I edit?")
    )
    hooks = _make_hooks()

    session = AgentSession(
        config=SessionConfig(),
        provider=provider,
        tools={"read_file": _make_mock_tool("read_file")},
        hooks=hooks,
    )
    result = await session.process_input("fix the bug")

    assert result == "Which file should I edit?"
    assert session._state_machine.state == SessionState.AWAITING_INPUT


@pytest.mark.asyncio
async def test_statement_response_enters_idle():
    """Model making a statement -> IDLE state (existing behavior)."""
    provider = AsyncMock()
    provider.complete = AsyncMock(
        return_value=_text_response("I've fixed the bug.")
    )
    hooks = _make_hooks()

    session = AgentSession(
        config=SessionConfig(),
        provider=provider,
        tools={"read_file": _make_mock_tool("read_file")},
        hooks=hooks,
    )
    result = await session.process_input("fix the bug")

    assert result == "I've fixed the bug."
    assert session._state_machine.state == SessionState.IDLE


@pytest.mark.asyncio
async def test_awaiting_input_event_emitted():
    """AGENT_AWAITING_INPUT event is emitted for questions."""
    provider = AsyncMock()
    provider.complete = AsyncMock(
        return_value=_text_response("What framework are you using?")
    )
    hooks = _make_hooks()

    session = AgentSession(
        config=SessionConfig(),
        provider=provider,
        tools={"read_file": _make_mock_tool("read_file")},
        hooks=hooks,
    )
    await session.process_input("add tests")

    event_names = [e for e, _ in hooks._emitted]
    assert "agent:awaiting_input" in event_names

    # session_end should NOT be emitted
    assert "agent:session_end" not in event_names


@pytest.mark.asyncio
async def test_session_end_not_emitted_for_question():
    """SESSION_END is not emitted when entering AWAITING_INPUT."""
    provider = AsyncMock()
    provider.complete = AsyncMock(
        return_value=_text_response("Do you want me to proceed?")
    )
    hooks = _make_hooks()

    session = AgentSession(
        config=SessionConfig(),
        provider=provider,
        tools={},
        hooks=hooks,
    )
    await session.process_input("start")

    event_names = [e for e, _ in hooks._emitted]
    assert "agent:session_end" not in event_names


@pytest.mark.asyncio
async def test_resume_with_input_continues_session():
    """resume_with_input() transitions back and processes the answer."""
    call_count = 0

    async def side_effect(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _text_response("What file?")
        else:
            return _text_response("Done editing src/main.py")

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=side_effect)
    hooks = _make_hooks()

    session = AgentSession(
        config=SessionConfig(),
        provider=provider,
        tools={"read_file": _make_mock_tool("read_file")},
        hooks=hooks,
    )

    # First input -> question
    result1 = await session.process_input("edit the main file")
    assert session._state_machine.state == SessionState.AWAITING_INPUT
    assert result1 == "What file?"

    # Resume with answer
    result2 = await session.resume_with_input("src/main.py")
    assert result2 == "Done editing src/main.py"
    assert session._state_machine.state == SessionState.IDLE
```

**Step 2: Run tests to verify they fail**

Run: `cd modules/loop-agent && python -m pytest tests/test_awaiting_input.py -v`
Expected: FAIL -- `AgentSession` has no `_looks_like_question` method, no `AGENT_AWAITING_INPUT` event.

### Task 2: Add AGENT_AWAITING_INPUT event constant

**Files:**
- Modify: `modules/loop-agent/amplifier_module_loop_agent/events.py`

**Step 1: Add the event constant**

Add after `AGENT_SESSION_END = "agent:session_end"` (line 18):

```python
AGENT_AWAITING_INPUT = "agent:awaiting_input"
```

**Step 2: Add to `__all__` list**

Add `"AGENT_AWAITING_INPUT"` to the `__all__` list.

**Step 3: Add import in agent_session.py**

In `agent_session.py`, add `AGENT_AWAITING_INPUT` to the events import block (line 36-53).

**Step 4: Verify import**

Run: `cd modules/loop-agent && python -c "from amplifier_module_loop_agent.events import AGENT_AWAITING_INPUT; print(AGENT_AWAITING_INPUT)"`
Expected: `agent:awaiting_input`

**Step 5: Commit**

```
git add modules/loop-agent/amplifier_module_loop_agent/events.py
git add modules/loop-agent/amplifier_module_loop_agent/agent_session.py
git commit -m "feat(loop-agent): add AGENT_AWAITING_INPUT event constant"
```

### Task 3: Add `_looks_like_question` heuristic and `resume_with_input`

**Files:**
- Modify: `modules/loop-agent/amplifier_module_loop_agent/agent_session.py`

**Step 1: Add `_looks_like_question` static method**

Place it in a new section after the "Content extraction" section (after line 571), before "Graceful shutdown":

```python
# ------------------------------------------------------------------
# Question detection (spec Section 2.3: AWAITING_INPUT)
# ------------------------------------------------------------------

@staticmethod
def _looks_like_question(text: str) -> bool:
    """Detect if model text looks like a question directed at the user.

    Heuristic: strip trailing whitespace, markdown formatting, and
    code fences. If the cleaned text ends with '?', treat it as a
    question. This intentionally errs on the side of caution --
    only text that clearly ends as a question triggers AWAITING_INPUT.
    """
    if not text or not text.strip():
        return False

    cleaned = text.rstrip()
    lines = cleaned.split("\n")

    # Walk backwards past empty lines and code fences
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("```"):
            continue
        return stripped.endswith("?")

    return False
```

**Step 2: Add `resume_with_input` public method**

Place it after `process_input()` in the "Public API" section:

```python
async def resume_with_input(self, answer: str) -> str:
    """Resume from AWAITING_INPUT state with the user's answer.

    Transitions AWAITING_INPUT -> PROCESSING -> IDLE and then calls
    process_input() with the user's answer as the new prompt.

    Args:
        answer: The user's response to the agent's question.

    Returns:
        The agent's response after processing the answer.

    Raises:
        InvalidTransitionError: If not in AWAITING_INPUT state.
    """
    self._state_machine.resume_input()  # AWAITING_INPUT -> PROCESSING
    self._state_machine.complete()       # PROCESSING -> IDLE
    return await self.process_input(answer)
```

**Step 3: Run heuristic unit tests**

Run: `cd modules/loop-agent && python -m pytest tests/test_awaiting_input.py::TestLooksLikeQuestion -v`
Expected: All 9 heuristic tests PASS.

**Step 4: Commit**

```
git add modules/loop-agent/amplifier_module_loop_agent/agent_session.py
git commit -m "feat(loop-agent): add question detection heuristic and resume_with_input"
```

### Task 4: Wire question detection into natural completion branch

**Files:**
- Modify: `modules/loop-agent/amplifier_module_loop_agent/agent_session.py:333-338`

**Step 1: Replace the natural completion branch**

Replace lines 333-338:

```python
# Natural completion: no tool calls -> done
if not tool_calls:
    self._state_machine.complete()  # PROCESSING -> IDLE
    await self._emit_session_end()
    # Process follow-up queue after loop completes
    return await self._process_follow_ups(text)
```

With:

```python
# Natural completion: no tool calls
if not tool_calls:
    # Detect if the model is asking the user a question
    if self._looks_like_question(text):
        self._state_machine.await_input()  # PROCESSING -> AWAITING_INPUT
        await self._hooks.emit(
            AGENT_AWAITING_INPUT,
            {"text": text, "session_id": self._session_id},
        )
        # Do NOT emit session_end or process follow-ups.
        # Host decides: answer via resume_with_input() or close.
        return text
    else:
        self._state_machine.complete()  # PROCESSING -> IDLE
        await self._emit_session_end()
        return await self._process_follow_ups(text)
```

**Step 2: Run all awaiting-input tests**

Run: `cd modules/loop-agent && python -m pytest tests/test_awaiting_input.py -v`
Expected: All tests PASS.

**Step 3: Run existing tests for regression**

Run: `cd modules/loop-agent && python -m pytest tests/test_agent_session.py -v`
Expected: All existing tests PASS. (Existing test responses like "Hello!", "Read complete", "done" etc. do not end with `?` so they all take the IDLE path.)

**Step 4: Commit**

```
git add modules/loop-agent/amplifier_module_loop_agent/agent_session.py
git commit -m "feat(loop-agent): detect questions and transition to AWAITING_INPUT (C-7)

When the model responds with text only (no tool calls) and the text
ends with a question mark, transition to AWAITING_INPUT instead of
IDLE. Emit agent:awaiting_input event so the host can distinguish
'agent completed' from 'agent is asking a question'.

Host can answer via resume_with_input() or close the session.

Heuristic: strips trailing whitespace, code fences, and checks if the
last meaningful line ends with '?'. Intentionally conservative to avoid
false positives.

Spec: Section 2.3 (PROCESSING -> AWAITING_INPUT)
Fixes: C-7 from adversarial review"
```

---

## Backward Compatibility

- **Behavioral change for question-like responses.** Text ending with `?` now results in `AWAITING_INPUT` instead of `IDLE`. Host applications that only check for `IDLE` will see a different state.
- **Mitigation:** The `AGENT_AWAITING_INPUT` event gives hosts an explicit signal. Hosts that don't handle it can simply call `session.shutdown()` or `resume_with_input("")` to continue.
- **Existing test responses** ("Hello!", "done", "Read complete", etc.) do not end with `?` and are unaffected.
- **SESSION_END is not emitted** in the `AWAITING_INPUT` path. This is correct per spec -- the session hasn't ended, it's waiting for input.

## Dependencies on Upstream Fixes

- **None.** The `SessionState.AWAITING_INPUT` enum value and `await_input()` / `resume_input()` transitions already exist in `state.py`. This fix only activates the dead code.

## PR Details

**Branch:** `track1/1a4-awaiting-input`
**Title:** `feat(loop-agent): implement AWAITING_INPUT question detection (C-7)`
**Labels:** `track1`, `agent-loop`, `spec-compliance`, `critical`
**Reviewers:** @bkrabach
