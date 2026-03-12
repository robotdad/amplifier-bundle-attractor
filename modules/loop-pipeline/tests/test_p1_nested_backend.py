"""Tests for nested backend wiring (P1).

When a parent pipeline runs a child pipeline via a folder/pipeline node,
the child HandlerRegistry should receive the parent's backend so that
child codergen nodes call the backend correctly.

Tests:
- test_backend_propagated_to_child: asserts backend IS propagated (post-fix)
- test_parent_codergen_uses_backend: baseline confirmation
"""

from __future__ import annotations

import os  # noqa: F401 — used in future P1 test phases

import pytest

from amplifier_module_loop_pipeline.context import PipelineContext
from amplifier_module_loop_pipeline.dot_parser import parse_dot
from amplifier_module_loop_pipeline.engine import PipelineEngine
from amplifier_module_loop_pipeline.graph import Edge, Graph, Node  # noqa: F401 — Edge/Graph staged for future phases
from amplifier_module_loop_pipeline.handlers import HandlerRegistry
from amplifier_module_loop_pipeline.handlers.manager_loop import ManagerLoopHandler  # noqa: F401 — staged for future phases
from amplifier_module_loop_pipeline.handlers.pipeline import PipelineHandler  # noqa: F401 — staged for future phases
from amplifier_module_loop_pipeline.outcome import Outcome, StageStatus  # noqa: F401 — Outcome staged for future phases

# ---------------------------------------------------------------------------
# SpyBackend
# ---------------------------------------------------------------------------


class SpyBackend:
    """Records every (node_id, prompt) call made by the codergen handler."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def run(self, node: Node, prompt: str, context: PipelineContext) -> str:
        self.calls.append((node.id, prompt))
        return "done"

    def was_called_for(self, node_id: str) -> bool:
        """Return True if the backend was called for the given node_id."""
        return any(call[0] == node_id for call in self.calls)


# ---------------------------------------------------------------------------
# CHILD_DOT constant: simple child pipeline
# ---------------------------------------------------------------------------

CHILD_DOT = """\
digraph child {
    start [shape=Mdiamond]
    child_work [prompt="Do child work"]
    done [shape=Msquare]
    start -> child_work -> done
}
"""

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _write_dot(path: str, content: str) -> None:
    """Write DOT content to a file at the given path."""
    with open(path, "w") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNestedBackendWiring:
    """Tests for nested backend wiring in pipeline execution."""

    @pytest.mark.asyncio
    async def test_backend_propagated_to_child(self, tmp_path):
        """Child codergen nodes DO receive the parent's backend (post-fix).

        When a folder node launches a child pipeline, PipelineHandler creates a
        new HandlerRegistry with the backend forwarded. As a result, the
        spy backend records calls from the child's codergen nodes.
        """
        # Write child.dot to tmp_path
        child_dot_path = str(tmp_path / "child.dot")
        _write_dot(child_dot_path, CHILD_DOT)

        # Build parent DOT: start -> folder_node (child.dot) -> done
        parent_dot = """\
digraph parent {
    start [shape=Mdiamond]
    sub [shape=folder, dot_file="child.dot"]
    done [shape=Msquare]
    start -> sub -> done
}
"""
        graph = parse_dot(parent_dot)
        graph.source_dir = str(tmp_path)

        spy = SpyBackend()
        context = PipelineContext()
        registry = HandlerRegistry(backend=spy)
        logs_root = str(tmp_path / "logs")

        engine = PipelineEngine(
            graph=graph,
            context=context,
            handler_registry=registry,
            logs_root=logs_root,
        )
        outcome = await engine.run()

        # Parent pipeline should still succeed overall
        assert outcome.status == StageStatus.SUCCESS

        # FIX VERIFIED: child_work IS called via spy because
        # PipelineHandler now creates HandlerRegistry(backend=self._backend).
        assert spy.was_called_for("child_work") is True, (
            "Expected child_work in spy calls — backend should be propagated "
            "to child pipelines via PipelineHandler"
        )

    @pytest.mark.asyncio
    async def test_parent_codergen_uses_backend(self, tmp_path):
        """Parent-level codergen nodes DO use the backend (baseline).

        Confirms that when a codergen node runs directly in the parent
        pipeline (not inside a nested pipeline), the backend is called
        correctly. This establishes the baseline that backend wiring works
        at the top level.
        """
        parent_dot = """\
