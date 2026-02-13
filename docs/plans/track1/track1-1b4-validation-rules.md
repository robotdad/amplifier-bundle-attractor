# Track 1-1B4: Add 5 Missing Validation Lint Rules (C-10)

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Add the 5 missing lint rules from spec Section 7.2: `condition_syntax` (ERROR), `stylesheet_syntax` (ERROR), `type_known` (WARNING), `fidelity_valid` (WARNING), `retry_target_exists` (WARNING).
**Architecture:** Each rule is a private function in `validation.py` following the existing pattern `_check_<rule>(graph, diags)`. The two ERROR rules import the condition parser and stylesheet parser respectively to validate syntax. The three WARNING rules perform lookup checks against known sets and graph node IDs.
**Tech Stack:** Python, pytest

**Finding:** C-10 from adversarial-spec-review.md
**Spec Reference:** Section 7.2 -- Built-In Lint Rules table

---

## Root Cause

**File:** `modules/loop-pipeline/amplifier_module_loop_pipeline/validation.py`

Current `validate()` function (lines 58-75) calls 8 rule functions:

```python
def validate(graph: Graph) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    _check_start_node(graph, diags)
    _check_terminal_node(graph, diags)
    _check_edge_targets(graph, diags)
    _check_start_no_incoming(graph, diags)
    _check_exit_no_outgoing(graph, diags)
    _check_reachability(graph, diags)
    _check_goal_gate_has_retry(graph, diags)
    _check_prompt_on_llm_nodes(graph, diags)
    return diags
```

**Missing 5 rules per spec Section 7.2:**

| Rule | Severity | What it checks |
|------|----------|----------------|
| `condition_syntax` | ERROR | Edge condition expressions must parse correctly |
| `stylesheet_syntax` | ERROR | `model_stylesheet` must parse as valid stylesheet |
| `type_known` | WARNING | Node `type` values should be in `SHAPE_TO_HANDLER` values |
| `fidelity_valid` | WARNING | Fidelity mode values must be in `VALID_FIDELITY_MODES` |
| `retry_target_exists` | WARNING | `retry_target` and `fallback_retry_target` must reference existing node IDs |

**Impact of missing ERROR rules:** Invalid condition expressions (`condition="outcome === fail"`) and malformed stylesheets (`model_stylesheet="{ broken"`) pass validation silently and crash at runtime.

---

## The Fix

### Task 1: Write failing tests for `condition_syntax` rule

**Files:**
- Modify: `modules/loop-pipeline/tests/test_validation.py`

**Step 1: Write the failing tests**

Add to the end of `test_validation.py`:

```python
def test_condition_syntax_valid_conditions():
    """condition_syntax: valid conditions produce no diagnostics."""
    from amplifier_module_loop_pipeline.validation import validate

    graph = _make_graph(
        edges_extra=[
            Edge(from_node="work", to_node="done", condition="outcome=success"),
        ]
    )
    diags = validate(graph)
    condition_diags = [d for d in diags if d.rule == "condition_syntax"]
    assert len(condition_diags) == 0


def test_condition_syntax_invalid_condition_is_error():
    """condition_syntax: malformed condition expression produces ERROR."""
    from amplifier_module_loop_pipeline.validation import validate

    graph = _make_graph(
        edges_extra=[
            Edge(from_node="work", to_node="done", condition="===broken"),
        ]
    )
    diags = validate(graph)
    condition_diags = [d for d in diags if d.rule == "condition_syntax"]
    assert len(condition_diags) == 1
    assert condition_diags[0].severity == "ERROR"


def test_condition_syntax_empty_condition_ok():
    """condition_syntax: empty condition is always valid (means unconditional)."""
    from amplifier_module_loop_pipeline.validation import validate

    graph = _make_graph(
        edges_extra=[
            Edge(from_node="work", to_node="done", condition=""),
        ]
    )
    diags = validate(graph)
    condition_diags = [d for d in diags if d.rule == "condition_syntax"]
    assert len(condition_diags) == 0
```

You also need a `_make_graph` helper if it doesn't already exist. Add at the top of the test file (below imports) if missing:

