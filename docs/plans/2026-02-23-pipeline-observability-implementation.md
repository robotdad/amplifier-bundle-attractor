# Pipeline Observability System — Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Build the pipeline observability system (Layers 1, 2, 3, 5) so agents can query pipeline state and users see rich progress during execution.

**Architecture:** A single new module `hooks-pipeline-observability` houses the `PipelineRunState` data model, a state aggregator hook, a status context-bar hook, and event persistence registration. A separate thin tool module `tool-pipeline-status` reads from the `pipeline.state` contribution channel. The existing `hooks-pipeline-progress` module is upgraded in-place to produce rich output for all 22 events.

**Tech Stack:** Python 3.11+, amplifier-core (hooks, contribution channels, ToolResult), pytest + pytest-asyncio, dataclasses, JSON serialization.

**Design doc:** `docs/plans/2026-02-23-pipeline-observability-design.md`

---

## Module Organization

```
modules/
├── hooks-pipeline-observability/          # NEW — data model + state aggregator + status bar + event persistence
│   ├── amplifier_module_hooks_pipeline_observability/
│   │   ├── __init__.py                    # mount(), module metadata
│   │   ├── models.py                      # PipelineRunState + all supporting dataclasses
│   │   ├── aggregator.py                  # StateAggregator hook (subscribes to all 22 events, maintains state)
│   │   └── status_bar.py                  # StatusBarHook (context injection as system-reminder)
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_models.py
│   │   ├── test_aggregator.py
│   │   ├── test_status_bar.py
│   │   └── test_mount.py
│   └── pyproject.toml
│
├── hooks-pipeline-progress/               # EXISTING — upgrade from 4 events to all 22
│   ├── amplifier_module_hooks_pipeline_progress/
│   │   └── __init__.py                    # Enhanced with 18 new handlers
│   └── tests/
│       └── test_hooks.py                  # Extended with new handler tests
│
└── tool-pipeline-status/                  # NEW — thin query tool
    ├── amplifier_module_tool_pipeline_status/
    │   └── __init__.py                    # PipelineStatusTool + mount()
    ├── tests/
    │   ├── __init__.py
    │   └── test_tool.py
    └── pyproject.toml
```

---

## Event Constant Reference

All 22 events from `modules/loop-pipeline/amplifier_module_loop_pipeline/pipeline_events.py`:

| Constant | String | Emitted by |
|---|---|---|
| `PIPELINE_START` | `pipeline:start` | `engine.py` — `run()` |
| `PIPELINE_COMPLETE` | `pipeline:complete` | `engine.py` — `_emit_complete()` |
| `PIPELINE_NODE_START` | `pipeline:node_start` | `engine.py` — `run()` |
| `PIPELINE_NODE_COMPLETE` | `pipeline:node_complete` | `engine.py` — `run()` |
| `PIPELINE_EDGE_SELECTED` | `pipeline:edge_selected` | `engine.py` — `run()` |
| `PIPELINE_CHECKPOINT` | `pipeline:checkpoint` | `engine.py` — `run()` |
| `PIPELINE_GOAL_GATE_CHECK` | `pipeline:goal_gate_check` | `engine.py` — `_check_goal_gates()` |
| `PIPELINE_ERROR` | `pipeline:error` | `engine.py` — `run()` |
| `PIPELINE_PARALLEL_STARTED` | `pipeline:parallel_started` | `handlers/parallel.py` |
| `PIPELINE_PARALLEL_BRANCH_STARTED` | `pipeline:parallel_branch_started` | `handlers/parallel.py` |
| `PIPELINE_PARALLEL_BRANCH_COMPLETED` | `pipeline:parallel_branch_completed` | `handlers/parallel.py` |
| `PIPELINE_PARALLEL_COMPLETED` | `pipeline:parallel_completed` | `handlers/parallel.py` |
| `PIPELINE_INTERVIEW_STARTED` | `pipeline:interview_started` | `handlers/human.py` |
| `PIPELINE_INTERVIEW_COMPLETED` | `pipeline:interview_completed` | `handlers/human.py` |
| `PIPELINE_INTERVIEW_TIMEOUT` | `pipeline:interview_timeout` | `handlers/human.py` |
| `PIPELINE_STAGE_RETRYING` | `pipeline:stage_retrying` | `retry.py` |
| `PIPELINE_STAGE_FAILED` | `pipeline:stage_failed` | `retry.py` |
| `PROVIDER_REQUEST` | `provider:request` | (provider modules) |
| `PROVIDER_RESPONSE` | `provider:response` | (provider modules) |
| `PROVIDER_ERROR` | `provider:error` | (provider modules) |

Note: The last 3 (`provider:*`) are defined in `pipeline_events.py` but emitted by provider modules, not the engine. The `pipeline:interview_timeout` is emitted inside `handlers/human.py`. That's 20 events from the attractor engine/handlers, plus 3 provider events = 20 unique pipeline events + 3 provider events. The design doc says "22 events" — we'll subscribe to all 20 `pipeline:*` events plus the 3 `provider:*` events where relevant.

---

## Event Payload Reference

These are the exact `data` dicts emitted by the engine (read from `engine.py`, `retry.py`, `handlers/parallel.py`, `handlers/human.py`):

```python
# pipeline:start
{"graph_name": str, "node_count": int, "edge_count": int, "goal": str}

# pipeline:complete
{"status": str, "total_nodes_executed": int, "duration_ms": float}

# pipeline:node_start
{"node_id": str, "handler_type": str, "attempt": int}

# pipeline:node_complete
{"node_id": str, "status": str, "duration_ms": float}

# pipeline:edge_selected
{"from_node": str, "to_node": str, "edge_label": str}

# pipeline:checkpoint
{"node_id": str, "checkpoint_path": str}

# pipeline:goal_gate_check
{"satisfied": list[str], "unsatisfied": list[str]}

# pipeline:error
{"node_id": str, "error_type": str, "message": str}

# pipeline:parallel_started
{"node_id": str, "branch_count": int}

# pipeline:parallel_branch_started
{"node_id": str, "branch_node_id": str}

# pipeline:parallel_branch_completed
{"node_id": str, "branch_node_id": str, "status": str}

# pipeline:parallel_completed
{"node_id": str, "branch_count": int, "result_count": int}

# pipeline:interview_started
{"node_id": str, "question": str}

# pipeline:interview_completed
{"node_id": str, "answer": str}

# pipeline:interview_timeout
{"node_id": str, "prompt": str, "timeout": bool}

# pipeline:stage_retrying
{"node_id": str, "attempt": int, "max_attempts": int, "delay_ms": float}

# pipeline:stage_failed
{"node_id": str, "attempts": int, "final_status": str}
```

---

## Task 1: Create `hooks-pipeline-observability` module scaffold

**Files:**
- Create: `modules/hooks-pipeline-observability/pyproject.toml`
- Create: `modules/hooks-pipeline-observability/amplifier_module_hooks_pipeline_observability/__init__.py`
- Create: `modules/hooks-pipeline-observability/tests/__init__.py`
- Create: `modules/hooks-pipeline-observability/tests/test_mount.py`

This task creates the module skeleton with a minimal `mount()` function and a test that verifies it's callable.

**Step 1: Create the pyproject.toml**

Create file `modules/hooks-pipeline-observability/pyproject.toml`:

```toml
[project]
name = "amplifier-module-hooks-pipeline-observability"
version = "0.1.0"
description = "Pipeline observability hooks — state aggregator, status bar, and event persistence for Attractor"
license = "MIT"
requires-python = ">=3.11"
authors = [
    { name = "Microsoft MADE:Explorations Team" },
]
dependencies = ["amplifier-core"]

[project.entry-points."amplifier.modules"]
hooks-pipeline-observability = "amplifier_module_hooks_pipeline_observability:mount"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.uv]
package = true

[tool.uv.sources]
amplifier-core = { path = "../../../amplifier-core", editable = true }

[tool.hatch.build.targets.wheel]
packages = ["amplifier_module_hooks_pipeline_observability"]

[tool.hatch.metadata]
allow-direct-references = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--import-mode=importlib"
asyncio_mode = "strict"

[dependency-groups]
dev = [
    "amplifier-core",
    "pytest>=9.0.2",
    "pytest-asyncio>=1.3.0",
]
```

**Step 2: Create the minimal `__init__.py`**

Create file `modules/hooks-pipeline-observability/amplifier_module_hooks_pipeline_observability/__init__.py`:

```python
"""Pipeline observability hooks — state aggregator, status bar, and event persistence."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Amplifier module metadata
__amplifier_module_type__ = "hooks"


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> None:
    """Mount pipeline observability hooks into the Amplifier coordinator."""
    logger.info("Mounted hooks-pipeline-observability")
```

**Step 3: Create tests/__init__.py**

Create file `modules/hooks-pipeline-observability/tests/__init__.py`:

```python
```

(Empty file.)

**Step 4: Write the failing test**

Create file `modules/hooks-pipeline-observability/tests/test_mount.py`:

```python
"""Tests for hooks-pipeline-observability module mount."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from amplifier_module_hooks_pipeline_observability import mount


def test_mount_is_callable():
    """mount() should be importable and callable."""
    assert callable(mount)


@pytest.mark.asyncio(loop_scope="session")
async def test_mount_does_not_crash():
    """mount() should accept a coordinator mock without error."""
    coordinator = MagicMock()
    await mount(coordinator)
```

**Step 5: Initialize the venv and run tests**

```bash
cd modules/hooks-pipeline-observability && uv sync && uv run pytest tests/ -q --tb=short
```

Expected: 2 passed.

**Step 6: Commit**

```bash
git add modules/hooks-pipeline-observability/
git commit -m "feat: scaffold hooks-pipeline-observability module"
```

---

## Task 2: `PipelineRunState` data model — core dataclasses

**Files:**
- Create: `modules/hooks-pipeline-observability/amplifier_module_hooks_pipeline_observability/models.py`
- Create: `modules/hooks-pipeline-observability/tests/test_models.py`

This task creates all the dataclasses from the design doc: `NodeInfo`, `EdgeInfo`, `NodeRun`, `EdgeDecision`, `GoalGateCheck`, `BranchInfo`, `HumanInteraction`, `SupervisorCycle`, and `PipelineRunState`.

**Step 1: Write the failing test**

Create file `modules/hooks-pipeline-observability/tests/test_models.py`:

