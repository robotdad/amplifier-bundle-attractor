# Track 1-1B6: Add Missing Pipeline Event Categories (H-10)

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Add 9 missing event types across 3 categories: parallel events (4), human interaction events (3), and retry events (2). Wire emission points into the corresponding handlers and retry logic.
**Architecture:** Event constants go in `pipeline_events.py`. Emission calls go in the handlers (`parallel.py`, `human.py`) and retry logic (`retry.py`). The engine already passes `hooks` to handlers via the `HandlerRegistry`, but currently only the engine itself emits events. Handlers need access to a hooks object to emit their own events. The simplest approach: pass hooks through the existing `logs_root` pattern -- add a `hooks` parameter to handler `execute()` calls, or use a simpler approach of having the engine emit events around handler calls (pre/post pattern).
**Tech Stack:** Python, pytest

**Finding:** H-10 from adversarial-spec-review.md
**Spec Reference:** Section 9.6 -- Observability and Events

---

## Root Cause

**File:** `modules/loop-pipeline/amplifier_module_loop_pipeline/pipeline_events.py` (all 42 lines)

Current event constants (8 total):
```python
PIPELINE_START = "pipeline:start"
PIPELINE_COMPLETE = "pipeline:complete"
PIPELINE_NODE_START = "pipeline:node_start"
PIPELINE_NODE_COMPLETE = "pipeline:node_complete"
PIPELINE_EDGE_SELECTED = "pipeline:edge_selected"
PIPELINE_CHECKPOINT = "pipeline:checkpoint"
PIPELINE_GOAL_GATE_CHECK = "pipeline:goal_gate_check"
PIPELINE_ERROR = "pipeline:error"
```

**Missing per spec Section 9.6:**

| Category | Event | Spec Name | Where to Emit |
|----------|-------|-----------|---------------|
| Parallel | `pipeline:parallel_started` | ParallelStarted | `parallel.py` at start of execute |
| Parallel | `pipeline:parallel_branch_started` | ParallelBranchStarted | `parallel.py` in run_branch |
| Parallel | `pipeline:parallel_branch_completed` | ParallelBranchCompleted | `parallel.py` in run_branch |
| Parallel | `pipeline:parallel_completed` | ParallelCompleted | `parallel.py` at end of execute |
| Human | `pipeline:interview_started` | InterviewStarted | `human.py` before ask() |
| Human | `pipeline:interview_completed` | InterviewCompleted | `human.py` after ask() |
| Human | `pipeline:interview_timeout` | InterviewTimeout | `human.py` on timeout |
| Retry | `pipeline:stage_retrying` | StageRetrying | `retry.py` before retry sleep |
| Retry | `pipeline:stage_failed` | StageFailed | `retry.py` on final failure |

**Problem:** No observability for parallel execution, human interaction, or retry attempts. Frontends (TUI, web) cannot display parallel branch progress, human gate status, or retry attempts.

---

## The Fix

### Task 1: Add event constants to pipeline_events.py

**Files:**
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/pipeline_events.py`

**Step 1: Write the failing test**

Add to `modules/loop-pipeline/tests/test_pipeline_events.py`:

```python
def test_all_spec_event_constants_exist():
    """All spec Section 9.6 event types must have constants defined."""
    from amplifier_module_loop_pipeline import pipeline_events as pe

    required_events = [
        # Existing
        "PIPELINE_START",
        "PIPELINE_COMPLETE",
        "PIPELINE_NODE_START",
        "PIPELINE_NODE_COMPLETE",
        "PIPELINE_EDGE_SELECTED",
        "PIPELINE_CHECKPOINT",
        "PIPELINE_GOAL_GATE_CHECK",
        "PIPELINE_ERROR",
        # New: Parallel
        "PIPELINE_PARALLEL_STARTED",
        "PIPELINE_PARALLEL_BRANCH_STARTED",
        "PIPELINE_PARALLEL_BRANCH_COMPLETED",
        "PIPELINE_PARALLEL_COMPLETED",
        # New: Human
        "PIPELINE_INTERVIEW_STARTED",
        "PIPELINE_INTERVIEW_COMPLETED",
        "PIPELINE_INTERVIEW_TIMEOUT",
        # New: Retry
        "PIPELINE_STAGE_RETRYING",
        "PIPELINE_STAGE_FAILED",
    ]

    for name in required_events:
        assert hasattr(pe, name), f"Missing event constant: {name}"
        value = getattr(pe, name)
        assert isinstance(value, str), f"{name} should be a string, got {type(value)}"
        assert value.startswith("pipeline:"), f"{name} should start with 'pipeline:'"
