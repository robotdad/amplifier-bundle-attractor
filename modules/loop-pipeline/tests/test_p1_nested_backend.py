"""Baseline test documenting the nested backend wiring bug (P1).

When a parent pipeline runs a child pipeline via a folder/pipeline node,
the child HandlerRegistry is created WITHOUT the parent's backend.
This means child codergen nodes bypass the backend entirely.

These tests PASS before the fix is applied:
- test_backend_not_propagated_to_child_currently: documents the bug
- test_parent_codergen_uses_backend: baseline confirmation

After the fix, test_backend_not_propagated_to_child_currently should FAIL
and be replaced with a test asserting the backend IS propagated.
"""

from __future__ import annotations

import os

import pytest

from amplifier_module_loop_pipeline.context import PipelineContext
from amplifier_module_loop_pipeline.dot_parser import parse_dot
from amplifier_module_loop_pipeline.engine import PipelineEngine
from amplifier_module_loop_pipeline.graph import Edge, Graph, Node
from amplifier_module_loop_pipeline.handlers import HandlerRegistry
from amplifier_module_loop_pipeline.handlers.manager_loop import ManagerLoopHandler
from amplifier_module_loop_pipeline.handlers.pipeline import PipelineHandler
from amplifier_module_loop_pipeline.outcome import Outcome, StageStatus

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
    """Documents the nested backend wiring bug and provides a baseline check."""

    @pytest.mark.asyncio
    async def test_backend_not_propagated_to_child_currently(self, tmp_path):
        """Child codergen nodes do NOT receive the parent's backend (documents bug).

        When a folder node launches a child pipeline, PipelineHandler creates a
        new HandlerRegistry() without forwarding the backend. As a result, the
        spy backend does not record calls from the child's codergen nodes.

        This test PASSES before the fix, documenting the current broken behavior.
        After the fix is applied, this assertion should be inverted (or replaced).
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

        # BUG DOCUMENTED: child_work is NOT called via spy because
        # PipelineHandler creates HandlerRegistry() without the backend.
        called_node_ids = [call[0] for call in spy.calls]
        assert "child_work" not in called_node_ids, (
            "Expected child_work NOT in spy calls — documents the bug that "
            "backend is not propagated to child pipelines"
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
