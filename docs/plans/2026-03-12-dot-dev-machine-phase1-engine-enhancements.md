# DOT Dev-Machine Phase 1: Engine Enhancements

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Add three small attributes to the Attractor pipeline engine that the DOT dev-machine pipelines require: `continue_on_fail`, `parse_json`, and `tool_env`.
**Architecture:** Two files change — `engine.py` gets `continue_on_fail` handling in the main execution loop; `handlers/tool.py` gets `parse_json` and `tool_env` handling inside the tool handler. Each task is independently testable with a new `test_p{N}_*.py` file.
**Tech Stack:** Python 3.11+, asyncio, pytest + pytest-asyncio (strict mode), `uv run pytest`

---

## Verified Facts (read before coding)

- **Module root:** `modules/loop-pipeline/amplifier_module_loop_pipeline/`
- **Engine:** `engine.py` — `continue_on_fail` inserts after the `auto_status` block (line ~323), before `# Step 3: Record completion`
- **Tool handler:** `handlers/tool.py` — `parse_json` and `tool_env` both go inside `ToolHandler.execute()`
- **Test directory:** `tests/` — naming convention `test_p{N}_*.py` for feature-level tests
- **Existing similar feature:** `auto_status` in engine.py (lines 310–323) — study this before Task 1
- **No conftest.py** — `tmp_path` and `caplog` are built-in pytest fixtures
- **pytest asyncio mode:** `strict` — every async test needs `@pytest.mark.asyncio`
- **Test count baseline:** 997 tests passing — verify with a full run after each task

**Run all tests:**
```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/modules/loop-pipeline
uv run pytest tests/ -v
```

---

## Task 1: `continue_on_fail` Node Attribute (~20 LOC)

**Files:**
- Create: `modules/loop-pipeline/tests/test_p8_continue_on_fail.py`
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/engine.py`

**Behavior:** When a node has `continue_on_fail="true"` in its attrs and the handler returns a FAIL outcome, the engine overrides the outcome to SUCCESS for edge-selection purposes while logging a WARNING with the failure reason. Applies to any node type. Does not affect SUCCESS outcomes.

---

### Step 1: Write the failing tests

Create `modules/loop-pipeline/tests/test_p8_continue_on_fail.py` with this exact content:

```python
"""Tests for continue_on_fail node attribute (Phase 1, Task 1).

When a node has continue_on_fail="true" and the handler returns FAIL,
the engine overrides it to SUCCESS for edge-selection purposes while
logging the failure as a WARNING.
"""

from __future__ import annotations

import logging

import pytest

from amplifier_module_loop_pipeline.context import PipelineContext
from amplifier_module_loop_pipeline.engine import PipelineEngine
from amplifier_module_loop_pipeline.graph import Edge, Graph, Node
from amplifier_module_loop_pipeline.handlers import HandlerRegistry
from amplifier_module_loop_pipeline.outcome import Outcome, StageStatus


