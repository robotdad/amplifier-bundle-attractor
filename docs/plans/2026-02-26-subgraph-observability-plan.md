# Subgraph Observability Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

> **Spec Review Warning:** The spec review loop exhausted after 3 iterations before
> reaching approval. The final verdict was APPROVED, but the human reviewer should
> verify the implementation independently during the approval gate.

**Goal:** Enhance `PipelineHandler` to capture subgraph run data and emit prefixed lifecycle events for nested pipeline observability.

**Architecture:** Three additions to `PipelineHandler`: (1) a `_subgraph_runs` dict that accumulates observability data keyed by node ID after each child engine run, (2) an `_emit()` helper that conditionally forwards events through the hooks system, and (3) two event emission points — `pipeline:subgraph_start` before and `pipeline:subgraph_complete` after the child engine run. No new files are created; this is a surgical enhancement of one handler class and its test file.

**Tech Stack:** Python 3.12+, pytest, asyncio, `unittest.mock.AsyncMock`. All code lives in `amplifier-bundle-attractor/modules/loop-pipeline/`.

**Baseline:** 909 tests passing. After: 912 tests (3 new).

**Test command:** `cd amplifier-bundle-attractor/modules/loop-pipeline && .venv/bin/pytest tests/ -q`

**Depends on:** Task 5 (the `PipelineHandler.execute()` method and its existing tests must already exist).

---

## Key Types Reference