```python
"""Tests for the PipelineRunState data model."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from amplifier_module_hooks_pipeline_observability.models import (
    BranchInfo,
    EdgeDecision,
    EdgeInfo,
    GoalGateCheck,
    HumanInteraction,
    NodeInfo,
    NodeRun,
    PipelineRunState,
    SupervisorCycle,
)


def test_node_info_construction():
    """NodeInfo can be constructed with required fields."""
    info = NodeInfo(id="plan", label="Plan", shape="box", type="codergen", prompt="Plan the work")
    assert info.id == "plan"
    assert info.shape == "box"


def test_edge_info_construction():
    """EdgeInfo can be constructed with required fields."""
    info = EdgeInfo(from_node="A", to_node="B", label="success", condition="", weight=0)
    assert info.from_node == "A"
    assert info.to_node == "B"


def test_node_run_defaults():
    """NodeRun initializes metric fields to zero."""
    now = datetime.now(timezone.utc)
    run = NodeRun(status="running", attempt=1, started_at=now)
    assert run.llm_calls == 0
    assert run.tokens_in == 0
    assert run.tokens_out == 0
    assert run.tokens_cached == 0
    assert run.completed_at is None
    assert run.duration_ms == 0


def test_edge_decision_construction():
    """EdgeDecision tracks routing decisions."""
    edge = EdgeInfo(from_node="A", to_node="B", label="success", condition="", weight=0)
    decision = EdgeDecision(
        from_node="A",
        evaluated_edges=[{"edge": "A->B", "matched": True}, {"edge": "A->C", "matched": False}],
        selected_edge=edge,
        reason="condition matched",
    )
    assert decision.from_node == "A"
    assert len(decision.evaluated_edges) == 2


def test_goal_gate_check_construction():
    """GoalGateCheck tracks gate satisfaction."""
    now = datetime.now(timezone.utc)
    check = GoalGateCheck(
        timestamp=now,
        satisfied=["validate"],
        unsatisfied=["test"],
        action="retry",
    )
    assert check.action == "retry"
    assert "test" in check.unsatisfied


def test_branch_info_construction():
    """BranchInfo tracks parallel branch execution."""
    now = datetime.now(timezone.utc)
    branch = BranchInfo(
        branch_id="branch-1",
        target_node="impl_a",
        status="success",
        started_at=now,
    )
    assert branch.branch_id == "branch-1"
    assert branch.duration_ms == 0


def test_human_interaction_construction():
    """HumanInteraction tracks human gate interactions."""
    interaction = HumanInteraction(
        node_id="review_gate",
        question="Approve?",
        options=["Yes", "No"],
        selected="Yes",
        wait_time_ms=5000,
    )
    assert interaction.selected == "Yes"


def test_supervisor_cycle_construction():
    """SupervisorCycle tracks manager-supervisor loops."""
    cycle = SupervisorCycle(
        cycle_number=1,
        observation="Code looks good",
        steering_message="Proceed to testing",
        wait_result="completed",
    )
    assert cycle.cycle_number == 1


def test_pipeline_run_state_construction():
    """PipelineRunState can be constructed with minimal fields."""
    state = PipelineRunState(
        pipeline_id="run-001",
        dot_source="digraph { A -> B }",
        goal="Build a widget",
    )
    assert state.status == "pending"
    assert state.current_node is None
    assert state.nodes_completed == 0
    assert state.nodes_total == 0
    assert state.total_llm_calls == 0
    assert state.execution_path == []
    assert state.node_runs == {}


def test_pipeline_run_state_to_dict():
    """PipelineRunState.to_dict() returns a JSON-serializable dictionary."""
    state = PipelineRunState(
        pipeline_id="run-001",
        dot_source="digraph { A -> B }",
        goal="Build a widget",
    )
    d = state.to_dict()
    assert isinstance(d, dict)
    assert d["pipeline_id"] == "run-001"
    assert d["status"] == "pending"
    # Must be JSON-serializable
    json_str = json.dumps(d)
    assert "run-001" in json_str


def test_pipeline_run_state_to_dict_with_datetimes():
    """to_dict() correctly serializes datetime objects to ISO strings."""
    now = datetime.now(timezone.utc)
    state = PipelineRunState(
        pipeline_id="run-002",
        dot_source="digraph { A -> B }",
        goal="Test datetimes",
    )
    node_run = NodeRun(status="success", attempt=1, started_at=now, completed_at=now, duration_ms=1234)
    state.node_runs["A"] = [node_run]
    d = state.to_dict()
    # Must be JSON-serializable even with datetimes
    json_str = json.dumps(d)
    assert "run-002" in json_str
```

**Step 2: Run tests to verify they fail**

```bash
cd modules/hooks-pipeline-observability && uv run pytest tests/test_models.py -q --tb=short
```

Expected: FAIL — `ModuleNotFoundError: No module named 'amplifier_module_hooks_pipeline_observability.models'`

**Step 3: Write the implementation**

Create file `modules/hooks-pipeline-observability/amplifier_module_hooks_pipeline_observability/models.py`:

```python
"""Pipeline observability data model.

The PipelineRunState is the centerpiece of the observability system.
Every consumer reads from it: the status bar hook, the progress hook,
the query tool, and future REST API endpoints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class NodeInfo:
    """Static information about a graph node."""

    id: str
    label: str = ""
    shape: str = "box"
    type: str = ""
    prompt: str = ""


@dataclass
class EdgeInfo:
    """Static information about a graph edge."""

    from_node: str
    to_node: str
    label: str = ""
    condition: str = ""
    weight: int = 0


@dataclass
class NodeRun:
    """A single execution of a node (supports retries — multiple runs per node)."""

    status: str  # "running" | "success" | "fail" | "timeout" | "partial_success"
    attempt: int  # 1-based
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int = 0
    outcome_notes: str | None = None
    llm_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_cached: int = 0


@dataclass
class EdgeDecision:
    """Record of an edge routing decision at a node."""

    from_node: str
    evaluated_edges: list[Any]  # all candidate edges with conditions + match result
    selected_edge: EdgeInfo
    reason: str  # "condition matched" | "weight priority" | "default"


@dataclass
class GoalGateCheck:
    """Record of a goal gate evaluation at an exit node."""

    timestamp: datetime
    satisfied: list[str]  # node IDs that passed
    unsatisfied: list[str]  # node IDs that failed
    action: str  # "complete" | "retry" | "fail"


@dataclass
class BranchInfo:
    """A single branch in a parallel fan-out."""

    branch_id: str
    target_node: str
    status: str  # "pending" | "running" | "success" | "fail"
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int = 0
    outcome_notes: str | None = None


@dataclass
class HumanInteraction:
    """Record of a human gate interaction."""

    node_id: str
    question: str
    options: list[str]
    selected: str
    wait_time_ms: int = 0


@dataclass
class SupervisorCycle:
    """Record of a manager-supervisor observe/steer/wait cycle."""

    cycle_number: int
    observation: str
    steering_message: str
    wait_result: str


@dataclass
class PipelineRunState:
    """Comprehensive pipeline execution state.

    Maintained by the state aggregator hook, updated on every pipeline event.
    This is the centerpiece that every consumer reads from.
    """

    # Identity
    pipeline_id: str
    dot_source: str
    goal: str

    # Graph structure (populated from pipeline:start)
    nodes: dict[str, NodeInfo] = field(default_factory=dict)
    edges: list[EdgeInfo] = field(default_factory=list)

    # Execution progress
    status: str = "pending"  # "pending" | "running" | "complete" | "failed"
    current_node: str | None = None
    execution_path: list[str] = field(default_factory=list)
    branches_taken: list[EdgeInfo] = field(default_factory=list)

    # Per-node execution detail (supports retries/loops — list per node)
    node_runs: dict[str, list[NodeRun]] = field(default_factory=dict)

    # Edge routing decisions (for conditional visualization)
    edge_decisions: list[EdgeDecision] = field(default_factory=list)

    # Loop/retry tracking
    loop_iterations: dict[str, int] = field(default_factory=dict)
    goal_gate_checks: list[GoalGateCheck] = field(default_factory=list)

    # Parallel execution tracking
    parallel_branches: dict[str, list[BranchInfo]] = field(default_factory=dict)

    # Subgraph execution (recursive — for nested DOT subgraphs)
    subgraph_runs: dict[str, Any] = field(default_factory=dict)

    # Human gate interactions
    human_interactions: list[HumanInteraction] = field(default_factory=list)

    # Manager-supervisor cycles
    supervisor_cycles: dict[str, list[SupervisorCycle]] = field(default_factory=dict)

    # Aggregate metrics
    total_elapsed_ms: int = 0
    total_llm_calls: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_tokens_cached: int = 0
    total_tokens_reasoning: int = 0
    nodes_completed: int = 0
    nodes_total: int = 0

    # Per-node timing breakdown
    timing: dict[str, int] = field(default_factory=dict)

    # Error info
    errors: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary.

        Converts datetime objects to ISO format strings.
        Converts dataclass instances to plain dicts recursively.
        """
        return _serialize(self)


def _serialize(obj: Any) -> Any:
    """Recursively serialize dataclass instances and datetimes to JSON-safe types."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "__dataclass_fields__"):
        result = {}
        for field_name in obj.__dataclass_fields__:
            result[field_name] = _serialize(getattr(obj, field_name))
        return result
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    return obj
```

**Step 4: Run tests to verify they pass**

```bash
cd modules/hooks-pipeline-observability && uv run pytest tests/test_models.py -q --tb=short
```

Expected: all passed (12 tests).

**Step 5: Commit**

```bash
cd modules/hooks-pipeline-observability && git add -A
git commit -m "feat: PipelineRunState data model with all supporting dataclasses"
```

---

## Task 3: State aggregator — `pipeline:start` and `pipeline:complete`

**Files:**
- Create: `modules/hooks-pipeline-observability/amplifier_module_hooks_pipeline_observability/aggregator.py`
- Create: `modules/hooks-pipeline-observability/tests/test_aggregator.py`

The state aggregator is a hook class that subscribes to all pipeline events and maintains a `PipelineRunState` in memory. We build it incrementally — this task handles the two lifecycle events.

**Step 1: Write the failing test**

Create file `modules/hooks-pipeline-observability/tests/test_aggregator.py`:

```python
"""Tests for the pipeline state aggregator hook."""

from __future__ import annotations

import pytest

from amplifier_module_hooks_pipeline_observability.aggregator import StateAggregator
from amplifier_module_hooks_pipeline_observability.models import PipelineRunState


@pytest.mark.asyncio(loop_scope="session")
async def test_handle_pipeline_start_creates_state():
    """pipeline:start should create a PipelineRunState with status=running."""
    agg = StateAggregator()
    assert agg.state is None

    await agg.handle_pipeline_start("pipeline:start", {
        "graph_name": "test-graph",
        "node_count": 3,
        "edge_count": 2,
        "goal": "Build a thing",
    })

    assert agg.state is not None
    assert agg.state.status == "running"
    assert agg.state.goal == "Build a thing"
    assert agg.state.nodes_total == 3
    assert agg.state.pipeline_id == "test-graph"


@pytest.mark.asyncio(loop_scope="session")
async def test_handle_pipeline_complete_sets_status():
    """pipeline:complete should set status and total_elapsed_ms."""
    agg = StateAggregator()
    await agg.handle_pipeline_start("pipeline:start", {
        "graph_name": "g",
        "node_count": 2,
        "edge_count": 1,
        "goal": "test",
    })

    await agg.handle_pipeline_complete("pipeline:complete", {
        "status": "success",
        "total_nodes_executed": 2,
        "duration_ms": 5432.1,
    })

    assert agg.state.status == "complete"
    assert agg.state.total_elapsed_ms == 5432
    assert agg.state.nodes_completed == 2


@pytest.mark.asyncio(loop_scope="session")
async def test_handle_pipeline_complete_failed():
    """pipeline:complete with fail status should set status=failed."""
    agg = StateAggregator()
    await agg.handle_pipeline_start("pipeline:start", {
        "graph_name": "g",
        "node_count": 1,
        "edge_count": 0,
        "goal": "test",
    })

    await agg.handle_pipeline_complete("pipeline:complete", {
        "status": "fail",
        "total_nodes_executed": 0,
        "duration_ms": 100.0,
    })

    assert agg.state.status == "failed"


@pytest.mark.asyncio(loop_scope="session")
async def test_get_state_returns_none_before_start():
    """get_state() returns None before any pipeline has started."""
    agg = StateAggregator()
    assert agg.get_state() is None


@pytest.mark.asyncio(loop_scope="session")
async def test_get_state_returns_state_after_start():
    """get_state() returns the current PipelineRunState."""
    agg = StateAggregator()
    await agg.handle_pipeline_start("pipeline:start", {
        "graph_name": "g",
        "node_count": 1,
        "edge_count": 0,
        "goal": "test",
    })
    state = agg.get_state()
    assert isinstance(state, PipelineRunState)
    assert state.status == "running"
```

**Step 2: Run tests to verify they fail**

```bash
cd modules/hooks-pipeline-observability && uv run pytest tests/test_aggregator.py -q --tb=short
```

