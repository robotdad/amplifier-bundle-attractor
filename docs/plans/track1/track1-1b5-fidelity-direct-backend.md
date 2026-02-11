# Track 1-1B5: Wire Fidelity Into DirectProviderBackend (H-9)

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Make the `DirectProviderBackend` (the working E2E code path) fidelity-aware so that context carryover between nodes respects the `fidelity` attribute.
**Architecture:** `DirectProviderBackend` in `__init__.py` currently starts a fresh `messages` list for every node call with zero awareness of fidelity. The fix adds: (1) tracking of completed node outcomes and message history per thread key, (2) fidelity resolution via the existing `fidelity.py` module, (3) for `full` mode: reuse the accumulated message history from previous calls sharing the same thread key, (4) for all other modes: build a preamble from completed node history and prepend it to the prompt.
**Tech Stack:** Python, pytest

**Finding:** H-9 from adversarial-spec-review.md
**Spec Reference:** Section 5.4 -- Context Fidelity, FID-001-010

---

## Root Cause

**File:** `modules/loop-pipeline/amplifier_module_loop_pipeline/__init__.py` lines 31-148 (`DirectProviderBackend`)

Current `run()` method always creates a fresh message list:

```python
    async def run(self, node, prompt, context, **kwargs):
        # ...
        messages: list[Message] = [Message(role="user", content=prompt)]  # <-- always fresh
```

**Problem:** The `AmplifierBackend` in `backend.py` lines 80-175 IS fidelity-aware -- it calls `resolve_fidelity()`, `resolve_thread_key()`, `build_preamble()`, and maintains a `_session_pool` and `_completed_nodes` dict. But `AmplifierBackend` requires `session.spawn` which has zero E2E coverage (C-3). The `DirectProviderBackend` is the working path, and it completely ignores fidelity.

**What needs to happen:**
1. `DirectProviderBackend` needs to accept `incoming_edge` and `graph` parameters (like `AmplifierBackend.run()`)
2. It needs to call `resolve_fidelity()` and `resolve_thread_key()`
3. For `full` mode: maintain message history per thread key and reuse it
4. For other modes: call `build_preamble()` and prepend to prompt
5. Track completed node outcomes for preamble generation
6. The `PipelineEngine` or `CodergenHandler` needs to pass `incoming_edge` and `graph` through to the backend

---

## The Fix

### Task 1: Write failing tests for fidelity-aware DirectProviderBackend

**Files:**
- Create: `modules/loop-pipeline/tests/test_direct_backend_fidelity.py`

**Step 1: Write the failing tests**