```

**Step 2: Run to verify it fails**

Run: `cd /path/to/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/test_pipeline_events.py::test_all_spec_event_constants_exist -xvs`

Expected: FAIL -- `Missing event constant: PIPELINE_PARALLEL_STARTED`

**Step 3: Add the constants to pipeline_events.py**

Read the existing file then append after the `PIPELINE_ERROR` constant:

```python
# ---------------------------------------------------------------------------
# Parallel execution (spec Section 9.6)
# ---------------------------------------------------------------------------
PIPELINE_PARALLEL_STARTED: str = "pipeline:parallel_started"
PIPELINE_PARALLEL_BRANCH_STARTED: str = "pipeline:parallel_branch_started"
PIPELINE_PARALLEL_BRANCH_COMPLETED: str = "pipeline:parallel_branch_completed"
PIPELINE_PARALLEL_COMPLETED: str = "pipeline:parallel_completed"

# ---------------------------------------------------------------------------
# Human interaction (spec Section 9.6)
# ---------------------------------------------------------------------------
PIPELINE_INTERVIEW_STARTED: str = "pipeline:interview_started"
PIPELINE_INTERVIEW_COMPLETED: str = "pipeline:interview_completed"
PIPELINE_INTERVIEW_TIMEOUT: str = "pipeline:interview_timeout"

# ---------------------------------------------------------------------------
# Retry lifecycle (spec Section 9.6)
# ---------------------------------------------------------------------------
PIPELINE_STAGE_RETRYING: str = "pipeline:stage_retrying"
PIPELINE_STAGE_FAILED: str = "pipeline:stage_failed"
```

**Step 4: Run the test**

Run: `cd /path/to/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/test_pipeline_events.py::test_all_spec_event_constants_exist -xvs`

Expected: PASS

**Step 5: Commit**

```bash
cd /path/to/amplifier-bundle-attractor
git add modules/loop-pipeline/amplifier_module_loop_pipeline/pipeline_events.py
git add modules/loop-pipeline/tests/test_pipeline_events.py
git commit -m "feat: add 9 missing pipeline event constants (H-10, spec 9.6)"
```

---

### Task 2: Add hooks parameter to handler execute() and wire through registry

**Files:**
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/handlers/__init__.py`

The current `NodeHandler` protocol requires `execute(node, context, graph, logs_root)`. Rather than changing the protocol (which would break all handlers), we pass hooks through the registry to handlers that need it.

**Step 1: Update HandlerRegistry to store hooks**

In `handlers/__init__.py`, update `HandlerRegistry.__init__`:

Find:
```python
    def __init__(self, **kwargs: Any) -> None:
```

After the handler dict construction (line 75), add:

```python
        self._hooks = kwargs.get("hooks")
```

Add a property:
```python
    @property
    def hooks(self) -> Any:
        """Access the hooks object for event emission."""
        return self._hooks
```

**Step 2: Update handler constructors that need hooks**

Update `ParallelHandler` and `HumanGateHandler` initialization in the registry to pass hooks:

```python
        self._handlers: dict[str, NodeHandler] = {
            "start": StartHandler(),
            "exit": ExitHandler(),
            "codergen": CodergenHandler(**kwargs),
            "conditional": ConditionalHandler(),
            "tool": ToolHandler(),
            "wait.human": HumanGateHandler(
                interviewer=kwargs.get("interviewer"),
                hooks=kwargs.get("hooks"),
            ),
            "stack.manager_loop": ManagerLoopHandler(
                subgraph_runner=kwargs.get("subgraph_runner"),
            ),
            "parallel": ParallelHandler(
                subgraph_runner=kwargs.get("subgraph_runner"),
                hooks=kwargs.get("hooks"),
            ),
            "parallel.fan_in": FanInHandler(),
        }
```

**Step 3: Update engine to pass hooks to HandlerRegistry**

In `__init__.py` (PipelineOrchestrator.execute), update the registry construction:

Find:
```python
        registry = HandlerRegistry(backend=backend)
```

