"""Tests for per-node failure routing (1b2).

When no edge matches after node execution, the engine should check
retry_target and fallback_retry_target on the node and graph before
returning FAIL.

Fallback chain: node.retry_target → node.fallback_retry_target →
                graph.retry_target → graph.fallback_retry_target → terminate.

Spec coverage: EXEC-015–018, Section 3.3.
"""

from __future__ import annotations

from typing import Any

import pytest

from amplifier_module_loop_pipeline.context import PipelineContext
from amplifier_module_loop_pipeline.engine import PipelineEngine
from amplifier_module_loop_pipeline.graph import Edge, Graph, Node
from amplifier_module_loop_pipeline.handlers import HandlerRegistry
from amplifier_module_loop_pipeline.outcome import Outcome, StageStatus
from amplifier_module_loop_pipeline.pipeline_events import PIPELINE_ERROR


class CountingBackend:
    """Backend that tracks call count per node and returns configurable outcomes."""

    def __init__(self, outcomes: dict[str, list[Outcome | str]] | None = None):
        self._outcomes = outcomes or {}
        self._call_counts: dict[str, int] = {}

    async def run(self, node, prompt, context) -> str | Outcome:
        count = self._call_counts.get(node.id, 0)
        self._call_counts[node.id] = count + 1
        seq = self._outcomes.get(node.id, ["done"])
        if count < len(seq):
            return seq[count]
        return seq[-1]  # repeat last

    def call_count(self, node_id: str) -> int:
        return self._call_counts.get(node_id, 0)


def _make_engine(
    graph: Graph,
    backend: object | None = None,
    logs_root: str = "/tmp/test-failure-routing",
    hooks: object | None = None,
) -> PipelineEngine:
    context = PipelineContext()
    registry = HandlerRegistry(backend=backend)
    return PipelineEngine(
        graph=graph,
        context=context,
        handler_registry=registry,
        logs_root=logs_root,
        hooks=hooks,
    )


class TestNodeRetryTarget:
    """When no edge matches, engine checks node.retry_target first."""

    @pytest.mark.asyncio
    async def test_node_retry_target_redirects_on_no_edge(self, tmp_path):
        """Node's retry_target is used when no edge matches."""
        # dead_end has retry_target pointing to recovery node
        graph = Graph(
            name="test",
            nodes={
                "start": Node(id="start", shape="Mdiamond"),
                "dead_end": Node(
                    id="dead_end",
                    prompt="work",
                    attrs={"retry_target": "recovery"},
                ),
                "recovery": Node(id="recovery", prompt="recover"),
                "exit": Node(id="exit", shape="Msquare"),
            },
            edges=[
                Edge(from_node="start", to_node="dead_end"),
                # dead_end has NO outgoing edges — triggers failure routing
                Edge(from_node="recovery", to_node="exit"),
            ],
        )
        backend = CountingBackend()
        engine = _make_engine(graph, backend=backend, logs_root=str(tmp_path))
        outcome = await engine.run()
        # Should have routed to recovery and then to exit
        assert outcome.status != StageStatus.FAIL or "No matching edge" not in (
            outcome.failure_reason or ""
        )
        assert backend.call_count("recovery") >= 1

    @pytest.mark.asyncio
    async def test_node_fallback_retry_target_used_when_primary_missing(self, tmp_path):
        """Node's fallback_retry_target is used when retry_target is absent."""
        graph = Graph(
            name="test",
            nodes={
                "start": Node(id="start", shape="Mdiamond"),
                "dead_end": Node(
                    id="dead_end",
                    prompt="work",
                    attrs={"fallback_retry_target": "fallback"},
                ),
                "fallback": Node(id="fallback", prompt="fallback work"),
                "exit": Node(id="exit", shape="Msquare"),
            },
            edges=[
                Edge(from_node="start", to_node="dead_end"),
                Edge(from_node="fallback", to_node="exit"),
            ],
        )
        backend = CountingBackend()
        engine = _make_engine(graph, backend=backend, logs_root=str(tmp_path))
        await engine.run()
        assert backend.call_count("fallback") >= 1