```python
from amplifier_module_loop_pipeline.graph import Graph, Node, Edge


def _make_graph(edges_extra=None, nodes_extra=None, graph_attrs=None):
    """Helper to build a minimal valid graph with optional extras."""
    nodes = {
        "start": Node(id="start", shape="Mdiamond"),
        "work": Node(id="work", shape="box", prompt="do work"),
        "done": Node(id="done", shape="Msquare"),
    }
    if nodes_extra:
        for n in nodes_extra:
            nodes[n.id] = n

    edges = [
        Edge(from_node="start", to_node="work"),
        Edge(from_node="work", to_node="done"),
    ]
    if edges_extra:
        edges.extend(edges_extra)

    return Graph(
        name="test",
        nodes=nodes,
        edges=edges,
        graph_attrs=graph_attrs or {},
    )
```

**Step 2: Run to verify tests fail**

Run: `cd /path/to/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/test_validation.py::test_condition_syntax_invalid_condition_is_error -xvs`

Expected: FAIL -- `assert len(condition_diags) == 1` fails because the rule doesn't exist yet

**Step 3: Commit**

```bash
cd /path/to/amplifier-bundle-attractor
git add modules/loop-pipeline/tests/test_validation.py
git commit -m "test: add condition_syntax validation tests (C-10)"
```

---

### Task 2: Implement `_check_condition_syntax` rule

**Files:**
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/validation.py`

**Step 1: Add the import for the condition parser**

At the top of `validation.py`, after the existing imports (line 15), add:

```python
from .conditions import evaluate_condition
from .context import PipelineContext
from .outcome import Outcome, StageStatus
```

**Step 2: Add the `_check_condition_syntax` function**

Add after `_check_prompt_on_llm_nodes` (after line 269):

```python
def _check_condition_syntax(graph: Graph, diags: list[Diagnostic]) -> None:
    """LINT: condition_syntax -- edge condition expressions must parse correctly.

    Attempts to evaluate each non-empty condition with dummy values.
    If the parser raises, the condition has invalid syntax.
    """
    dummy_outcome = Outcome(status=StageStatus.SUCCESS)
    dummy_context = PipelineContext()

    for edge in graph.edges:
        if not edge.condition or not edge.condition.strip():
            continue
        try:
            evaluate_condition(edge.condition, dummy_outcome, dummy_context)
        except Exception as exc:
            diags.append(
                Diagnostic(
                    rule="condition_syntax",
                    severity="ERROR",
                    message=(
                        f"Edge {edge.from_node} -> {edge.to_node}: "
                        f"invalid condition expression '{edge.condition}': {exc}"
                    ),
                    edge=(edge.from_node, edge.to_node),
                    fix="Fix the condition expression syntax (supported: key=value, key!=value, &&)",
                )
            )
```

**Step 3: Register the rule in `validate()`**

In the `validate()` function, add after `_check_prompt_on_llm_nodes(graph, diags)`:

```python
    _check_condition_syntax(graph, diags)
```

**Step 4: Run condition_syntax tests**

Run: `cd /path/to/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/test_validation.py -k "condition_syntax" -xvs`

Expected: All PASS

**Step 5: Commit**

```bash
git add modules/loop-pipeline/amplifier_module_loop_pipeline/validation.py
git commit -m "feat: add condition_syntax validation rule (C-10, spec 7.2)"
```

---

### Task 3: Write tests and implement `_check_stylesheet_syntax` rule

**Files:**
- Modify: `modules/loop-pipeline/tests/test_validation.py`
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/validation.py`

**Step 1: Write the failing tests**

Add to `test_validation.py`:

```python
def test_stylesheet_syntax_valid():
    """stylesheet_syntax: valid stylesheet produces no diagnostics."""
    from amplifier_module_loop_pipeline.validation import validate

    graph = _make_graph(
        graph_attrs={"model_stylesheet": "* { llm_model: test; }"}
    )
    graph.model_stylesheet = "* { llm_model: test; }"
    diags = validate(graph)
    style_diags = [d for d in diags if d.rule == "stylesheet_syntax"]
    assert len(style_diags) == 0


def test_stylesheet_syntax_empty_ok():
    """stylesheet_syntax: empty stylesheet is valid."""
    from amplifier_module_loop_pipeline.validation import validate

    graph = _make_graph()
    graph.model_stylesheet = ""
    diags = validate(graph)
    style_diags = [d for d in diags if d.rule == "stylesheet_syntax"]
    assert len(style_diags) == 0


def test_stylesheet_syntax_invalid_is_error():
    """stylesheet_syntax: unparseable stylesheet produces ERROR."""
    from amplifier_module_loop_pipeline.validation import validate

    graph = _make_graph()
    # Completely broken syntax -- no valid rules extractable
    graph.model_stylesheet = "{{{{not valid css at all"
    diags = validate(graph)
    style_diags = [d for d in diags if d.rule == "stylesheet_syntax"]
    assert len(style_diags) == 1
    assert style_diags[0].severity == "ERROR"
```

