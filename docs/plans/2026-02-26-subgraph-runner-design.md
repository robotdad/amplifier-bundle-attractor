# Subgraph Runner — Nested Pipeline Execution Design

## Goal

Enable pipeline nodes to execute external DOT files as nested sub-pipelines, with full observability into child pipeline state.

## Background

Three use cases drive this feature, in priority order:

1. **Reusable pipeline templates** — define a review pipeline once, invoke it from multiple parent pipelines
2. **Dynamic pipeline composition** — select which child pipeline to run via context variable expansion (`$language-review.dot`)
3. **Organizational scoping** — break large pipelines into manageable, independently testable units

The NLSpec defines `stack.child_dotfile` as a graph-level attribute for the manager loop handler (Section 4.11). Subgraph blocks in DOT syntax (Section 2.10) are scoping/styling constructs, not execution units. No node-level attribute for external pipeline references exists in the current spec. This design extends the spec's pattern to be more general.

## Approach

Two-layer design:

1. A new `pipeline` handler as the **primitive** — any node can invoke an external DOT file
2. Enhancement of the existing `stack.manager_loop` handler to use the primitive when `stack.child_dotfile` is set

This gives us a general-purpose mechanism (the handler) and backward-compatible integration with the existing manager loop pattern.

## Architecture

```
Parent Pipeline (engine A)
  ├── NodeA (llm handler)
  ├── ReviewPhase (pipeline handler, shape=folder)
  │     └── Creates child PipelineEngine (engine B)
  │           ├── ChildNode1
  │           ├── ChildNode2
  │           └── ... (full child pipeline)
  │     ← Returns Outcome to parent
  └── NodeC (routes on ReviewPhase outcome)
```

The parent engine delegates to a child engine. The child engine is fully independent — own graph, own context (cloned), own logs directory, own event capture — but cooperative cancellation propagates from parent to child.

## Components

### 1. `PipelineHandler` — The Primitive

**New handler type:** `pipeline` (shape: `folder`)

When a node has `shape=folder` or `node_type="pipeline"`, the `PipelineHandler` executes an external DOT file as a nested pipeline. The node carries:

- `dot_file="path/to/child.dot"` — resolved relative to the parent DOT file's directory, with `$variable` expansion from context
- Standard node attributes work as normal (timeout, max_retries, llm_provider, etc.)

**Execution flow:**

1. Resolve `dot_file` path (expand `$variables`, resolve relative to parent)
2. Read and parse the DOT source into a new `Graph`
3. Create a new `PipelineEngine` with: the child graph, a cloned context, a fresh `HandlerRegistry` (with a cloned backend), its own `logs_root` subdirectory (`{parent_logs}/subgraph_{node_id}/`)
4. Pass the `cancel_event` through (cooperative cancellation propagates to children)
5. Run `engine.run(goal=...)` — goal comes from the child graph's `goal` attribute or the parent context
6. Return the child engine's `Outcome` with `context_updates` applied to the parent

**What the parent gets back:** The `Outcome` object (status, preferred_label, notes, context_updates). The parent can route on it via edge conditions and preferred_label just like any other node.

### 2. Observability — Child Pipeline State in the Parent

The `subgraph_runs` field already exists in `PipelineRunState` (typed as `dict[str, Any]`). We populate it with the child engine's full execution state.

**What gets captured per nested pipeline execution:**

```python
subgraph_runs[node_id] = {
    "dot_file": "path/to/child.dot",
    "dot_source": child_graph.dot_source,
    "pipeline_id": child_graph.name,
    "goal": child_goal,
    "status": outcome.status.value,
    "execution_path": child_engine.completed_nodes,
    "node_outcomes": {nid: {...} for nid in child_engine.node_outcomes},
    "timing": child_timing_dict,
    "total_elapsed_ms": child_duration,
    "nodes_completed": len(child_engine.completed_nodes),
    "nodes_total": len(child_graph.nodes),
}
```

