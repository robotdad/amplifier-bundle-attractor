# Track 1-1B2: Implement Per-Node Failure Routing (H-6)

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** When no edge matches after a node execution and the outcome is FAIL, check `retry_target` and `fallback_retry_target` on the node and graph before terminating the pipeline.
**Architecture:** The engine's main loop in `engine.py` lines 244-260 currently returns FAIL immediately when `select_edge()` returns `None`. The fix adds a fallback chain: fail-edge check (already handled by `select_edge` via condition matching) -> node `retry_target` -> node `fallback_retry_target` -> graph `retry_target` -> graph `fallback_retry_target` -> terminate.
**Tech Stack:** Python, pytest

**Finding:** H-6 from adversarial-spec-review.md
**Spec Reference:** Section 3.7 -- Failure Routing

---

## Root Cause

**File:** `modules/loop-pipeline/amplifier_module_loop_pipeline/engine.py` lines 244-260

Current code when edge selection returns `None`:

```python
            # Step 5: Select next edge
            edge = select_edge(current_node.id, outcome, self.context, self.graph)
            if edge is None:
                fail_outcome = Outcome(
                    status=StageStatus.FAIL,
                    failure_reason=f"No matching edge from node '{current_node.id}'",
                )
                await self._emit(
                    PIPELINE_ERROR,
                    {
                        "node_id": current_node.id,
                        "error_type": "no_matching_edge",
                        "message": fail_outcome.failure_reason or "",
                    },
                )
                await self._emit_complete(fail_outcome, pipeline_start_time)
                return fail_outcome
```

**Problem:** The spec Section 3.7 defines a four-step failure routing chain:

1. **Fail edge:** An outgoing edge with `condition="outcome=fail"` -- this IS already handled by `select_edge()` step 1 (condition matching). If there's a `condition="outcome=fail"` edge and the outcome is fail, it will match.
2. **Retry target:** Node attribute `retry_target` -- **NOT CHECKED**
3. **Fallback retry target:** Node attribute `fallback_retry_target` -- **NOT CHECKED**
4. **Graph-level targets:** `graph.retry_target` then `graph.fallback_retry_target` -- **NOT CHECKED**

When a node fails and has no matching outgoing edge (no fail-condition edge), the pipeline immediately terminates even if `retry_target` is configured on the node.

Note: The goal gate check in `_check_goal_gates()` (lines 298-363) DOES implement the retry target fallback chain correctly. The bug is that the main execution loop does NOT.

---

## The Fix

### Task 1: Write failing tests for per-node failure routing

**Files:**
- Create: `modules/loop-pipeline/tests/test_failure_routing.py`

**Step 1: Write the failing tests**