**Step 2: Implement the rule**

Add the import at the top of `validation.py`:

```python
from .stylesheet import parse_stylesheet
```

Add the function after `_check_condition_syntax`:

```python
def _check_stylesheet_syntax(graph: Graph, diags: list[Diagnostic]) -> None:
    """LINT: stylesheet_syntax -- model_stylesheet must parse as valid rules.

    Attempts to parse the stylesheet. If parsing produces no rules from
    non-empty input, the stylesheet has invalid syntax.
    """
    css = graph.model_stylesheet
    if not css or not css.strip():
        return

    try:
        rules = parse_stylesheet(css)
    except Exception as exc:
        diags.append(
            Diagnostic(
                rule="stylesheet_syntax",
                severity="ERROR",
                message=f"model_stylesheet failed to parse: {exc}",
                fix="Fix the stylesheet syntax. Format: selector { property: value; }",
            )
        )
        return

    # If there was non-trivial content but no rules extracted, it's invalid
    if not rules and len(css.strip()) > 5:
        diags.append(
            Diagnostic(
                rule="stylesheet_syntax",
                severity="ERROR",
                message="model_stylesheet contains content but no valid rules were parsed",
                fix="Fix the stylesheet syntax. Format: selector { property: value; }",
            )
        )
```

Register in `validate()`:

```python
    _check_stylesheet_syntax(graph, diags)
```

**Step 3: Run tests**

Run: `cd /path/to/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/test_validation.py -k "stylesheet_syntax" -xvs`

Expected: All PASS

**Step 4: Commit**

```bash
git add modules/loop-pipeline/amplifier_module_loop_pipeline/validation.py modules/loop-pipeline/tests/test_validation.py
git commit -m "feat: add stylesheet_syntax validation rule (C-10, spec 7.2)"
```

---

### Task 4: Write tests and implement `_check_type_known` rule

**Files:**
- Modify: `modules/loop-pipeline/tests/test_validation.py`
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/validation.py`

**Step 1: Write the failing tests**

Add to `test_validation.py`:

```python
def test_type_known_valid_type():
    """type_known: recognized type produces no warning."""
    from amplifier_module_loop_pipeline.validation import validate

    graph = _make_graph(
        nodes_extra=[
            Node(id="gate", shape="box", type="conditional", prompt="decide"),
        ],
        edges_extra=[
            Edge(from_node="work", to_node="gate"),
            Edge(from_node="gate", to_node="done"),
        ],
    )
    diags = validate(graph)
    type_diags = [d for d in diags if d.rule == "type_known"]
    assert len(type_diags) == 0


def test_type_known_unknown_type_warns():
    """type_known: unrecognized type produces WARNING."""
    from amplifier_module_loop_pipeline.validation import validate

    graph = _make_graph(
        nodes_extra=[
            Node(id="custom", shape="box", type="nonexistent_handler", prompt="x"),
        ],
        edges_extra=[
            Edge(from_node="work", to_node="custom"),
            Edge(from_node="custom", to_node="done"),
        ],
    )
    diags = validate(graph)
    type_diags = [d for d in diags if d.rule == "type_known"]
    assert len(type_diags) == 1
    assert type_diags[0].severity == "WARNING"
    assert "nonexistent_handler" in type_diags[0].message


def test_type_known_empty_type_ok():
    """type_known: empty type (shape-based resolution) is always valid."""
    from amplifier_module_loop_pipeline.validation import validate

    graph = _make_graph()  # work node has type="" (default)
    diags = validate(graph)
    type_diags = [d for d in diags if d.rule == "type_known"]
    assert len(type_diags) == 0