Replace with:
```python
        registry = HandlerRegistry(backend=backend, hooks=hooks)
```

**Step 4: Run tests to ensure nothing breaks**

Run: `cd /path/to/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/ -x --tb=short -q`

Expected: PASS (the hooks parameter is optional with `kwargs.get`)

**Step 5: Commit**

```bash
cd /path/to/amplifier-bundle-attractor
git add modules/loop-pipeline/amplifier_module_loop_pipeline/handlers/__init__.py
git add modules/loop-pipeline/amplifier_module_loop_pipeline/__init__.py
git commit -m "refactor: pass hooks through HandlerRegistry to handlers (H-10)"
```

---

### Task 3: Wire parallel events into ParallelHandler

**Files:**
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/handlers/parallel.py`
- Modify: `modules/loop-pipeline/tests/test_parallel.py`

**Step 1: Write the failing test**

Add to `test_parallel.py`:

```python
@pytest.mark.asyncio
async def test_parallel_handler_emits_events():
    """ParallelHandler must emit parallel lifecycle events."""
    from amplifier_module_loop_pipeline.handlers.parallel import ParallelHandler
    from amplifier_module_loop_pipeline.pipeline_events import (
        PIPELINE_PARALLEL_STARTED,
        PIPELINE_PARALLEL_BRANCH_STARTED,
        PIPELINE_PARALLEL_BRANCH_COMPLETED,
        PIPELINE_PARALLEL_COMPLETED,
    )

    emitted = []

    class MockHooks:
        async def emit(self, event_name, data):
            emitted.append((event_name, data))

    async def mock_runner(node_id, ctx, graph, logs_root):
        return Outcome(status=StageStatus.SUCCESS, notes="ok")

    handler = ParallelHandler(subgraph_runner=mock_runner, hooks=MockHooks())

    graph = Graph(
        name="test",
        nodes={
            "par": Node(id="par", shape="component"),
            "b1": Node(id="b1", shape="box"),
            "b2": Node(id="b2", shape="box"),
        },
        edges=[
            Edge(from_node="par", to_node="b1"),
            Edge(from_node="par", to_node="b2"),
        ],
    )

    ctx = PipelineContext()
    await handler.execute(graph.nodes["par"], ctx, graph, "/tmp/test")

    event_names = [e[0] for e in emitted]
    assert PIPELINE_PARALLEL_STARTED in event_names
    assert PIPELINE_PARALLEL_BRANCH_STARTED in event_names
    assert PIPELINE_PARALLEL_BRANCH_COMPLETED in event_names
    assert PIPELINE_PARALLEL_COMPLETED in event_names
```

**Step 2: Update ParallelHandler to accept hooks and emit events**

In `parallel.py`, update `__init__`:

```python
    def __init__(
        self,
        subgraph_runner: SubgraphRunner | None = None,
        hooks: Any = None,
    ) -> None:
        self._runner = subgraph_runner
        self._hooks = hooks
```

Add a helper method:

```python
    async def _emit(self, event_name: str, data: dict[str, Any]) -> None:
        """Emit an event via hooks, if provided."""
        if self._hooks is not None:
            await self._hooks.emit(event_name, data)
```

In the `execute()` method, add event emissions:

After identifying branches (line 70-75), add:
```python
        from ..pipeline_events import (
            PIPELINE_PARALLEL_STARTED,
            PIPELINE_PARALLEL_BRANCH_STARTED,
            PIPELINE_PARALLEL_BRANCH_COMPLETED,
            PIPELINE_PARALLEL_COMPLETED,
        )

        await self._emit(
            PIPELINE_PARALLEL_STARTED,
            {"node_id": node.id, "branch_count": len(branches)},
        )
```

In `run_branch()`, before and after the runner call:
```python
            async with semaphore:
                await self._emit(
                    PIPELINE_PARALLEL_BRANCH_STARTED,
                    {"node_id": node.id, "branch_node_id": target_node_id},
                )
                branch_context = context.clone()
                # ... existing execution code ...
                await self._emit(
                    PIPELINE_PARALLEL_BRANCH_COMPLETED,
                    {
                        "node_id": node.id,
                        "branch_node_id": target_node_id,
                        "status": outcome.status.value,
                    },
                )