```python
"""Tests for per-node failure routing (spec Section 3.7, H-6).

When a node fails and no edge matches, the engine should check:
1. retry_target on the node
2. fallback_retry_target on the node
3. retry_target on the graph
4. fallback_retry_target on the graph
before terminating the pipeline.
"""

import pytest

from amplifier_module_loop_pipeline.context import PipelineContext
from amplifier_module_loop_pipeline.engine import PipelineEngine
from amplifier_module_loop_pipeline.graph import Edge, Graph, Node
from amplifier_module_loop_pipeline.handlers import HandlerRegistry, NodeHandler
from amplifier_module_loop_pipeline.outcome import Outcome, StageStatus


class FailOnceHandler:
    """Handler that fails the first time for a given node, succeeds after."""

    def __init__(self):
        self._call_counts: dict[str, int] = {}

    async def execute(self, node, context, graph, logs_root):
        count = self._call_counts.get(node.id, 0) + 1
        self._call_counts[node.id] = count
        if count == 1:
            return Outcome(status=StageStatus.FAIL, failure_reason="first attempt fails")
        return Outcome(status=StageStatus.SUCCESS, notes="retry succeeded")


class AlwaysFailHandler:
    """Handler that always fails."""

    async def execute(self, node, context, graph, logs_root):
        return Outcome(status=StageStatus.FAIL, failure_reason="always fails")


class AlwaysSuccessHandler:
    """Handler that always succeeds."""

    async def execute(self, node, context, graph, logs_root):
        return Outcome(status=StageStatus.SUCCESS, notes="ok")


def _make_graph_with_retry_target():
    """Build a graph: start -> work -> done, where work has retry_target=work.

    work has no fail-condition edge, so on failure the engine must use
    retry_target to jump back to work.
    """
    return Graph(
        name="test",
        nodes={
            "start": Node(id="start", shape="Mdiamond"),
            "work": Node(
                id="work",
                shape="box",
                prompt="do work",
                attrs={
                    "retry_target": "work",
                    "max_retries": 0,  # no handler-level retry
                },
            ),
            "done": Node(id="done", shape="Msquare"),
        },
        edges=[
            Edge(from_node="start", to_node="work"),
            Edge(from_node="work", to_node="done", condition="outcome=success"),
            # NOTE: no "outcome=fail" edge -- failure routing must use retry_target
        ],
    )


@pytest.mark.asyncio
async def test_failure_routing_uses_node_retry_target(tmp_path):
    """When no edge matches a failed node, engine jumps to retry_target."""
    graph = _make_graph_with_retry_target()

    fail_once = FailOnceHandler()
    registry = HandlerRegistry()
    registry.register("codergen", fail_once)

    engine = PipelineEngine(
        graph=graph,
        context=PipelineContext(),
        handler_registry=registry,
        logs_root=str(tmp_path),
    )
    outcome = await engine.run(goal="test")

    # Should succeed: work fails -> retry_target=work -> work succeeds -> done
    assert outcome.status == StageStatus.SUCCESS
    # work should appear twice in completed_nodes
    assert engine.completed_nodes.count("work") == 2


@pytest.mark.asyncio
async def test_failure_routing_uses_node_fallback_retry_target(tmp_path):
    """When retry_target is missing, engine uses fallback_retry_target."""
    graph = Graph(
        name="test",
        nodes={
            "start": Node(id="start", shape="Mdiamond"),
            "work": Node(
                id="work",
                shape="box",
                prompt="do work",
                attrs={"fallback_retry_target": "work"},
            ),
            "done": Node(id="done", shape="Msquare"),
        },
        edges=[
            Edge(from_node="start", to_node="work"),
            Edge(from_node="work", to_node="done", condition="outcome=success"),
        ],
    )

    fail_once = FailOnceHandler()
    registry = HandlerRegistry()
    registry.register("codergen", fail_once)

    engine = PipelineEngine(
        graph=graph,
        context=PipelineContext(),
        handler_registry=registry,
        logs_root=str(tmp_path),
    )
    outcome = await engine.run(goal="test")
    assert outcome.status == StageStatus.SUCCESS


@pytest.mark.asyncio
async def test_failure_routing_uses_graph_retry_target(tmp_path):
    """When node has no retry targets, engine checks graph-level retry_target."""
    graph = Graph(
        name="test",
        nodes={
            "start": Node(id="start", shape="Mdiamond"),
            "work": Node(id="work", shape="box", prompt="do work"),
            "done": Node(id="done", shape="Msquare"),
        },
        edges=[
            Edge(from_node="start", to_node="work"),
            Edge(from_node="work", to_node="done", condition="outcome=success"),
        ],
        graph_attrs={"retry_target": "work"},
    )

    fail_once = FailOnceHandler()
    registry = HandlerRegistry()
    registry.register("codergen", fail_once)

    engine = PipelineEngine(
        graph=graph,
        context=PipelineContext(),
        handler_registry=registry,
        logs_root=str(tmp_path),
    )
    outcome = await engine.run(goal="test")
    assert outcome.status == StageStatus.SUCCESS


@pytest.mark.asyncio
async def test_failure_routing_uses_graph_fallback_retry_target(tmp_path):
    """Last resort: graph-level fallback_retry_target."""
    graph = Graph(
        name="test",
        nodes={
            "start": Node(id="start", shape="Mdiamond"),
            "work": Node(id="work", shape="box", prompt="do work"),
            "done": Node(id="done", shape="Msquare"),
        },
        edges=[
            Edge(from_node="start", to_node="work"),
            Edge(from_node="work", to_node="done", condition="outcome=success"),
        ],
        graph_attrs={"fallback_retry_target": "work"},
    )

    fail_once = FailOnceHandler()
    registry = HandlerRegistry()
    registry.register("codergen", fail_once)

    engine = PipelineEngine(
        graph=graph,
        context=PipelineContext(),
        handler_registry=registry,
        logs_root=str(tmp_path),
    )
    outcome = await engine.run(goal="test")
    assert outcome.status == StageStatus.SUCCESS


@pytest.mark.asyncio
async def test_failure_routing_terminates_when_no_targets(tmp_path):
    """When no retry targets exist anywhere, pipeline fails."""
    graph = Graph(
        name="test",
        nodes={
            "start": Node(id="start", shape="Mdiamond"),
            "work": Node(id="work", shape="box", prompt="do work"),
            "done": Node(id="done", shape="Msquare"),
        },
        edges=[
            Edge(from_node="start", to_node="work"),
            Edge(from_node="work", to_node="done", condition="outcome=success"),
        ],
    )

    always_fail = AlwaysFailHandler()
    registry = HandlerRegistry()
    registry.register("codergen", always_fail)

    engine = PipelineEngine(
        graph=graph,
        context=PipelineContext(),
        handler_registry=registry,
        logs_root=str(tmp_path),
    )
    outcome = await engine.run(goal="test")
    assert outcome.status == StageStatus.FAIL


@pytest.mark.asyncio
async def test_failure_routing_has_retry_limit(tmp_path):
    """Failure routing must not loop forever -- bounded by _MAX_GOAL_GATE_RETRIES."""
    graph = Graph(
        name="test",
        nodes={
            "start": Node(id="start", shape="Mdiamond"),
            "work": Node(
                id="work",
                shape="box",
                prompt="do work",
                attrs={"retry_target": "work"},
            ),
            "done": Node(id="done", shape="Msquare"),
        },
        edges=[
            Edge(from_node="start", to_node="work"),
            Edge(from_node="work", to_node="done", condition="outcome=success"),
        ],
    )

    always_fail = AlwaysFailHandler()
    registry = HandlerRegistry()
    registry.register("codergen", always_fail)

    engine = PipelineEngine(
        graph=graph,
        context=PipelineContext(),
        handler_registry=registry,
        logs_root=str(tmp_path),
    )
    outcome = await engine.run(goal="test")
    # Must eventually fail, not loop forever
    assert outcome.status == StageStatus.FAIL
```

