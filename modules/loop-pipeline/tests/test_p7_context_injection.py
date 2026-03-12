"""Tests for P7: context variable injection from parent nodes into child pipelines.

When a folder node (PipelineHandler) or house node (ManagerLoopHandler) has
attributes like context.my_var="hello", the child pipeline should be able to
reference $my_var in its prompts.

Task 6: Baseline tests documenting the current (broken) behavior.
Task 8: Tests replaced/added after the fix is in place.
"""

from __future__ import annotations

import pytest

from amplifier_module_loop_pipeline.context import PipelineContext
from amplifier_module_loop_pipeline.dot_parser import parse_dot
from amplifier_module_loop_pipeline.engine import PipelineEngine
from amplifier_module_loop_pipeline.graph import Node
from amplifier_module_loop_pipeline.handlers import HandlerRegistry
from amplifier_module_loop_pipeline.outcome import StageStatus


# ---------------------------------------------------------------------------
# CapturingBackend
# ---------------------------------------------------------------------------


class CapturingBackend:
    """Records node_id → prompt text and node_id → context snapshot."""

    def __init__(self) -> None:
        self.prompts: dict[str, str] = {}
        self.context_snapshots: dict[str, dict] = {}

    async def run(self, node: Node, prompt: str, context: PipelineContext) -> str:
        self.prompts[node.id] = prompt
        self.context_snapshots[node.id] = context.snapshot()
        return "done"

    def prompt_for(self, node_id: str) -> str:
        """Return the captured prompt for a node, or '' if not captured."""
        return self.prompts.get(node_id, "")

    def context_for(self, node_id: str) -> dict:
        """Return the captured context snapshot for a node, or {} if not captured."""
        return self.context_snapshots.get(node_id, {})


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _write_dot(path: str, content: str) -> None:
    """Write DOT content to a file at the given path."""
    with open(path, "w") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# TestContextInjectionPipelineHandler — baselines (Task 6)
# ---------------------------------------------------------------------------


class TestContextInjectionPipelineHandler:
    """Baseline tests documenting context injection behavior for folder nodes.

    These tests document the CURRENT state of the system:
    - test_context_attr_not_injected_today: BUG — $topic is NOT expanded today
    - test_parent_context_key_available_in_child_before_fix: $goal works via clone

    Both should PASS (they document current behavior, not desired behavior).
    """

    @pytest.mark.asyncio
    async def test_context_attr_not_injected_today(self, tmp_path):
        """BUG BASELINE: context.topic attr on folder node is NOT injected today.

        Parent has context.topic="auth service" on the folder node.
        Child DOT has $topic in its prompt.
        Without the fix, $topic is NOT expanded — the raw token remains.

        This test PASSES today (it documents the bug).
        It will be REPLACED by test_context_attr_injected_into_child after the fix.
        """
        child_dot = """\
digraph child {
    start [shape=Mdiamond]
    work [prompt="Review the $topic architecture"]
    done [shape=Msquare]
    start -> work -> done
}
"""
        child_path = tmp_path / "child.dot"
        _write_dot(str(child_path), child_dot)

        parent_dot = f"""\
digraph parent {{
    start [shape=Mdiamond]
    sub [shape=folder, dot_file="{child_path}", "context.topic"="auth service"]
    done [shape=Msquare]
    start -> sub -> done
}}
"""
        graph = parse_dot(parent_dot)
        graph.source_dir = str(tmp_path)

        capturing = CapturingBackend()
        context = PipelineContext()
        registry = HandlerRegistry(backend=capturing)
        logs_root = str(tmp_path / "logs")

        engine = PipelineEngine(
            graph=graph,
            context=context,
            handler_registry=registry,
            logs_root=logs_root,
        )
        outcome = await engine.run()

        assert outcome.status == StageStatus.SUCCESS
        work_prompt = capturing.prompt_for("work")

        # BUG DOCUMENTED: $topic is NOT expanded — raw token remains in prompt
        assert "$topic" in work_prompt, (
            f"Expected raw '$topic' to remain in prompt (bug documented), "
            f"got: {work_prompt!r}"
        )
        assert "auth service" not in work_prompt, (
            f"Expected 'auth service' NOT in prompt before fix, got: {work_prompt!r}"
        )

    @pytest.mark.asyncio
    async def test_parent_context_key_available_in_child_before_fix(self, tmp_path):
        """graph.goal from parent IS available in child (this works via clone).

        Baseline confirming that context.clone() already propagates graph.goal.
        The child prompt $goal should expand to the parent's goal text.
        This works WITHOUT any fix (via clone).
        """
        child_dot = """\
digraph child {
    start [shape=Mdiamond]
    work [prompt="Implement $goal system"]
    done [shape=Msquare]
    start -> work -> done
}
"""
        child_path = tmp_path / "child.dot"
        _write_dot(str(child_path), child_dot)

        parent_dot = f"""\
digraph parent {{
    goal = "user authentication"
    start [shape=Mdiamond]
    sub [shape=folder, dot_file="{child_path}"]
    done [shape=Msquare]
    start -> sub -> done
}}
"""
        graph = parse_dot(parent_dot)
        graph.source_dir = str(tmp_path)

        capturing = CapturingBackend()
        context = PipelineContext()
        registry = HandlerRegistry(backend=capturing)
        logs_root = str(tmp_path / "logs")

        engine = PipelineEngine(
            graph=graph,
            context=context,
            handler_registry=registry,
            logs_root=logs_root,
        )
        outcome = await engine.run(goal="user authentication")

        assert outcome.status == StageStatus.SUCCESS
        work_prompt = capturing.prompt_for("work")

        # BASELINE: graph.goal IS available in child via context clone
        assert "user authentication" in work_prompt, (
            f"Expected parent's goal 'user authentication' in child prompt "
            f"(this works via clone), got: {work_prompt!r}"
        )