class FailingBackend:
    """Backend that returns FAIL for nodes whose IDs start with 'fail_'."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(
        self, node: Node, prompt: str, context: PipelineContext
    ) -> str | Outcome:
        self.calls.append(node.id)
        if node.id.startswith("fail_"):
            return Outcome(
                status=StageStatus.FAIL,
                failure_reason="intentional test failure",
            )
        return "ok"


class TestContinueOnFail:
    """Tests for the continue_on_fail node attribute in the engine."""

    @pytest.mark.asyncio
    async def test_continue_on_fail_overrides_fail_to_success(self, tmp_path):
        """Engine overrides FAIL to SUCCESS when continue_on_fail=true."""
        graph = Graph(
            name="test",
            nodes={
                "start": Node(id="start", shape="Mdiamond"),
                "fail_step": Node(
                    id="fail_step",
                    shape="box",
                    prompt="do work",
                    attrs={"continue_on_fail": "true"},
                ),
                "exit": Node(id="exit", shape="Msquare"),
            },
            edges=[
                Edge(from_node="start", to_node="fail_step"),
                Edge(from_node="fail_step", to_node="exit"),
            ],
        )
        context = PipelineContext()
        registry = HandlerRegistry(backend=FailingBackend())
        engine = PipelineEngine(
            graph=graph,
            context=context,
            handler_registry=registry,
            logs_root=str(tmp_path),
        )
        outcome = await engine.run()
        assert engine.node_outcomes["fail_step"].status == StageStatus.SUCCESS
        assert outcome.status in (StageStatus.SUCCESS, StageStatus.PARTIAL_SUCCESS)

    @pytest.mark.asyncio
    async def test_continue_on_fail_pipeline_continues_to_next_node(self, tmp_path):
        """Pipeline continues executing the next node after continue_on_fail override."""
        backend = FailingBackend()
        graph = Graph(
            name="test",
            nodes={
                "start": Node(id="start", shape="Mdiamond"),
                "fail_step": Node(
                    id="fail_step",
                    shape="box",
                    prompt="do work",
                    attrs={"continue_on_fail": "true"},
                ),
                "next_step": Node(id="next_step", shape="box", prompt="continue"),
                "exit": Node(id="exit", shape="Msquare"),
            },
            edges=[
                Edge(from_node="start", to_node="fail_step"),
                Edge(from_node="fail_step", to_node="next_step"),
                Edge(from_node="next_step", to_node="exit"),
            ],
        )
        context = PipelineContext()
        registry = HandlerRegistry(backend=backend)
        engine = PipelineEngine(
            graph=graph,
            context=context,
            handler_registry=registry,
            logs_root=str(tmp_path),
        )
        await engine.run()
        assert "next_step" in backend.calls

    @pytest.mark.asyncio
    async def test_continue_on_fail_without_flag_preserves_fail(self, tmp_path):
        """Without continue_on_fail, FAIL outcome is not overridden."""
        graph = Graph(
            name="test",
            nodes={
                "start": Node(id="start", shape="Mdiamond"),
                "fail_step": Node(id="fail_step", shape="box", prompt="work"),
                "exit": Node(id="exit", shape="Msquare"),
            },
            edges=[
                Edge(from_node="start", to_node="fail_step"),
                Edge(from_node="fail_step", to_node="exit", condition="outcome=fail"),
            ],
        )
        context = PipelineContext()
        registry = HandlerRegistry(backend=FailingBackend())
        engine = PipelineEngine(
            graph=graph,
            context=context,
            handler_registry=registry,
            logs_root=str(tmp_path),
        )
        await engine.run()
        assert engine.node_outcomes["fail_step"].status == StageStatus.FAIL

    @pytest.mark.asyncio
    async def test_continue_on_fail_logs_warning(self, tmp_path, caplog):
        """continue_on_fail logs a WARNING containing the node id and 'continue_on_fail'."""
        graph = Graph(
            name="test",
            nodes={
                "start": Node(id="start", shape="Mdiamond"),
                "fail_step": Node(
                    id="fail_step",
                    shape="box",
                    prompt="work",
                    attrs={"continue_on_fail": "true"},
                ),
                "exit": Node(id="exit", shape="Msquare"),
            },
            edges=[
                Edge(from_node="start", to_node="fail_step"),
                Edge(from_node="fail_step", to_node="exit"),
            ],
        )
        context = PipelineContext()
        registry = HandlerRegistry(backend=FailingBackend())
        engine = PipelineEngine(
            graph=graph,
            context=context,
            handler_registry=registry,
            logs_root=str(tmp_path),
        )
        with caplog.at_level(
            logging.WARNING,
            logger="amplifier_module_loop_pipeline.engine",
        ):
            await engine.run()
        assert "continue_on_fail" in caplog.text
        assert "fail_step" in caplog.text

    @pytest.mark.asyncio
    async def test_continue_on_fail_does_not_affect_success(self, tmp_path):
        """continue_on_fail on a node that succeeds does not change the outcome."""
        backend = FailingBackend()  # returns "ok" for non-fail_ nodes
        graph = Graph(
            name="test",
            nodes={
                "start": Node(id="start", shape="Mdiamond"),
                "ok_step": Node(
                    id="ok_step",
                    shape="box",
                    prompt="work",
                    attrs={"continue_on_fail": "true"},
                ),
                "exit": Node(id="exit", shape="Msquare"),
            },
            edges=[
                Edge(from_node="start", to_node="ok_step"),
                Edge(from_node="ok_step", to_node="exit"),
            ],
        )
        context = PipelineContext()
        registry = HandlerRegistry(backend=backend)
        engine = PipelineEngine(
            graph=graph,
            context=context,
            handler_registry=registry,
            logs_root=str(tmp_path),
        )
        await engine.run()
        # Node succeeded naturally — status is SUCCESS (not an override artifact)
        assert engine.node_outcomes["ok_step"].status == StageStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_continue_on_fail_works_on_tool_nodes(self, tmp_path):
        """continue_on_fail works on tool nodes (parallelogram shape) via real subprocess."""
        from amplifier_module_loop_pipeline.dot_parser import parse_dot
        from amplifier_module_loop_pipeline.validation import validate_or_raise

        dot_source = """
        digraph {
            start [shape=Mdiamond]
            preflight [shape=parallelogram,
                tool_command="false",
                continue_on_fail="true"]
            work [shape=parallelogram, tool_command="echo done"]
            exit [shape=Msquare]
            start -> preflight -> work -> exit
        }
        """
        graph = parse_dot(dot_source)
        validate_or_raise(graph)
        context = PipelineContext()
        registry = HandlerRegistry()
        engine = PipelineEngine(
            graph=graph,
            context=context,
            handler_registry=registry,
            logs_root=str(tmp_path),
        )
        outcome = await engine.run()
        # Pipeline should reach 'work' and succeed despite 'preflight' failing
        assert "done" in context.get("tool.output", "")
        assert outcome.status in (StageStatus.SUCCESS, StageStatus.PARTIAL_SUCCESS)
```

---

### Step 2: Run tests to verify they fail

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/modules/loop-pipeline
uv run pytest tests/test_p8_continue_on_fail.py -v
```

Expected: All 6 tests FAIL. The `test_continue_on_fail_overrides_fail_to_success` test will fail because the engine currently has no `continue_on_fail` logic, so the failing node's FAIL status is preserved and the pipeline errors trying to find an edge from a FAIL outcome.

---

### Step 3: Write the implementation

Open `amplifier_module_loop_pipeline/engine.py`.

Find the `auto_status` block (around line 310–323):
```python
            # L-9: auto_status — override non-success to SUCCESS when enabled
            if current_node.auto_status is True and not outcome.is_success:
                logger.debug(
                    "Node '%s' has auto_status=true; overriding %s to SUCCESS",
                    current_node.id,
                    outcome.status.value,
                )
                outcome = Outcome(
                    status=StageStatus.SUCCESS,
                    notes=f"auto_status override (was {outcome.status.value})",
                    context_updates=outcome.context_updates,
                    preferred_label=outcome.preferred_label,
                    suggested_next_ids=outcome.suggested_next_ids,
                )
```

Immediately after that block (before `# Step 3: Record completion`), insert:
```python

            # continue_on_fail: override FAIL to SUCCESS for routing, log the failure
            if (
                current_node.attrs.get("continue_on_fail") == "true"
                and outcome.status == StageStatus.FAIL
            ):
                logger.warning(
                    "Node '%s' failed but continue_on_fail=true; overriding to SUCCESS "
                    "(failure: %s)",
                    current_node.id,
                    outcome.failure_reason or outcome.notes or "no reason given",
                )
                outcome = Outcome(
                    status=StageStatus.SUCCESS,
                    notes=(
                        f"continue_on_fail override (was FAIL: "
                        f"{outcome.failure_reason or outcome.notes})"
                    ),
                    context_updates=outcome.context_updates,
                    preferred_label=outcome.preferred_label,
                    suggested_next_ids=outcome.suggested_next_ids,
                )
```

The result should look like:
```python
            # L-9: auto_status — override non-success to SUCCESS when enabled
            if current_node.auto_status is True and not outcome.is_success:
                logger.debug(
                    "Node '%s' has auto_status=true; overriding %s to SUCCESS",
                    current_node.id,
                    outcome.status.value,
                )
                outcome = Outcome(
                    status=StageStatus.SUCCESS,
                    notes=f"auto_status override (was {outcome.status.value})",
                    context_updates=outcome.context_updates,
                    preferred_label=outcome.preferred_label,
                    suggested_next_ids=outcome.suggested_next_ids,
                )

            # continue_on_fail: override FAIL to SUCCESS for routing, log the failure
            if (
                current_node.attrs.get("continue_on_fail") == "true"
                and outcome.status == StageStatus.FAIL
            ):
                logger.warning(
                    "Node '%s' failed but continue_on_fail=true; overriding to SUCCESS "
                    "(failure: %s)",
                    current_node.id,
                    outcome.failure_reason or outcome.notes or "no reason given",
                )
                outcome = Outcome(
                    status=StageStatus.SUCCESS,
                    notes=(
                        f"continue_on_fail override (was FAIL: "
                        f"{outcome.failure_reason or outcome.notes})"
                    ),
                    context_updates=outcome.context_updates,
                    preferred_label=outcome.preferred_label,
                    suggested_next_ids=outcome.suggested_next_ids,
                )

            # Step 3: Record completion
            self.completed_nodes.append(current_node.id)
```

No imports need to change — `logger`, `Outcome`, and `StageStatus` are already imported at the top of `engine.py`.

---

### Step 4: Run tests to verify they pass

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/modules/loop-pipeline
uv run pytest tests/test_p8_continue_on_fail.py -v
```

Expected: All 6 tests PASS.

---

### Step 5: Run the full suite to verify no regressions

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/modules/loop-pipeline
uv run pytest tests/ -v
```

Expected: 997 existing tests + 6 new = 1003 tests PASS. Zero failures.

---

### Step 6: Commit

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/modules/loop-pipeline
git add amplifier_module_loop_pipeline/engine.py tests/test_p8_continue_on_fail.py
git commit -m "feat: add continue_on_fail node attribute to engine

When a node has continue_on_fail=\"true\" and the handler returns FAIL,
the engine overrides the outcome to SUCCESS for edge-selection while
logging a WARNING with the failure reason. Needed by dev-machine
preflight steps (spec-drift-check, api-inventory, module-health-check)
that are informational and must not halt the pipeline.

Tests: test_p8_continue_on_fail.py (6 tests)"
```

---

## Task 2: `parse_json` Flag on Tool Nodes (~30 LOC)

**Files:**
- Create: `modules/loop-pipeline/tests/test_p9_parse_json.py`
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/handlers/tool.py`

**Behavior:** When a `parallelogram` (tool) node has `parse_json="true"`, after the command executes successfully, the handler `json.loads()` the stdout. If the result is a dict, each key-value pair is injected into the pipeline context via `context.set(key, value)` and included in the outcome's `context_updates`. If JSON parsing fails, log a WARNING and continue — the node still returns SUCCESS.

---

### Step 1: Write the failing tests

Create `modules/loop-pipeline/tests/test_p9_parse_json.py` with this exact content:

```python
"""Tests for parse_json tool node flag (Phase 1, Task 2).

