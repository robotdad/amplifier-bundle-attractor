# Pipeline Observability System Design

## Goal

Build a comprehensive pipeline observability system that serves two audiences:

1. **Agents now** -- query pipeline state, compile reports, answer "what happened in this pipeline run?"
2. **Dashboards later** -- REST API driving visual DOT graph overlays with progress, drill-down per node, timing, metrics, loop iteration counts, and multi-instance dashboards

The pipeline engine already emits 22 events with rich data payloads. The problem is on the subscriber side -- nobody is aggregating them into a useful view. Users currently see "Status: converged, Iteration: 0, Passed: 4" with no visibility into which nodes ran, timing, routing decisions, or LLM metrics.

## Background

The Attractor pipeline engine emits events via `hooks.emit()` at every significant execution point: node starts/completions, edge routing decisions, goal gate checks, parallel branch fan-out/fan-in, retries, provider calls, and more. There are 22 distinct events covering the full lifecycle of a pipeline run.

However, the current `hooks-pipeline-progress` hook only subscribes to 4 of these events and produces minimal output. The result is that pipeline runs are opaque -- operators and agents see a final summary ("converged, Iteration: 0, Passed: 4") with no way to understand what happened during execution. This makes debugging, optimization, and confidence-building impossible.

The Amplifier ecosystem already provides the infrastructure to solve this: hooks for event collection, contribution channels for queryable state, CXDB for structured persistence, and the existing event log for audit trails. The work is on the subscriber/aggregation side, not the emitter side.

## Key Design Decisions

1. **Leverage the Amplifier ecosystem** -- use hooks for event collection, contribution channels for queryable state, CXDB for structured persistence, and the existing event log for audit trails.
2. **Events are already emitted** -- the pipeline engine emits 22 events via `hooks.emit()`. All work is on the subscriber/aggregation side.
3. **The data model is the centerpiece** -- a comprehensive `PipelineRunState` that every consumer reads from (status hook, progress hook, query tool, future REST API).
4. **Layered architecture** -- 5 independent layers, each useful on its own, each building on the event stream.

## Architecture: 5 Layers

```
Pipeline Engine (already emits 22 events)
        |
   +---------+---------+---------+---------+---------+
   |         |         |         |         |         |
Layer 1   Layer 2   Layer 3   Layer 4   Layer 5
Enhanced  Status    Event     CXDB      Query
Progress  Hook     Persist   Handlers  Tool
Hook     (context  (JSONL)   (PR to    (contrib
(rich     bar)              CI repo)   channel)
 output)
```

Each layer is independently useful:

- **Layer 1** gives human-readable real-time output
- **Layer 2** gives persistent in-context visibility (like the todo reminder)
- **Layer 3** gives audit trail and post-hoc analysis via events.jsonl
- **Layer 4** gives structured queryability via CXDB tools
- **Layer 5** gives programmatic access for agents and future dashboards

---

### Layer 1: Enhanced Progress Hook (immediate win)

Upgrade `hooks-pipeline-progress` from 4 events to all 22 events. Rich real-time output showing:

- Node execution with handler type and timing
- Edge routing decisions with conditions
- Provider/LLM call metrics (model, tokens, cached, duration)
- Retry attempts and delays
- Parallel branch fan-out/fan-in tracking
- Goal gate satisfaction status
- Running totals (nodes completed, tokens used, elapsed time)

Delivered via `HookResult.user_message` for clean UX. Example output:

```
[PIPELINE] Starting: implement feature (4 nodes, 3 edges)
[PIPELINE] > generate_code [codergen] (attempt 1)
[PROVIDER]   -> anthropic/claude-sonnet (23 tools)
[PROVIDER]   <- 1,247 tokens (842 cached) in 3.2s
[PIPELINE] generate_code: success (4.5s)
[PIPELINE] -> edge: generate_code --[success]--> validate
[PIPELINE] > validate [conditional]
[PIPELINE] validate retrying (attempt 2/3, delay 1s)
[PIPELINE] validate: success (2.1s)
[PIPELINE] Goal gate: 3/4 satisfied, 1 unsatisfied
[PIPELINE] Complete: converged | 3 nodes | 14.2s | 3,891 tokens
```

Zero engine changes required. The events are already emitted.

---

### Layer 2: Status Hook (persistent context bar)

A `system-reminder` hook (like the todo hook) that injects pipeline progress into the session context. Always visible, updates after each pipeline event.

What the agent and user see in their context:

```
<system-reminder source="hooks-pipeline-status">
Pipeline: plan-implement-test.dot
Status: running | Node 3/5: implement (codergen) | 45.2s elapsed
Completed: plan (success, 4.2s), analyze (success, 3.1s)
Current: implement -- started 12.3s ago
Remaining: validate, done
Tokens: 4,891 (1,203 cached) across 2 LLM calls
</system-reminder>
```

Injected via the hooks' context contribution mechanism (same pattern as the todo reminder). Lightweight (5-6 lines), always visible, and updates after each pipeline event.

