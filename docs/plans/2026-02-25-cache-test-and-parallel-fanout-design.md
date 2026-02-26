# Cache Efficiency Test + Parallel Fan-Out Fix — Design

> **Date**: 2026-02-25
> **Status**: Approved

---

## Feature 1: Multi-Turn Cache Efficiency Test (NLSpec Gap #7)

### Problem

NLSpec Section 8.6, DoD item 9:
> "Multi-turn session: cache_read_tokens >50% at turn 5+"

All per-provider cache token extraction is unit-tested with mocks (8 tests pass).
The Anthropic adapter auto-injects `cache_control` breakpoints. OpenAI/Gemini
read from usage fields. The `Usage` type sums correctly. But no multi-turn
integration test exists to verify the >50% threshold.

### Design

New integration test gated with `@pytest.mark.integration`:

**File:** `modules/unified-llm-client/tests/integration/test_multi_turn_cache_efficiency.py`

The test:
1. Builds a 6-turn conversation with a 500+ word stable system prompt
2. Each turn adds a short user message, accumulates full history
3. Calls `client.generate()` for each turn
4. After turn 5, asserts `cache_read_tokens / input_tokens > 0.50`
5. Parametrized across `["anthropic", "openai", "gemini"]`
6. Skips providers when API keys are missing

Also include a real-world DOT file test using `~/dev/semport.dot` and
`~/dev/consensus_task.dot` as fixtures — these exercise multi-turn
conversations with real providers and verify caching across the pipeline
execution path.

Follows the same gating pattern as `tests/dod/test_8_10_integration_smoke.py`.

### Implementation Scope

Pure test — no production code changes. Closes the last FAIL in Section 8.6.

---

## Feature 2: Parallel Fan-Out — Fix Shared State Race Conditions

### Problem

Both `ParallelHandler` (shape=component nodes) and the engine's
`_execute_parallel_fan_out` (multi-edge divergence) already use
`asyncio.gather` — they ARE genuinely concurrent at the coroutine level.

The real issue: `AmplifierBackend` has shared mutable state that concurrent
branches corrupt:

```python
self._spawn_checked = False           # race on first parallel call
self._session_pool: dict[str, str]    # mutated by concurrent branches
self._completed_nodes: dict[str, Outcome]  # written by each branch
self._last_node_id: str | None = None      # last-writer-wins
```

When parallel branches share a single backend instance, `_session_pool`
entries get overwritten, `_completed_nodes` accumulates cross-branch
contamination, and `_last_node_id` is meaningless.

### Design: Clone-Per-Branch Isolation

Each parallel branch gets its own backend state. This matches the NLSpec's
"isolated clone of the parent context" philosophy.

**Changes:**

1. **Add `clone()` method to backend classes** (`AmplifierBackend`,
   `DirectProviderBackend`). Creates a new instance sharing the immutable
   provider/client references but with fresh mutable state
   (`_session_pool`, `_completed_nodes`, `_last_node_id`, `_spawn_checked`).

2. **Engine `_execute_parallel_fan_out`** — clone the backend (via handler
   registry or direct reference) before passing to each branch's
   `execute_with_retry` call.

3. **`ParallelHandler`** — already receives the runner callable. The runner
   needs to use a cloned backend. This is wired through the handler registry
   or by making the runner factory backend-aware.

4. **Merge strategy** — after branches complete, no merge of backend state
   is needed. Results are captured via `Outcome` objects returned from each
   branch. The engine already records outcomes in `self.node_outcomes` and
   `self.completed_nodes` from the returned results.

### Why Not Locks

`asyncio.Lock()` around mutations would serialize the critical sections,
defeating parallelism. Clone-per-branch is zero-contention.

### Testing

1. **Timing test** — 3 parallel branches with artificial delay. Assert
   wall-clock < 3× single-branch duration (proving concurrency).
2. **State isolation test** — concurrent branches don't corrupt each
   other's `_completed_nodes` or `_session_pool`.
3. **Existing tests must pass** — `test_parallel.py` (400 lines),
   `test_parallel_policies.py` (507 lines), engine fan-out tests.

### Files Changed

| File | Change |
|------|--------|
| `backend.py` | Add `clone()` to `AmplifierBackend` and `DirectProviderBackend` |
| `engine.py` | Clone backend per branch in `_execute_parallel_fan_out` |
| `handlers/parallel.py` | Wire cloned backend through runner |
| `handlers/__init__.py` or `handlers.py` | `HandlerRegistry` supports backend cloning |
| `tests/test_engine.py` | Timing test, state isolation test |
| `tests/test_parallel.py` | Backend isolation test |

### What We Skip

- `_spawn_fn` concurrency investigation — depends on coordinator implementation,
  out of scope. Clone-per-branch isolates the backend state regardless.
- Lock-based approach — rejected in favor of clone isolation.

---

## Success Criteria

### Cache Efficiency Test
1. Integration test exists, gated with `@pytest.mark.integration`
2. Passes with real API keys for all 3 providers
3. Verifies `cache_read_tokens / input_tokens > 0.50` at turn 5+
4. Real DOT file fixtures exercise the pipeline path
5. NLSpec Section 8.6 FAIL → PASS

### Parallel Fan-Out
1. Backend `clone()` method exists and creates isolated instances
2. Engine and ParallelHandler use cloned backends per branch
3. Timing test proves concurrent execution (< 3× single branch)
4. State isolation test proves no cross-branch contamination
5. All 873+ engine tests pass
6. All existing parallel tests pass