Expected: FAIL — `ModuleNotFoundError: No module named 'amplifier_module_hooks_pipeline_observability.aggregator'`

**Step 3: Write the implementation**

Create file `modules/hooks-pipeline-observability/amplifier_module_hooks_pipeline_observability/aggregator.py`:

```python
"""Pipeline state aggregator hook.

Subscribes to all pipeline events and maintains a comprehensive
PipelineRunState in memory. Registered on the ``pipeline.state``
contribution channel so other components can query it.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from .models import (
    BranchInfo,
    EdgeDecision,
    EdgeInfo,
    GoalGateCheck,
    HumanInteraction,
    NodeRun,
    PipelineRunState,
)

logger = logging.getLogger(__name__)


class StateAggregator:
    """Maintains a PipelineRunState from pipeline event stream.

    Each handler method corresponds to one pipeline event.
    The state is available via ``get_state()`` or the contribution channel.
    """

    def __init__(self) -> None:
        self.state: PipelineRunState | None = None
        self._pipeline_start_time: float | None = None
        self._node_start_times: dict[str, float] = {}

    def get_state(self) -> PipelineRunState | None:
        """Return the current pipeline state, or None if no pipeline has started."""
        return self.state

    # -- Pipeline lifecycle ------------------------------------------------

    async def handle_pipeline_start(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:start — create the PipelineRunState."""
        self._pipeline_start_time = time.monotonic()
        self.state = PipelineRunState(
            pipeline_id=data.get("graph_name", "unknown"),
            dot_source="",  # populated later if available
            goal=data.get("goal", ""),
            status="running",
            nodes_total=data.get("node_count", 0),
        )

    async def handle_pipeline_complete(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:complete — finalize the PipelineRunState."""
        if self.state is None:
            return
        status = data.get("status", "success")
        self.state.status = "failed" if status == "fail" else "complete"
        self.state.total_elapsed_ms = int(data.get("duration_ms", 0))
        self.state.nodes_completed = data.get("total_nodes_executed", self.state.nodes_completed)

    # -- Node lifecycle ----------------------------------------------------

    async def handle_node_start(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:node_start — record node execution start."""
        if self.state is None:
            return
        node_id = data.get("node_id", "")
        self.state.current_node = node_id
        self._node_start_times[node_id] = time.monotonic()

        now = datetime.now(timezone.utc)
        attempt = data.get("attempt", 1)
        run = NodeRun(status="running", attempt=attempt, started_at=now)
        self.state.node_runs.setdefault(node_id, []).append(run)

        if node_id not in self.state.execution_path:
            self.state.execution_path.append(node_id)

    async def handle_node_complete(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:node_complete — record node execution result."""
        if self.state is None:
            return
        node_id = data.get("node_id", "")
        status = data.get("status", "success")
        duration_ms = int(data.get("duration_ms", 0))

        # Update the most recent NodeRun for this node
        runs = self.state.node_runs.get(node_id, [])
        if runs:
            current_run = runs[-1]
            current_run.status = status
            current_run.completed_at = datetime.now(timezone.utc)
            current_run.duration_ms = duration_ms

        self.state.nodes_completed += 1
        self.state.timing[node_id] = self.state.timing.get(node_id, 0) + duration_ms
        self.state.current_node = None

    # -- Edge routing ------------------------------------------------------

    async def handle_edge_selected(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:edge_selected — record routing decision."""
        if self.state is None:
            return
        edge = EdgeInfo(
            from_node=data.get("from_node", ""),
            to_node=data.get("to_node", ""),
            label=data.get("edge_label", ""),
        )
        self.state.branches_taken.append(edge)

    # -- Checkpoint --------------------------------------------------------

    async def handle_checkpoint(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:checkpoint — no state change needed, just acknowledgment."""
        pass

    # -- Goal gates --------------------------------------------------------

    async def handle_goal_gate_check(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:goal_gate_check — record gate evaluation."""
        if self.state is None:
            return
        satisfied = data.get("satisfied", [])
        unsatisfied = data.get("unsatisfied", [])
        action = "complete" if not unsatisfied else "retry"

        check = GoalGateCheck(
            timestamp=datetime.now(timezone.utc),
            satisfied=satisfied,
            unsatisfied=unsatisfied,
            action=action,
        )
        self.state.goal_gate_checks.append(check)

    # -- Errors ------------------------------------------------------------

    async def handle_error(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:error — record error."""
        if self.state is None:
            return
        self.state.errors.append({
            "node_id": data.get("node_id", ""),
            "error_type": data.get("error_type", ""),
            "message": data.get("message", ""),
        })

    # -- Parallel execution ------------------------------------------------

    async def handle_parallel_started(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:parallel_started — initialize parallel tracking."""
        if self.state is None:
            return
        node_id = data.get("node_id", "")
        self.state.parallel_branches[node_id] = []

    async def handle_parallel_branch_started(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:parallel_branch_started — record branch start."""
        if self.state is None:
            return
        node_id = data.get("node_id", "")
        branch_node_id = data.get("branch_node_id", "")
        now = datetime.now(timezone.utc)
        branch = BranchInfo(
            branch_id=branch_node_id,
            target_node=branch_node_id,
            status="running",
            started_at=now,
        )
        self.state.parallel_branches.setdefault(node_id, []).append(branch)

    async def handle_parallel_branch_completed(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:parallel_branch_completed — record branch result."""
        if self.state is None:
            return
        node_id = data.get("node_id", "")
        branch_node_id = data.get("branch_node_id", "")
        status = data.get("status", "success")

        branches = self.state.parallel_branches.get(node_id, [])
        for branch in branches:
            if branch.branch_id == branch_node_id:
                branch.status = status
                branch.completed_at = datetime.now(timezone.utc)
                break

    async def handle_parallel_completed(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:parallel_completed — no additional state change needed."""
        pass

    # -- Human interaction -------------------------------------------------

    async def handle_interview_started(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:interview_started — record start of interaction."""
        pass  # We record the full interaction on completion

    async def handle_interview_completed(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:interview_completed — record interaction result."""
        if self.state is None:
            return
        interaction = HumanInteraction(
            node_id=data.get("node_id", ""),
            question="",
            options=[],
            selected=data.get("answer", ""),
        )
        self.state.human_interactions.append(interaction)

    async def handle_interview_timeout(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:interview_timeout — record timeout."""
        if self.state is None:
            return
        interaction = HumanInteraction(
            node_id=data.get("node_id", ""),
            question=data.get("prompt", ""),
            options=[],
            selected="TIMEOUT",
            wait_time_ms=0,
        )
        self.state.human_interactions.append(interaction)

    # -- Retry lifecycle ---------------------------------------------------

    async def handle_stage_retrying(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:stage_retrying — increment loop iteration count."""
        if self.state is None:
            return
        node_id = data.get("node_id", "")
        self.state.loop_iterations[node_id] = self.state.loop_iterations.get(node_id, 0) + 1

    async def handle_stage_failed(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:stage_failed — record retry exhaustion."""
        if self.state is None:
            return
        node_id = data.get("node_id", "")
        self.state.errors.append({
            "node_id": node_id,
            "error_type": "retries_exhausted",
            "message": f"Node '{node_id}' exhausted {data.get('attempts', 0)} attempts",
        })
```

**Step 4: Run tests to verify they pass**

```bash
cd modules/hooks-pipeline-observability && uv run pytest tests/test_aggregator.py -q --tb=short
```

Expected: 5 passed.

**Step 5: Commit**

```bash
cd modules/hooks-pipeline-observability && git add -A
git commit -m "feat: state aggregator with pipeline lifecycle event handlers"
```

---

## Task 4: State aggregator — node, edge, retry, parallel, interview, error events

**Files:**
- Modify: `modules/hooks-pipeline-observability/tests/test_aggregator.py`

This task adds tests for all remaining event handlers that were implemented in Task 3.

**Step 1: Append tests to the existing test file**

Add to end of `modules/hooks-pipeline-observability/tests/test_aggregator.py`:

```python


# -- Node lifecycle tests --------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_handle_node_start_tracks_current_node():
    """pipeline:node_start sets current_node and creates a NodeRun."""
    agg = StateAggregator()
    await agg.handle_pipeline_start("pipeline:start", {
        "graph_name": "g", "node_count": 2, "edge_count": 1, "goal": "test",
    })

    await agg.handle_node_start("pipeline:node_start", {
        "node_id": "plan", "handler_type": "codergen", "attempt": 1,
    })

    assert agg.state.current_node == "plan"
    assert "plan" in agg.state.node_runs
    assert len(agg.state.node_runs["plan"]) == 1
    assert agg.state.node_runs["plan"][0].status == "running"
    assert agg.state.node_runs["plan"][0].attempt == 1
    assert "plan" in agg.state.execution_path


@pytest.mark.asyncio(loop_scope="session")
async def test_handle_node_complete_updates_run():
    """pipeline:node_complete updates the NodeRun and increments nodes_completed."""
    agg = StateAggregator()
    await agg.handle_pipeline_start("pipeline:start", {
        "graph_name": "g", "node_count": 2, "edge_count": 1, "goal": "test",
    })
    await agg.handle_node_start("pipeline:node_start", {
        "node_id": "plan", "handler_type": "codergen", "attempt": 1,
    })

    await agg.handle_node_complete("pipeline:node_complete", {
        "node_id": "plan", "status": "success", "duration_ms": 1500.0,
    })

    assert agg.state.nodes_completed == 1
    assert agg.state.current_node is None
    run = agg.state.node_runs["plan"][0]
    assert run.status == "success"
    assert run.duration_ms == 1500
    assert run.completed_at is not None
    assert agg.state.timing["plan"] == 1500


# -- Edge routing tests ----------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_handle_edge_selected_records_edge():
    """pipeline:edge_selected records the taken edge."""
    agg = StateAggregator()
    await agg.handle_pipeline_start("pipeline:start", {
        "graph_name": "g", "node_count": 2, "edge_count": 1, "goal": "test",
    })

    await agg.handle_edge_selected("pipeline:edge_selected", {
        "from_node": "plan", "to_node": "impl", "edge_label": "success",
    })

    assert len(agg.state.branches_taken) == 1
    assert agg.state.branches_taken[0].from_node == "plan"
    assert agg.state.branches_taken[0].to_node == "impl"


# -- Goal gate tests -------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_handle_goal_gate_check_records_check():
    """pipeline:goal_gate_check records gate evaluation."""
    agg = StateAggregator()
    await agg.handle_pipeline_start("pipeline:start", {
        "graph_name": "g", "node_count": 2, "edge_count": 1, "goal": "test",
    })

    await agg.handle_goal_gate_check("pipeline:goal_gate_check", {
        "satisfied": ["validate"], "unsatisfied": ["test"],
    })

    assert len(agg.state.goal_gate_checks) == 1
    check = agg.state.goal_gate_checks[0]
    assert check.satisfied == ["validate"]
    assert check.unsatisfied == ["test"]
    assert check.action == "retry"


@pytest.mark.asyncio(loop_scope="session")
async def test_handle_goal_gate_all_satisfied():
    """pipeline:goal_gate_check with empty unsatisfied sets action=complete."""
    agg = StateAggregator()
    await agg.handle_pipeline_start("pipeline:start", {
        "graph_name": "g", "node_count": 1, "edge_count": 0, "goal": "test",
    })

    await agg.handle_goal_gate_check("pipeline:goal_gate_check", {
        "satisfied": ["validate", "test"], "unsatisfied": [],
    })

    assert agg.state.goal_gate_checks[0].action == "complete"


# -- Error tests -----------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_handle_error_records_error():
    """pipeline:error records the error details."""
    agg = StateAggregator()
    await agg.handle_pipeline_start("pipeline:start", {
        "graph_name": "g", "node_count": 1, "edge_count": 0, "goal": "test",
    })

    await agg.handle_error("pipeline:error", {
        "node_id": "plan", "error_type": "no_matching_edge", "message": "No edge from plan",
    })

    assert len(agg.state.errors) == 1
    assert agg.state.errors[0]["error_type"] == "no_matching_edge"


# -- Parallel execution tests ----------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_parallel_lifecycle():
    """Full parallel lifecycle: started -> branch_started -> branch_completed -> completed."""
    agg = StateAggregator()
    await agg.handle_pipeline_start("pipeline:start", {
        "graph_name": "g", "node_count": 4, "edge_count": 3, "goal": "test",
    })

    await agg.handle_parallel_started("pipeline:parallel_started", {
        "node_id": "fan_out", "branch_count": 2,
    })
    assert "fan_out" in agg.state.parallel_branches

    await agg.handle_parallel_branch_started("pipeline:parallel_branch_started", {
        "node_id": "fan_out", "branch_node_id": "branch_a",
    })
    await agg.handle_parallel_branch_started("pipeline:parallel_branch_started", {
        "node_id": "fan_out", "branch_node_id": "branch_b",
    })
    assert len(agg.state.parallel_branches["fan_out"]) == 2
    assert agg.state.parallel_branches["fan_out"][0].status == "running"

    await agg.handle_parallel_branch_completed("pipeline:parallel_branch_completed", {
        "node_id": "fan_out", "branch_node_id": "branch_a", "status": "success",
    })
    assert agg.state.parallel_branches["fan_out"][0].status == "success"
    assert agg.state.parallel_branches["fan_out"][0].completed_at is not None

    await agg.handle_parallel_completed("pipeline:parallel_completed", {
        "node_id": "fan_out", "branch_count": 2, "result_count": 2,
    })


# -- Human interaction tests -----------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_handle_interview_completed():
    """pipeline:interview_completed records the interaction."""
    agg = StateAggregator()
    await agg.handle_pipeline_start("pipeline:start", {
        "graph_name": "g", "node_count": 1, "edge_count": 0, "goal": "test",
    })

    await agg.handle_interview_completed("pipeline:interview_completed", {
        "node_id": "gate", "answer": "Yes",
    })

    assert len(agg.state.human_interactions) == 1
    assert agg.state.human_interactions[0].selected == "Yes"


@pytest.mark.asyncio(loop_scope="session")
async def test_handle_interview_timeout():
    """pipeline:interview_timeout records a timeout interaction."""
    agg = StateAggregator()
    await agg.handle_pipeline_start("pipeline:start", {
        "graph_name": "g", "node_count": 1, "edge_count": 0, "goal": "test",
    })

    await agg.handle_interview_timeout("pipeline:interview_timeout", {
        "node_id": "gate", "prompt": "Approve?", "timeout": True,
    })

    assert len(agg.state.human_interactions) == 1
    assert agg.state.human_interactions[0].selected == "TIMEOUT"


# -- Retry lifecycle tests -------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_handle_stage_retrying_increments_counter():
    """pipeline:stage_retrying increments loop_iterations."""
    agg = StateAggregator()
    await agg.handle_pipeline_start("pipeline:start", {
        "graph_name": "g", "node_count": 1, "edge_count": 0, "goal": "test",
    })

    await agg.handle_stage_retrying("pipeline:stage_retrying", {
        "node_id": "validate", "attempt": 1, "max_attempts": 3, "delay_ms": 200,
    })
    assert agg.state.loop_iterations["validate"] == 1

    await agg.handle_stage_retrying("pipeline:stage_retrying", {
        "node_id": "validate", "attempt": 2, "max_attempts": 3, "delay_ms": 400,
    })
    assert agg.state.loop_iterations["validate"] == 2


@pytest.mark.asyncio(loop_scope="session")
async def test_handle_stage_failed_records_error():
    """pipeline:stage_failed records a retries_exhausted error."""
    agg = StateAggregator()
    await agg.handle_pipeline_start("pipeline:start", {
        "graph_name": "g", "node_count": 1, "edge_count": 0, "goal": "test",
    })

    await agg.handle_stage_failed("pipeline:stage_failed", {
        "node_id": "validate", "attempts": 3, "final_status": "fail",
    })

    assert len(agg.state.errors) == 1
    assert agg.state.errors[0]["error_type"] == "retries_exhausted"


# -- Resilience tests ------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_handlers_safe_before_start():
    """All handlers should be no-ops (not crash) when called before pipeline:start."""
    agg = StateAggregator()
    # None of these should raise
    await agg.handle_node_start("pipeline:node_start", {"node_id": "x", "handler_type": "y", "attempt": 1})
    await agg.handle_node_complete("pipeline:node_complete", {"node_id": "x", "status": "success", "duration_ms": 0})
    await agg.handle_edge_selected("pipeline:edge_selected", {"from_node": "a", "to_node": "b", "edge_label": ""})
    await agg.handle_goal_gate_check("pipeline:goal_gate_check", {"satisfied": [], "unsatisfied": []})
    await agg.handle_error("pipeline:error", {"node_id": "x", "error_type": "test", "message": "test"})
    await agg.handle_parallel_started("pipeline:parallel_started", {"node_id": "x", "branch_count": 0})
    await agg.handle_parallel_branch_started("pipeline:parallel_branch_started", {"node_id": "x", "branch_node_id": "y"})
    await agg.handle_parallel_branch_completed("pipeline:parallel_branch_completed", {"node_id": "x", "branch_node_id": "y", "status": "success"})
    await agg.handle_interview_completed("pipeline:interview_completed", {"node_id": "x", "answer": "y"})
    await agg.handle_stage_retrying("pipeline:stage_retrying", {"node_id": "x", "attempt": 1, "max_attempts": 3, "delay_ms": 100})
    await agg.handle_stage_failed("pipeline:stage_failed", {"node_id": "x", "attempts": 3, "final_status": "fail"})
    assert agg.state is None  # Still None — nothing crashed
```

**Step 2: Run tests**

```bash
cd modules/hooks-pipeline-observability && uv run pytest tests/test_aggregator.py -q --tb=short
```

Expected: all passed (20 tests total).

**Step 3: Commit**

```bash
cd modules/hooks-pipeline-observability && git add -A
git commit -m "test: comprehensive aggregator tests for all event handlers"
```

---

## Task 5: Wire aggregator into `mount()` with contribution channel

**Files:**
- Modify: `modules/hooks-pipeline-observability/amplifier_module_hooks_pipeline_observability/__init__.py`
- Modify: `modules/hooks-pipeline-observability/tests/test_mount.py`

This task wires the aggregator into the module's `mount()` function: registers all event handlers with the hooks system and registers the `pipeline.state` contribution channel + `observability.events` for event persistence (Layer 3).

**Step 1: Write the failing test**

Replace the entire contents of `modules/hooks-pipeline-observability/tests/test_mount.py`:

```python
"""Tests for hooks-pipeline-observability module mount."""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from amplifier_module_hooks_pipeline_observability import mount


def test_mount_is_callable():
    """mount() should be importable and callable."""
    assert callable(mount)


@pytest.mark.asyncio(loop_scope="session")
async def test_mount_registers_all_pipeline_hooks():
    """mount() should register handlers for all pipeline events."""
    hooks_mock = MagicMock()
    coordinator = MagicMock()
    coordinator.get.return_value = hooks_mock

    await mount(coordinator)

    coordinator.get.assert_called_with("hooks")

    # Collect all registered event names
    registered_events = [c.args[0] for c in hooks_mock.register.call_args_list]

    # All 17 pipeline events must be registered
    expected_events = [
        "pipeline:start",
        "pipeline:complete",
        "pipeline:node_start",
        "pipeline:node_complete",
        "pipeline:edge_selected",
        "pipeline:checkpoint",
        "pipeline:goal_gate_check",
        "pipeline:error",
        "pipeline:parallel_started",
        "pipeline:parallel_branch_started",
        "pipeline:parallel_branch_completed",
        "pipeline:parallel_completed",
        "pipeline:interview_started",
        "pipeline:interview_completed",
        "pipeline:interview_timeout",
        "pipeline:stage_retrying",
        "pipeline:stage_failed",
    ]
    for event in expected_events:
        assert event in registered_events, f"Missing handler for {event}"


@pytest.mark.asyncio(loop_scope="session")
async def test_mount_registers_pipeline_state_contribution():
    """mount() should register a pipeline.state contribution channel."""
    hooks_mock = MagicMock()
    coordinator = MagicMock()
    coordinator.get.return_value = hooks_mock

    await mount(coordinator)

    # Check that register_contributor was called with "pipeline.state"
    contrib_calls = coordinator.register_contributor.call_args_list
    channel_names = [c.args[0] for c in contrib_calls]
    assert "pipeline.state" in channel_names


@pytest.mark.asyncio(loop_scope="session")
async def test_mount_registers_observability_events():
    """mount() should register pipeline events on the observability.events channel."""
    hooks_mock = MagicMock()
    coordinator = MagicMock()
    coordinator.get.return_value = hooks_mock

    await mount(coordinator)

    contrib_calls = coordinator.register_contributor.call_args_list
    channel_names = [c.args[0] for c in contrib_calls]
    assert "observability.events" in channel_names
```

**Step 2: Run tests to verify they fail**

```bash
cd modules/hooks-pipeline-observability && uv run pytest tests/test_mount.py -q --tb=short
```