When a tool node has parse_json="true", after executing the command,
the handler auto-parses JSON stdout and injects each top-level key
into the pipeline context via context.set(key, value).
"""

from __future__ import annotations

import json
import logging

import pytest

from amplifier_module_loop_pipeline.context import PipelineContext
from amplifier_module_loop_pipeline.graph import Graph, Node
from amplifier_module_loop_pipeline.handlers.tool import ToolHandler
from amplifier_module_loop_pipeline.outcome import StageStatus


def _make_graph() -> Graph:
    return Graph(
        name="test",
        nodes={"start": Node(id="start", shape="Mdiamond")},
        edges=[],
    )


def _make_context() -> PipelineContext:
    return PipelineContext()


class TestParseJson:
    """Tests for the parse_json attribute on tool nodes."""

    @pytest.mark.asyncio
    async def test_parse_json_injects_keys_into_context(self, tmp_path):
        """parse_json=true injects JSON stdout keys as context variables."""
        data = {"status": "healthy", "epoch": 3, "phase": "build"}
        command = f"echo '{json.dumps(data)}'"
        node = Node(
            id="orient",
            attrs={"tool_command": command, "parse_json": "true"},
        )
        handler = ToolHandler()
        ctx = _make_context()
        outcome = await handler.execute(node, ctx, _make_graph(), str(tmp_path))
        assert outcome.status == StageStatus.SUCCESS
        assert ctx.get("status") == "healthy"
        assert ctx.get("epoch") == 3
        assert ctx.get("phase") == "build"

    @pytest.mark.asyncio
    async def test_parse_json_not_set_does_not_parse(self, tmp_path):
        """Without parse_json, JSON stdout is not parsed into context."""
        data = {"status": "healthy"}
        command = f"echo '{json.dumps(data)}'"
        node = Node(id="tool", attrs={"tool_command": command})
        handler = ToolHandler()
        ctx = _make_context()
        await handler.execute(node, ctx, _make_graph(), str(tmp_path))
        # "status" key must NOT be injected from JSON parsing
        assert ctx.get("status") is None

    @pytest.mark.asyncio
    async def test_parse_json_malformed_json_logs_warning_and_succeeds(
        self, tmp_path, caplog
    ):
        """parse_json with invalid JSON logs a WARNING but still returns SUCCESS."""
        node = Node(
            id="bad_json",
            attrs={
                "tool_command": "echo 'not valid json'",
                "parse_json": "true",
            },
        )
        handler = ToolHandler()
        ctx = _make_context()
        with caplog.at_level(logging.WARNING):
            outcome = await handler.execute(node, ctx, _make_graph(), str(tmp_path))
        assert outcome.status == StageStatus.SUCCESS
        assert any(
            "parse_json" in r.message.lower() or "json" in r.message.lower()
            for r in caplog.records
        )

    @pytest.mark.asyncio
    async def test_parse_json_non_dict_json_not_injected(self, tmp_path):
        """parse_json with a JSON array does not inject keys (only dicts supported)."""
        node = Node(
            id="array_json",
            attrs={"tool_command": "echo '[1, 2, 3]'", "parse_json": "true"},
        )
        handler = ToolHandler()
        ctx = _make_context()
        outcome = await handler.execute(node, ctx, _make_graph(), str(tmp_path))
        assert outcome.status == StageStatus.SUCCESS
        # tool.output is still set, but no numeric keys are injected
        assert ctx.get("tool.output") is not None
        assert ctx.get(0) is None

    @pytest.mark.asyncio
    async def test_parse_json_keys_included_in_context_updates(self, tmp_path):
        """parse_json keys are in the outcome's context_updates dict."""
        data = {"build_status": "clean", "test_count": 42}
        command = f"echo '{json.dumps(data)}'"
        node = Node(
            id="build_check",
            attrs={"tool_command": command, "parse_json": "true"},
        )
        handler = ToolHandler()
        ctx = _make_context()
        outcome = await handler.execute(node, ctx, _make_graph(), str(tmp_path))
        assert outcome.status == StageStatus.SUCCESS
        assert outcome.context_updates is not None
        assert outcome.context_updates.get("build_status") == "clean"
        assert outcome.context_updates.get("test_count") == 42

    @pytest.mark.asyncio
    async def test_parse_json_tool_output_still_set(self, tmp_path):
        """tool.output is still set in context even when parse_json is used."""
        data = {"key": "value"}
        raw_json = json.dumps(data)
        command = f"echo '{raw_json}'"
        node = Node(
            id="tool",
            attrs={"tool_command": command, "parse_json": "true"},
        )
        handler = ToolHandler()
        ctx = _make_context()
        await handler.execute(node, ctx, _make_graph(), str(tmp_path))
        assert "tool.output" in (ctx.get("tool.output") or "") or ctx.get("tool.output") is not None
        assert raw_json in ctx.get("tool.output", "")

    @pytest.mark.asyncio
    async def test_parse_json_failed_command_not_parsed(self, tmp_path):
        """parse_json is not invoked when the command exits non-zero."""
        node = Node(
            id="fail_tool",
            attrs={"tool_command": "false", "parse_json": "true"},
        )
        handler = ToolHandler()
        ctx = _make_context()
        outcome = await handler.execute(node, ctx, _make_graph(), str(tmp_path))
        assert outcome.status == StageStatus.FAIL
        # No keys should be injected from a failed command
        assert ctx.get("status") is None