The implementer needs to understand these types (do NOT import them in new code — they're already in scope):

- **`Outcome`** (`amplifier_module_loop_pipeline/outcome.py`): Dataclass with `.status` (a `StageStatus` enum), `.notes`, `.failure_reason`. Access the string value via `outcome.status.value` (e.g., `"success"`).
- **`StageStatus`** (`amplifier_module_loop_pipeline/outcome.py`): Enum with `SUCCESS`, `PARTIAL_SUCCESS`, `RETRY`, `FAIL`, `SKIPPED`.
- **`PipelineEngine`** (`amplifier_module_loop_pipeline/engine.py`): After `.run()` completes, exposes `.completed_nodes` (list of node ID strings) and `.node_outcomes` (dict of node ID → `Outcome`).
- **`Node`** (`amplifier_module_loop_pipeline/graph.py`): Has `.id` (str), `.attrs` (dict).
- **`Graph`** (`amplifier_module_loop_pipeline/graph.py`): Has `.name` (str), `.nodes` (dict), `.goal` (str | None).
- **hooks object**: Any object with `async emit(event_name: str, data: dict) -> Any`. May be `None`.

---

## Phase 1 — Implementation (Single Task)

This is a single cohesive task — the `_subgraph_runs` dict, the `_emit()` helper, and the two event emission points are all tightly coupled within `execute()`.

---

### Task 1: Add `_subgraph_runs` dict and `_emit()` helper to `PipelineHandler.__init__`

**Files:**
- Modify: `amplifier_module_loop_pipeline/handlers/pipeline.py` (lines 67–75, the `__init__` method)
- Test: `tests/test_pipeline_handler.py`

**Step 1: Write the failing test**

Open `tests/test_pipeline_handler.py`. At the very bottom of the file (after the `TestPipelineHandlerExecute` class which ends around line 228), add the following test class:

```python
# ---------------------------------------------------------------------------
# PipelineHandler observability tests
# ---------------------------------------------------------------------------


class TestPipelineHandlerObservability:
    """Tests for subgraph observability — _subgraph_runs capture and event emission."""

    @pytest.mark.asyncio
    async def test_populates_subgraph_runs(self, tmp_path):
        """After execution, handler._subgraph_runs['sub'] contains all expected keys."""
        graph = _make_parent_graph(tmp_path)
        node = graph.nodes["sub"]
        context = PipelineContext()
        logs_root = str(tmp_path / "logs")

        handler = PipelineHandler()
        await handler.execute(node, context, graph, logs_root)

        assert "sub" in handler._subgraph_runs
        run = handler._subgraph_runs["sub"]
        expected_keys = {
            "dot_file",
            "dot_source",
            "pipeline_id",
            "goal",
            "status",
            "execution_path",
            "node_outcomes",
            "total_elapsed_ms",
            "nodes_completed",
            "nodes_total",
        }
        assert expected_keys.issubset(run.keys())
        assert run["status"] == "success"
        assert isinstance(run["total_elapsed_ms"], float)
        assert isinstance(run["nodes_completed"], int)
        assert isinstance(run["nodes_total"], int)
        assert run["nodes_completed"] > 0
```

**Step 2: Run test to verify it fails**

```bash
cd amplifier-bundle-attractor/modules/loop-pipeline && .venv/bin/pytest tests/test_pipeline_handler.py::TestPipelineHandlerObservability::test_populates_subgraph_runs -v
```

Expected: FAIL — `AttributeError: 'PipelineHandler' object has no attribute '_subgraph_runs'`

**Step 3: Write minimal implementation — `__init__` changes**

In `amplifier_module_loop_pipeline/handlers/pipeline.py`, modify the `__init__` method. Find the current `__init__` (around line 67):

```python
    def __init__(
        self,
        handler_registry_factory: Any = None,
        cancel_event: Any = None,
        hooks: Any = None,
    ) -> None:
        self._handler_registry_factory = handler_registry_factory
        self._cancel_event = cancel_event
        self._hooks = hooks
```

Add one line at the end of `__init__`:

```python
    def __init__(
        self,
        handler_registry_factory: Any = None,
        cancel_event: Any = None,
        hooks: Any = None,
    ) -> None:
        self._handler_registry_factory = handler_registry_factory
        self._cancel_event = cancel_event
        self._hooks = hooks
        self._subgraph_runs: dict[str, Any] = {}
```

Then add the `_emit` helper method immediately after `__init__` (before `execute`):

```python
    async def _emit(self, event_name: str, data: dict[str, Any]) -> None:
        """Emit an event via hooks, if provided."""
        if self._hooks is not None:
            await self._hooks.emit(event_name, data)
```

**Step 4: Add observability data capture to `execute()`**

In the `execute()` method, make three changes. All insertions go into the existing method body — no existing lines are removed or modified.

**Change A — Emit `pipeline:subgraph_start` before child engine run.**

Find the comment `# (10) Determine child goal` (around line 166). After the `child_goal = ...` line, add:

```python
        # (10b) Emit pipeline:subgraph_start event
        pipeline_id = child_graph.name or ""
        await self._emit(
            "pipeline:subgraph_start",
            {
                "node_id": node.id,
                "dot_file": dot_file,
                "pipeline_id": pipeline_id,
                "goal": child_goal or "",
            },
        )
```

**Change B — Wrap the child engine run with timing.**

Find the comment `# (11) Run child engine` (around line 181). Change the timing to wrap the `try/except` block:

Before (current code):
```python
        # (11) Run child engine
        try:
            outcome = await child_engine.run(goal=child_goal)
        except Exception as exc:
            logger.exception("Child pipeline failed for node '%s'", node.id)
            return Outcome(
                status=StageStatus.FAIL,
                failure_reason=f"Child pipeline exception: {exc}",
            )
```

After (add timing around it):
```python
        # (11) Run child engine
        subgraph_start_time = time.monotonic()
        try:
            outcome = await child_engine.run(goal=child_goal)
        except Exception as exc:
            logger.exception("Child pipeline failed for node '%s'", node.id)
            return Outcome(
                status=StageStatus.FAIL,
                failure_reason=f"Child pipeline exception: {exc}",
            )
        subgraph_elapsed_ms = (time.monotonic() - subgraph_start_time) * 1000
```

Note: `time` is already imported at the top of the file (line 14).

**Change C — Populate `_subgraph_runs` and emit `pipeline:subgraph_complete`.**

Immediately after `subgraph_elapsed_ms = ...` and before the `# (12) Return child outcome` comment, add:

```python
        # (11b) Populate _subgraph_runs with observability data
        self._subgraph_runs[node.id] = {
            "dot_file": dot_file,
            "dot_source": dot_source,
            "pipeline_id": pipeline_id,
            "goal": child_goal or "",
            "status": outcome.status.value,
            "execution_path": list(child_engine.completed_nodes),
            "node_outcomes": {
                nid: {
                    "status": o.status.value,
                    "notes": o.notes,
                    "failure_reason": o.failure_reason,
                }
                for nid, o in child_engine.node_outcomes.items()
            },
            "total_elapsed_ms": subgraph_elapsed_ms,
            "nodes_completed": len(child_engine.completed_nodes),
            "nodes_total": len(child_graph.nodes),
        }

        # (11c) Emit pipeline:subgraph_complete event
        await self._emit(
            "pipeline:subgraph_complete",
            {
                "node_id": node.id,
                "pipeline_id": pipeline_id,
                "status": outcome.status.value,
                "duration_ms": subgraph_elapsed_ms,
                "nodes_completed": len(child_engine.completed_nodes),
                "nodes_total": len(child_graph.nodes),
            },
        )
```

**Step 5: Run test to verify it passes**

```bash
cd amplifier-bundle-attractor/modules/loop-pipeline && .venv/bin/pytest tests/test_pipeline_handler.py::TestPipelineHandlerObservability::test_populates_subgraph_runs -v
```

Expected: PASS

**Step 6: Commit (do not commit yet — continue to Task 2)**

---

### Task 2: Add `test_emits_subgraph_start_event` test

**Files:**
- Test: `tests/test_pipeline_handler.py` (append to `TestPipelineHandlerObservability` class)

**Step 1: Write the test**

Add to the `TestPipelineHandlerObservability` class, after `test_populates_subgraph_runs`:

```python
    @pytest.mark.asyncio
    async def test_emits_subgraph_start_event(self, tmp_path):
        """hooks.emit is called with 'pipeline:subgraph_start' including node_id."""
        from unittest.mock import AsyncMock

        hooks = AsyncMock()
        graph = _make_parent_graph(tmp_path)
        node = graph.nodes["sub"]
        context = PipelineContext()
        logs_root = str(tmp_path / "logs")

        handler = PipelineHandler(hooks=hooks)
        await handler.execute(node, context, graph, logs_root)

        # Find the pipeline:subgraph_start call
        start_calls = [
            c for c in hooks.emit.call_args_list if c[0][0] == "pipeline:subgraph_start"
        ]
        assert len(start_calls) == 1
        data = start_calls[0][0][1]
        assert data["node_id"] == "sub"
        assert "dot_file" in data
        assert "pipeline_id" in data
        assert "goal" in data
```

**Why filtering `call_args_list`:** When `hooks` is an `AsyncMock`, the child `PipelineEngine` also receives the same hooks object and emits its own events (`pipeline:start`, `pipeline:node_start`, etc.). We filter to find only the `pipeline:subgraph_start` call made by `PipelineHandler._emit()`.

**Step 2: Run test to verify it passes**

```bash
cd amplifier-bundle-attractor/modules/loop-pipeline && .venv/bin/pytest tests/test_pipeline_handler.py::TestPipelineHandlerObservability::test_emits_subgraph_start_event -v
```

Expected: PASS (implementation was done in Task 1)

**Step 3: Commit (do not commit yet — continue to Task 3)**

---

### Task 3: Add `test_emits_subgraph_complete_event` test

**Files:**
- Test: `tests/test_pipeline_handler.py` (append to `TestPipelineHandlerObservability` class)

**Step 1: Write the test**

Add to the `TestPipelineHandlerObservability` class, after `test_emits_subgraph_start_event`:

```python
    @pytest.mark.asyncio
    async def test_emits_subgraph_complete_event(self, tmp_path):
        """hooks.emit is called with 'pipeline:subgraph_complete' including node_id, status, duration_ms."""
        from unittest.mock import AsyncMock

        hooks = AsyncMock()
        graph = _make_parent_graph(tmp_path)
        node = graph.nodes["sub"]
        context = PipelineContext()
        logs_root = str(tmp_path / "logs")

        handler = PipelineHandler(hooks=hooks)
        await handler.execute(node, context, graph, logs_root)

        # Find the pipeline:subgraph_complete call
        complete_calls = [
            c
            for c in hooks.emit.call_args_list
            if c[0][0] == "pipeline:subgraph_complete"
        ]
        assert len(complete_calls) == 1
        data = complete_calls[0][0][1]
        assert data["node_id"] == "sub"
        assert data["status"] == "success"
        assert "duration_ms" in data
        assert isinstance(data["duration_ms"], float)
        assert "pipeline_id" in data
        assert "nodes_completed" in data
        assert "nodes_total" in data
```

**Step 2: Run test to verify it passes**

```bash
cd amplifier-bundle-attractor/modules/loop-pipeline && .venv/bin/pytest tests/test_pipeline_handler.py::TestPipelineHandlerObservability::test_emits_subgraph_complete_event -v
```

Expected: PASS (implementation was done in Task 1)

**Step 3: Run all observability tests together**

```bash
cd amplifier-bundle-attractor/modules/loop-pipeline && .venv/bin/pytest tests/test_pipeline_handler.py::TestPipelineHandlerObservability -v
```

Expected: 3 PASSED

**Step 4: Run the full test_pipeline_handler.py file**

```bash
cd amplifier-bundle-attractor/modules/loop-pipeline && .venv/bin/pytest tests/test_pipeline_handler.py -v
```

Expected: 17 PASSED (8 resolve_dot_path + 6 execute + 3 observability)

**Step 5: Run code quality checks**

```bash
cd amplifier-bundle-attractor/modules/loop-pipeline && python -m ruff check amplifier_module_loop_pipeline/handlers/pipeline.py tests/test_pipeline_handler.py
cd amplifier-bundle-attractor/modules/loop-pipeline && python -m ruff format --check amplifier_module_loop_pipeline/handlers/pipeline.py tests/test_pipeline_handler.py
```

Expected: No issues.

**Step 6: Run full test suite**

```bash
cd amplifier-bundle-attractor/modules/loop-pipeline && .venv/bin/pytest tests/ -q
```

Expected: 912 passed (909 baseline + 3 new). Note: some test files may show collection errors due to pre-existing `unified_llm` import issues unrelated to this task — those are expected and do not count against this task.

**Step 7: Commit**

```
git add amplifier-bundle-attractor/modules/loop-pipeline/amplifier_module_loop_pipeline/handlers/pipeline.py amplifier-bundle-attractor/modules/loop-pipeline/tests/test_pipeline_handler.py
git commit -m "feat: add subgraph observability — subgraph_runs capture and event emission"
```

---

## Verification Checklist

After all tasks are complete, verify these acceptance criteria:

| # | Criterion | How to verify |
|---|-----------|---------------|
| AC1 | `handler._subgraph_runs["sub"]` contains keys `status`, `dot_file`, `pipeline_id`, `nodes_completed`, `nodes_total`, `total_elapsed_ms` and `status == "success"` | `test_populates_subgraph_runs` passes |
| AC2 | `hooks.emit` called once with `("pipeline:subgraph_start", {"node_id": "sub", ...})` | `test_emits_subgraph_start_event` passes |
| AC3 | `hooks.emit` called once with `("pipeline:subgraph_complete", {"node_id": "sub", "status": "success", "duration_ms": ...})` | `test_emits_subgraph_complete_event` passes |
| AC4 | All 912 tests pass (909 + 3 new) | Full suite run |
| AC5 | Commit message: `feat: add subgraph observability — subgraph_runs capture and event emission` | Commit log |

---

## Files Changed Summary

| File | Action | Lines changed |
|------|--------|---------------|
| `amplifier_module_loop_pipeline/handlers/pipeline.py` | Modify | +1 line in `__init__`, +4 lines `_emit()` method, +10 lines subgraph_start emit, +3 lines timing, +19 lines subgraph_runs populate, +11 lines subgraph_complete emit |
| `tests/test_pipeline_handler.py` | Modify | +89 lines (new `TestPipelineHandlerObservability` class with 3 test methods) |