Expected: 3 of 4 FAIL (the new tests fail because `mount()` doesn't register hooks yet).

**Step 3: Update the implementation**

Replace the contents of `modules/hooks-pipeline-observability/amplifier_module_hooks_pipeline_observability/__init__.py`:

```python
"""Pipeline observability hooks — state aggregator, status bar, and event persistence."""

from __future__ import annotations

import logging
from typing import Any

from .aggregator import StateAggregator
from .status_bar import StatusBarHook

logger = logging.getLogger(__name__)

# Amplifier module metadata
__amplifier_module_type__ = "hooks"

# All pipeline events this module subscribes to
_PIPELINE_EVENTS = [
    "pipeline:start",
    "pipeline:complete",
    "pipeline:node_start",
    "pipeline:node_complete",
    "pipeline:edge_selected",
    "pipeline:checkpoint",
    "pipeline:goal_gate_check",
    "pipeline:error",
    "pipeline:parallel_started",
    "pipeline:parallel_branch_started",
    "pipeline:parallel_branch_completed",
    "pipeline:parallel_completed",
    "pipeline:interview_started",
    "pipeline:interview_completed",
    "pipeline:interview_timeout",
    "pipeline:stage_retrying",
    "pipeline:stage_failed",
]

# Map event names to StateAggregator handler method names
_AGGREGATOR_HANDLER_MAP: dict[str, str] = {
    "pipeline:start": "handle_pipeline_start",
    "pipeline:complete": "handle_pipeline_complete",
    "pipeline:node_start": "handle_node_start",
    "pipeline:node_complete": "handle_node_complete",
    "pipeline:edge_selected": "handle_edge_selected",
    "pipeline:checkpoint": "handle_checkpoint",
    "pipeline:goal_gate_check": "handle_goal_gate_check",
    "pipeline:error": "handle_error",
    "pipeline:parallel_started": "handle_parallel_started",
    "pipeline:parallel_branch_started": "handle_parallel_branch_started",
    "pipeline:parallel_branch_completed": "handle_parallel_branch_completed",
    "pipeline:parallel_completed": "handle_parallel_completed",
    "pipeline:interview_started": "handle_interview_started",
    "pipeline:interview_completed": "handle_interview_completed",
    "pipeline:interview_timeout": "handle_interview_timeout",
    "pipeline:stage_retrying": "handle_stage_retrying",
    "pipeline:stage_failed": "handle_stage_failed",
}

# Map event names to StatusBarHook handler method names
_STATUS_BAR_HANDLER_MAP: dict[str, str] = {
    "pipeline:start": "handle_pipeline_start",
    "pipeline:complete": "handle_pipeline_complete",
    "pipeline:node_start": "handle_node_start",
    "pipeline:node_complete": "handle_node_complete",
}


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> None:
    """Mount pipeline observability hooks into the Amplifier coordinator.

    Registers:
    1. StateAggregator — subscribes to all 17 pipeline events, maintains PipelineRunState
    2. StatusBarHook — subscribes to key events, provides system-reminder context injection
    3. pipeline.state contribution channel — makes state queryable
    4. observability.events contribution — ensures pipeline events land in events.jsonl
    """
    hooks = coordinator.get("hooks")
    aggregator = StateAggregator()
    status_bar = StatusBarHook(aggregator)

    # Register aggregator handlers for all pipeline events
    for event_name, handler_name in _AGGREGATOR_HANDLER_MAP.items():
        handler = getattr(aggregator, handler_name)
        hooks.register(event_name, handler, name="pipeline-observability")

    # Register status bar handlers for key events
    for event_name, handler_name in _STATUS_BAR_HANDLER_MAP.items():
        handler = getattr(status_bar, handler_name)
        hooks.register(event_name, handler, name="pipeline-status-bar")

    # Layer 5: Register pipeline.state contribution channel
    coordinator.register_contributor(
        "pipeline.state",
        "hooks-pipeline-observability",
        aggregator.get_state,
    )

    # Layer 3: Register pipeline events for observability.events discovery
    coordinator.register_contributor(
        "observability.events",
        "hooks-pipeline-observability",
        lambda: _PIPELINE_EVENTS,
    )

    logger.info("Mounted hooks-pipeline-observability (aggregator + status bar + event persistence)")
```

**Step 4: Create the status_bar.py stub** (we'll fill it in Task 6)

Create file `modules/hooks-pipeline-observability/amplifier_module_hooks_pipeline_observability/status_bar.py`:

```python
"""Pipeline status bar hook — context injection as system-reminder.

Provides a lightweight, always-visible pipeline progress summary
in the agent's session context, similar to the todo hook reminder.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class StatusBarHook:
    """Generates a system-reminder string showing pipeline progress.

    Reads state from the StateAggregator (passed at construction)
    and formats a compact summary.
    """

    def __init__(self, aggregator: Any) -> None:
        self._aggregator = aggregator

    async def handle_pipeline_start(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:start for status bar."""
        pass

    async def handle_pipeline_complete(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:complete for status bar."""
        pass

    async def handle_node_start(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:node_start for status bar."""
        pass

    async def handle_node_complete(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:node_complete for status bar."""
        pass
```

**Step 5: Run all tests**

```bash
cd modules/hooks-pipeline-observability && uv run pytest tests/ -q --tb=short
```

Expected: all passed.

**Step 6: Commit**

```bash
cd modules/hooks-pipeline-observability && git add -A
git commit -m "feat: wire aggregator into mount with contribution channels and event persistence"
```

---

## Task 6: Status bar hook (Layer 2) — context injection

**Files:**
- Modify: `modules/hooks-pipeline-observability/amplifier_module_hooks_pipeline_observability/status_bar.py`
- Create: `modules/hooks-pipeline-observability/tests/test_status_bar.py`

The status bar hook reads from the aggregator and formats a compact `system-reminder` string. This is the "always visible" progress bar.

**Step 1: Write the failing test**

Create file `modules/hooks-pipeline-observability/tests/test_status_bar.py`:

```python
"""Tests for the pipeline status bar hook."""

from __future__ import annotations

import pytest

from amplifier_module_hooks_pipeline_observability.aggregator import StateAggregator
from amplifier_module_hooks_pipeline_observability.status_bar import StatusBarHook


@pytest.mark.asyncio(loop_scope="session")
async def test_format_status_before_start():
    """format_status() returns empty string before any pipeline starts."""
    agg = StateAggregator()
    bar = StatusBarHook(agg)
    assert bar.format_status() == ""


@pytest.mark.asyncio(loop_scope="session")
async def test_format_status_during_run():
    """format_status() shows running state with current node."""
    agg = StateAggregator()
    bar = StatusBarHook(agg)

    await agg.handle_pipeline_start("pipeline:start", {
        "graph_name": "my-pipeline", "node_count": 3, "edge_count": 2, "goal": "Build widget",
    })
    await agg.handle_node_start("pipeline:node_start", {
        "node_id": "plan", "handler_type": "codergen", "attempt": 1,
    })

    status = bar.format_status()
    assert "my-pipeline" in status
    assert "running" in status.lower()
    assert "plan" in status
    assert "1/3" in status  # node progress


@pytest.mark.asyncio(loop_scope="session")
async def test_format_status_after_node_complete():
    """format_status() shows completed nodes."""
    agg = StateAggregator()
    bar = StatusBarHook(agg)

    await agg.handle_pipeline_start("pipeline:start", {
        "graph_name": "my-pipeline", "node_count": 3, "edge_count": 2, "goal": "Build widget",
    })
    await agg.handle_node_start("pipeline:node_start", {
        "node_id": "plan", "handler_type": "codergen", "attempt": 1,
    })
    await agg.handle_node_complete("pipeline:node_complete", {
        "node_id": "plan", "status": "success", "duration_ms": 2500,
    })

    status = bar.format_status()
    assert "plan" in status
    assert "success" in status.lower()


@pytest.mark.asyncio(loop_scope="session")
async def test_format_status_after_complete():
    """format_status() shows completion status."""
    agg = StateAggregator()
    bar = StatusBarHook(agg)

    await agg.handle_pipeline_start("pipeline:start", {
        "graph_name": "my-pipeline", "node_count": 2, "edge_count": 1, "goal": "test",
    })
    await agg.handle_node_start("pipeline:node_start", {
        "node_id": "A", "handler_type": "codergen", "attempt": 1,
    })
    await agg.handle_node_complete("pipeline:node_complete", {
        "node_id": "A", "status": "success", "duration_ms": 1000,
    })
    await agg.handle_pipeline_complete("pipeline:complete", {
        "status": "success", "total_nodes_executed": 1, "duration_ms": 1234,
    })

    status = bar.format_status()
    assert "complete" in status.lower()


@pytest.mark.asyncio(loop_scope="session")
async def test_format_status_fits_in_6_lines():
    """format_status() output should be compact (<=6 lines)."""
    agg = StateAggregator()
    bar = StatusBarHook(agg)

    await agg.handle_pipeline_start("pipeline:start", {
        "graph_name": "complex-pipeline", "node_count": 10, "edge_count": 12, "goal": "Big task",
    })
    await agg.handle_node_start("pipeline:node_start", {
        "node_id": "step_1", "handler_type": "codergen", "attempt": 1,
    })
    await agg.handle_node_complete("pipeline:node_complete", {
        "node_id": "step_1", "status": "success", "duration_ms": 3000,
    })
    await agg.handle_node_start("pipeline:node_start", {
        "node_id": "step_2", "handler_type": "conditional", "attempt": 1,
    })

    status = bar.format_status()
    lines = [line for line in status.strip().split("\n") if line.strip()]
    assert len(lines) <= 6, f"Status bar too long ({len(lines)} lines): {status}"
```

**Step 2: Run tests to verify they fail**

```bash
cd modules/hooks-pipeline-observability && uv run pytest tests/test_status_bar.py -q --tb=short
```

Expected: FAIL — `format_status` returns empty string for all cases.

**Step 3: Update the implementation**

Replace `modules/hooks-pipeline-observability/amplifier_module_hooks_pipeline_observability/status_bar.py`:

```python
"""Pipeline status bar hook — context injection as system-reminder.

Provides a lightweight, always-visible pipeline progress summary
in the agent's session context, similar to the todo hook reminder.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class StatusBarHook:
    """Generates a system-reminder string showing pipeline progress.

    Reads state from the StateAggregator (passed at construction)
    and formats a compact summary (max 6 lines).
    """

    def __init__(self, aggregator: Any) -> None:
        self._aggregator = aggregator

    def format_status(self) -> str:
        """Format the current pipeline state as a compact status string.

        Returns empty string if no pipeline is running.
        """
        state = self._aggregator.get_state()
        if state is None:
            return ""

        lines: list[str] = []

        # Line 1: Pipeline identity and status
        lines.append(f"Pipeline: {state.pipeline_id}")

        # Line 2: Status with current node or completion info
        if state.status == "running":
            node_progress = f"Node {state.nodes_completed + 1}/{state.nodes_total}"
            current = f": {state.current_node}" if state.current_node else ""
            elapsed = f" | {state.total_elapsed_ms / 1000:.1f}s" if state.total_elapsed_ms else ""
            lines.append(f"Status: running | {node_progress}{current}{elapsed}")
        elif state.status in ("complete", "failed"):
            elapsed = f"{state.total_elapsed_ms / 1000:.1f}s" if state.total_elapsed_ms else "0s"
            lines.append(f"Status: {state.status} | {state.nodes_completed} nodes | {elapsed}")
        else:
            lines.append(f"Status: {state.status}")

        # Line 3: Completed nodes summary (compact)
        completed = []
        for node_id, runs in state.node_runs.items():
            if runs and runs[-1].status not in ("running",):
                duration = f", {runs[-1].duration_ms / 1000:.1f}s" if runs[-1].duration_ms else ""
                completed.append(f"{node_id} ({runs[-1].status}{duration})")
        if completed:
            lines.append(f"Completed: {', '.join(completed)}")

        # Line 4: Current node detail
        if state.current_node and state.status == "running":
            runs = state.node_runs.get(state.current_node, [])
            attempt_info = ""
            if runs and runs[-1].attempt > 1:
                attempt_info = f" (attempt {runs[-1].attempt})"
            lines.append(f"Current: {state.current_node}{attempt_info}")

        # Line 5: Metrics
        if state.total_llm_calls or state.total_tokens_in or state.total_tokens_out:
            tokens = state.total_tokens_in + state.total_tokens_out
            cached = f" ({state.total_tokens_cached} cached)" if state.total_tokens_cached else ""
            lines.append(f"Tokens: {tokens}{cached} across {state.total_llm_calls} LLM calls")

        # Line 6: Errors if any
        if state.errors:
            lines.append(f"Errors: {len(state.errors)}")

        return "\n".join(lines)

    # -- Event handlers (update is implicit via aggregator) ----------------
    # These exist so mount() can register them, but the real state updates
    # happen in the StateAggregator. The status bar just re-reads on format.

    async def handle_pipeline_start(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:start for status bar."""
        pass

    async def handle_pipeline_complete(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:complete for status bar."""
        pass

    async def handle_node_start(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:node_start for status bar."""
        pass

    async def handle_node_complete(self, event: str, data: dict[str, Any]) -> None:
        """Handle pipeline:node_complete for status bar."""
        pass
```

**Step 4: Run tests**

```bash
cd modules/hooks-pipeline-observability && uv run pytest tests/test_status_bar.py -q --tb=short
```

Expected: all passed (5 tests).

**Step 5: Commit**

```bash
cd modules/hooks-pipeline-observability && git add -A
git commit -m "feat: status bar hook with compact context injection formatting"
```

---

## Task 7: Enhanced progress hook (Layer 1) — upgrade to all events

**Files:**
- Modify: `modules/hooks-pipeline-progress/amplifier_module_hooks_pipeline_progress/__init__.py`
- Modify: `modules/hooks-pipeline-progress/tests/test_hooks.py`

Upgrade the existing 4-event progress hook to handle all 17 pipeline events with rich formatted output.

**Step 1: Write the new failing tests**

Append to end of `modules/hooks-pipeline-progress/tests/test_hooks.py`:

```python


# -- New event handler tests (Layer 1 upgrade) ------------------------------


@pytest.mark.asyncio
async def test_handle_edge_selected():
    """handle_edge_selected should not crash and logs edge routing."""
    hook = PipelineProgressHook()
    await hook.handle_edge_selected("pipeline:edge_selected", {
        "from_node": "plan", "to_node": "impl", "edge_label": "success",
    })


@pytest.mark.asyncio
async def test_handle_checkpoint():
    """handle_checkpoint should not crash."""
    hook = PipelineProgressHook()
    await hook.handle_checkpoint("pipeline:checkpoint", {
        "node_id": "plan", "checkpoint_path": "/tmp/checkpoint.json",
    })


@pytest.mark.asyncio
async def test_handle_goal_gate_check():
    """handle_goal_gate_check should not crash."""
    hook = PipelineProgressHook()
    await hook.handle_goal_gate_check("pipeline:goal_gate_check", {
        "satisfied": ["validate"], "unsatisfied": ["test"],
    })


@pytest.mark.asyncio
async def test_handle_error():
    """handle_error should not crash."""
    hook = PipelineProgressHook()
    await hook.handle_error("pipeline:error", {
        "node_id": "plan", "error_type": "no_matching_edge", "message": "No edge",
    })


@pytest.mark.asyncio
async def test_handle_parallel_started():
    """handle_parallel_started should not crash."""
    hook = PipelineProgressHook()
    await hook.handle_parallel_started("pipeline:parallel_started", {
        "node_id": "fan_out", "branch_count": 3,
    })


@pytest.mark.asyncio
async def test_handle_parallel_branch_started():
    """handle_parallel_branch_started should not crash."""
    hook = PipelineProgressHook()
    await hook.handle_parallel_branch_started("pipeline:parallel_branch_started", {
        "node_id": "fan_out", "branch_node_id": "branch_a",
    })


@pytest.mark.asyncio
async def test_handle_parallel_branch_completed():
    """handle_parallel_branch_completed should not crash."""
    hook = PipelineProgressHook()
    await hook.handle_parallel_branch_completed("pipeline:parallel_branch_completed", {
        "node_id": "fan_out", "branch_node_id": "branch_a", "status": "success",
    })


@pytest.mark.asyncio
async def test_handle_parallel_completed():
    """handle_parallel_completed should not crash."""
    hook = PipelineProgressHook()
    await hook.handle_parallel_completed("pipeline:parallel_completed", {
        "node_id": "fan_out", "branch_count": 3, "result_count": 3,
    })


@pytest.mark.asyncio
async def test_handle_interview_started():
    """handle_interview_started should not crash."""
    hook = PipelineProgressHook()
    await hook.handle_interview_started("pipeline:interview_started", {
        "node_id": "gate", "question": "Approve?",
    })


@pytest.mark.asyncio
async def test_handle_interview_completed():
    """handle_interview_completed should not crash."""
    hook = PipelineProgressHook()
    await hook.handle_interview_completed("pipeline:interview_completed", {
        "node_id": "gate", "answer": "Yes",
    })


@pytest.mark.asyncio
async def test_handle_interview_timeout():
    """handle_interview_timeout should not crash."""
    hook = PipelineProgressHook()
    await hook.handle_interview_timeout("pipeline:interview_timeout", {
        "node_id": "gate", "prompt": "Approve?", "timeout": True,
    })


@pytest.mark.asyncio
async def test_handle_stage_retrying():
    """handle_stage_retrying should not crash."""
    hook = PipelineProgressHook()
    await hook.handle_stage_retrying("pipeline:stage_retrying", {
        "node_id": "validate", "attempt": 2, "max_attempts": 3, "delay_ms": 400.0,
    })


@pytest.mark.asyncio
async def test_handle_stage_failed():
    """handle_stage_failed should not crash."""
    hook = PipelineProgressHook()
    await hook.handle_stage_failed("pipeline:stage_failed", {
        "node_id": "validate", "attempts": 3, "final_status": "fail",
    })


@pytest.mark.asyncio
async def test_mount_registers_all_17_events():
    """mount() should register handlers for all 17 pipeline events."""
    hooks_mock = MagicMock()
    coordinator = MagicMock()
    coordinator.get.return_value = hooks_mock

    await mount(coordinator)

    registered_events = [call.args[0] for call in hooks_mock.register.call_args_list]
    expected = [
        "pipeline:start", "pipeline:complete",
        "pipeline:node_start", "pipeline:node_complete",
        "pipeline:edge_selected", "pipeline:checkpoint",
        "pipeline:goal_gate_check", "pipeline:error",
        "pipeline:parallel_started", "pipeline:parallel_branch_started",
        "pipeline:parallel_branch_completed", "pipeline:parallel_completed",
        "pipeline:interview_started", "pipeline:interview_completed",
        "pipeline:interview_timeout",
        "pipeline:stage_retrying", "pipeline:stage_failed",
    ]
    for event in expected:
        assert event in registered_events, f"Missing handler for {event}"
    assert len(registered_events) == 17


@pytest.mark.asyncio
async def test_pipeline_start_includes_edge_count():
    """handle_pipeline_start should log node and edge counts."""
    hook = PipelineProgressHook()
    await hook.handle_pipeline_start("pipeline:start", {
        "goal": "test", "node_count": 5, "edge_count": 4,
    })
    # If it didn't raise, the enhanced handler works
    assert hook._start_time is not None
```

**Step 2: Run tests to verify they fail**

```bash
cd modules/hooks-pipeline-progress && uv run pytest tests/test_hooks.py -q --tb=short
```

Expected: FAIL — `AttributeError: 'PipelineProgressHook' object has no attribute 'handle_edge_selected'`

**Step 3: Update the implementation**

Replace `modules/hooks-pipeline-progress/amplifier_module_hooks_pipeline_progress/__init__.py`:

```python
"""Pipeline progress display hook — rich real-time output during pipeline execution."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Amplifier module metadata
__amplifier_module_type__ = "hooks"


class PipelineProgressHook:
    """Listens on all pipeline events and logs human-readable progress lines.

    Tracks per-node start times so completion messages include wall-clock
    duration, and records overall pipeline elapsed time.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._start_time: float | None = None
        self._node_starts: dict[str, float] = {}

    # -- Pipeline lifecycle ------------------------------------------------

    async def handle_pipeline_start(self, event: str, data: dict[str, Any]) -> None:
        self._start_time = time.time()
        goal = data.get("goal", "")
        node_count = data.get("node_count", 0)
        edge_count = data.get("edge_count", 0)
        logger.info("[PIPELINE] Starting: %s (%d nodes, %d edges)", goal, node_count, edge_count)

    async def handle_pipeline_complete(self, event: str, data: dict[str, Any]) -> None:
        status = data.get("status", "")
        nodes_executed = data.get("total_nodes_executed", 0)
        duration_ms = data.get("duration_ms", 0)
        total = time.time() - self._start_time if self._start_time else 0
        logger.info(
            "[PIPELINE] Complete: %s | %d nodes | %.1fs | %.0fms engine time",
            status, nodes_executed, total, duration_ms,
        )

    # -- Node lifecycle ----------------------------------------------------

    async def handle_node_start(self, event: str, data: dict[str, Any]) -> None:
        node_id = data.get("node_id", "")
        handler = data.get("handler_type", "")
        attempt = data.get("attempt", 1)
        self._node_starts[node_id] = time.time()
        attempt_str = f" (attempt {attempt})" if attempt > 1 else ""
        logger.info("[PIPELINE] \u25b6 %s [%s]%s", node_id, handler, attempt_str)

    async def handle_node_complete(self, event: str, data: dict[str, Any]) -> None:
        node_id = data.get("node_id", "")
        status = data.get("status", "")
        duration_ms = data.get("duration_ms", 0)
        start = self._node_starts.get(node_id)
        wall = f" ({time.time() - start:.1f}s)" if start else ""
        symbol = "\u2713" if status == "success" else ("\u2717" if status == "fail" else "?")
        logger.info("[PIPELINE] %s %s: %s%s (%.0fms)", symbol, node_id, status, wall, duration_ms)

    # -- Edge routing ------------------------------------------------------

    async def handle_edge_selected(self, event: str, data: dict[str, Any]) -> None:
        from_node = data.get("from_node", "")
        to_node = data.get("to_node", "")
        label = data.get("edge_label", "")
        label_str = f" [{label}]" if label else ""
        logger.info("[PIPELINE] -> %s --%s--> %s", from_node, label_str, to_node)

    # -- Checkpoint --------------------------------------------------------

    async def handle_checkpoint(self, event: str, data: dict[str, Any]) -> None:
        node_id = data.get("node_id", "")
        logger.debug("[PIPELINE] Checkpoint saved at %s", node_id)

    # -- Goal gates --------------------------------------------------------

    async def handle_goal_gate_check(self, event: str, data: dict[str, Any]) -> None:
        satisfied = data.get("satisfied", [])
        unsatisfied = data.get("unsatisfied", [])
        total = len(satisfied) + len(unsatisfied)
        logger.info(
            "[PIPELINE] Goal gate: %d/%d satisfied, %d unsatisfied",
            len(satisfied), total, len(unsatisfied),
        )

    # -- Errors ------------------------------------------------------------

    async def handle_error(self, event: str, data: dict[str, Any]) -> None:
        node_id = data.get("node_id", "")
        error_type = data.get("error_type", "")
        message = data.get("message", "")
        logger.warning("[PIPELINE] ERROR at %s (%s): %s", node_id, error_type, message)

    # -- Parallel execution ------------------------------------------------

    async def handle_parallel_started(self, event: str, data: dict[str, Any]) -> None:
        node_id = data.get("node_id", "")
        count = data.get("branch_count", 0)
        logger.info("[PIPELINE] Parallel fan-out: %s (%d branches)", node_id, count)

    async def handle_parallel_branch_started(self, event: str, data: dict[str, Any]) -> None:
        node_id = data.get("node_id", "")
        branch = data.get("branch_node_id", "")
        logger.info("[PIPELINE]   \u25b6 branch: %s -> %s", node_id, branch)

    async def handle_parallel_branch_completed(self, event: str, data: dict[str, Any]) -> None:
        branch = data.get("branch_node_id", "")
        status = data.get("status", "")
        symbol = "\u2713" if status == "success" else ("\u2717" if status == "fail" else "?")
        logger.info("[PIPELINE]   %s branch: %s (%s)", symbol, branch, status)

    async def handle_parallel_completed(self, event: str, data: dict[str, Any]) -> None:
        node_id = data.get("node_id", "")
        branch_count = data.get("branch_count", 0)
        result_count = data.get("result_count", 0)
        logger.info("[PIPELINE] Parallel fan-in: %s (%d/%d completed)", node_id, result_count, branch_count)

    # -- Human interaction -------------------------------------------------

    async def handle_interview_started(self, event: str, data: dict[str, Any]) -> None:
        node_id = data.get("node_id", "")
        question = data.get("question", "")
        logger.info("[PIPELINE] Human gate: %s — %s", node_id, question)

    async def handle_interview_completed(self, event: str, data: dict[str, Any]) -> None:
        node_id = data.get("node_id", "")
        answer = data.get("answer", "")
        logger.info("[PIPELINE] Human gate: %s — answered: %s", node_id, answer)

    async def handle_interview_timeout(self, event: str, data: dict[str, Any]) -> None:
        node_id = data.get("node_id", "")
        logger.warning("[PIPELINE] Human gate: %s — TIMEOUT", node_id)

    # -- Retry lifecycle ---------------------------------------------------

    async def handle_stage_retrying(self, event: str, data: dict[str, Any]) -> None:
        node_id = data.get("node_id", "")
        attempt = data.get("attempt", 0)
        max_attempts = data.get("max_attempts", 0)
        delay_ms = data.get("delay_ms", 0)
        logger.info(
            "[PIPELINE] %s retrying (attempt %d/%d, delay %.0fms)",
            node_id, attempt, max_attempts, delay_ms,
        )

    async def handle_stage_failed(self, event: str, data: dict[str, Any]) -> None:
        node_id = data.get("node_id", "")
        attempts = data.get("attempts", 0)
        final_status = data.get("final_status", "fail")
        logger.warning("[PIPELINE] %s FAILED after %d attempts (%s)", node_id, attempts, final_status)


# All pipeline events and their handler method names
_HANDLER_MAP: dict[str, str] = {
    "pipeline:start": "handle_pipeline_start",
    "pipeline:complete": "handle_pipeline_complete",
    "pipeline:node_start": "handle_node_start",
    "pipeline:node_complete": "handle_node_complete",
    "pipeline:edge_selected": "handle_edge_selected",
    "pipeline:checkpoint": "handle_checkpoint",
    "pipeline:goal_gate_check": "handle_goal_gate_check",
    "pipeline:error": "handle_error",
    "pipeline:parallel_started": "handle_parallel_started",
    "pipeline:parallel_branch_started": "handle_parallel_branch_started",
    "pipeline:parallel_branch_completed": "handle_parallel_branch_completed",
    "pipeline:parallel_completed": "handle_parallel_completed",
    "pipeline:interview_started": "handle_interview_started",
    "pipeline:interview_completed": "handle_interview_completed",
    "pipeline:interview_timeout": "handle_interview_timeout",
    "pipeline:stage_retrying": "handle_stage_retrying",
    "pipeline:stage_failed": "handle_stage_failed",
}


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> None:
    """Mount the pipeline progress hook into the Amplifier coordinator."""
    hook = PipelineProgressHook(config)
    hooks = coordinator.get("hooks")
    for event_name, handler_name in _HANDLER_MAP.items():
        handler = getattr(hook, handler_name)
        hooks.register(event_name, handler, name="pipeline-progress")
```

**Step 4: Run all tests**

```bash
cd modules/hooks-pipeline-progress && uv run pytest tests/test_hooks.py -q --tb=short
```

Expected: all passed. Note: the old test `test_mount_registers_hooks` asserted `hooks_mock.register.call_count == 4` — that will now fail because we register 17. Update it:

In the test file, find the line `assert hooks_mock.register.call_count == 4` and change it to `assert hooks_mock.register.call_count == 17`.

**Step 5: Run tests again after fixing the count**

```bash
cd modules/hooks-pipeline-progress && uv run pytest tests/test_hooks.py -q --tb=short
```

Expected: all passed.

**Step 6: Commit**

```bash
cd modules/hooks-pipeline-progress && git add -A
git commit -m "feat: upgrade progress hook from 4 events to all 17 pipeline events"
```

---

## Task 8: Create `tool-pipeline-status` module (Layer 5 query tool)

**Files:**
- Create: `modules/tool-pipeline-status/pyproject.toml`
- Create: `modules/tool-pipeline-status/amplifier_module_tool_pipeline_status/__init__.py`
- Create: `modules/tool-pipeline-status/tests/__init__.py`
- Create: `modules/tool-pipeline-status/tests/test_tool.py`

A thin tool that reads from the `pipeline.state` contribution channel and returns the full `PipelineRunState` as structured JSON.

**Step 1: Create the pyproject.toml**

Create file `modules/tool-pipeline-status/pyproject.toml`:

```toml
[project]
name = "amplifier-module-tool-pipeline-status"
version = "0.1.0"
description = "Pipeline status query tool — returns PipelineRunState as structured JSON"
license = "MIT"
requires-python = ">=3.11"
authors = [
    { name = "Microsoft MADE:Explorations Team" },
]
dependencies = ["amplifier-core"]

[project.entry-points."amplifier.modules"]
tool-pipeline-status = "amplifier_module_tool_pipeline_status:mount"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.uv]
package = true

[tool.uv.sources]
amplifier-core = { path = "../../../amplifier-core", editable = true }

[tool.hatch.build.targets.wheel]
packages = ["amplifier_module_tool_pipeline_status"]

[tool.hatch.metadata]
allow-direct-references = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--import-mode=importlib"
asyncio_mode = "strict"

[dependency-groups]
dev = [
    "amplifier-core",
    "pytest>=9.0.2",
    "pytest-asyncio>=1.3.0",
]
```

**Step 2: Create tests/__init__.py**

Create file `modules/tool-pipeline-status/tests/__init__.py`:

```python
```

**Step 3: Write the failing test**

Create file `modules/tool-pipeline-status/tests/test_tool.py`:

```python
"""Tests for tool-pipeline-status."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from amplifier_module_tool_pipeline_status import PipelineStatusTool, mount


def test_tool_name():
    """Tool has correct name."""
    tool = PipelineStatusTool(config={})
    assert tool.name == "pipeline_status"


def test_tool_description():
    """Tool description mentions pipeline."""
    tool = PipelineStatusTool(config={})
    assert "pipeline" in tool.description.lower()


def test_tool_input_schema():
    """Tool input schema allows optional filter parameter."""
    tool = PipelineStatusTool(config={})
    schema = tool.input_schema
    assert schema["type"] == "object"
    assert "filter" in schema["properties"]


@pytest.mark.asyncio(loop_scope="session")
async def test_no_pipeline_state_returns_message():
    """When no pipeline has run, tool returns informative message."""
    coordinator = MagicMock()
    coordinator.collect_contributions = AsyncMock(return_value=[])

    tool = PipelineStatusTool(config={}, coordinator=coordinator)
    result = await tool.execute({})

    assert result.success
    assert "no pipeline" in result.output["message"].lower() or "no active" in result.output["message"].lower()


@pytest.mark.asyncio(loop_scope="session")
async def test_returns_pipeline_state_dict():
    """When pipeline state exists, tool returns it as a dict."""
    # Simulate a PipelineRunState-like object with a to_dict method
    mock_state = MagicMock()
    mock_state.to_dict.return_value = {
        "pipeline_id": "test-graph",
        "status": "running",
        "goal": "Build widget",
        "nodes_completed": 1,
        "nodes_total": 3,
        "current_node": "plan",
    }

    coordinator = MagicMock()
    coordinator.collect_contributions = AsyncMock(return_value=[mock_state])

    tool = PipelineStatusTool(config={}, coordinator=coordinator)
    result = await tool.execute({})

    assert result.success
    assert result.output["pipeline_id"] == "test-graph"
    assert result.output["status"] == "running"


@pytest.mark.asyncio(loop_scope="session")
async def test_returns_metrics_filter():
    """With filter=metrics, tool returns only aggregate metrics."""
    mock_state = MagicMock()
    mock_state.to_dict.return_value = {
        "pipeline_id": "test-graph",
        "status": "running",
        "goal": "Build widget",
        "nodes_completed": 1,
        "nodes_total": 3,
        "current_node": "plan",
        "total_elapsed_ms": 5000,
        "total_llm_calls": 2,
        "total_tokens_in": 1000,
        "total_tokens_out": 500,
        "total_tokens_cached": 200,
        "total_tokens_reasoning": 0,
        "timing": {"plan": 3000},
    }

    coordinator = MagicMock()
    coordinator.collect_contributions = AsyncMock(return_value=[mock_state])

    tool = PipelineStatusTool(config={}, coordinator=coordinator)
    result = await tool.execute({"filter": "metrics"})

    assert result.success
    assert "total_elapsed_ms" in result.output
    assert "total_llm_calls" in result.output
    # Metrics filter should NOT include full execution_path etc.
    assert "execution_path" not in result.output


@pytest.mark.asyncio(loop_scope="session")
async def test_mount_registers_tool():
    """mount() registers the tool with the coordinator."""
    coordinator = MagicMock()
    coordinator.mount = AsyncMock()

    await mount(coordinator, config={})

    coordinator.mount.assert_called_once()
    args = coordinator.mount.call_args
    assert args[0][0] == "tools"
    assert args[1]["name"] == "pipeline_status"


@pytest.mark.asyncio(loop_scope="session")
async def test_no_coordinator_returns_error():
    """Tool without coordinator returns error."""
    tool = PipelineStatusTool(config={})
    result = await tool.execute({})

    assert not result.success
    assert "coordinator" in result.error["message"].lower() or "not available" in result.error["message"].lower()
```

**Step 4: Run tests to verify they fail**

```bash
cd modules/tool-pipeline-status && uv sync && uv run pytest tests/ -q --tb=short
```

Expected: FAIL — module doesn't exist yet.

**Step 5: Write the implementation**

Create file `modules/tool-pipeline-status/amplifier_module_tool_pipeline_status/__init__.py`:

```python
"""Pipeline status query tool — returns PipelineRunState as structured JSON.

Reads from the ``pipeline.state`` contribution channel and returns
the current pipeline state. Supports optional filters for compact responses.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Amplifier module metadata
__amplifier_module_type__ = "tool"

__all__ = ["PipelineStatusTool", "mount"]

# Metric fields to extract for the "metrics" filter
_METRIC_KEYS = {
    "pipeline_id",
    "status",
    "goal",
    "nodes_completed",
    "nodes_total",
    "total_elapsed_ms",
    "total_llm_calls",
    "total_tokens_in",
    "total_tokens_out",
    "total_tokens_cached",
    "total_tokens_reasoning",
    "timing",
}


class PipelineStatusTool:
    """Query the current pipeline execution state.

    Returns the full PipelineRunState or filtered subsets.
    Reads from the ``pipeline.state`` contribution channel.
    """

    name = "pipeline_status"
    description = (
        "Query the current pipeline execution state. Returns status, "
        "progress, timing, metrics, routing decisions, and error details. "
        "Use filter='metrics' for aggregate metrics only."
    )

    def __init__(self, config: dict[str, Any], coordinator: Any = None) -> None:
        self.config = config
        self.coordinator = coordinator

    @property
    def input_schema(self) -> dict:
        """Return JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "description": (
                        "Optional filter: 'metrics' for aggregate metrics only, "
                        "'current' for current node info only. Omit for full state."
                    ),
                    "enum": ["metrics", "current"],
                },
            },
        }

    async def execute(self, input: dict[str, Any]) -> Any:
        """Execute the pipeline_status tool."""
        from amplifier_core import ToolResult

        if self.coordinator is None:
            return ToolResult(
                success=False,
                error={"message": "Pipeline status not available: coordinator not configured."},
            )

        # Collect from the pipeline.state contribution channel
        contributions = await self.coordinator.collect_contributions("pipeline.state")

        # Find the first non-None state
        state = None
        for contrib in contributions:
            if contrib is not None:
                state = contrib
                break

        if state is None:
            return ToolResult(
                success=True,
                output={"message": "No active pipeline. No pipeline has run in this session yet."},
            )

        # Serialize the state
        state_dict = state.to_dict() if hasattr(state, "to_dict") else dict(state)

        # Apply filter
        filter_type = input.get("filter")
        if filter_type == "metrics":
            filtered = {k: v for k, v in state_dict.items() if k in _METRIC_KEYS}
            return ToolResult(success=True, output=filtered)
        elif filter_type == "current":
            current = {
                "pipeline_id": state_dict.get("pipeline_id"),
                "status": state_dict.get("status"),
                "current_node": state_dict.get("current_node"),
                "nodes_completed": state_dict.get("nodes_completed"),
                "nodes_total": state_dict.get("nodes_total"),
                "total_elapsed_ms": state_dict.get("total_elapsed_ms"),
            }
            return ToolResult(success=True, output=current)

        # Full state
        return ToolResult(success=True, output=state_dict)


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> None:
    """Mount the pipeline_status tool."""
    config = config or {}
    tool = PipelineStatusTool(config, coordinator)
    await coordinator.mount("tools", tool, name=tool.name)
    logger.info("Mounted pipeline_status tool")
```

**Step 6: Run tests**

```bash
cd modules/tool-pipeline-status && uv run pytest tests/ -q --tb=short
```

Expected: all passed (8 tests).

**Step 7: Commit**

```bash
cd modules/tool-pipeline-status && git add -A
git commit -m "feat: pipeline_status query tool reads from pipeline.state contribution channel"
```

---

## Task 9: Full integration test — complete event sequence

**Files:**
- Create: `modules/hooks-pipeline-observability/tests/test_integration.py`

This test replays a realistic sequence of events (start → node_start → node_complete → edge → node_start → retry → node_complete → goal_gate → complete) and verifies the full `PipelineRunState` at the end.

**Step 1: Write the test**

Create file `modules/hooks-pipeline-observability/tests/test_integration.py`:

```python
"""Integration test — replay a realistic event sequence through the full system."""

from __future__ import annotations

import json

import pytest

from amplifier_module_hooks_pipeline_observability.aggregator import StateAggregator
from amplifier_module_hooks_pipeline_observability.status_bar import StatusBarHook


@pytest.mark.asyncio(loop_scope="session")
async def test_full_pipeline_event_sequence():
    """Replay a 3-node pipeline with retry and goal gate, verify final state."""
    agg = StateAggregator()
    bar = StatusBarHook(agg)

    # 1. Pipeline starts
    await agg.handle_pipeline_start("pipeline:start", {
        "graph_name": "plan-implement-test",
        "node_count": 5,
        "edge_count": 4,
        "goal": "Build the widget",
    })
    assert agg.state.status == "running"

    # 2. Node "plan" starts and completes
    await agg.handle_node_start("pipeline:node_start", {
        "node_id": "plan", "handler_type": "codergen", "attempt": 1,
    })
    assert agg.state.current_node == "plan"

    await agg.handle_node_complete("pipeline:node_complete", {
        "node_id": "plan", "status": "success", "duration_ms": 4200,
    })
    assert agg.state.nodes_completed == 1

    # 3. Edge from plan -> implement
    await agg.handle_edge_selected("pipeline:edge_selected", {
        "from_node": "plan", "to_node": "implement", "edge_label": "success",
    })

    # 4. Node "implement" starts and completes
    await agg.handle_node_start("pipeline:node_start", {
        "node_id": "implement", "handler_type": "codergen", "attempt": 1,
    })
    await agg.handle_node_complete("pipeline:node_complete", {
        "node_id": "implement", "status": "success", "duration_ms": 8100,
    })

    # 5. Edge from implement -> validate
    await agg.handle_edge_selected("pipeline:edge_selected", {
        "from_node": "implement", "to_node": "validate", "edge_label": "success",
    })

    # 6. Node "validate" starts, retries, then succeeds
    await agg.handle_node_start("pipeline:node_start", {
        "node_id": "validate", "handler_type": "conditional", "attempt": 1,
    })

    # Retry
    await agg.handle_stage_retrying("pipeline:stage_retrying", {
        "node_id": "validate", "attempt": 1, "max_attempts": 3, "delay_ms": 200,
    })
    assert agg.state.loop_iterations["validate"] == 1

    # Second attempt completes
    await agg.handle_node_complete("pipeline:node_complete", {
        "node_id": "validate", "status": "success", "duration_ms": 2100,
    })

    # 7. Goal gate check — all satisfied
    await agg.handle_goal_gate_check("pipeline:goal_gate_check", {
        "satisfied": ["validate"], "unsatisfied": [],
    })
    assert len(agg.state.goal_gate_checks) == 1
    assert agg.state.goal_gate_checks[0].action == "complete"

    # 8. Pipeline completes
    await agg.handle_pipeline_complete("pipeline:complete", {
        "status": "success", "total_nodes_executed": 3, "duration_ms": 14200,
    })

    # -- Verify final state -----------------------------------------------
    state = agg.get_state()
    assert state.status == "complete"
    assert state.goal == "Build the widget"
    assert state.nodes_completed == 3
    assert state.nodes_total == 5
    assert state.total_elapsed_ms == 14200

    # Execution path
    assert state.execution_path == ["plan", "implement", "validate"]

    # Node runs
    assert len(state.node_runs["plan"]) == 1
    assert state.node_runs["plan"][0].status == "success"
    assert state.node_runs["plan"][0].duration_ms == 4200

    assert len(state.node_runs["implement"]) == 1
    assert state.node_runs["implement"][0].status == "success"

    assert len(state.node_runs["validate"]) == 1
    assert state.node_runs["validate"][0].status == "success"

    # Edges taken
    assert len(state.branches_taken) == 2
    assert state.branches_taken[0].from_node == "plan"
    assert state.branches_taken[1].from_node == "implement"

    # Timing
    assert state.timing["plan"] == 4200
    assert state.timing["implement"] == 8100
    assert state.timing["validate"] == 2100

    # Loop iterations
    assert state.loop_iterations["validate"] == 1

    # Goal gate checks
    assert len(state.goal_gate_checks) == 1

    # Errors
    assert len(state.errors) == 0

    # JSON serialization round-trip
    d = state.to_dict()
    json_str = json.dumps(d)
    parsed = json.loads(json_str)
    assert parsed["pipeline_id"] == "plan-implement-test"
    assert parsed["status"] == "complete"

    # Status bar is compact
    status_text = bar.format_status()
    lines = [l for l in status_text.strip().split("\n") if l.strip()]
    assert len(lines) <= 6
    assert "complete" in status_text.lower()


@pytest.mark.asyncio(loop_scope="session")
async def test_failed_pipeline_event_sequence():
    """Replay a pipeline that fails due to error, verify error state."""
    agg = StateAggregator()

    await agg.handle_pipeline_start("pipeline:start", {
        "graph_name": "fail-test", "node_count": 2, "edge_count": 1, "goal": "test",
    })

    await agg.handle_node_start("pipeline:node_start", {
        "node_id": "A", "handler_type": "codergen", "attempt": 1,
    })
    await agg.handle_node_complete("pipeline:node_complete", {
        "node_id": "A", "status": "fail", "duration_ms": 500,
    })

    await agg.handle_error("pipeline:error", {
        "node_id": "A", "error_type": "no_matching_edge", "message": "No edge from A",
    })

    await agg.handle_pipeline_complete("pipeline:complete", {
        "status": "fail", "total_nodes_executed": 1, "duration_ms": 600,
    })

    state = agg.get_state()
    assert state.status == "failed"
    assert len(state.errors) == 1
    assert state.errors[0]["node_id"] == "A"
    assert state.nodes_completed == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_parallel_pipeline_event_sequence():
    """Replay a pipeline with parallel fan-out/fan-in."""
    agg = StateAggregator()

    await agg.handle_pipeline_start("pipeline:start", {
        "graph_name": "parallel-test", "node_count": 5, "edge_count": 4, "goal": "test",
    })

    # Fan-out node
    await agg.handle_node_start("pipeline:node_start", {
        "node_id": "fan_out", "handler_type": "component", "attempt": 1,
    })

    await agg.handle_parallel_started("pipeline:parallel_started", {
        "node_id": "fan_out", "branch_count": 2,
    })
    await agg.handle_parallel_branch_started("pipeline:parallel_branch_started", {
        "node_id": "fan_out", "branch_node_id": "branch_a",
    })
    await agg.handle_parallel_branch_started("pipeline:parallel_branch_started", {
        "node_id": "fan_out", "branch_node_id": "branch_b",
    })
    await agg.handle_parallel_branch_completed("pipeline:parallel_branch_completed", {
        "node_id": "fan_out", "branch_node_id": "branch_a", "status": "success",
    })
    await agg.handle_parallel_branch_completed("pipeline:parallel_branch_completed", {
        "node_id": "fan_out", "branch_node_id": "branch_b", "status": "success",
    })
    await agg.handle_parallel_completed("pipeline:parallel_completed", {
        "node_id": "fan_out", "branch_count": 2, "result_count": 2,
    })

    await agg.handle_node_complete("pipeline:node_complete", {
        "node_id": "fan_out", "status": "success", "duration_ms": 3000,
    })

    # Verify parallel tracking
    state = agg.get_state()
    assert "fan_out" in state.parallel_branches
    assert len(state.parallel_branches["fan_out"]) == 2
    assert state.parallel_branches["fan_out"][0].status == "success"
    assert state.parallel_branches["fan_out"][1].status == "success"
```

**Step 2: Run tests**

```bash
cd modules/hooks-pipeline-observability && uv run pytest tests/test_integration.py -q --tb=short
```

Expected: all passed (3 tests).

**Step 3: Run ALL module tests together**

```bash
cd modules/hooks-pipeline-observability && uv run pytest tests/ -q --tb=short
```

Expected: all passed.

**Step 4: Commit**

```bash
cd modules/hooks-pipeline-observability && git add -A
git commit -m "test: integration tests for full pipeline event sequences"
```

---

## Task 10: Final cleanup and all-modules test run

**Files:**
- No new files — verification only

Run all tests across all three affected modules to make sure nothing is broken.

**Step 1: Run hooks-pipeline-observability tests**

```bash
cd modules/hooks-pipeline-observability && uv run pytest tests/ -q --tb=short
```

Expected: all passed.

**Step 2: Run hooks-pipeline-progress tests**

```bash
cd modules/hooks-pipeline-progress && uv run pytest tests/ -q --tb=short
```

Expected: all passed.

**Step 3: Run tool-pipeline-status tests**

```bash
cd modules/tool-pipeline-status && uv run pytest tests/ -q --tb=short
```

Expected: all passed.

**Step 4: Run tool-pipeline-run tests** (to make sure we didn't break anything)

```bash
cd modules/tool-pipeline-run && uv run pytest tests/ -q --tb=short
```

Expected: all passed (existing tests unchanged).

**Step 5: Final commit with all changes**

```bash
git add -A
git commit -m "feat: pipeline observability system (Layers 1, 2, 3, 5)

- New module: hooks-pipeline-observability
  - PipelineRunState data model with all supporting dataclasses
  - StateAggregator hook subscribed to all 17 pipeline events
  - StatusBarHook for context injection (system-reminder style)
  - Event persistence via observability.events contribution channel
  - pipeline.state contribution channel for query access

- Upgraded: hooks-pipeline-progress (4 events -> 17 events)
  - Rich formatted output for all pipeline event types
  - Parallel, retry, human gate, goal gate, error logging

- New module: tool-pipeline-status
  - pipeline_status tool reads from pipeline.state channel
  - Full state, metrics-only, or current-node filtered output
  - JSON-serializable for future REST API consumption"
```

---

## Summary

| Task | What | Files | Estimated Time |
|------|------|-------|----------------|
| 1 | Module scaffold | 4 new files | 2 min |
| 2 | PipelineRunState data model | 2 new files | 5 min |
| 3 | State aggregator (start/complete) | 2 new files | 5 min |
| 4 | Aggregator tests (all events) | 1 modified file | 4 min |
| 5 | Wire mount() + contribution channels | 2 modified files, 1 new file | 5 min |
| 6 | Status bar hook | 1 modified file, 1 new file | 5 min |
| 7 | Enhanced progress hook (Layer 1) | 2 modified files | 5 min |
| 8 | Pipeline status query tool | 4 new files | 5 min |
| 9 | Integration tests | 1 new file | 3 min |
| 10 | Final verification | 0 files | 2 min |

**Total: ~41 minutes, 10 tasks, ~18 new files, ~2 modified files**
