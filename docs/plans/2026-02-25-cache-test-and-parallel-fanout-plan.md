# Cache Efficiency Test + Parallel Fan-Out Fix — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close NLSpec gap #7 (multi-turn cache efficiency test) and fix parallel fan-out shared state race conditions in the pipeline engine.

**Architecture:** Task 1 is a pure integration test in unified-llm-client. Tasks 2–4 add clone-per-branch isolation to the backend and handler registry so parallel branches don't corrupt each other's state.

**Tech Stack:** Python, pytest, asyncio

**Repo:** `amplifier-bundle-attractor` at `/home/bkrabach/dev/attractor-next/amplifier-bundle-attractor`

**Testing commands:**
- Engine: `cd modules/loop-pipeline && .venv/bin/pytest tests/ -q`
- Unified LLM: `cd modules/unified-llm-client && .venv/bin/pytest tests/ -q`
- Integration (needs API keys): `cd modules/unified-llm-client && .venv/bin/pytest tests/dod/test_8_6_caching.py -m integration -v`

---

## Task 1: Multi-Turn Cache Efficiency Integration Test

**Files:**
- Create: `modules/unified-llm-client/tests/dod/test_multi_turn_cache_efficiency.py`

**Step 1: Create the integration test file**

Follow the same gating pattern as `tests/dod/test_8_10_integration_smoke.py`:
- Module-level `pytestmark = pytest.mark.integration`
- Class-level `@pytest.mark.skipif(not HAS_KEYS, ...)`
- `@pytest.mark.asyncio(loop_scope="function")`

```python
"""NLSpec Section 8.6, DoD item 9: Multi-turn cache efficiency test.

Verifies cache_read_tokens / input_tokens > 50% after 5+ turns.
Requires real API keys: ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY.
Run with: pytest -m integration
"""
from __future__ import annotations

import os
import pytest
from unified_llm import Message, Role
from unified_llm.client import Client
from unified_llm.generate import generate

pytestmark = pytest.mark.integration

SKIP_REASON = "API keys not set"
HAS_KEYS = all(
    os.environ.get(k)
    for k in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
) and (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))

# ~600 word system prompt to create a substantial cacheable prefix
SYSTEM_PROMPT = (
    "You are an expert software architect specializing in distributed systems, "
    "microservices, and cloud-native applications. You have deep knowledge of "
    "Kubernetes, Docker, service meshes (Istio, Linkerd), message brokers "
    "(Kafka, RabbitMQ, NATS), databases (PostgreSQL, MongoDB, Redis, "
    "CockroachDB), and observability stacks (Prometheus, Grafana, Jaeger, "
    "OpenTelemetry). When answering questions, provide concise, actionable "
    "advice grounded in production experience. Consider trade-offs between "
    "consistency, availability, and partition tolerance. Reference specific "
    "tools and patterns by name. Mention failure modes and mitigation "
    "strategies. Always consider the operational complexity of your "
    "recommendations.\n\n"
    "Your areas of particular expertise include:\n"
    "- Event-driven architectures and CQRS patterns\n"
    "- Circuit breaker and bulkhead patterns for resilience\n"
    "- Blue-green and canary deployment strategies\n"
    "- Database migration strategies for zero-downtime deployments\n"
    "- API gateway patterns and rate limiting\n"
    "- Secrets management and zero-trust networking\n"
    "- Cost optimization for cloud workloads\n"
    "- Performance profiling and capacity planning\n"
    "- Multi-region deployment and data replication\n"
    "- Container security and supply chain integrity\n\n"
    "When discussing architecture decisions, always frame your response "
    "in terms of: (1) the problem being solved, (2) the proposed solution, "
    "(3) alternatives considered, (4) trade-offs and risks, (5) operational "
    "requirements for production readiness."
)

# Short user prompts for each turn (keep small so system prompt dominates)
TURN_PROMPTS = [
    "What's the best circuit breaker library for Python microservices?",
    "How should I configure retry backoff for that?",
    "What metrics should I monitor for circuit breaker health?",
    "How do I test circuit breaker behavior in integration tests?",
    "What's the failure mode if the circuit stays open too long?",
    "How do I combine this with a bulkhead pattern?",
]

PROVIDER_MODELS = {
    "anthropic": "claude-sonnet-4-5-20250514",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
}


@pytest.mark.skipif(not HAS_KEYS, reason=SKIP_REASON)
class TestMultiTurnCacheEfficiency:
    """NLSpec 8.6 DoD: cache_read_tokens > 50% at turn 5+."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_cache_efficiency_per_provider(self):
        client = Client.from_env()

        for provider, model in PROVIDER_MODELS.items():
            key_var = {
                "anthropic": "ANTHROPIC_API_KEY",
                "openai": "OPENAI_API_KEY",
                "gemini": "GEMINI_API_KEY",
            }[provider]
            alt_var = "GOOGLE_API_KEY" if provider == "gemini" else None
            if not os.environ.get(key_var) and not (alt_var and os.environ.get(alt_var)):
                continue  # skip this provider

            messages: list[Message] = []

            for turn_idx, prompt in enumerate(TURN_PROMPTS):
                messages.append(Message(role=Role.USER, content=prompt))

                result = await generate(
                    model=model,
                    prompt=messages,
                    system=SYSTEM_PROMPT,
                    max_tokens=150,
                    provider=provider,
                    client=client,
                )

                assert result.text, f"{provider} turn {turn_idx}: empty response"
                assert result.usage, f"{provider} turn {turn_idx}: no usage"

                # Accumulate assistant response for next turn
                messages.append(Message(role=Role.ASSISTANT, content=result.text))

                # Check cache efficiency from turn 5 onward (0-indexed: turn_idx >= 4)
                if turn_idx >= 4 and result.usage.input_tokens > 0:
                    cache_read = result.usage.cache_read_tokens or 0
                    input_total = result.usage.input_tokens
                    ratio = cache_read / input_total if input_total > 0 else 0

                    assert ratio > 0.50, (
                        f"{provider} turn {turn_idx + 1}: cache ratio {ratio:.2%} "
                        f"({cache_read}/{input_total}) — expected >50%"
                    )
```