```

**Step 2: Implement the rule**

Add after `_check_stylesheet_syntax`:

```python
# All known handler types (values from SHAPE_TO_HANDLER mapping)
_KNOWN_HANDLER_TYPES: frozenset[str] = frozenset(SHAPE_TO_HANDLER.values())


def _check_type_known(graph: Graph, diags: list[Diagnostic]) -> None:
    """LINT: type_known -- node type values should be recognized handler types."""
    for node in graph.nodes.values():
        if not node.type:
            continue  # empty type uses shape-based resolution, always valid
        if node.type not in _KNOWN_HANDLER_TYPES:
            diags.append(
                Diagnostic(
                    rule="type_known",
                    severity="WARNING",
                    message=(
                        f"Node '{node.id}' has unknown type '{node.type}'. "
                        f"Known types: {', '.join(sorted(_KNOWN_HANDLER_TYPES))}"
                    ),
                    node_id=node.id,
                    fix=f"Use a recognized type or register a custom handler for '{node.type}'",
                )
            )
```

Register in `validate()`:

```python
    _check_type_known(graph, diags)
```

**Step 3: Run tests**

Run: `cd /path/to/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/test_validation.py -k "type_known" -xvs`

Expected: All PASS

**Step 4: Commit**

```bash
git add modules/loop-pipeline/amplifier_module_loop_pipeline/validation.py modules/loop-pipeline/tests/test_validation.py
git commit -m "feat: add type_known validation rule (C-10, spec 7.2)"
```

---

### Task 5: Write tests and implement `_check_fidelity_valid` rule

**Files:**
- Modify: `modules/loop-pipeline/tests/test_validation.py`
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/validation.py`

**Step 1: Write the failing tests**

Add to `test_validation.py`:

```python
def test_fidelity_valid_recognized_mode():
    """fidelity_valid: recognized fidelity mode produces no warning."""
    from amplifier_module_loop_pipeline.validation import validate

    graph = _make_graph()
    graph.nodes["work"].attrs["fidelity"] = "full"
    diags = validate(graph)
    fid_diags = [d for d in diags if d.rule == "fidelity_valid"]
    assert len(fid_diags) == 0


def test_fidelity_valid_invalid_mode_warns():
    """fidelity_valid: unrecognized fidelity mode produces WARNING."""
    from amplifier_module_loop_pipeline.validation import validate

    graph = _make_graph()
    graph.nodes["work"].attrs["fidelity"] = "typo_fidelity"
    diags = validate(graph)
    fid_diags = [d for d in diags if d.rule == "fidelity_valid"]
    assert len(fid_diags) == 1
    assert fid_diags[0].severity == "WARNING"
    assert "typo_fidelity" in fid_diags[0].message


def test_fidelity_valid_graph_default():
    """fidelity_valid: invalid graph default_fidelity produces WARNING."""
    from amplifier_module_loop_pipeline.validation import validate

    graph = _make_graph(graph_attrs={"default_fidelity": "invalid_mode"})
    diags = validate(graph)
    fid_diags = [d for d in diags if d.rule == "fidelity_valid"]
    assert len(fid_diags) >= 1
    assert any("invalid_mode" in d.message for d in fid_diags)


def test_fidelity_valid_edge_fidelity():
    """fidelity_valid: invalid edge fidelity produces WARNING."""
    from amplifier_module_loop_pipeline.validation import validate

    graph = _make_graph(
        edges_extra=[
            Edge(
                from_node="work",
                to_node="done",
                attrs={"fidelity": "bogus"},
            ),
        ]
    )
    diags = validate(graph)
    fid_diags = [d for d in diags if d.rule == "fidelity_valid"]
    assert len(fid_diags) >= 1
```

**Step 2: Implement the rule**

Add the import at the top of `validation.py`:

```python
from .fidelity import VALID_FIDELITY_MODES
```

Add the function:

```python
def _check_fidelity_valid(graph: Graph, diags: list[Diagnostic]) -> None:
    """LINT: fidelity_valid -- fidelity mode values must be recognized."""
    # Check node-level fidelity
    for node in graph.nodes.values():
        fidelity = node.attrs.get("fidelity")
        if fidelity and fidelity not in VALID_FIDELITY_MODES:
            diags.append(
                Diagnostic(
                    rule="fidelity_valid",
                    severity="WARNING",
                    message=(
                        f"Node '{node.id}' has unrecognized fidelity mode '{fidelity}'. "
                        f"Valid modes: {', '.join(sorted(VALID_FIDELITY_MODES))}"
                    ),
                    node_id=node.id,
                    fix=f"Use one of: {', '.join(sorted(VALID_FIDELITY_MODES))}",
                )
            )

    # Check graph-level default_fidelity
    graph_fidelity = graph.graph_attrs.get("default_fidelity")
    if graph_fidelity and graph_fidelity not in VALID_FIDELITY_MODES:
        diags.append(
            Diagnostic(
                rule="fidelity_valid",
                severity="WARNING",
                message=(
                    f"Graph attribute default_fidelity has unrecognized value '{graph_fidelity}'. "
                    f"Valid modes: {', '.join(sorted(VALID_FIDELITY_MODES))}"
                ),
                fix=f"Use one of: {', '.join(sorted(VALID_FIDELITY_MODES))}",
            )
        )

    # Check edge-level fidelity
    for edge in graph.edges:
        edge_fidelity = edge.attrs.get("fidelity")
        if edge_fidelity and edge_fidelity not in VALID_FIDELITY_MODES:
            diags.append(
                Diagnostic(
                    rule="fidelity_valid",
                    severity="WARNING",
                    message=(
                        f"Edge {edge.from_node} -> {edge.to_node} has unrecognized "
                        f"fidelity mode '{edge_fidelity}'. "
                        f"Valid modes: {', '.join(sorted(VALID_FIDELITY_MODES))}"
                    ),
                    edge=(edge.from_node, edge.to_node),
                    fix=f"Use one of: {', '.join(sorted(VALID_FIDELITY_MODES))}",
                )
            )
```

Register in `validate()`:

```python
    _check_fidelity_valid(graph, diags)
```

**Step 3: Run tests**

Run: `cd /path/to/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/test_validation.py -k "fidelity_valid" -xvs`

Expected: All PASS

**Step 4: Commit**

```bash
git add modules/loop-pipeline/amplifier_module_loop_pipeline/validation.py modules/loop-pipeline/tests/test_validation.py
git commit -m "feat: add fidelity_valid validation rule (C-10, spec 7.2)"
```

---

### Task 6: Write tests and implement `_check_retry_target_exists` rule

**Files:**
- Modify: `modules/loop-pipeline/tests/test_validation.py`
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/validation.py`

**Step 1: Write the failing tests**

Add to `test_validation.py`:

```python
def test_retry_target_exists_valid():
    """retry_target_exists: target pointing to real node is ok."""
    from amplifier_module_loop_pipeline.validation import validate

    graph = _make_graph()
    graph.nodes["work"].attrs["retry_target"] = "work"  # points to itself
    diags = validate(graph)
    rt_diags = [d for d in diags if d.rule == "retry_target_exists"]
    assert len(rt_diags) == 0


def test_retry_target_exists_missing_target_warns():
    """retry_target_exists: target pointing to nonexistent node produces WARNING."""
    from amplifier_module_loop_pipeline.validation import validate

    graph = _make_graph()
    graph.nodes["work"].attrs["retry_target"] = "nonexistent_node"
    diags = validate(graph)
    rt_diags = [d for d in diags if d.rule == "retry_target_exists"]
    assert len(rt_diags) == 1
    assert rt_diags[0].severity == "WARNING"
    assert "nonexistent_node" in rt_diags[0].message


def test_retry_target_exists_fallback_missing_warns():
    """retry_target_exists: fallback_retry_target with bad reference warns."""
    from amplifier_module_loop_pipeline.validation import validate

    graph = _make_graph()
    graph.nodes["work"].attrs["fallback_retry_target"] = "ghost"
    diags = validate(graph)
    rt_diags = [d for d in diags if d.rule == "retry_target_exists"]
    assert len(rt_diags) == 1


def test_retry_target_exists_graph_level():
    """retry_target_exists: graph-level retry_target with bad reference warns."""
    from amplifier_module_loop_pipeline.validation import validate

    graph = _make_graph(graph_attrs={"retry_target": "nonexistent"})
    diags = validate(graph)
    rt_diags = [d for d in diags if d.rule == "retry_target_exists"]
    assert len(rt_diags) >= 1