```

---

### Step 2: Run tests to verify they fail

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/modules/loop-pipeline
uv run pytest tests/test_p9_parse_json.py -v
```

Expected: Most tests FAIL. The `test_parse_json_not_set_does_not_parse` and `test_parse_json_failed_command_not_parsed` tests may pass (existing behavior), but the injection tests will fail because the tool handler doesn't yet parse JSON.

---

### Step 3: Write the implementation

Replace the entire content of `amplifier_module_loop_pipeline/handlers/tool.py` with:

```python
"""Tool node handler — executes shell commands.

Reads the tool_command from node attributes, executes it via subprocess,
captures stdout, and returns SUCCESS or FAIL based on exit code.

Attributes supported:
    parse_json: When "true", auto-parses JSON stdout and injects each
        top-level key into pipeline context after successful execution.
    tool_env: Comma-separated context variable names to inject as
        uppercased environment variables before command execution.

Spec coverage: TOOL-001–004, Section 4.10.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from ..context import PipelineContext
from ..graph import Graph, Node
from ..outcome import Outcome, StageStatus

logger = logging.getLogger(__name__)


class ToolHandler:
    """Handler for tool nodes (shape=parallelogram).

    Executes an external command configured via the node's
    ``tool_command`` attribute.
    """

    async def execute(
        self,
        node: Node,
        context: PipelineContext,
        graph: Graph,
        logs_root: str,
    ) -> Outcome:
        """Execute a tool command and return the outcome.

        Writes command.txt and output.txt to the stage log directory.
        Stores stdout in context as ``tool.output``.
        """
        command = node.attrs.get("tool_command", "")
        if not command:
            return Outcome(
                status=StageStatus.FAIL,
                failure_reason="No tool_command specified on node",
            )

        # Write command to logs
        stage_dir = os.path.join(logs_root, node.id)
        os.makedirs(stage_dir, exist_ok=True)
        _write_file(os.path.join(stage_dir, "command.txt"), command)

        # M-16: Read timeout from node attribute (seconds)
        timeout_s: float | None = None
        if node.timeout is not None:
            timeout_s = float(node.timeout)

        # tool_env: resolve context vars and inject as uppercase env vars
        env: dict[str, str] | None = None
        tool_env_raw = node.attrs.get("tool_env", "")
        if tool_env_raw:
            env = os.environ.copy()
            for var_name in (v.strip() for v in tool_env_raw.split(",")):
                if var_name:
                    value = context.get(var_name)
                    if value is not None:
                        env[var_name.upper()] = str(value)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_s
                )
            except asyncio.TimeoutError:
                # Kill the process on timeout
                proc.kill()
                await proc.wait()
                return Outcome(
                    status=StageStatus.FAIL,
                    failure_reason=f"Timeout after {timeout_s}s: {command}",
                )
            stdout_text = stdout_bytes.decode(errors="replace") if stdout_bytes else ""
            stderr_text = stderr_bytes.decode(errors="replace") if stderr_bytes else ""

            # Write output to logs
            _write_file(
                os.path.join(stage_dir, "output.txt"),
                stdout_text + stderr_text,
            )

            if proc.returncode != 0:
                return Outcome(
                    status=StageStatus.FAIL,
                    failure_reason=(
                        f"Command exited with code {proc.returncode}: "
                        f"{stderr_text.strip() or stdout_text.strip()}"
                    ),
                )

            # Store stdout in context
            context.set("tool.output", stdout_text)
            context_updates: dict[str, Any] = {"tool.output": stdout_text}

            # parse_json: auto-parse JSON stdout and inject top-level keys into context
            if node.attrs.get("parse_json") == "true":
                try:
                    parsed = json.loads(stdout_text)
                    if isinstance(parsed, dict):
                        for key, value in parsed.items():
                            context.set(key, value)
                            context_updates[key] = value
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(
                        "parse_json: could not parse stdout as JSON for node '%s': %s",
                        node.id,
                        e,
                    )

            return Outcome(
                status=StageStatus.SUCCESS,
                context_updates=context_updates,
                notes=f"Tool completed: {command}",
            )
        except Exception as e:
            return Outcome(
                status=StageStatus.FAIL,
                failure_reason=str(e),
            )


def _write_file(path: str, content: str) -> None:
    """Write content to a file."""
    with open(path, "w") as f:
        f.write(content)
```