**Step 2: Run the test (requires API keys)**

```bash
cd modules/unified-llm-client && .venv/bin/pytest tests/dod/test_multi_turn_cache_efficiency.py -m integration -v
```

If API keys are available, expect: PASS for providers that support caching.
If API keys are NOT available, expect: SKIP.

Also run the full non-integration suite to confirm no import breakage:
```bash
cd modules/unified-llm-client && .venv/bin/pytest tests/ -q --ignore=tests/dod/test_multi_turn_cache_efficiency.py
```
Expected: 599 passed.

**Step 3: Commit**

```
test: multi-turn cache efficiency integration test (NLSpec 8.6 DoD)
```

---

## Task 2: Add `clone()` method to `AmplifierBackend`

**Files:**
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/backend.py`
- Test: `modules/loop-pipeline/tests/test_backend_clone.py` (create)

**Step 1: Write test for backend clone**

```python
"""Tests for AmplifierBackend.clone() — parallel branch isolation."""
import pytest
from unittest.mock import MagicMock
from amplifier_module_loop_pipeline.backend import AmplifierBackend


def test_clone_creates_independent_mutable_state():
    """Clone shares immutable refs but has fresh mutable state."""
    backend = AmplifierBackend(
        coordinator=MagicMock(),
        profiles={"anthropic": "default"},
        provider=MagicMock(),
        tools={"bash": MagicMock()},
        hooks=MagicMock(),
    )
    # Mutate original
    backend._session_pool["key1"] = "session-1"
    backend._completed_nodes["node1"] = MagicMock()
    backend._last_node_id = "node1"

    clone = backend.clone()

    # Mutable state is independent
    assert clone._session_pool == {}
    assert clone._completed_nodes == {}
    assert clone._last_node_id is None
    assert clone._spawn_checked is False

    # Immutable refs are shared
    assert clone._coordinator is backend._coordinator
    assert clone._profiles is backend._profiles
    assert clone._provider is backend._provider
    assert clone._hooks is backend._hooks

    # Mutations don't cross
    clone._session_pool["key2"] = "session-2"
    assert "key2" not in backend._session_pool
```

**Step 2: Run test, verify it fails** (no `clone()` method yet)

```bash
cd modules/loop-pipeline && .venv/bin/pytest tests/test_backend_clone.py -v
```

**Step 3: Implement `clone()` on AmplifierBackend**

Add after `__init__` in `backend.py`:

```python
def clone(self) -> "AmplifierBackend":
    """Create a copy with fresh mutable state for parallel branch isolation.

    Shares immutable references (coordinator, profiles, provider, tools,
    hooks, unified_client) but creates independent mutable state so
    concurrent branches don't corrupt each other.
    """
    new = AmplifierBackend(
        coordinator=self._coordinator,
        profiles=self._profiles,
        provider=self._provider,
        tools=dict(self._tools),  # shallow copy — tool objects are shared
        unified_client=self._unified_client,
        hooks=self._hooks,
    )
    return new
```

**Step 4: Run test, verify it passes. Run full suite (876 tests).**

**Step 5: Commit**

```
feat: add clone() to AmplifierBackend for parallel branch isolation
```

---

## Task 3: Add `clone_for_branch()` to `HandlerRegistry`

**Files:**
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/handlers/__init__.py`
- Test: `modules/loop-pipeline/tests/test_handler_registry_clone.py` (create)