```python
"""Tests for fidelity-aware DirectProviderBackend (H-9).

Validates that DirectProviderBackend respects fidelity modes:
- full: reuses message history between calls with same thread key
- compact/truncate/summary: prepends a preamble to the prompt
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from amplifier_module_loop_pipeline import DirectProviderBackend
from amplifier_module_loop_pipeline.context import PipelineContext
from amplifier_module_loop_pipeline.graph import Edge, Graph, Node
from amplifier_module_loop_pipeline.outcome import StageStatus


def _make_mock_provider(response_text="Done"):
    """Create a mock provider that returns a text-only response."""
    provider = AsyncMock()
    response = MagicMock()
    text_block = MagicMock()
    text_block.text = response_text
    response.content = [text_block]
    response.tool_calls = None
    provider.complete = AsyncMock(return_value=response)
    return provider


def _make_graph_with_fidelity(node_fidelity="compact"):
    """Build a minimal graph with a node that has a fidelity attribute."""
    return Graph(
        name="test",
        nodes={
            "start": Node(id="start", shape="Mdiamond"),
            "step1": Node(
                id="step1",
                shape="box",
                prompt="First step",
                attrs={"fidelity": node_fidelity},
            ),
            "step2": Node(
                id="step2",
                shape="box",
                prompt="Second step",
                attrs={"fidelity": node_fidelity},
            ),
            "done": Node(id="done", shape="Msquare"),
        },
        edges=[
            Edge(from_node="start", to_node="step1"),
            Edge(from_node="step1", to_node="step2"),
            Edge(from_node="step2", to_node="done"),
        ],
    )


@pytest.mark.asyncio
async def test_direct_backend_compact_fidelity_prepends_preamble():
    """With compact fidelity, the prompt should include a preamble after first node."""
    provider = _make_mock_provider("Step completed successfully")
    backend = DirectProviderBackend(provider)
    graph = _make_graph_with_fidelity("compact")
    context = PipelineContext()
    context.set("graph.goal", "test goal")

    edge_to_step1 = graph.edges[0]  # start -> step1

    # First call -- step1
    outcome1 = await backend.run(
        graph.nodes["step1"],
        "First step prompt",
        context,
        incoming_edge=edge_to_step1,
        graph=graph,
    )
    assert outcome1.status == StageStatus.SUCCESS

    edge_to_step2 = graph.edges[1]  # step1 -> step2

    # Second call -- step2 should have preamble with step1's outcome
    outcome2 = await backend.run(
        graph.nodes["step2"],
        "Second step prompt",
        context,
        incoming_edge=edge_to_step2,
        graph=graph,
    )
    assert outcome2.status == StageStatus.SUCCESS

    # Check that the second call's messages included preamble content
    second_call_args = provider.complete.call_args_list[1]
    request = second_call_args[0][0]
    user_message = request.messages[0].content
    # The preamble should mention the goal and completed stages
    assert "test goal" in user_message or "step1" in user_message


@pytest.mark.asyncio
async def test_direct_backend_truncate_fidelity_minimal_preamble():
    """With truncate fidelity, preamble should be minimal (just goal + run ID)."""
    provider = _make_mock_provider("Done")
    backend = DirectProviderBackend(provider)
    graph = _make_graph_with_fidelity("truncate")
    context = PipelineContext()
    context.set("graph.goal", "my goal")

    # First node call to populate history
    await backend.run(
        graph.nodes["step1"], "Step 1", context,
        incoming_edge=graph.edges[0], graph=graph,
    )

    # Second node call should have truncate preamble
    await backend.run(
        graph.nodes["step2"], "Step 2", context,
        incoming_edge=graph.edges[1], graph=graph,
    )

    second_request = provider.complete.call_args_list[1][0][0]
    user_content = second_request.messages[0].content
    assert "my goal" in user_content


@pytest.mark.asyncio
async def test_direct_backend_full_fidelity_reuses_messages():
    """With full fidelity, message history should accumulate across calls."""
    provider = _make_mock_provider("Response text")
    backend = DirectProviderBackend(provider)
    graph = _make_graph_with_fidelity("full")
    context = PipelineContext()

    # First call
    await backend.run(
        graph.nodes["step1"], "First prompt", context,
        incoming_edge=graph.edges[0], graph=graph,
    )

    # Second call should include the first call's messages
    await backend.run(
        graph.nodes["step2"], "Second prompt", context,
        incoming_edge=graph.edges[1], graph=graph,
    )

    second_request = provider.complete.call_args_list[1][0][0]
    # In full mode, messages from step1 should carry over
    # At minimum: user(first prompt), assistant(response), user(second prompt)
    assert len(second_request.messages) >= 3


@pytest.mark.asyncio
async def test_direct_backend_without_graph_falls_back_gracefully():
    """When graph/edge not provided, backend works like before (no fidelity)."""
    provider = _make_mock_provider("ok")
    backend = DirectProviderBackend(provider)
    context = PipelineContext()

    node = Node(id="work", shape="box", prompt="do work")
    outcome = await backend.run(node, "do work", context)
    assert outcome.status == StageStatus.SUCCESS
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/test_direct_backend_fidelity.py -xvs`

Expected: FAIL -- `run()` doesn't accept `incoming_edge` or `graph` kwargs (TypeError)

**Step 3: Commit failing tests**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor
git add modules/loop-pipeline/tests/test_direct_backend_fidelity.py
git commit -m "test: add fidelity-aware DirectProviderBackend tests (H-9)"
```

---

### Task 2: Add fidelity state tracking to DirectProviderBackend

**Files:**
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/__init__.py` lines 31-50

**Step 1: Update `__init__` to add fidelity state**

Find the `DirectProviderBackend.__init__` method (lines 40-50):