digraph parent {
    start [shape=Mdiamond]
    parent_work [prompt="Do parent work"]
    done [shape=Msquare]
    start -> parent_work -> done
}
"""
        graph = parse_dot(parent_dot)
        graph.source_dir = str(tmp_path)

        spy = SpyBackend()
        context = PipelineContext()
        registry = HandlerRegistry(backend=spy)
        logs_root = str(tmp_path / "logs")

        engine = PipelineEngine(
            graph=graph,
            context=context,
            handler_registry=registry,
            logs_root=logs_root,
        )
        outcome = await engine.run()

        assert outcome.status == StageStatus.SUCCESS

        # BASELINE: parent_work IS called via the spy backend
        called_node_ids = [call[0] for call in spy.calls]
        assert "parent_work" in called_node_ids, (
            "Expected parent_work in spy calls — baseline: parent backend works"
        )


# ---------------------------------------------------------------------------
# TestManagerLoopBackendWiring
# ---------------------------------------------------------------------------


class TestManagerLoopBackendWiring:
    """Tests for backend propagation through ManagerLoopHandler._run_child_dotfile."""

    @pytest.mark.asyncio
    async def test_manager_child_dotfile_backend_propagated(self, tmp_path):
        """Backend IS propagated to child pipelines launched by ManagerLoopHandler.

        When a house node uses stack.child_dotfile to run a child pipeline,
        the child HandlerRegistry must receive the parent's backend so that
        child codergen nodes call the backend correctly.
        """
        # Write managed_child.dot to tmp_path with a worker node
        managed_child_dot = """\
digraph managed_child {
  start [shape=Mdiamond];
  worker [prompt="Do worker work"];
  done [shape=Msquare];
  start -> worker -> done;
}
"""
        child_dot_path = tmp_path / "managed_child.dot"
        child_dot_path.write_text(managed_child_dot)

        # Build parent graph with a house node using stack.child_dotfile
        manager_node = Node(
            id="manager",
            shape="house",
            attrs={
                "manager.max_cycles": "1",
                "stack.child_dotfile": str(child_dot_path),
            },
        )
        parent_graph = Graph(
            name="parent",
            nodes={
                "start": Node(id="start", shape="Mdiamond"),
                "manager": manager_node,
                "done": Node(id="done", shape="Msquare"),
            },
            edges=[
                Edge(from_node="start", to_node="manager"),
                Edge(from_node="manager", to_node="done"),
            ],
        )
        parent_graph.source_dir = str(tmp_path)

        spy = SpyBackend()
        context = PipelineContext()
        registry = HandlerRegistry(backend=spy)
        logs_root = str(tmp_path / "logs")

        engine = PipelineEngine(
            graph=parent_graph,
            context=context,
            handler_registry=registry,
            logs_root=logs_root,
        )
        outcome = await engine.run()

        # Pipeline should succeed before we assert backend propagation
        assert outcome.status == StageStatus.SUCCESS

        # FIX VERIFIED: worker IS called via spy because
        # ManagerLoopHandler._run_child_dotfile now creates
        # HandlerRegistry(backend=self._backend).
        assert spy.was_called_for("worker") is True, (
            "Expected worker in spy calls — backend should be propagated "
            "to child pipelines via ManagerLoopHandler._run_child_dotfile"
        )


# ---------------------------------------------------------------------------
# TestThreeLevelNesting
# ---------------------------------------------------------------------------


class TestThreeLevelNesting:
    """Tests confirming backend propagation depth across 3 levels (A → B → C)."""

    LEAF_DOT = """\