---

### Step 4: Run tests to verify they pass

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/modules/loop-pipeline
uv run pytest tests/test_p9_parse_json.py -v
```

Expected: All 7 tests PASS.

---

### Step 5: Run the full suite to verify no regressions

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/modules/loop-pipeline
uv run pytest tests/ -v
```

Expected: 1003 existing tests + 7 new = 1010 tests PASS. Zero failures.

---

### Step 6: Commit

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/modules/loop-pipeline
git add amplifier_module_loop_pipeline/handlers/tool.py tests/test_p9_parse_json.py
git commit -m "feat: add parse_json flag to tool handler

When a tool node has parse_json=\"true\", after successful command
execution, stdout is parsed as JSON and each top-level key is injected
into the pipeline context via context.set(). Keys also included in
outcome.context_updates for diamond-node routing. Malformed JSON logs
a WARNING but does not fail the node. Needed by dev-machine orient,
build-check, and post-session-status nodes that output structured JSON.

Tests: test_p9_parse_json.py (7 tests)"
```

---

## Task 3: `tool_env` Attribute (~30 LOC)

**Files:**
- Create: `modules/loop-pipeline/tests/test_p10_tool_env.py`
- No new source changes needed — `tool.py` already has `tool_env` from Task 2

> **Note:** Task 2 already implemented `tool_env` in the complete `tool.py` replacement above. Task 3 only adds the tests. If you followed Task 2 exactly, the `tool_env` code is already in place.

**Behavior:** When a tool node has `tool_env="state_file,build_command"`, the handler reads each comma-separated variable name from pipeline context, converts to uppercase (`state_file` → `STATE_FILE`), and passes as environment variables to the subprocess. Variables not found in context are silently skipped. Leading/trailing whitespace around names is trimmed.

---

### Step 1: Write the failing tests

Create `modules/loop-pipeline/tests/test_p10_tool_env.py` with this exact content:

```python
"""Tests for tool_env attribute on tool nodes (Phase 1, Task 3).

When a tool node has tool_env="state_file,build_command", before executing
the command, the handler resolves each named variable from pipeline context
and injects it as an environment variable (STATE_FILE, BUILD_COMMAND) into
the subprocess environment.
"""

