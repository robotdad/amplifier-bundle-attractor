"""Tests for checkpointing and resume.

After every node execution, a JSON checkpoint is saved so the pipeline
can resume after crashes. Tests cover serialization, deserialization,
engine integration, and resume-from-checkpoint behavior.

Spec coverage: CHKP-001–006, Section 5.3.
"""

import json
import os

import pytest

from amplifier_module_loop_pipeline.checkpoint import (
    Checkpoint,
    load_checkpoint,
    save_checkpoint,
)
from amplifier_module_loop_pipeline.context import PipelineContext
from amplifier_module_loop_pipeline.dot_parser import parse_dot
from amplifier_module_loop_pipeline.engine import PipelineEngine
from amplifier_module_loop_pipeline.graph import Node
from amplifier_module_loop_pipeline.handlers import HandlerRegistry
from amplifier_module_loop_pipeline.outcome import StageStatus
from amplifier_module_loop_pipeline.validation import validate_or_raise


# --- Checkpoint model ---


class TestCheckpointModel:
    """CHKP-001: Checkpoint captures execution state."""

    def test_create_checkpoint(self):
        cp = Checkpoint(
            current_node="plan",
            completed_nodes={"start": "success", "plan": "success"},
            context_snapshot={"graph.goal": "build auth"},
            node_outcomes={
                "start": {"status": "success", "notes": "Start node"},
                "plan": {"status": "success", "notes": "Planned"},
            },
            timestamp="2025-01-01T00:00:00Z",
        )
        assert cp.current_node == "plan"
        assert len(cp.completed_nodes) == 2
        assert cp.context_snapshot["graph.goal"] == "build auth"

    def test_checkpoint_has_timestamp(self):
        cp = Checkpoint(
            current_node="step1",
            completed_nodes={},
            context_snapshot={},
            node_outcomes={},
            timestamp="2025-06-15T12:00:00Z",
        )
        assert cp.timestamp == "2025-06-15T12:00:00Z"

    def test_checkpoint_node_retries(self):
        """Checkpoint preserves retry counters."""
        cp = Checkpoint(
            current_node="flaky",
            completed_nodes={"flaky": "success"},
            context_snapshot={},
            node_outcomes={},
            timestamp="2025-01-01T00:00:00Z",
            node_retries={"flaky": 3},
        )
        assert cp.node_retries["flaky"] == 3


# --- Serialization ---


