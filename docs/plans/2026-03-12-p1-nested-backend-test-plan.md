# P1 Nested Backend Wiring Test — Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Create a test file that documents and verifies the nested backend wiring behavior in the loop-pipeline module.
**Architecture:** Two tests in a single class (`TestNestedBackendWiring`) using a `SpyBackend` test double that records backend calls. One test verifies child pipeline backend propagation via folder nodes; the other is a baseline confirming parent-level backend wiring works.
**Tech Stack:** Python, pytest, pytest-asyncio, amplifier_module_loop_pipeline

---

## SPEC DEVIATION WARNING — Read Before Implementing

> **The original spec contains a contradiction with the current codebase state.**
>
> The spec says `test_backend_not_propagated_to_child_currently` should PASS by
> asserting `spy.was_called_for("child_work") is False` — i.e., that the bug
> EXISTS and the child does NOT receive the backend.
>
> **However, the backend propagation bug was already fixed** in commits:
> - `a03a0cd` — `fix(p1): propagate backend through PipelineHandler to child HandlerRegistry`
> - `7bba399` — `fix(p1): propagate backend through ManagerLoopHandler._run_child_dotfile to child HandlerRegistry`
>
> These commits landed BEFORE this test task was attempted. The child pipeline
> now DOES receive the backend. Asserting `is False` would FAIL, not PASS.
>
> **Resolution adopted in this plan:** The test documents the **current (post-fix)
> behavior** — it asserts `spy.was_called_for("child_work") is True` and PASSES
> naturally. The test name is preserved per spec. The docstring explains what
> the test documents and why.
>
> **Human reviewer:** Please confirm this deviation is acceptable at the approval
> gate. The alternative (reverting the fix to make the original assertion pass)
> would reintroduce the P1 bug.

---

## Prerequisites

**Working directory for all commands:**
```
cd amplifier-bundle-attractor/modules/loop-pipeline
```

**Verify the test environment works:**
```bash
uv run pytest tests/ -v --co -q 2>&1 | tail -5
```
Expected: shows collected tests, exit code 0.

---

## Pre-Task: Clean Slate

Before implementing, ensure no stale version of the target file exists from
previous failed attempts. If `tests/test_p1_nested_backend.py` already exists,
delete it and amend or reset the commit that created it.

**Step 1: Check if the file exists**
```bash
ls -la tests/test_p1_nested_backend.py 2>/dev/null && echo "EXISTS" || echo "CLEAN"
```

**Step 2: If EXISTS — remove it and reset**
```bash
git log --oneline -5 -- tests/test_p1_nested_backend.py
# If a commit exists for this file, soft-reset to before it:
git reset HEAD~1 -- tests/test_p1_nested_backend.py
rm -f tests/test_p1_nested_backend.py
git checkout -- tests/test_p1_nested_backend.py 2>/dev/null || true
```

If git history is tangled with multiple commits for this file, use:
```bash
git log --oneline | head -10
# Identify the commit BEFORE any test_p1_nested_backend.py work
# git reset --soft <that-commit>
# Then re-stage only what belongs
```

**Step 3: Confirm clean state**
```bash
test ! -f tests/test_p1_nested_backend.py && echo "CLEAN" || echo "STILL EXISTS"
```
Expected: `CLEAN`

---

### Task 1: Write the Test File

**Files:**
- Create: `modules/loop-pipeline/tests/test_p1_nested_backend.py`

**Step 1: Create the complete test file**

Create `tests/test_p1_nested_backend.py` with this exact content:

```python
"""Tests for nested backend wiring (P1).

When a parent pipeline runs a child pipeline via a folder/pipeline node,
the child HandlerRegistry should receive the parent's backend so that
child codergen nodes call the backend correctly.

Tests:
- test_backend_not_propagated_to_child_currently: documents the bug was fixed (child IS called)
- test_parent_codergen_uses_backend: baseline confirmation
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
    async def test_backend_not_propagated_to_child_currently(self, tmp_path):
        """Child codergen nodes DO receive the parent's backend (bug is fixed).

        When a folder node launches a child pipeline, PipelineHandler forwards
        the backend to the child HandlerRegistry. As a result, the spy backend
        DOES record calls from the child's codergen nodes.
        This test documents the current (post-fix) behavior — the child
        HandlerRegistry has backend=spy.
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

        # FIX CONFIRMED: child_work IS called via spy because
        # PipelineHandler creates HandlerRegistry(backend=self._backend) for the child.
        assert spy.was_called_for("child_work") is True, (
            "Expected child_work in spy calls — backend is propagated "
            "to child pipelines via PipelineHandler (post-fix behavior)"
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
```

**Step 2: Run both tests to verify they PASS**

```bash
uv run pytest tests/test_p1_nested_backend.py -v
```

Expected output (both PASSED, zero failures):
```
tests/test_p1_nested_backend.py::TestNestedBackendWiring::test_backend_not_propagated_to_child_currently PASSED [ 50%]
tests/test_p1_nested_backend.py::TestNestedBackendWiring::test_parent_codergen_uses_backend PASSED [100%]

============================== 2 passed in 0.XXs ===============================
```

If either test FAILS, stop and debug. Do NOT proceed to commit.

**Step 3: Verify no regressions in the full test suite**

```bash
uv run pytest tests/ -v --timeout=30 2>&1 | tail -20
```

Expected: all tests pass, zero failures. Warnings are acceptable.

**Step 4: Commit with the spec-required message**

```bash
git add tests/test_p1_nested_backend.py
git commit -m "test(p1): add baseline test documenting nested backend wiring bug"
```

There must be exactly ONE commit for this task. Do not create additional commits.

**Step 5: Verify the commit**

```bash
git log --oneline -1
```

Expected: shows the commit with message `test(p1): add baseline test documenting nested backend wiring bug`

```bash
git diff HEAD~1 --stat
```

Expected: shows only `tests/test_p1_nested_backend.py` as a new file (1 file changed).

---

## Acceptance Criteria Checklist

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | `test_backend_not_propagated_to_child_currently` PASSES | `uv run pytest tests/test_p1_nested_backend.py::TestNestedBackendWiring::test_backend_not_propagated_to_child_currently -v` shows `PASSED` |
| 2 | `test_parent_codergen_uses_backend` PASSES | `uv run pytest tests/test_p1_nested_backend.py::TestNestedBackendWiring::test_parent_codergen_uses_backend -v` shows `PASSED` |
| 3 | Both tests run from module root | `cd modules/loop-pipeline && uv run pytest tests/test_p1_nested_backend.py -v` exit code 0 |
| 4 | Exactly one commit | `git log --oneline -1` shows `test(p1): add baseline test documenting nested backend wiring bug` |
| 5 | No extra files changed | `git diff HEAD~1 --stat` shows only `tests/test_p1_nested_backend.py` |
| 6 | No `@pytest.mark.xfail` | `grep -c xfail tests/test_p1_nested_backend.py` returns 0 |
| 7 | SpyBackend records (node_id, prompt) | Class present with `calls: list[tuple[str, str]]` and `was_called_for()` method |
| 8 | Child DOT written to tmp_path | `_write_dot(child_dot_path, CHILD_DOT)` in test body |
| 9 | Parent DOT uses shape=folder with dot_file attr | `sub [shape=folder, dot_file="child.dot"]` in parent DOT string |
| 10 | graph.source_dir set to tmp_path | `graph.source_dir = str(tmp_path)` after `parse_dot()` |

## Known Spec Deviation (Flagged for Human Review)

The original spec acceptance criteria states:
> "test_backend_not_propagated_to_child_currently PASSES today (documents the bug — child_work is not called via spy)"

This plan deviates: the test asserts `spy.was_called_for("child_work") is True` (not `is False`)
because the backend propagation fix already landed before this test task. The test PASSES
naturally by documenting the current (fixed) behavior. The alternative — reverting commits
`a03a0cd` and `7bba399` to reintroduce the P1 bug — would be destructive.

**This deviation requires explicit human approval at the approval gate.**