from __future__ import annotations

import pytest

from amplifier_module_loop_pipeline.context import PipelineContext
from amplifier_module_loop_pipeline.graph import Graph, Node
from amplifier_module_loop_pipeline.handlers.tool import ToolHandler
from amplifier_module_loop_pipeline.outcome import StageStatus


def _make_graph() -> Graph:
    return Graph(
        name="test",
        nodes={"start": Node(id="start", shape="Mdiamond")},
        edges=[],
    )


def _make_context(**kwargs) -> PipelineContext:
    ctx = PipelineContext()
    for key, value in kwargs.items():
        ctx.set(key, value)
    return ctx


class TestToolEnv:
    """Tests for the tool_env attribute on tool nodes."""

    @pytest.mark.asyncio
    async def test_tool_env_injects_single_var_as_env_var(self, tmp_path):
        """tool_env injects a context variable as an uppercased environment variable."""
        ctx = _make_context(state_file="/project/.dev-machine/STATE.yaml")
        node = Node(
            id="orient",
            attrs={
                "tool_command": "echo $STATE_FILE",
                "tool_env": "state_file",
            },
        )
        handler = ToolHandler()
        outcome = await handler.execute(node, ctx, _make_graph(), str(tmp_path))
        assert outcome.status == StageStatus.SUCCESS
        assert "/project/.dev-machine/STATE.yaml" in ctx.get("tool.output", "")

    @pytest.mark.asyncio
    async def test_tool_env_injects_multiple_vars(self, tmp_path):
        """tool_env comma-separated list injects multiple context vars as env vars."""
        ctx = _make_context(
            build_command="uv run pytest",
            test_command="uv run pytest tests/",
        )
        node = Node(
            id="build_check",
            attrs={
                "tool_command": 'echo "BUILD=$BUILD_COMMAND TEST=$TEST_COMMAND"',
                "tool_env": "build_command,test_command",
            },
        )
        handler = ToolHandler()
        outcome = await handler.execute(node, ctx, _make_graph(), str(tmp_path))
        assert outcome.status == StageStatus.SUCCESS
        output = ctx.get("tool.output", "")
        assert "uv run pytest" in output

    @pytest.mark.asyncio
    async def test_tool_env_uppercase_conversion(self, tmp_path):
        """tool_env converts snake_case var names to UPPER_CASE env var names."""
        ctx = _make_context(my_project_path="/home/user/myproject")
        node = Node(
            id="tool",
            attrs={
                "tool_command": "echo $MY_PROJECT_PATH",
                "tool_env": "my_project_path",
            },
        )
        handler = ToolHandler()
        outcome = await handler.execute(node, ctx, _make_graph(), str(tmp_path))
        assert outcome.status == StageStatus.SUCCESS
        assert "/home/user/myproject" in ctx.get("tool.output", "")

    @pytest.mark.asyncio
    async def test_tool_env_missing_context_var_skipped_no_crash(self, tmp_path):
        """tool_env silently skips context vars that are not set in context."""
        ctx = _make_context()  # empty — missing_var is not set
        node = Node(
            id="tool",
            attrs={
                "tool_command": "echo hello",
                "tool_env": "missing_var",
            },
        )
        handler = ToolHandler()
        outcome = await handler.execute(node, ctx, _make_graph(), str(tmp_path))
        # Must not crash; node succeeds even when tool_env var is absent
        assert outcome.status == StageStatus.SUCCESS
        assert "hello" in ctx.get("tool.output", "")

    @pytest.mark.asyncio
    async def test_tool_env_whitespace_trimmed_from_var_names(self, tmp_path):
        """tool_env trims whitespace around variable names in the comma-separated list."""
        ctx = _make_context(state_file="/trimmed/STATE.yaml")
        node = Node(
            id="tool",
            attrs={
                "tool_command": "echo $STATE_FILE",
                "tool_env": " state_file ",  # leading/trailing whitespace
            },
        )
        handler = ToolHandler()
        outcome = await handler.execute(node, ctx, _make_graph(), str(tmp_path))
        assert outcome.status == StageStatus.SUCCESS
        assert "/trimmed/STATE.yaml" in ctx.get("tool.output", "")

    @pytest.mark.asyncio
    async def test_tool_env_not_set_does_not_inject(self, tmp_path):
        """Without tool_env, context vars are NOT injected as env vars."""
        # Use a highly unique var name to avoid collision with real env
        ctx = _make_context(attractor_unique_test_xyz="/my/unique/path")
        node = Node(
            id="tool",
            attrs={
                "tool_command": "echo ${ATTRACTOR_UNIQUE_TEST_XYZ:-NOT_SET}",
                # No tool_env attribute
            },
        )
        handler = ToolHandler()
        outcome = await handler.execute(node, ctx, _make_graph(), str(tmp_path))
        assert outcome.status == StageStatus.SUCCESS
        # The env var should NOT be set — should print NOT_SET
        assert "NOT_SET" in ctx.get("tool.output", "")
        assert "/my/unique/path" not in ctx.get("tool.output", "")

    @pytest.mark.asyncio
    async def test_tool_env_with_parse_json_combined(self, tmp_path):
        """tool_env and parse_json can be used together on the same node."""
        import json

        ctx = _make_context(project_dir="/myproject")
        data = {"status": "healthy", "loc": 5000}
        node = Node(
            id="health_check",
            attrs={
                # Command uses the injected env var and produces JSON
                "tool_command": f"echo '{json.dumps(data)}'",
                "tool_env": "project_dir",
                "parse_json": "true",
            },
        )
        handler = ToolHandler()
        outcome = await handler.execute(node, ctx, _make_graph(), str(tmp_path))
        assert outcome.status == StageStatus.SUCCESS
        # parse_json should have injected the keys
        assert ctx.get("status") == "healthy"
        assert ctx.get("loc") == 5000