```

**Step 2: Implement the rule**

Add the function:

```python
def _check_retry_target_exists(graph: Graph, diags: list[Diagnostic]) -> None:
    """LINT: retry_target_exists -- retry targets must reference existing nodes."""
    node_ids = set(graph.nodes.keys())

    # Check node-level retry targets
    for node in graph.nodes.values():
        for attr_name in ("retry_target", "fallback_retry_target"):
            target = node.attrs.get(attr_name)
            if target and target not in node_ids:
                diags.append(
                    Diagnostic(
                        rule="retry_target_exists",
                        severity="WARNING",
                        message=(
                            f"Node '{node.id}' has {attr_name}='{target}' "
                            f"but no node with ID '{target}' exists"
                        ),
                        node_id=node.id,
                        fix=f"Set {attr_name} to a valid node ID or remove it",
                    )
                )

    # Check graph-level retry targets
    for attr_name in ("retry_target", "fallback_retry_target"):
        target = graph.graph_attrs.get(attr_name)
        if target and target not in node_ids:
            diags.append(
                Diagnostic(
                    rule="retry_target_exists",
                    severity="WARNING",
                    message=(
                        f"Graph attribute {attr_name}='{target}' "
                        f"references nonexistent node '{target}'"
                    ),
                    fix=f"Set graph {attr_name} to a valid node ID or remove it",
                )
            )
```

Register in `validate()`:

```python
    _check_retry_target_exists(graph, diags)
```

**Step 3: Run tests**

Run: `cd /path/to/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/test_validation.py -k "retry_target_exists" -xvs`

Expected: All PASS

**Step 4: Run full test suite**

Run: `cd /path/to/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/ -x --tb=short -q`

Expected: All PASS

**Step 5: Commit**

```bash
git add modules/loop-pipeline/amplifier_module_loop_pipeline/validation.py modules/loop-pipeline/tests/test_validation.py
git commit -m "feat: add retry_target_exists validation rule (C-10, spec 7.2)

Completes all 5 missing validation rules from spec Section 7.2:
- condition_syntax (ERROR)
- stylesheet_syntax (ERROR)
- type_known (WARNING)
- fidelity_valid (WARNING)
- retry_target_exists (WARNING)

The validate() function now checks all 13 spec-defined lint rules."
```

---

## Final `validate()` Function After All Rules

```python
def validate(graph: Graph) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    _check_start_node(graph, diags)          # existing
    _check_terminal_node(graph, diags)       # existing
    _check_edge_targets(graph, diags)        # existing
    _check_start_no_incoming(graph, diags)   # existing
    _check_exit_no_outgoing(graph, diags)    # existing
    _check_reachability(graph, diags)        # existing
    _check_goal_gate_has_retry(graph, diags) # existing
    _check_prompt_on_llm_nodes(graph, diags) # existing
    _check_condition_syntax(graph, diags)    # NEW
    _check_stylesheet_syntax(graph, diags)   # NEW
    _check_type_known(graph, diags)          # NEW
    _check_fidelity_valid(graph, diags)      # NEW
    _check_retry_target_exists(graph, diags) # NEW
    return diags
```

## Backward Compatibility

- **Medium risk.** The two new ERROR rules (`condition_syntax`, `stylesheet_syntax`) may cause previously-passing graphs to fail validation if they contain malformed conditions or stylesheets that were silently ignored before. This is the correct behavior -- they would have crashed at runtime anyway.
- The three WARNING rules won't block execution, only produce diagnostics.
- Existing tests may need updates if they use graphs with intentionally invalid conditions/stylesheets. Search for `condition=` and `model_stylesheet=` in test fixtures.

## Dependencies

- Imports `evaluate_condition` from `conditions.py` (already exists)
- Imports `parse_stylesheet` from `stylesheet.py` (already exists)
- Imports `VALID_FIDELITY_MODES` from `fidelity.py` (already exists)

## PR Details

- **Branch:** `track1/1b4-validation-rules`
- **Title:** `feat: add 5 missing validation lint rules (C-10, spec Section 7.2)`
- **Labels:** `track1`, `pipeline`, `spec-compliance`, `critical`