**Step 2: Run tests to verify they fail**

Run: `cd /path/to/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/test_failure_routing.py -xvs`

Expected: `test_failure_routing_uses_node_retry_target` FAILS with `AssertionError: assert <StageStatus.FAIL> == <StageStatus.SUCCESS>`

**Step 3: Commit failing tests**

```bash
cd /path/to/amplifier-bundle-attractor
git add modules/loop-pipeline/tests/test_failure_routing.py
git commit -m "test: add per-node failure routing tests (H-6)"
```

---

### Task 2: Implement failure routing fallback chain in engine

**Files:**
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/engine.py` lines 244-260

**Step 1: Add failure routing retry counter**

In `engine.py`, in the `__init__` method (around line 70), after `self.completed_nodes`, add:

```python
        self._failure_routing_retries: int = 0
```

**Step 2: Replace the `edge is None` block with failure routing**

In `engine.py`, find the block at lines 244-260:

```python
            # Step 5: Select next edge
            edge = select_edge(current_node.id, outcome, self.context, self.graph)
            if edge is None:
                fail_outcome = Outcome(
                    status=StageStatus.FAIL,
                    failure_reason=f"No matching edge from node '{current_node.id}'",
                )
                await self._emit(
                    PIPELINE_ERROR,
                    {
                        "node_id": current_node.id,
                        "error_type": "no_matching_edge",
                        "message": fail_outcome.failure_reason or "",
                    },
                )
                await self._emit_complete(fail_outcome, pipeline_start_time)
                return fail_outcome
