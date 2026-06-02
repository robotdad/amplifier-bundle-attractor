"""Tests for subgraph runtime-context propagation in PipelineHandler.

Bug: the injection loop in PipelineHandler.execute() overwrites a cloned context key
with the RAW DOT-file attribute string instead of substituting against the parent
runtime snapshot.  For example, a folder node attr like

    context.child_input="${build.artifact_id}"

stores the literal template string ``"${build.artifact_id}"`` in the child context,
clobbering the good cloned value and leaving downstream ``${child_input}``
substitution unresolved.

Fix: pre-substitute each attr value against the parent snapshot before storing it
in the child context.

All test identifiers use neutral names (parent_runtime_key, build.artifact_id,
child_input) unrelated to any private project terminology.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from amplifier_module_loop_pipeline.context import PipelineContext
from amplifier_module_loop_pipeline.graph import Edge, Graph, Node
from amplifier_module_loop_pipeline.handlers import HandlerRegistry
from amplifier_module_loop_pipeline.handlers.context import HandlerContext
from amplifier_module_loop_pipeline.handlers.pipeline import PipelineHandler
from amplifier_module_loop_pipeline.outcome import StageStatus


# ---------------------------------------------------------------------------
# Minimal backend that captures the child-context snapshot at each node run
# ---------------------------------------------------------------------------


class _ContextCapturingBackend:
    """Records the context snapshot seen at each child node execution.

    Returning the plain string "done" is sufficient — the child engine treats
    it as a successful text response for a default (non-pipeline) node.
    """

    def __init__(self) -> None:
        self.captured: dict[str, dict] = {}

    async def run(
        self,
        node: Node,
        prompt: str,
        context: PipelineContext,
        incoming_edge=None,
        graph=None,
    ) -> str:
        self.captured[node.id] = context.snapshot()
        return "done"

    def context_for(self, node_id: str) -> dict:
        """Return the captured context snapshot for *node_id*, or {} if absent."""
        return self.captured.get(node_id, {})


def _make_capturing_factory() -> tuple[_ContextCapturingBackend, object]:
    """Return (backend, factory) so tests can inspect the child context later.

    All HandlerRegistry instances returned by the factory share the same
    backend, which records the child context snapshot for every node it runs.
    """

    backend = _ContextCapturingBackend()

    def factory() -> HandlerRegistry:
        return HandlerRegistry(HandlerContext(backend=backend))

    return backend, factory


# ---------------------------------------------------------------------------
# Minimal child DOT file shared by all tests
# ---------------------------------------------------------------------------

_CHILD_DOT = """\
digraph child {
    start [shape=Mdiamond]
    work  [prompt="child work"]
    done  [shape=Msquare]
    start -> work -> done
}
"""


def _make_folder_node(dot_file: str, extra_attrs: dict[str, str]) -> Node:
    """Build a folder/pipeline Node pointing at *dot_file* with *extra_attrs*."""
    attrs: dict[str, str] = {"dot_file": dot_file, **extra_attrs}
    return Node(id="sub", shape="folder", type="pipeline", attrs=attrs)


def _make_parent_graph(folder_node: Node, source_dir: str) -> Graph:
    """Wrap *folder_node* in a minimal start → sub → done graph."""
    return Graph(
        name="parent",
        nodes={
            "start": Node(id="start", shape="Mdiamond"),
            "sub": folder_node,
            "done": Node(id="done", shape="Msquare"),
        },
        edges=[
            Edge(from_node="start", to_node="sub"),
            Edge(from_node="sub", to_node="done"),
        ],
        source_dir=source_dir,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSubgraphRuntimeContextPropagation:
    """PipelineHandler.execute() must pre-substitute attr values against the
    parent runtime snapshot before injecting them into the child context."""

    # ------------------------------------------------------------------
    # Test 1 — main regression: runtime parent value propagates correctly
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_runtime_parent_value_propagates_to_child_context(
        self, tmp_path: Path
    ) -> None:
        """context.child_input="${build.artifact_id}" resolves to the parent runtime value.

        Setup:
        - Parent context has ``build.artifact_id = "abc123"`` set at runtime.
        - Folder node attr: ``context.child_input = "${build.artifact_id}"``.

        Expected (after fix):
        - Child context ``child_input == "abc123"`` (resolved from parent snapshot).

        Before fix the injection loop stores the literal template string
        ``"${build.artifact_id}"``, which is the wrong value.
        """
        child_dot = tmp_path / "child.dot"
        child_dot.write_text(_CHILD_DOT)

        parent_runtime_key = "build.artifact_id"
        parent_runtime_value = "abc123"

        node = _make_folder_node(
            str(child_dot),
            {"context.child_input": f"${{{parent_runtime_key}}}"},
        )
        graph = _make_parent_graph(node, str(tmp_path))

        parent_context = PipelineContext()
        parent_context.set(parent_runtime_key, parent_runtime_value)

        backend, factory = _make_capturing_factory()
        handler = PipelineHandler(handler_registry_factory=factory)
        outcome = await handler.execute(
            node, parent_context, graph, str(tmp_path / "logs")
        )

        assert outcome.status == StageStatus.SUCCESS

        child_ctx = backend.context_for("work")
        child_input_value = child_ctx.get("child_input")
        assert child_input_value == parent_runtime_value, (
            f"Expected child_input={parent_runtime_value!r} (resolved from parent "
            f"runtime snapshot), but got {child_input_value!r}. "
            "The injection loop must substitute attr values against the parent "
            "snapshot instead of storing the raw template string."
        )

    # ------------------------------------------------------------------
    # Test 2 — regression guard: static attr value passes through unchanged
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_static_attr_value_injected_unchanged(self, tmp_path: Path) -> None:
        """context.literal_key="hello" injects "hello" unchanged into child context.

        Static attr values (no ``$`` tokens) must pass through as-is after the fix.
        """
        child_dot = tmp_path / "child.dot"
        child_dot.write_text(_CHILD_DOT)

        node = _make_folder_node(
            str(child_dot),
            {"context.literal_key": "hello"},
        )
        graph = _make_parent_graph(node, str(tmp_path))

        parent_context = PipelineContext()
        backend, factory = _make_capturing_factory()
        handler = PipelineHandler(handler_registry_factory=factory)
        outcome = await handler.execute(
            node, parent_context, graph, str(tmp_path / "logs")
        )

        assert outcome.status == StageStatus.SUCCESS

        child_ctx = backend.context_for("work")
        literal_value = child_ctx.get("literal_key")
        assert literal_value == "hello", (
            f"Expected literal_key='hello' (unchanged static value), "
            f"got {literal_value!r}."
        )

    # ------------------------------------------------------------------
    # Test 3 — absent parent key passes through literally (substitute_context
    #           semantics: unknown tokens are left unchanged)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_absent_parent_key_passes_through_literally(
        self, tmp_path: Path
    ) -> None:
        """context.child_input="${missing.key}" passes through as-is when key is absent.

        ``substitute_context`` semantics: tokens whose key is not in the snapshot
        are left unchanged.  This must hold after the fix.
        """
        child_dot = tmp_path / "child.dot"
        child_dot.write_text(_CHILD_DOT)

        node = _make_folder_node(
            str(child_dot),
            {"context.child_input": "${missing.key}"},
        )
        graph = _make_parent_graph(node, str(tmp_path))

        parent_context = PipelineContext()  # "missing.key" is NOT set
        backend, factory = _make_capturing_factory()
        handler = PipelineHandler(handler_registry_factory=factory)
        outcome = await handler.execute(
            node, parent_context, graph, str(tmp_path / "logs")
        )

        assert outcome.status == StageStatus.SUCCESS

        child_ctx = backend.context_for("work")
        child_input_value = child_ctx.get("child_input")
        assert child_input_value == "${missing.key}", (
            f"Expected literal passthrough '${{missing.key}}' for absent parent key, "
            f"got {child_input_value!r}."
        )