class TestGraphRetryTarget:
    """Graph-level retry targets are checked after node-level."""

    @pytest.mark.asyncio
    async def test_graph_retry_target_used_when_node_has_none(self, tmp_path):
        """Graph's retry_target is used when node has no retry targets."""
        graph = Graph(
            name="test",
            nodes={
                "start": Node(id="start", shape="Mdiamond"),
                "dead_end": Node(id="dead_end", prompt="work"),
                "graph_recovery": Node(id="graph_recovery", prompt="recover"),
                "exit": Node(id="exit", shape="Msquare"),
            },
            edges=[
                Edge(from_node="start", to_node="dead_end"),
                Edge(from_node="graph_recovery", to_node="exit"),
            ],
            graph_attrs={"retry_target": "graph_recovery"},
        )
        backend = CountingBackend()
        engine = _make_engine(graph, backend=backend, logs_root=str(tmp_path))
        await engine.run()
        assert backend.call_count("graph_recovery") >= 1

    @pytest.mark.asyncio
    async def test_graph_fallback_retry_target_last_resort(self, tmp_path):
        """Graph's fallback_retry_target is the last resort before terminate."""
        graph = Graph(
            name="test",
            nodes={
                "start": Node(id="start", shape="Mdiamond"),
                "dead_end": Node(id="dead_end", prompt="work"),
                "last_resort": Node(id="last_resort", prompt="last chance"),
                "exit": Node(id="exit", shape="Msquare"),
            },
            edges=[
                Edge(from_node="start", to_node="dead_end"),
                Edge(from_node="last_resort", to_node="exit"),
            ],
            graph_attrs={"fallback_retry_target": "last_resort"},
        )
        backend = CountingBackend()
        engine = _make_engine(graph, backend=backend, logs_root=str(tmp_path))
        await engine.run()
        assert backend.call_count("last_resort") >= 1


class TestFailureRoutingTerminate:
    """When no retry target exists anywhere, engine terminates with FAIL."""

    @pytest.mark.asyncio
    async def test_no_retry_target_anywhere_returns_fail(self, tmp_path):
        """No retry targets at any level → FAIL with 'No matching edge'."""
        graph = Graph(
            name="test",
            nodes={
                "start": Node(id="start", shape="Mdiamond"),
                "dead_end": Node(id="dead_end", prompt="work"),
                "exit": Node(id="exit", shape="Msquare"),
            },
            edges=[
                Edge(from_node="start", to_node="dead_end"),
            ],
        )
        backend = CountingBackend()
        engine = _make_engine(graph, backend=backend, logs_root=str(tmp_path))
        outcome = await engine.run()
        assert outcome.status == StageStatus.FAIL
        assert "No matching edge" in (outcome.failure_reason or "")


class TestFailureRoutingBounded:
    """Failure routing retries must be bounded to prevent infinite loops."""

    @pytest.mark.asyncio
    async def test_failure_routing_bounded_by_max_retries(self, tmp_path):
        """Failure routing retries are bounded (no infinite loop).

        If the retry target also has no matching edges and loops back,
        the engine must eventually terminate.
        """
        # Both nodes have no outgoing edges, retry_target points to each other
        graph = Graph(
            name="test",
            nodes={
                "start": Node(id="start", shape="Mdiamond"),
                "a": Node(id="a", prompt="work", attrs={"retry_target": "b"}),
                "b": Node(id="b", prompt="work", attrs={"retry_target": "a"}),
                "exit": Node(id="exit", shape="Msquare"),
            },
            edges=[
                Edge(from_node="start", to_node="a"),
                # Neither a nor b have outgoing edges → infinite retry loop
            ],
        )
        backend = CountingBackend()
        engine = _make_engine(graph, backend=backend, logs_root=str(tmp_path))
        outcome = await engine.run()
        # Must terminate (not hang) and return FAIL
        assert outcome.status == StageStatus.FAIL
        # Total calls should be bounded by _MAX_GOAL_GATE_RETRIES (shared limit)
        total_calls = backend.call_count("a") + backend.call_count("b")
        assert total_calls <= PipelineEngine._MAX_GOAL_GATE_RETRIES + 5


# ---------------------------------------------------------------------------
# Issue #251: Handler failure_reason preservation on routing termination
# ---------------------------------------------------------------------------


