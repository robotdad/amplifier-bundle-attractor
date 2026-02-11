# Track 1-1B3: Fix Multi-Class Stylesheet Matching (H-8)

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Fix `.code` selector to match nodes with `class="code,critical"` by splitting comma-separated classes and matching individually.
**Architecture:** The `_selector_matches()` function in `stylesheet.py` line 175 does exact string equality (`sel[1:] == node_class`). The fix splits `node_class` on commas and checks if the selector's class name is in the resulting set.
**Tech Stack:** Python, pytest

**Finding:** H-8 from adversarial-spec-review.md
**Spec Reference:** Section 2.6 -- `class` attribute is "Comma-separated class names for model stylesheet targeting." Section 8.3 -- `.class_name` selector "Matches nodes with that class."

---

## Root Cause

**File:** `modules/loop-pipeline/amplifier_module_loop_pipeline/stylesheet.py` lines 167-176

```python
def _selector_matches(rule: StyleRule, node_id: str, node_class: str) -> bool:
    """Check if a rule's selector matches a node."""
    sel = rule.selector
    if sel == "*":
        return True
    if sel.startswith("#"):
        return sel[1:] == node_id
    if sel.startswith("."):
        return sel[1:] == node_class   # <-- BUG: exact string equality
    return False
```

**Problem:** When a node has `class="code,critical"`, the class selector `.code` checks `"code" == "code,critical"` which is `False`. The spec says classes are comma-separated and individually selectable.

Additionally, `apply_stylesheet()` line 150 passes `node.attrs.get("class", "")` as a single string. The `_selector_matches` function receives the raw comma-separated string and never parses it.

---

## The Fix

### Task 1: Write failing tests for multi-class matching

**Files:**
- Modify: `modules/loop-pipeline/tests/test_stylesheet.py`

**Step 1: Write the failing tests**

Add these tests to the end of `test_stylesheet.py`:

```python
def test_selector_matches_single_class_in_multiclass_node():
    """Spec Section 2.6/8.3: .code must match class='code,critical'."""
    from amplifier_module_loop_pipeline.stylesheet import StyleRule, _selector_matches

    rule = StyleRule(selector=".code", specificity=1, properties={"llm_model": "x"})

    # Single class -- should match
    assert _selector_matches(rule, "node1", "code") is True

    # Multi-class -- should ALSO match
    assert _selector_matches(rule, "node1", "code,critical") is True

    # Different class -- should not match
    assert _selector_matches(rule, "node1", "critical") is False


def test_selector_matches_second_class_in_multiclass_node():
    """The second class in a comma-separated list should also be matchable."""
    from amplifier_module_loop_pipeline.stylesheet import StyleRule, _selector_matches

    rule = StyleRule(selector=".critical", specificity=1, properties={"llm_model": "x"})
    assert _selector_matches(rule, "node1", "code,critical") is True


def test_selector_matches_with_spaces_around_commas():
    """Classes with spaces around commas should still match."""
    from amplifier_module_loop_pipeline.stylesheet import StyleRule, _selector_matches

    rule = StyleRule(selector=".code", specificity=1, properties={"llm_model": "x"})
    assert _selector_matches(rule, "node1", "code, critical") is True
    assert _selector_matches(rule, "node1", " code , critical ") is True


def test_selector_matches_empty_class():
    """Empty class string should not match any class selector."""
    from amplifier_module_loop_pipeline.stylesheet import StyleRule, _selector_matches

    rule = StyleRule(selector=".code", specificity=1, properties={"llm_model": "x"})
    assert _selector_matches(rule, "node1", "") is False


def test_apply_stylesheet_multiclass_node():
    """Integration: stylesheet rule .code applies to node with class='code,critical'."""
    from amplifier_module_loop_pipeline.stylesheet import (
        apply_stylesheet,
        parse_stylesheet,
    )
    from amplifier_module_loop_pipeline.graph import Graph, Node, Edge

    css = '.code { llm_model: claude-opus-4-6; }'
    rules = parse_stylesheet(css)

    graph = Graph(
        name="test",
        nodes={
            "start": Node(id="start", shape="Mdiamond"),
            "work": Node(
                id="work",
                shape="box",
                attrs={"class": "code,critical"},
            ),
            "done": Node(id="done", shape="Msquare"),
        },
        edges=[
            Edge(from_node="start", to_node="work"),
            Edge(from_node="work", to_node="done"),
        ],
    )

    apply_stylesheet(graph, rules)

    # work node has class="code,critical", .code rule should have matched
    assert graph.nodes["work"].attrs.get("llm_model") == "claude-opus-4-6"
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/test_stylesheet.py::test_selector_matches_single_class_in_multiclass_node -xvs`

Expected: FAIL on `assert _selector_matches(rule, "node1", "code,critical") is True`

**Step 3: Commit failing tests**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor
git add modules/loop-pipeline/tests/test_stylesheet.py
git commit -m "test: add multi-class stylesheet matching tests (H-8)"
```

---

### Task 2: Fix `_selector_matches` to split comma-separated classes

**Files:**
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/stylesheet.py` lines 167-176

**Step 1: Replace the `_selector_matches` function**

Find (lines 167-176):

```python
def _selector_matches(rule: StyleRule, node_id: str, node_class: str) -> bool:
    """Check if a rule's selector matches a node."""
    sel = rule.selector
    if sel == "*":
        return True
    if sel.startswith("#"):
        return sel[1:] == node_id
    if sel.startswith("."):
        return sel[1:] == node_class
    return False
```

Replace with:

```python
def _selector_matches(rule: StyleRule, node_id: str, node_class: str) -> bool:
    """Check if a rule's selector matches a node.

    For class selectors (.name), splits comma-separated classes and
    checks membership. Spec Section 2.6: class attribute is
    "Comma-separated class names for model stylesheet targeting."
    """
    sel = rule.selector
    if sel == "*":
        return True
    if sel.startswith("#"):
        return sel[1:] == node_id
    if sel.startswith("."):
        target_class = sel[1:]
        # Split comma-separated classes, strip whitespace, check membership
        node_classes = {c.strip() for c in node_class.split(",") if c.strip()}
        return target_class in node_classes
    return False
```

**Step 2: Run the new stylesheet tests**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/test_stylesheet.py -xvs`

Expected: All PASS (including existing tests)

**Step 3: Run full test suite**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/ -x --tb=short -q`

Expected: All PASS

**Step 4: Commit**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor
git add modules/loop-pipeline/amplifier_module_loop_pipeline/stylesheet.py
git commit -m "fix: split comma-separated classes in stylesheet matching (H-8)

_selector_matches now splits node_class on commas and checks
membership, so .code matches class='code,critical'.

Spec Section 2.6: class is 'Comma-separated class names'.
Spec Section 8.3: .class_name 'Matches nodes with that class'."
```

---

## Backward Compatibility

- **No risk.** Single-class nodes (the only case that worked before) produce a one-element set. `"code" in {"code"}` is `True`, identical to the previous `"code" == "code"`. The only behavioral change is that multi-class nodes now match correctly.

## Dependencies

- None. Self-contained one-function fix.

## PR Details

- **Branch:** `track1/1b3-multiclass-stylesheet`
- **Title:** `fix: multi-class stylesheet matching (H-8, spec Section 2.6/8.3)`
- **Labels:** `track1`, `pipeline`, `spec-compliance`