The `HandlerRegistry` holds pre-constructed handlers. `CodergenHandler` holds the backend. For parallel isolation, we need a way to get a registry (or at least a handler set) with a cloned backend.

**Step 1: Write test**

```python
"""Tests for HandlerRegistry.clone_for_branch()."""
from unittest.mock import MagicMock
from amplifier_module_loop_pipeline.handlers import HandlerRegistry


def test_clone_for_branch_isolates_backend():
    """Cloned registry has an independent backend on its codergen handler."""
    backend = MagicMock()
    backend.clone = MagicMock(return_value=MagicMock())

    registry = HandlerRegistry(backend=backend)
    cloned = registry.clone_for_branch()

    backend.clone.assert_called_once()
    # The codergen handler in the clone should have the cloned backend
    original_codergen = registry._handlers["codergen"]
    cloned_codergen = cloned._handlers["codergen"]
    assert cloned_codergen._backend is not original_codergen._backend
```

**Step 2: Run test, verify it fails**

**Step 3: Implement `clone_for_branch()`**

In `HandlerRegistry`, add:

```python
def clone_for_branch(self) -> "HandlerRegistry":
    """Create a shallow clone with an isolated backend for parallel branches.

    The codergen handler gets a cloned backend with fresh mutable state.
    All other handlers are shared (they are stateless or use only the
    runner callback which is per-engine).
    """
    import copy
    cloned = copy.copy(self)
    cloned._handlers = dict(self._handlers)  # shallow copy the dict

    # Clone the codergen handler with an isolated backend
    original_codergen = self._handlers.get("codergen")
    if original_codergen is not None and hasattr(original_codergen, "_backend"):
        backend = getattr(original_codergen._backend, "clone", None)
        if backend and callable(backend):
            from amplifier_module_loop_pipeline.handlers.codergen import CodergenHandler
            cloned._handlers["codergen"] = CodergenHandler(backend=original_codergen._backend.clone())
    return cloned
```

**Step 4: Run test, verify it passes. Run full suite.**

**Step 5: Commit**

```
feat: add clone_for_branch() to HandlerRegistry for parallel isolation
```

---

## Task 4: Wire clone-per-branch in engine fan-out + add timing test

**Files:**
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/engine.py` (~line 803)
- Test: `modules/loop-pipeline/tests/test_engine.py` (add tests)

**Step 1: Write timing test for parallel fan-out**

Add to `test_engine.py`:

```python
@pytest.mark.asyncio
async def test_parallel_fan_out_executes_concurrently():
    """Parallel branches run concurrently, not sequentially."""
    import asyncio
    import time

    delay_ms = 200  # each branch takes 200ms

    # Build a graph with 3 parallel edges from a single node
    # (use existing test fixture patterns from test_multi_edge_fan_out_executes_all_targets)
    # Hook the handler to inject a delay
    # Assert total wall-clock < 3 * delay_ms (proving concurrency)
    # A generous bound: < 2 * delay_ms accounts for overhead
```

Adapt from the existing `test_multi_edge_fan_out_executes_all_targets` (line 704 in test_engine.py). The key addition: inject an `asyncio.sleep(0.2)` into each branch handler, measure total wall time, assert it's < 0.5s (2.5x a single branch, leaving room for overhead but proving they don't run sequentially at 0.6s+).

**Step 2: Write state isolation test**

```python
@pytest.mark.asyncio
async def test_parallel_fan_out_isolates_backend_state():
    """Each parallel branch gets its own backend clone — no cross-contamination."""
    # Run a fan-out, capture the backend instances used by each branch
    # Assert they are different objects
```

**Step 3: Modify `_execute_parallel_fan_out` in engine.py**

In the `run_branch` closure (~line 810), before getting the handler, clone the registry:

```python
async def run_branch(target_node_id: str) -> dict[str, Any]:
    branch_context = self.context.clone()
    # Clone handler registry for this branch so each gets its own backend
    branch_registry = self.handler_registry.clone_for_branch()
    node = self.graph.nodes[target_node_id]
    handler = branch_registry.get(node)
    # ... rest of run_branch uses branch_registry instead of self.handler_registry
```

**Step 4: Run tests, verify they pass. Run full suite (876+ tests).**

**Step 5: Commit**

```
feat: clone-per-branch isolation in parallel fan-out execution
```

---

## Task Dependency Graph

```
Task 1 (cache test)     — independent, unified-llm-client repo
Task 2 (backend clone)  — independent
Task 3 (registry clone) — depends on Task 2
Task 4 (wire + timing)  — depends on Task 3
```

Tasks 1 and 2 can run in parallel. Tasks 3–4 are sequential.