The status hook solves a different problem than the progress hook. The progress hook emits log lines that scroll by. The status hook is **always visible** in the session context -- so even if the agent is deep in a tool call, you (or any observing system) can see where the pipeline is at.

---

### Layer 3: Event Persistence

Register all 16 `pipeline:*` events with the `observability.events` contribution channel during module mount. This ensures the logging hook auto-discovers and subscribes to them, landing all pipeline events in `events.jsonl`.

```python
# In loop-pipeline mount() or hooks-pipeline-progress mount():
coordinator.register_contributor("observability.events", "pipeline-engine", lambda: [
    "pipeline:start", "pipeline:complete", "pipeline:node_start",
    "pipeline:node_complete", "pipeline:edge_selected", "pipeline:checkpoint",
    "pipeline:goal_gate_check", "pipeline:error", "pipeline:parallel_started",
    "pipeline:parallel_branch_started", "pipeline:parallel_branch_completed",
    "pipeline:parallel_completed", "pipeline:interview_started",
    "pipeline:interview_completed", "pipeline:stage_retrying",
    "pipeline:stage_failed",
])
```

This is a small change that enables post-hoc analysis. Pipeline events may already be partially landing in events.jsonl, but explicit registration ensures complete and reliable capture.

---

### Layer 4: CXDB Pipeline Handlers (PR to context-intelligence)

Add handlers to the CXDB hook's `build_event_map()` following the existing recipe event pattern. Each pipeline event maps to a `system` turn with structured content. This makes pipeline runs queryable via CXDB tools:

- "Which nodes ran, in what order, how long each took?"
- "What was the total token usage across all nodes?"
- "Where did the pipeline fail?"
- "Compare this run to the previous one"

This is a separate PR to the context-intelligence bundle repository. The handler pattern already exists for recipe events, so the implementation follows an established convention.

---

### Layer 5: Pipeline State Aggregator + Query Tool

A stateful hook that maintains the comprehensive `PipelineRunState` data model (see next section). Registers on a `pipeline.state` contribution channel, making it queryable by:

- A `pipeline_status` tool (agent can query on demand)
- External systems with coordinator access
- Future REST API endpoint for dashboards

The query tool returns the full `PipelineRunState` or filtered subsets (e.g., just metrics, just the current node, just the execution path). This is what enables agents to answer "what happened?" and what future dashboards will poll for visual rendering.

---

## The Core Data Model: PipelineRunState

This is the centerpiece that every consumer reads from. Maintained by the state aggregator hook, updated on every pipeline event.

```python
@dataclass
class PipelineRunState:
    # Identity
    pipeline_id: str                          # session ID or run ID
    dot_source: str                           # the full DOT graph source (for visualization)
    goal: str

    # Graph structure (populated from pipeline:start)
    nodes: dict[str, NodeInfo]                # ALL nodes: id, shape, type, prompt, label
    edges: list[EdgeInfo]                     # ALL edges: from, to, condition, weight, label

    # Execution progress
    status: str                               # "pending" | "running" | "complete" | "failed"
    current_node: str | None
    execution_path: list[str]                 # ordered list of nodes visited
    branches_taken: list[EdgeInfo]            # which edges were selected

    # Per-node execution detail (supports retries/loops -- list per node)
    node_runs: dict[str, list[NodeRun]]

    # Edge routing decisions (for conditional visualization)
    edge_decisions: list[EdgeDecision]

    # Loop/retry tracking
    loop_iterations: dict[str, int]           # node_id -> total iteration count
    goal_gate_checks: list[GoalGateCheck]

    # Parallel execution tracking
    parallel_branches: dict[str, list[BranchInfo]]

    # Subgraph execution (recursive -- for nested DOT subgraphs)
    subgraph_runs: dict[str, PipelineRunState]

    # Human gate interactions
    human_interactions: list[HumanInteraction]

    # Manager-supervisor cycles
    supervisor_cycles: dict[str, list[SupervisorCycle]]

    # Aggregate metrics
    total_elapsed_ms: int
    total_llm_calls: int
    total_tokens_in: int
    total_tokens_out: int
    total_tokens_cached: int
    total_tokens_reasoning: int
    nodes_completed: int
    nodes_total: int

    # Per-node timing breakdown (including retries)
    timing: dict[str, int]                    # node_id -> total_ms
```

### Supporting Data Classes

```python
@dataclass
class NodeRun:
    status: str                               # "running" | "success" | "fail" | "timeout"
    attempt: int                              # which attempt (1-based, >1 for retries)
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int
    outcome: Outcome | None                   # full outcome with notes, context_updates
    llm_calls: int                            # number of LLM calls in this run
    tokens_in: int
    tokens_out: int
    tokens_cached: int


@dataclass
class EdgeDecision:
    from_node: str
    evaluated_edges: list                     # all candidate edges with conditions + match result
    selected_edge: EdgeInfo
    reason: str                               # "condition matched" | "weight priority" | "default"


@dataclass
class GoalGateCheck:
    timestamp: datetime
    satisfied: list[str]                      # node IDs that passed
    unsatisfied: list[str]                    # node IDs that failed
    action: str                               # "complete" | "retry" | "fail"


@dataclass
class BranchInfo:
    branch_id: str
    target_node: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int
    outcome: Outcome | None


@dataclass
class HumanInteraction:
    node_id: str
    question: str
    options: list[str]
    selected: str
    wait_time_ms: int


@dataclass
class SupervisorCycle:
    cycle_number: int
    observation: str
    steering_message: str
    wait_result: str
```