```python
    def __init__(
        self,
        provider: Any,
        tools: dict[str, Any] | None = None,
        hooks: Any = None,
        coordinator: Any = None,
    ) -> None:
        self._provider = provider
        self._tools = tools or {}
        self._hooks = hooks
        self._coordinator = coordinator
```

Replace with:

```python
    def __init__(
        self,
        provider: Any,
        tools: dict[str, Any] | None = None,
        hooks: Any = None,
        coordinator: Any = None,
    ) -> None:
        self._provider = provider
        self._tools = tools or {}
        self._hooks = hooks
        self._coordinator = coordinator
        # Fidelity state (H-9): track completed nodes and message history
        self._completed_nodes: dict[str, Any] = {}
        self._message_pools: dict[str, list] = {}  # thread_key -> message history
        self._last_node_id: str | None = None
```

**Step 2: Commit**

```bash
git add modules/loop-pipeline/amplifier_module_loop_pipeline/__init__.py
git commit -m "refactor: add fidelity state tracking to DirectProviderBackend (H-9)"
```

---

### Task 3: Update `run()` to accept and use fidelity parameters

**Files:**
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/__init__.py` lines 52-148

**Step 1: Update the `run()` method signature and add fidelity logic**

Find the `run()` method (lines 52-148) and replace entirely:

```python
    async def run(
        self,
        node: Any,
        prompt: str,
        context: PipelineContext,
        *,
        incoming_edge: Any | None = None,
        graph: Any | None = None,
        **kwargs: Any,
    ) -> Outcome:
        """Run a mini agentic tool loop for *node*.

        Supports fidelity-aware context carryover (spec Section 5.4):
        - full: reuse message history from previous calls with same thread key
        - compact/truncate/summary: prepend preamble from completed node history
        """
        from amplifier_core import ChatRequest, Message

        from .backend import (
            _build_tool_specs,
            _extract_text,
            _extract_tool_calls,
            _build_assistant_message,
            _parse_outcome,
            _MAX_TOOL_LOOP_ROUNDS,
        )

        # Resolve fidelity mode (spec FID-001-010)
        fidelity = "compact"  # default
        thread_key = node.id
        if graph is not None:
            from .fidelity import (
                build_preamble,
                resolve_fidelity,
                resolve_thread_key,
            )

            fidelity = resolve_fidelity(node, incoming_edge, graph)
            thread_key = resolve_thread_key(
                node, incoming_edge, graph, self._last_node_id
            )

        # Build messages based on fidelity mode
        if fidelity == "full":
            # Reuse accumulated message history for this thread key
            messages = list(self._message_pools.get(thread_key, []))
            messages.append(Message(role="user", content=prompt))
        else:
            # Fresh session with preamble
            if graph is not None and self._completed_nodes:
                from .fidelity import build_preamble

                preamble = build_preamble(fidelity, context, self._completed_nodes)
                effective_prompt = (
                    f"{preamble}\n\n---\n\n{prompt}" if preamble else prompt
                )
            else:
                effective_prompt = prompt
            messages = [Message(role="user", content=effective_prompt)]

        reasoning_effort = node.attrs.get("reasoning_effort")
        tool_specs = _build_tool_specs(self._tools)

        for _round in range(_MAX_TOOL_LOOP_ROUNDS):
            request = ChatRequest(
                messages=messages,
                tools=tool_specs or None,
                tool_choice="auto" if tool_specs else None,
                reasoning_effort=reasoning_effort,
            )

            try:
                response = await self._provider.complete(request)
            except Exception as exc:
                logger.warning(
                    "Provider call failed for node %s (round %d): %s",
                    node.id,
                    _round,
                    exc,
                )
                return Outcome(
                    status=StageStatus.FAIL,
                    failure_reason=str(exc),
                )

            text = _extract_text(response)
            tool_calls = _extract_tool_calls(response, self._provider)

            if not tool_calls:
                # Model is done -- parse the final text as an outcome
                if text:
                    outcome = _parse_outcome(text)
                else:
                    outcome = Outcome(
                        status=StageStatus.SUCCESS,
                        notes=f"Stage completed: {node.id}",
                    )
                outcome.context_updates = {
                    "last_stage": node.id,
                    "last_response": text[:200] if text else "",
                }

                # Record fidelity state for future calls
                self._completed_nodes[node.id] = outcome
                self._last_node_id = node.id

                # For full fidelity: save message history including this response
                if fidelity == "full":
                    messages.append(
                        Message(role="assistant", content=text or "")
                    )
                    self._message_pools[thread_key] = messages

                return outcome

            # Append assistant message and execute tools
            messages.append(_build_assistant_message(response))

            for tc in tool_calls:
                tool = self._tools.get(tc.name)
                if tool is not None:
                    try:
                        result = await tool.execute(tc.arguments)
                        output = (
                            result.output
                            if hasattr(result, "output")
                            else str(result)
                        )
                    except Exception as exc:
                        output = f"Tool error: {exc}"
                else:
                    output = f"Unknown tool: {tc.name}"

                messages.append(
                    Message(
                        role="tool",
                        tool_call_id=tc.id,
                        content=(
                            str(output)
                            if not isinstance(output, str)
                            else output
                        ),
                    )
                )

        outcome = Outcome(
            status=StageStatus.PARTIAL_SUCCESS,
            notes=f"Max tool loop rounds ({_MAX_TOOL_LOOP_ROUNDS}) reached",
        )
        self._completed_nodes[node.id] = outcome
        self._last_node_id = node.id
        return outcome