**Event flow:** The child engine gets its own `EventCaptureHook` (or shares the parent's hook with a `subgraph:` event prefix). Events from the child pipeline appear in the parent's SSE stream prefixed with `subgraph:{node_id}:` — e.g., `subgraph:ReviewPhase:pipeline:node_complete`. Late-connecting SSE clients see the full child event history via replay.

**Dashboard integration:** The existing `PipelineView` can detect `subgraph_runs[nodeId]` and render a "drill into sub-pipeline" affordance on the node. Clicking it shows the child pipeline's graph and execution state in a nested view. This is future UI work — the data layer is what we build now.

**Logs directory structure:**

```
{parent_logs}/
  manifest.json
  checkpoint.json
  NodeA/status.json
  ReviewPhase/              <- the pipeline node
    status.json             <- parent's view of this node's outcome
    subgraph/               <- child pipeline's own logs
      manifest.json
      checkpoint.json
      ChildNode1/status.json
      ChildNode2/status.json
```

### 3. `stack.manager_loop` Enhancement

**Current behavior:** `ManagerLoopHandler` always uses the first outgoing edge as the child subgraph entry point, running nodes inline within the same graph via `_run_from`.

**Enhanced behavior:** When `stack.child_dotfile` is present (on the node or graph attrs), the manager handler:

1. Resolves the DOT file path (with `$variable` expansion)
2. Parses it into a child `Graph`
3. Creates a child `PipelineEngine` (same pattern as the `pipeline` handler)
4. Each observe/steer cycle runs the **full child pipeline** and ingests its outcome
5. The manager's stop condition evaluates against the child outcome as usual

**When `stack.child_dotfile` is NOT set:** Existing behavior is unchanged — the manager follows its first outgoing edge and runs inline via `_run_from`. Zero breaking changes.

**Attribute resolution priority:**

1. `node.attrs["stack.child_dotfile"]` (node-level — most specific)
2. `graph.graph_attrs["stack.child_dotfile"]` (graph-level — matches NLSpec)
3. If neither: fall back to first outgoing edge (current behavior)

This means the NLSpec's graph-level attribute still works, but you can also set it per-node for reuse — a single graph could have multiple manager nodes each supervising different child pipelines.

**Observability:** Same as the `pipeline` handler — each cycle's child run is captured in `subgraph_runs` with cycle indexing (`subgraph_runs[f"{node_id}_cycle_{n}"]`).

### 4. DOT File Resolution and Context Variable Expansion

**Path resolution order:**

1. If path starts with `/` — absolute, use as-is
2. If path starts with `$` — expand context variables first, then resolve
3. Otherwise — resolve relative to the parent DOT file's directory (stored on the parent `Graph` object via a new `source_dir: str = ""` field, set by the parser when a file path is known)
4. Fallback: resolve relative to `logs_root` (the working directory)

**Variable expansion:** Uses the existing `PipelineContext` variable expansion that already handles `$goal`, `$outcome`, etc. in prompts and conditions. Example: `dot_file="pipelines/$language-review.dot"` with `context["language"] = "python"` resolves to `pipelines/python-review.dot`.

**Validation:** At parse time (when the parent graph is parsed), we can't validate child DOT file existence because `$variables` aren't resolved yet. Validation happens at execution time — if the file doesn't exist or fails to parse, the `PipelineHandler` returns `Outcome(status=FAIL, failure_reason="Child DOT file not found: ...")`.

**Caching:** Parsed child graphs are NOT cached between executions. Each time a `pipeline` node executes, the DOT file is re-read and re-parsed. This keeps it simple and ensures changes to child DOT files take effect immediately. If performance becomes a concern, caching can be added later.

## Data Flow

```
Parent node executes
  → PipelineHandler.execute()
    → resolve dot_file path (expand $vars, resolve relative)
    → read + parse child DOT source → Graph
    → clone context, create child PipelineEngine
    → child_engine.run(goal=...)
      → child executes all its nodes (full pipeline)
      → child events emitted with subgraph:{node_id}: prefix
      → child logs written to {parent_logs}/subgraph_{node_id}/
    → capture child state into parent's subgraph_runs[node_id]
    → return child Outcome to parent
  → parent routes on Outcome (preferred_label, edge conditions)
```

## Error Handling

| Error | Handling |
|-------|----------|
| DOT file not found | `Outcome(status=FAIL, failure_reason="Child DOT file not found: {path}")` |
| DOT file parse failure | `Outcome(status=FAIL, failure_reason="Failed to parse child DOT: {error}")` |
| Child pipeline fails | Child's `Outcome` (with FAIL status) propagated to parent for edge routing |
| Child pipeline timeout | Parent node's timeout applies; cancel_event propagates to child |
| Cooperative cancellation | Parent's `cancel_event` passed to child engine; child checks it at each node |

## Testing Strategy

- **Unit tests for `PipelineHandler`:** Execute a simple child DOT, verify outcome propagation, context cloning, subgraph_runs capture
- **Unit tests for DOT resolution:** Absolute paths, relative paths, `$variable` expansion, missing file error
- **Unit tests for manager_loop enhancement:** With `stack.child_dotfile` set (node-level, graph-level), without it (existing behavior preserved)
- **Integration tests:** Multi-level nesting (parent → child → grandchild), cancellation propagation, event prefix correctness
- **Regression:** All existing 890+ engine tests must pass unchanged

## Files Changed

| File | Change |
|------|--------|
| `graph.py` | Add `source_dir: str = ""` to `Graph` dataclass |
| `dot_parser.py` | Set `source_dir` when file path is known; add `folder` to shape handling |
| `validation.py` | Add `folder` → `pipeline` to `SHAPE_TO_HANDLER` |
| `handlers/pipeline.py` | NEW — `PipelineHandler` implementation |
| `handlers/__init__.py` | Register `pipeline` handler in `HandlerRegistry`; update `clone_for_branch` |
| `handlers/manager_loop.py` | Enhance to use child DOT file when `stack.child_dotfile` is set |
| `engine.py` | Expose state for `subgraph_runs` capture after child execution |
| `pipeline_events.py` | Add `SUBGRAPH_START`, `SUBGRAPH_COMPLETE` event types |
| Tests | New test file(s) for `PipelineHandler`, enhanced `manager_loop` tests, DOT resolution tests |

## Success Criteria

1. A DOT node with `shape=folder, dot_file="child.dot"` executes the child DOT file as a nested pipeline
2. Context variable expansion works in `dot_file` paths (`$variable` resolved from context)
3. Child pipeline outcome is returned to parent for edge routing (conditions + preferred_label)
4. `subgraph_runs[node_id]` contains full child execution state (node outcomes, timing, execution path)
5. Child events appear in parent's event stream with `subgraph:{node_id}:` prefix
6. Child logs are written to `{parent_logs}/subgraph_{node_id}/`
7. Cooperative cancellation propagates to child engines
8. `stack.manager_loop` with `stack.child_dotfile` runs external DOT per cycle
9. `stack.manager_loop` without `stack.child_dotfile` behaves exactly as before
10. All existing tests pass (890+ engine tests)

## What We Defer

- **Dashboard UI** for drilling into nested pipelines (data layer only for now)
- **Child graph caching** (re-parse every execution — simplicity first)
- **Model stylesheet `@import`** (separate feature)
- **Circular/recursive pipeline detection** (relies on step limit safety bound)