class TestCheckpointSerialization:
    """CHKP-002–003: Checkpoint saves/loads as valid JSON."""

    def test_save_creates_json_file(self, tmp_path):
        cp = Checkpoint(
            current_node="plan",
            completed_nodes={"start": "success"},
            context_snapshot={"graph.goal": "test"},
            node_outcomes={"start": {"status": "success"}},
            timestamp="2025-01-01T00:00:00Z",
        )
        path = str(tmp_path / "checkpoint.json")
        save_checkpoint(cp, path)
        assert os.path.exists(path)

    def test_saved_json_is_valid(self, tmp_path):
        cp = Checkpoint(
            current_node="plan",
            completed_nodes={"start": "success"},
            context_snapshot={"graph.goal": "test"},
            node_outcomes={"start": {"status": "success"}},
            timestamp="2025-01-01T00:00:00Z",
        )
        path = str(tmp_path / "checkpoint.json")
        save_checkpoint(cp, path)
        # Must be valid JSON
        with open(path) as f:
            data = json.load(f)
        assert data["current_node"] == "plan"

    def test_saved_json_is_human_readable(self, tmp_path):
        """JSON should be indented for debugging."""
        cp = Checkpoint(
            current_node="step",
            completed_nodes={},
            context_snapshot={},
            node_outcomes={},
            timestamp="2025-01-01T00:00:00Z",
        )
        path = str(tmp_path / "checkpoint.json")
        save_checkpoint(cp, path)
        with open(path) as f:
            content = f.read()
        # Indented JSON has newlines and spaces
        assert "\n" in content

    def test_round_trip(self, tmp_path):
        """Save then load returns equivalent Checkpoint."""
        cp = Checkpoint(
            current_node="implement",
            completed_nodes={"start": "success", "plan": "success"},
            context_snapshot={"graph.goal": "build auth", "last_stage": "plan"},
            node_outcomes={
                "start": {"status": "success", "notes": "ok"},
                "plan": {"status": "success", "notes": "planned"},
            },
            timestamp="2025-06-15T12:00:00Z",
            node_retries={"plan": 2},
        )
        path = str(tmp_path / "checkpoint.json")
        save_checkpoint(cp, path)
        loaded = load_checkpoint(path)
        assert loaded.current_node == "implement"
        assert loaded.completed_nodes == {"start": "success", "plan": "success"}
        assert loaded.context_snapshot["graph.goal"] == "build auth"
        assert loaded.node_outcomes["plan"]["notes"] == "planned"
        assert loaded.timestamp == "2025-06-15T12:00:00Z"
        assert loaded.node_retries == {"plan": 2}

    def test_load_missing_file_raises(self, tmp_path):
        """Loading a nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_checkpoint(str(tmp_path / "nonexistent.json"))

    def test_save_with_empty_fields(self, tmp_path):
        """Empty checkpoint saves and loads correctly."""
        cp = Checkpoint(
            current_node="",
            completed_nodes={},
            context_snapshot={},
            node_outcomes={},
            timestamp="2025-01-01T00:00:00Z",
        )
        path = str(tmp_path / "checkpoint.json")
        save_checkpoint(cp, path)
        loaded = load_checkpoint(path)
        assert loaded.current_node == ""
        assert loaded.completed_nodes == {}

    def test_node_retries_default_empty(self, tmp_path):
        """When no node_retries in JSON, defaults to empty dict."""
        cp = Checkpoint(
            current_node="x",
            completed_nodes={},
            context_snapshot={},
            node_outcomes={},
            timestamp="2025-01-01T00:00:00Z",
        )
        path = str(tmp_path / "checkpoint.json")
        save_checkpoint(cp, path)
        loaded = load_checkpoint(path)
        assert loaded.node_retries == {}


# --- Engine integration ---


class MockBackend:
    """Backend that returns a fixed string for every call."""

    def __init__(self, return_value: str = "done"):
        self._return_value = return_value
        self.calls: list[str] = []

    async def run(self, node: Node, prompt: str, context: PipelineContext) -> str:
        self.calls.append(node.id)
        return self._return_value


def _make_engine(
    dot_source: str,
    backend: object | None = None,
    logs_root: str = "/tmp/test-pipeline",
) -> PipelineEngine:
    """Parse DOT, validate, and build an engine."""
    graph = parse_dot(dot_source)
    validate_or_raise(graph)
    context = PipelineContext()
    registry = HandlerRegistry(backend=backend)
    return PipelineEngine(
        graph=graph,
        context=context,
        handler_registry=registry,
        logs_root=logs_root,
    )


class TestCheckpointEngineIntegration:
    """CHKP-004: Engine saves checkpoint after each node."""

    @pytest.mark.asyncio
    async def test_checkpoint_saved_after_each_node(self, tmp_path):
        """Engine writes checkpoint.json after each node execution."""
        engine = _make_engine(
            dot_source="""
            digraph {
                start [shape=Mdiamond]
                plan [prompt="Plan"]
                implement [prompt="Build"]
                exit [shape=Msquare]
                start -> plan -> implement -> exit
            }
            """,
            backend=MockBackend("done"),
            logs_root=str(tmp_path),
        )
        await engine.run()
        checkpoint_path = tmp_path / "checkpoint.json"
        assert checkpoint_path.exists()
        data = json.loads(checkpoint_path.read_text())
        # After full run, completed_nodes should include start, plan, implement
        assert "start" in data["completed_nodes"]
        assert "plan" in data["completed_nodes"]
        assert "implement" in data["completed_nodes"]

    @pytest.mark.asyncio
    async def test_checkpoint_has_context_snapshot(self, tmp_path):
        """Checkpoint includes context state."""
        engine = _make_engine(
            dot_source="""
            digraph {
                goal = "build auth"
                start [shape=Mdiamond]
                step [prompt="Work"]
                exit [shape=Msquare]
                start -> step -> exit
            }
            """,
            backend=MockBackend("done"),
            logs_root=str(tmp_path),
        )
        await engine.run()
        data = json.loads((tmp_path / "checkpoint.json").read_text())
        assert "graph.goal" in data["context"]


class TestResumeFromCheckpoint:
    """CHKP-005–006: Resume from checkpoint skips completed nodes."""

    @pytest.mark.asyncio
    async def test_resume_skips_completed_nodes(self, tmp_path):
        """Resumed engine skips nodes that are already completed."""
        # First, create a checkpoint that says start and plan are done
        cp = Checkpoint(
            current_node="plan",
            completed_nodes={"start": "success", "plan": "success"},
            context_snapshot={"graph.goal": "build auth", "outcome": "success"},
            node_outcomes={
                "start": {"status": "success"},
                "plan": {"status": "success"},
            },
            timestamp="2025-01-01T00:00:00Z",
        )
        save_checkpoint(cp, str(tmp_path / "checkpoint.json"))

        # Now create an engine and resume from checkpoint
        backend = MockBackend("done")
        engine = _make_engine(
            dot_source="""
            digraph {
                goal = "build auth"
                start [shape=Mdiamond]
                plan [prompt="Plan"]
                implement [prompt="Build"]
                exit [shape=Msquare]
                start -> plan -> implement -> exit
            }
            """,
            backend=backend,
            logs_root=str(tmp_path),
        )
        outcome = await engine.run()
        assert outcome.status in (StageStatus.SUCCESS, StageStatus.PARTIAL_SUCCESS)
        # Backend should have been called for implement but NOT plan
        # (plan was completed in the checkpoint)
        assert "implement" in backend.calls
        assert "plan" not in backend.calls

    @pytest.mark.asyncio
    async def test_resume_restores_context(self, tmp_path):
        """Resumed engine has context values from checkpoint."""
        cp = Checkpoint(
            current_node="plan",
            completed_nodes={"start": "success", "plan": "success"},
            context_snapshot={
                "graph.goal": "build auth",
                "outcome": "success",
                "custom_key": "custom_value",
            },
            node_outcomes={
                "start": {"status": "success"},
                "plan": {"status": "success"},
            },
            timestamp="2025-01-01T00:00:00Z",
        )
        save_checkpoint(cp, str(tmp_path / "checkpoint.json"))

        backend = MockBackend("done")
        engine = _make_engine(
            dot_source="""
            digraph {
                goal = "build auth"
                start [shape=Mdiamond]
                plan [prompt="Plan"]
                implement [prompt="Build"]
                exit [shape=Msquare]
                start -> plan -> implement -> exit
            }
            """,
            backend=backend,
            logs_root=str(tmp_path),
        )
        await engine.run()
        # Context should include the restored values
        assert engine.context.get("custom_key") == "custom_value"

    @pytest.mark.asyncio
    async def test_no_checkpoint_runs_normally(self, tmp_path):
        """Engine without existing checkpoint runs from the beginning."""
        backend = MockBackend("done")
        engine = _make_engine(
            dot_source="""
            digraph {
                start [shape=Mdiamond]
                step [prompt="Work"]
                exit [shape=Msquare]
                start -> step -> exit
            }
            """,
            backend=backend,
            logs_root=str(tmp_path),
        )
        outcome = await engine.run()
        assert outcome.status in (StageStatus.SUCCESS, StageStatus.PARTIAL_SUCCESS)
        # Backend called for step (start is handled by StartHandler)
        assert "step" in backend.calls


class TestGraphFingerprintIsolation:
    """Issue #252: checkpoint pollution across graphs sharing the same logs_root."""

    @pytest.mark.asyncio
    async def test_stale_checkpoint_discarded_on_graph_mismatch(
        self, tmp_path, caplog
    ):
        """Engine B (Graph G') must not consume Engine A's (Graph G) checkpoint
        when both share the same logs_root.

        RED on main (no guard), GREEN after fix (fingerprint mismatch discards
        the stale checkpoint).
        """
        import logging

        shared_logs = str(tmp_path / "shared-logs")

        # Engine A: Graph G - runs fully, writes checkpoint with WorkerA + WorkerB
        graph_g = """
digraph {
    start [shape=Mdiamond]
    WorkerA [prompt="Work A"]
    WorkerB [prompt="Work B"]
    exit [shape=Msquare]
    start -> WorkerA -> WorkerB -> exit
}
"""
        engine_a = _make_engine(graph_g, backend=MockBackend("done"), logs_root=shared_logs)
        outcome_a = await engine_a.run()
        assert outcome_a.status in (StageStatus.SUCCESS, StageStatus.PARTIAL_SUCCESS)

        # Confirm checkpoint was written and contains Engine A's nodes
        checkpoint_path = os.path.join(shared_logs, "checkpoint.json")
        assert os.path.exists(checkpoint_path)
        with open(checkpoint_path) as f:
            raw = json.load(f)
        assert "WorkerA" in raw["completed_nodes"]

        # Engine B: Graph G' - different structure, same logs_root
        graph_g_prime = """
digraph {
    start [shape=Mdiamond]
    NestedRegression [prompt="Nested work"]
    exit [shape=Msquare]
    start -> NestedRegression -> exit
}
"""
        with caplog.at_level(
            logging.WARNING, logger="amplifier_module_loop_pipeline.engine"
        ):
            engine_b = _make_engine(
                graph_g_prime, backend=MockBackend("done"), logs_root=shared_logs
            )
            outcome_b = await engine_b.run()

        # Engine B must NOT have stale entries from Engine A's graph
        assert "WorkerA" not in engine_b.node_outcomes, (
            "stale WorkerA from Engine A must not appear in Engine B's node_outcomes"
        )
        assert "WorkerB" not in engine_b.node_outcomes, (
            "stale WorkerB from Engine A must not appear in Engine B's node_outcomes"
        )
        # Engine B must complete its own graph successfully
        assert outcome_b.status in (StageStatus.SUCCESS, StageStatus.PARTIAL_SUCCESS)

    @pytest.mark.asyncio
    async def test_checkpoint_accepted_on_matching_graph(self, tmp_path):
        """Resume still works when Engine B runs the same graph as Engine A.

        Should be GREEN on both main and after fix — same graph means same
        fingerprint, so the guard does not discard the checkpoint.
        """
        shared_logs = str(tmp_path / "logs")
        dot = """
digraph {
    start [shape=Mdiamond]
    plan [prompt="Plan"]
    implement [prompt="Implement"]
    exit [shape=Msquare]
    start -> plan -> implement -> exit
}
"""
        # Engine A: runs the full graph, writes checkpoint
        backend_a = MockBackend("done")
        engine_a = _make_engine(dot, backend=backend_a, logs_root=shared_logs)
        await engine_a.run()

        # Engine B: fresh engine, SAME graph, same logs_root -> must resume
        backend_b = MockBackend("done")
        engine_b = _make_engine(dot, backend=backend_b, logs_root=shared_logs)
        outcome_b = await engine_b.run()

        assert outcome_b.status in (StageStatus.SUCCESS, StageStatus.PARTIAL_SUCCESS)
        # Backend B must NOT be called — all nodes already completed by Engine A
        assert backend_b.calls == [], (
            f"Backend should not be called when all nodes are resumed; "
            f"got {backend_b.calls}"
        )

    @pytest.mark.asyncio
    async def test_backward_compat_checkpoint_without_fingerprint_still_resumes(
        self, tmp_path
    ):
        """Old-style checkpoints without graph_fingerprint must still enable resume.

        The backward-compat guard ``if cp.graph_fingerprint and ...`` is falsy for
        the empty-string default, so pre-fix checkpoints are always accepted.

        Should be GREEN on both main and after fix.
        """
        logs = str(tmp_path / "logs")
        os.makedirs(logs, exist_ok=True)

        # Handcrafted old-style checkpoint JSON: NO graph_fingerprint field
        old_checkpoint = {
            "current_node": "plan",
            "completed_nodes": {"start": "success", "plan": "success"},
            "context": {"graph.goal": ""},
            "node_outcomes": {
                "start": {"status": "success"},
                "plan": {"status": "success"},
            },
            "timestamp": "2025-01-01T00:00:00Z",
            "node_retries": {},
            "logs": [],
            # Intentionally NO "graph_fingerprint" key — simulates pre-fix checkpoint
        }
        with open(os.path.join(logs, "checkpoint.json"), "w") as f:
            json.dump(old_checkpoint, f)

        dot = """
digraph {
    start [shape=Mdiamond]
    plan [prompt="Plan"]
    implement [prompt="Implement"]
    exit [shape=Msquare]
    start -> plan -> implement -> exit
}
"""
        backend = MockBackend("done")
        engine = _make_engine(dot, backend=backend, logs_root=logs)
        outcome = await engine.run()

        assert outcome.status in (StageStatus.SUCCESS, StageStatus.PARTIAL_SUCCESS)
        # implement must have been executed (was NOT in old checkpoint)
        assert "implement" in backend.calls, (
            "implement should have been executed (not in old checkpoint)"
        )
        # plan must NOT have been executed (was in old checkpoint)
        assert "plan" not in backend.calls, (
            "plan should have been skipped (was already in old checkpoint)"
        )