digraph leaf {
    start [shape=Mdiamond]
    leaf_work [prompt="Do leaf work"]
    done [shape=Msquare]
    start -> leaf_work -> done
}
"""

    MID_DOT = """\
digraph mid {
    start [shape=Mdiamond]
    mid_work [prompt="Do mid work"]
    sub [shape=folder, dot_file="leaf.dot"]
    done [shape=Msquare]
    start -> mid_work -> sub -> done
}
"""

    PARENT_DOT = """\
digraph parent {
    start [shape=Mdiamond]
    parent_work [prompt="Do parent work"]
    sub [shape=folder, dot_file="mid.dot"]
    done [shape=Msquare]
    start -> parent_work -> sub -> done
}
"""

    def _setup_three_level(self, tmp_path):
        """Write leaf.dot and mid.dot; return parsed parent graph + SpyBackend."""
        _write_dot(str(tmp_path / "leaf.dot"), self.LEAF_DOT)
        _write_dot(str(tmp_path / "mid.dot"), self.MID_DOT)

        graph = parse_dot(self.PARENT_DOT)
        graph.source_dir = str(tmp_path)

        spy = SpyBackend()
        return graph, spy

    @pytest.mark.asyncio
    async def test_three_level_nesting_backend_propagated(self, tmp_path):
        """All three levels (parent_work, mid_work, leaf_work) are called via the backend.

        Confirms that backend propagation works across 3 levels of nesting:
        parent → mid (folder) → leaf (folder).
        """
        graph, spy = self._setup_three_level(tmp_path)

        context = PipelineContext()
        registry = HandlerRegistry(backend=spy)
        logs_root = str(tmp_path / "logs")

        engine = PipelineEngine(
            graph=graph,
            context=context,
            handler_registry=registry,
            logs_root=logs_root,
        )
        outcome = await engine.run()

        assert outcome.status == StageStatus.SUCCESS

        assert spy.was_called_for("parent_work") is True, (
            "Expected parent_work in spy calls — top-level codergen node must call backend"
        )
        assert spy.was_called_for("mid_work") is True, (
            "Expected mid_work in spy calls — backend must propagate to level 2"
        )
        assert spy.was_called_for("leaf_work") is True, (
            "Expected leaf_work in spy calls — backend must propagate to level 3"
        )

    @pytest.mark.asyncio
    async def test_three_level_call_order(self, tmp_path):
        """Backend calls follow depth-first order: parent_work → mid_work → leaf_work.

        Confirms that the execution order is depth-first: the parent codergen node
        runs before descending into mid, which runs before descending into leaf.
        """
        graph, spy = self._setup_three_level(tmp_path)

        context = PipelineContext()
        registry = HandlerRegistry(backend=spy)
        logs_root = str(tmp_path / "logs")

        engine = PipelineEngine(
            graph=graph,
            context=context,
            handler_registry=registry,
            logs_root=logs_root,
        )
        outcome = await engine.run()

        assert outcome.status == StageStatus.SUCCESS

        called_ids = [call[0] for call in spy.calls]
        assert "parent_work" in called_ids, "parent_work must appear in spy calls"
        assert "mid_work" in called_ids, "mid_work must appear in spy calls"
        assert "leaf_work" in called_ids, "leaf_work must appear in spy calls"

        parent_idx = called_ids.index("parent_work")
        mid_idx = called_ids.index("mid_work")
        leaf_idx = called_ids.index("leaf_work")

        assert parent_idx < mid_idx, (
            f"Expected parent_work (idx={parent_idx}) before mid_work (idx={mid_idx}) "
            "— depth-first order: parent runs before entering mid pipeline"
        )
        assert mid_idx < leaf_idx, (
            f"Expected mid_work (idx={mid_idx}) before leaf_work (idx={leaf_idx}) "
            "— depth-first order: mid runs before entering leaf pipeline"
        )