```

Replace with:

```python
            # Step 5: Select next edge
            edge = select_edge(current_node.id, outcome, self.context, self.graph)
            if edge is None:
                # Step 5b: Failure routing fallback chain (spec Section 3.7)
                # When no edge matches, try retry targets before terminating.
                retry_target = self._resolve_failure_retry_target(current_node)

                if (
                    retry_target is not None
                    and retry_target in self.graph.nodes
                    and self._failure_routing_retries < self._MAX_GOAL_GATE_RETRIES
                ):
                    self._failure_routing_retries += 1
                    logger.info(
                        "No matching edge from '%s', failure-routing to '%s' (attempt %d)",
                        current_node.id,
                        retry_target,
                        self._failure_routing_retries,
                    )
                    current_node = self.graph.nodes[retry_target]
                    continue

                # No retry target or retries exhausted -- fail the pipeline
                fail_outcome = Outcome(
                    status=StageStatus.FAIL,
                    failure_reason=f"No matching edge from node '{current_node.id}'",
                )
                await self._emit(
                    PIPELINE_ERROR,
                    {
                        "node_id": current_node.id,
                        "error_type": "no_matching_edge",
                        "message": fail_outcome.failure_reason or "",
                    },
                )
                await self._emit_complete(fail_outcome, pipeline_start_time)
                return fail_outcome
```

**Step 3: Add the `_resolve_failure_retry_target` method**

Add this method to `PipelineEngine`, after `_check_goal_gates()` (around line 363):

```python
    def _resolve_failure_retry_target(self, node: Node) -> str | None:
        """Resolve the retry target for failure routing.

        Spec Section 3.7: Failure Routing fallback chain:
        1. Node retry_target
        2. Node fallback_retry_target
        3. Graph retry_target
        4. Graph fallback_retry_target

        Returns the target node ID, or None if no target is configured.
        """
        return (
            node.attrs.get("retry_target")
            or node.attrs.get("fallback_retry_target")
            or self.graph.graph_attrs.get("retry_target")
            or self.graph.graph_attrs.get("fallback_retry_target")
            or None
        )
```

**Step 4: Run the failure routing tests**

Run: `cd /path/to/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/test_failure_routing.py -xvs`

Expected: All PASS

**Step 5: Run the full test suite to check for regressions**

Run: `cd /path/to/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/ -x --tb=short -q`

Expected: All PASS

**Step 6: Commit**

```bash
cd /path/to/amplifier-bundle-attractor
git add modules/loop-pipeline/amplifier_module_loop_pipeline/engine.py
git commit -m "fix: implement per-node failure routing fallback chain (H-6)

When no edge matches after a node execution, the engine now checks:
1. Node retry_target
2. Node fallback_retry_target
3. Graph retry_target
4. Graph fallback_retry_target
before terminating the pipeline (spec Section 3.7).

Bounded by _MAX_GOAL_GATE_RETRIES to prevent infinite loops."
```

---

## Backward Compatibility

- **Low risk.** Previously, `edge is None` always meant pipeline termination. Now it means "try failure routing first." Any pipeline that previously terminated on `edge is None` without retry targets will behave identically. Only pipelines with `retry_target` configured will see new behavior (jumping to the target).
- The `_failure_routing_retries` counter shares the same max bound as `_MAX_GOAL_GATE_RETRIES` (50). This is intentional -- both are "retry from a non-exit node" patterns and should share the safety limit.

## Dependencies

- None. This is a self-contained change to `engine.py`.

## PR Details

- **Branch:** `track1/1b2-failure-routing`
- **Title:** `fix: implement per-node failure routing (H-6, spec Section 3.7)`
- **Labels:** `track1`, `pipeline`, `spec-compliance`