class _FailOutcomeBackend:
    """Backend that returns a specific FAIL Outcome for one node, SUCCESS for others."""

    def __init__(self, fail_node: str, failure_reason: str | None = None) -> None:
        self._fail_node = fail_node
        self._failure_reason = failure_reason

    async def run(self, node: Node, prompt: str, context: Any) -> Outcome:
        if node.id == self._fail_node:
            return Outcome(status=StageStatus.FAIL, failure_reason=self._failure_reason)
        return Outcome(status=StageStatus.SUCCESS)


class _CapturingHooks:
    """Minimal hooks implementation that records all emitted events."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def emit(self, name: str, data: dict[str, Any]) -> None:
        self.events.append((name, data))

    def get(self, name: str) -> list[dict[str, Any]]:
        return [d for n, d in self.events if n == name]


def _graph_with_dead_end_worker() -> Graph:
    """Graph: start → worker (no outgoing edges from worker).

    A handler that returns FAIL with no matching FAIL-condition edge will
    trigger routing termination at worker.
    """
    return Graph(
        name="test",
        nodes={
            "start": Node(id="start", shape="Mdiamond"),
            "worker": Node(id="worker", prompt="work"),
            "exit": Node(id="exit", shape="Msquare"),
        },
        edges=[
            Edge(from_node="start", to_node="worker"),
            # No edge from worker — routing terminates there
        ],
    )


class TestHandlerFailureReasonPreservation:
    """Handler failure_reason must survive routing termination (issue #251).

    When a handler returns Outcome(FAIL, failure_reason="X") and no outgoing
    edge matches, the pipeline-level failure_reason must carry X, not the
    routing message.  The routing context ("No matching edge …") moves to
    the notes field when the handler provided its own reason.
    """

    @pytest.mark.asyncio
    async def test_handler_failure_reason_preserved_when_no_matching_edge(
        self, tmp_path
    ):
        """Handler failure_reason is preserved; routing message goes to notes."""
        graph = _graph_with_dead_end_worker()
        backend = _FailOutcomeBackend("worker", "specific handler failure reason")
        engine = _make_engine(graph, backend=backend, logs_root=str(tmp_path))
        outcome = await engine.run()

        assert outcome.status == StageStatus.FAIL
        # Handler's own reason must be the failure_reason
        assert outcome.failure_reason == "specific handler failure reason"
        # Routing context must be demoted to notes
        assert outcome.notes is not None
        assert "No matching edge" in outcome.notes
        # Routing message must NOT bleed into failure_reason
        assert "No matching edge" not in (outcome.failure_reason or "")

    @pytest.mark.asyncio
    async def test_routing_message_used_when_handler_has_no_failure_reason(
        self, tmp_path
    ):
        """Today's behaviour preserved: routing message used when handler silent.

        When a handler returns Outcome(FAIL) with no failure_reason, the routing
        message becomes the failure_reason and notes stays None.
        """
        graph = _graph_with_dead_end_worker()
        backend = _FailOutcomeBackend("worker", failure_reason=None)
        engine = _make_engine(graph, backend=backend, logs_root=str(tmp_path))
        outcome = await engine.run()

        assert outcome.status == StageStatus.FAIL
        assert "No matching edge" in (outcome.failure_reason or "")
        assert outcome.notes is None

    @pytest.mark.asyncio
    async def test_pipeline_error_event_carries_handler_failure_reason(self, tmp_path):
        """PIPELINE_ERROR event payload includes the handler's failure_reason.

        The event carries both routing context (message) and handler reason
        (handler_failure_reason) so consumers can distinguish the two.
        """
        graph = _graph_with_dead_end_worker()
        backend = _FailOutcomeBackend("worker", "handler says: something broke")
        hooks = _CapturingHooks()
        engine = _make_engine(
            graph, backend=backend, logs_root=str(tmp_path), hooks=hooks
        )
        await engine.run()

        error_events = hooks.get(PIPELINE_ERROR)
        assert len(error_events) == 1
        ev = error_events[0]
        assert ev.get("handler_failure_reason") == "handler says: something broke"
        assert "No matching edge" in ev.get("message", "")