```

Before the `return _apply_join_policy(...)` call:
```python
        await self._emit(
            PIPELINE_PARALLEL_COMPLETED,
            {
                "node_id": node.id,
                "branch_count": len(branches),
                "result_count": len(results),
            },
        )
```

**Step 3: Run tests**

Run: `cd /path/to/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/test_parallel.py -xvs`

Expected: All PASS

**Step 4: Commit**

```bash
cd /path/to/amplifier-bundle-attractor
git add modules/loop-pipeline/amplifier_module_loop_pipeline/handlers/parallel.py
git add modules/loop-pipeline/tests/test_parallel.py
git commit -m "feat: emit parallel lifecycle events from ParallelHandler (H-10)"
```

---

### Task 4: Wire human interaction events into HumanGateHandler

**Files:**
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/handlers/human.py`
- Modify: `modules/loop-pipeline/tests/test_human.py`

**Step 1: Write the failing test**

Add to `test_human.py`:

```python
@pytest.mark.asyncio
async def test_human_handler_emits_interview_events():
    """HumanGateHandler must emit interview lifecycle events."""
    from amplifier_module_loop_pipeline.pipeline_events import (
        PIPELINE_INTERVIEW_STARTED,
        PIPELINE_INTERVIEW_COMPLETED,
    )

    emitted = []

    class MockHooks:
        async def emit(self, event_name, data):
            emitted.append((event_name, data))

    class MockInterviewer:
        async def ask(self, question):
            from amplifier_module_loop_pipeline.interviewer import Answer, AnswerValue
            return Answer(value=AnswerValue.YES)

    handler = HumanGateHandler(interviewer=MockInterviewer(), hooks=MockHooks())

    node = Node(id="gate", shape="hexagon", label="Approve?")
    graph = Graph(
        name="test",
        nodes={"gate": node, "yes": Node(id="yes", shape="box")},
        edges=[Edge(from_node="gate", to_node="yes", label="Yes")],
    )
    ctx = PipelineContext()

    await handler.execute(node, ctx, graph, "/tmp/test")

    event_names = [e[0] for e in emitted]
    assert PIPELINE_INTERVIEW_STARTED in event_names
    assert PIPELINE_INTERVIEW_COMPLETED in event_names
```

**Step 2: Update HumanGateHandler to accept hooks and emit events**

In `human.py`, update `__init__` to accept `hooks`:

```python
    def __init__(self, interviewer=None, hooks=None):
        self._interviewer = interviewer
        self._hooks = hooks
```

Add `_emit` helper and emit events around the `self._interviewer.ask()` call:

```python
    async def _emit(self, event_name, data):
        if self._hooks is not None:
            await self._hooks.emit(event_name, data)
```

Before `ask()`:
```python
        from ..pipeline_events import (
            PIPELINE_INTERVIEW_STARTED,
            PIPELINE_INTERVIEW_COMPLETED,
            PIPELINE_INTERVIEW_TIMEOUT,
        )
        await self._emit(PIPELINE_INTERVIEW_STARTED, {
            "node_id": node.id,
            "question": question.text if hasattr(question, 'text') else str(question),
        })
```

After `ask()`:
```python
        await self._emit(PIPELINE_INTERVIEW_COMPLETED, {
            "node_id": node.id,
            "answer": str(answer.value) if hasattr(answer, 'value') else str(answer),
        })
```

On timeout (if the handler has timeout logic):
```python
        await self._emit(PIPELINE_INTERVIEW_TIMEOUT, {
            "node_id": node.id,
        })
```

**Step 3: Run tests**

Run: `cd /path/to/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/test_human.py -xvs`

Expected: All PASS

**Step 4: Commit**

```bash
cd /path/to/amplifier-bundle-attractor
git add modules/loop-pipeline/amplifier_module_loop_pipeline/handlers/human.py
git add modules/loop-pipeline/tests/test_human.py
git commit -m "feat: emit interview lifecycle events from HumanGateHandler (H-10)"
```

---

### Task 5: Wire retry events into retry.py

**Files:**
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/retry.py`
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/engine.py`
- Modify: `modules/loop-pipeline/tests/test_retry.py`

**Step 1: Write the failing test**

Add to `test_retry.py`:

```python
@pytest.mark.asyncio
async def test_retry_emits_retrying_event():
    """execute_with_retry must emit StageRetrying events on retry."""
    from amplifier_module_loop_pipeline.pipeline_events import (
        PIPELINE_STAGE_RETRYING,
        PIPELINE_STAGE_FAILED,
    )

    emitted = []

    class MockHooks:
        async def emit(self, event_name, data):
            emitted.append((event_name, data))

    call_count = 0

    class RetryThenSucceedHandler:
        async def execute(self, node, context, graph, logs_root):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return Outcome(status=StageStatus.RETRY, failure_reason="not yet")
            return Outcome(status=StageStatus.SUCCESS)

    node = Node(id="work", shape="box", prompt="do work")
    graph = Graph(
        name="test",
        nodes={"work": node},
        edges=[],
    )
    ctx = PipelineContext()
    policy = RetryPolicy(max_attempts=3, backoff=BackoffConfig(initial_delay_ms=0))

    await execute_with_retry(
        RetryThenSucceedHandler(),
        node,
        ctx,
        graph,
        "/tmp/test",
        policy,
        hooks=MockHooks(),
    )

    event_names = [e[0] for e in emitted]
    assert PIPELINE_STAGE_RETRYING in event_names
```

**Step 2: Add `hooks` parameter to `execute_with_retry`**

In `retry.py`, update the function signature:

```python
async def execute_with_retry(
    handler: Any,
    node: Node,
    context: PipelineContext,
    graph: Graph,
    logs_root: str,
    policy: RetryPolicy,
    hooks: Any = None,
) -> Outcome:
```

Add emission calls. In the RETRY branch (around line 133), before the sleep:

```python
            if hooks is not None:
                from .pipeline_events import PIPELINE_STAGE_RETRYING
                await hooks.emit(
                    PIPELINE_STAGE_RETRYING,
                    {
                        "node_id": node.id,
                        "attempt": attempt,
                        "max_attempts": policy.max_attempts,
                        "delay_ms": policy.backoff.delay_for_attempt(attempt),
                    },
                )
```

At the end when retries are exhausted (around line 150), before returning:

```python
    if hooks is not None:
        from .pipeline_events import PIPELINE_STAGE_FAILED
        await hooks.emit(
            PIPELINE_STAGE_FAILED,
            {
                "node_id": node.id,
                "attempts": policy.max_attempts,
                "final_status": "partial_success" if node.attrs.get("allow_partial") else "fail",
            },
        )
```

**Step 3: Update engine.py to pass hooks to execute_with_retry**

In `engine.py` line 200, update the call:

Find:
```python
            outcome = await execute_with_retry(
                handler,
                current_node,
                self.context,
                self.graph,
                self.logs_root,
                retry_policy,
            )
```

Replace with:
```python
            outcome = await execute_with_retry(
                handler,
                current_node,
                self.context,
                self.graph,
                self.logs_root,
                retry_policy,
                hooks=self.hooks,
            )
```

**Step 4: Run tests**

Run: `cd /path/to/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/test_retry.py -xvs`

Expected: All PASS

**Step 5: Run full test suite**

Run: `cd /path/to/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/ -x --tb=short -q`

Expected: All PASS

**Step 6: Commit**

```bash
cd /path/to/amplifier-bundle-attractor
git add modules/loop-pipeline/amplifier_module_loop_pipeline/retry.py
git add modules/loop-pipeline/amplifier_module_loop_pipeline/engine.py
git add modules/loop-pipeline/tests/test_retry.py
git commit -m "feat: emit retry lifecycle events from execute_with_retry (H-10)

Completes all 9 missing pipeline event types from spec Section 9.6:
- Parallel: started, branch_started, branch_completed, completed
- Human: interview_started, interview_completed, interview_timeout
- Retry: stage_retrying, stage_failed

All 17 event constants now defined in pipeline_events.py."
```

---

## Backward Compatibility

- **Low risk.** All new `hooks` parameters default to `None`. Existing callers that don't pass hooks continue to work without events.
- The `execute_with_retry` signature change adds `hooks=None` at the end. All existing callers pass positional args and won't be affected.
- Handlers that accept `hooks=None` in their constructors remain backward compatible.

## Dependencies

- None. All emission is conditional on `hooks is not None`.

## PR Details

- **Branch:** `track1/1b6-pipeline-events`
- **Title:** `feat: add missing pipeline event categories (H-10, spec Section 9.6)`
- **Labels:** `track1`, `pipeline`, `spec-compliance`, `observability`