```

**Step 2: Run the fidelity tests**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/test_direct_backend_fidelity.py -xvs`

Expected: All PASS

**Step 3: Run the full test suite to check for regressions**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/ -x --tb=short -q`

Expected: All PASS. The backward-compatible `**kwargs` means existing callers that don't pass `incoming_edge`/`graph` still work.

**Step 4: Commit**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor
git add modules/loop-pipeline/amplifier_module_loop_pipeline/__init__.py
git commit -m "fix: wire fidelity into DirectProviderBackend (H-9)

DirectProviderBackend now resolves fidelity mode per node:
- full: reuses message history across calls with same thread key
- compact/truncate/summary: prepends preamble from completed nodes

Uses resolve_fidelity(), resolve_thread_key(), build_preamble()
from fidelity.py (already implemented for AmplifierBackend).

Spec Section 5.4: Context Fidelity."
```

---

### Task 4: Pass incoming_edge and graph from CodergenHandler to backend

**Files:**
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/handlers/codergen.py`

**Step 1: Read the current codergen handler**

Read `handlers/codergen.py` to find where `backend.run()` is called. Look for the call signature -- it likely passes `node`, `prompt`, `context` but not `incoming_edge` or `graph`.

**Step 2: Update the backend.run() call to pass graph**

The `execute()` method receives `graph` as a parameter. The `incoming_edge` for a node isn't directly available in the handler (it's in the engine's edge selection), so we pass `graph` and let the backend resolve fidelity from node attributes and graph defaults. The edge is passed as `None` when not available (node-level and graph-level fidelity still work).

Find the `backend.run(...)` call and add `graph=graph`:

```python
# Before:
outcome = await self._backend.run(node, prompt, context)

# After:
outcome = await self._backend.run(node, prompt, context, graph=graph)
```

**Step 3: Run full test suite**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/ -x --tb=short -q`

Expected: All PASS

**Step 4: Commit**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor
git add modules/loop-pipeline/amplifier_module_loop_pipeline/handlers/codergen.py
git commit -m "fix: pass graph to backend.run() from CodergenHandler (H-9)"
```

---

## Backward Compatibility

- **Low risk.** The `run()` method now accepts optional keyword-only args `incoming_edge` and `graph` with defaults of `None`. All existing callers that don't pass these continue to work identically -- the backend falls back to "compact" fidelity with no preamble (same as before).
- The only behavioral change is when `graph` IS passed: the backend now builds preambles and reuses message history. This is the correct spec behavior.

## Dependencies

- Depends on `fidelity.py` which already exists and has 100% test coverage.
- `CodergenHandler` changes depend on understanding how `backend.run()` is called. Read `handlers/codergen.py` before implementing Task 4.

## PR Details

- **Branch:** `track1/1b5-fidelity-direct-backend`
- **Title:** `fix: wire fidelity into DirectProviderBackend (H-9, spec Section 5.4)`
- **Labels:** `track1`, `pipeline`, `spec-compliance`