```

---

### Step 2: Run tests to verify they pass (or fail if tool_env wasn't in Task 2)

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/modules/loop-pipeline
uv run pytest tests/test_p10_tool_env.py -v
```

**If Task 2 was done with the complete `tool.py` above:** All 7 tests should already PASS (tool_env was already implemented).

**If any tests fail:** Verify that `tool.py` contains the `tool_env` block (around line 30–45 of the new file). The block reads `node.attrs.get("tool_env", "")`, builds an `env` dict from `os.environ.copy()`, and passes it as `env=env` to `asyncio.create_subprocess_shell`.

---

### Step 3: Run the full suite

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/modules/loop-pipeline
uv run pytest tests/ -v
```

Expected: 1010 existing tests + 7 new = 1017 tests PASS. Zero failures.

---

### Step 4: Commit

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/modules/loop-pipeline
git add tests/test_p10_tool_env.py
git commit -m "feat: add tool_env attribute to tool handler (tests)

tool_env=\"state_file,build_command\" resolves each named variable from
pipeline context and injects it as an uppercase environment variable
(STATE_FILE, BUILD_COMMAND) into the subprocess. Missing context vars
are silently skipped. Whitespace around names is trimmed. Combined use
with parse_json is supported. Needed by dev-machine tool nodes that
reference project-specific paths via \$state_file, \$build_command.

Tests: test_p10_tool_env.py (7 tests)"
```

---

## Final Verification

Run the complete test suite one last time to confirm Phase 1 is clean:

```bash
cd /home/bkrabach/dev/attractor-dev-machine/amplifier-bundle-attractor/modules/loop-pipeline
uv run pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected output:
```
================== 1017 passed in X.XXs ==================
```

---

## Summary

| Task | Feature | LOC | File | Tests |
|------|---------|-----|------|-------|
| 1 | `continue_on_fail` | ~18 | `engine.py` | 6 in `test_p8_continue_on_fail.py` |
| 2 | `parse_json` | ~14 | `handlers/tool.py` | 7 in `test_p9_parse_json.py` |
| 3 | `tool_env` | ~10 | `handlers/tool.py` | 7 in `test_p10_tool_env.py` |

Total: ~42 LOC implementation, 3 new test files, 20 new tests.

After these three tasks, the engine can express:
- `continue_on_fail="true"` — preflight nodes that log failures without halting the pipeline
- `parse_json="true"` — tool nodes whose JSON stdout drives diamond-node routing via context variables
- `tool_env="state_file,build_command"` — tool nodes that receive project-specific paths as shell environment variables