### DOT Execution Pattern Coverage

This data model covers all execution patterns representable in DOT:

| Pattern | Coverage |
|---------|----------|
| Linear chains (A -> B -> C) | `execution_path` + `node_runs` |
| Conditional branches (diamond gates) | `edge_decisions` with evaluated candidates + selected edge |
| Retry loops (goal_gate + retry_target) | `loop_iterations` + multiple entries in `node_runs[node_id]` |
| Parallel fan-out/fan-in | `parallel_branches` with per-branch timing and status |
| Nested subgraphs | `subgraph_runs` (recursive `PipelineRunState`) |
| Human gates (hexagon) | `human_interactions` with wait time and selection |
| Manager-supervisor loops (house) | `supervisor_cycles` with observe/steer/wait details |
| Multiple visits to same node | `node_runs: dict[str, list[NodeRun]]` (list per node) |
| Edge-based routing decisions | `edge_decisions` with condition evaluation details |

### Dashboard / Visualization Consumers

Future REST API and dashboard consumers read this model to:

- Render the DOT graph with color-coded node states (pending, running, success, fail)
- Overlay timing on edges
- Show retry loop iteration counts on loop-back edges
- Expand parallel branches into swim lanes
- Drill into any node for execution history, prompts, responses, metrics
- Show aggregate metrics (tokens, cost, timing) per pipeline run
- Support a multi-instance dashboard showing all running pipelines with click-through to individual run detail

---

## Data Flow

```
Pipeline Engine
    |
    | hooks.emit("pipeline:node_start", {...})
    |
    v
Hook Subscribers (all independent, all receive same events)
    |
    +---> Enhanced Progress Hook (Layer 1)
    |         Formats event -> HookResult.user_message -> user sees rich log line
    |
    +---> Status Hook (Layer 2)
    |         Updates in-memory summary -> context contribution -> agent sees status bar
    |
    +---> Logging Hook (Layer 3, via observability.events registration)
    |         Serializes event -> appends to events.jsonl
    |
    +---> CXDB Hook (Layer 4)
    |         Maps event -> system turn -> stored in CXDB for structured queries
    |
    +---> State Aggregator (Layer 5)
              Updates PipelineRunState in memory -> contribution channel
              -> query tool reads it -> agent/dashboard consumes it
```

---

## Error Handling

- If the state aggregator hook throws during event processing, log the error and continue. Observability hooks must never break the pipeline they are observing.
- The data model maintains `status: "failed"` with error details when pipelines fail.
- Partial state is still valuable -- a failed pipeline should show exactly how far it got, which nodes succeeded, where the failure occurred, and what metrics accumulated up to that point.
- Each layer is independent. If CXDB handlers fail, the progress hook and status hook continue unaffected.

---

## Testing Strategy

1. **Unit tests for PipelineRunState data model** -- construction, updates from each of the 22 event types, serialization to JSON.
2. **Unit tests for the enhanced progress hook** -- verify output format for each event type, verify running totals accumulate correctly.
3. **Unit tests for the status hook** -- verify context injection format, verify updates after each event, verify format stays within 5-6 lines.
4. **Unit tests for the state aggregator** -- verify contribution channel registration and query, verify full state is built correctly from an event sequence.
5. **Integration test** -- run a multi-node pipeline with all hooks mounted, verify the full `PipelineRunState` is correct at completion.
6. **Query tool tests** -- verify the tool returns the expected `PipelineRunState` snapshot, verify filtered queries (metrics only, current node only).

---

## Scope Boundaries

### In v1

- **Layers 1-3**: Enhanced progress hook, status hook, event persistence
- **The PipelineRunState data model** and state aggregator hook
- **The query tool** on the `pipeline.state` contribution channel

### Separate work

- **Layer 4 (CXDB handlers)**: Separate PR to the context-intelligence bundle repository
- **REST API / dashboard**: Future -- the data model is designed to support it, but no HTTP endpoint in v1
- **Multi-instance aggregation**: Future -- requires a service layer that collects `PipelineRunState` from multiple sessions

---

## Open Questions

1. **Should PipelineRunState be serializable to JSON for writing to a status file (e.g., status.json at logs_root)?** This would give external observers a file to poll without needing coordinator access. Recommendation: yes.

2. **Should the query tool support historical queries (completed pipeline runs from events.jsonl)?** Or only live state from the contribution channel? Recommendation: live-only in v1, historical via CXDB once Layer 4 lands.
