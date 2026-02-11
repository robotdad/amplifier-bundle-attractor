# Track 1-1B1: Fix Transform Ordering (H-7)

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Move transforms to run BEFORE validation so that stylesheets can fix invalid configs before they're checked.
**Architecture:** Currently `__init__.py:PipelineOrchestrator.execute()` calls `validate_or_raise(graph)` on line 246, then `engine.py:run()` calls `apply_transforms()` on line 95. The fix moves `apply_transforms()` into `execute()` between parse and validate, and removes it from `engine.run()`.
**Tech Stack:** Python, pytest

**Finding:** H-7 from adversarial-spec-review.md
**Spec Reference:** Section 9.1 -- "Transforms applied after parsing and before validation."

---

## Root Cause

**File:** `modules/loop-pipeline/amplifier_module_loop_pipeline/__init__.py` lines 242-246
**File:** `modules/loop-pipeline/amplifier_module_loop_pipeline/engine.py` lines 94-95

Current execution order in `PipelineOrchestrator.execute()`:
```python
# __init__.py lines 242-246
# 2. Parse the DOT graph
graph = parse_dot(dot_source)

# 3. Validate the graph
validate_or_raise(graph)
```

Then later in `PipelineEngine.run()`:
```python
# engine.py lines 94-95
# Apply transforms (variable expansion, stylesheet) before execution
apply_transforms(self.graph, self.context)
```

**Problem:** Validation runs on the raw parsed graph BEFORE transforms (stylesheet, variable expansion) have been applied. A stylesheet that assigns `llm_model` to nodes will not have taken effect when validation checks for model config. More critically, a future `condition_syntax` or `stylesheet_syntax` validation rule would need the transforms to already be applied.

The spec says (Section 9.1):
```
FUNCTION prepare_pipeline(dot_source):
    graph = parse(dot_source)
    FOR EACH transform IN transforms:
        graph = transform.apply(graph)
    diagnostics = validate(graph)
    RETURN (graph, diagnostics)
```

---

## The Fix

### Task 1: Write failing test that proves transforms run after validation

**Files:**
- Modify: `modules/loop-pipeline/tests/test_transforms.py`

**Step 1: Write the failing test**

Add this test at the end of `test_transforms.py`:

```python
import pytest
from amplifier_module_loop_pipeline.validation import validate_or_raise, ValidationError
from amplifier_module_loop_pipeline.dot_parser import parse_dot
from amplifier_module_loop_pipeline.transforms import apply_transforms
from amplifier_module_loop_pipeline.context import PipelineContext


def test_transform_ordering_transforms_before_validate():
    """Spec 9.1: Transforms must run BEFORE validation.

    A stylesheet that sets llm_model on nodes should be applied before
    validation checks the graph. This test verifies the correct order
    by running parse -> transform -> validate and confirming success.
    """
    dot = '''
    digraph test {
        graph [
            goal="test",
            model_stylesheet="* { llm_model: test-model; llm_provider: test; }"
        ]
        start [shape=Mdiamond]
        work [shape=box, prompt="Do work"]
        done [shape=Msquare]
        start -> work -> done
    }
    '''
    graph = parse_dot(dot)
    ctx = PipelineContext()
    ctx.set("graph.goal", "test")

    # After transforms, nodes should have llm_model set by stylesheet
    apply_transforms(graph, ctx)
    assert graph.nodes["work"].attrs.get("llm_model") == "test-model"

    # Validation should pass on the transformed graph
    diags = validate_or_raise(graph)
    # No errors -- transforms ran first
    assert all(d.severity != "ERROR" for d in diags)
```

**Step 2: Run test to verify it passes (baseline -- this test should pass already)**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/test_transforms.py::test_transform_ordering_transforms_before_validate -xvs`

Expected: PASS (the test itself works; the ordering bug is in the orchestrator)

**Step 3: Write integration test that catches the ordering bug in the orchestrator**

Add to `test_transforms.py`:

```python
@pytest.mark.asyncio
async def test_orchestrator_applies_transforms_before_validation():
    """Integration: PipelineOrchestrator must apply transforms before validation.

    This tests the actual orchestrator execute() path, not just the
    individual functions.
    """
    from amplifier_module_loop_pipeline import PipelineOrchestrator

    dot = '''
    digraph test {
        graph [
            goal="test ordering",
            model_stylesheet="* { llm_model: test-model; }"
        ]
        start [shape=Mdiamond]
        work [shape=box, prompt="Do the work for $goal"]
        done [shape=Msquare]
        start -> work -> done
    }
    '''
    orchestrator = PipelineOrchestrator({"dot_source": dot})

    # This should succeed -- transforms fix the graph before validation
    result_json = await orchestrator.execute(
        prompt="test ordering",
        context=None,
        providers={},
        tools={},
        hooks=None,
    )
    import json
    result = json.loads(result_json)
    # Pipeline should complete (status is success or partial_success from simulation)
    assert result["status"] in ("success", "partial_success")
```

**Step 4: Run integration test**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/test_transforms.py::test_orchestrator_applies_transforms_before_validation -xvs`

Expected: PASS (since the current graph is valid even without transforms; but this establishes the integration pattern)

**Step 5: Commit test**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor
git add modules/loop-pipeline/tests/test_transforms.py
git commit -m "test: add transform ordering tests (H-7)"
```

---

### Task 2: Move transforms before validation in orchestrator

**Files:**
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/__init__.py` lines 242-252
- Modify: `modules/loop-pipeline/amplifier_module_loop_pipeline/engine.py` lines 91-95

**Step 1: Add transforms call before validation in `__init__.py`**

In `__init__.py`, find these lines (around 242-252):

```python
        # 2. Parse the DOT graph
        graph = parse_dot(dot_source)

        # 3. Validate the graph
        validate_or_raise(graph)

        # 4. Create pipeline context with goal from the prompt
        pipeline_context = PipelineContext()
        if prompt:
            pipeline_context.set("graph.goal", prompt)
```

Replace with:

```python
        # 2. Parse the DOT graph
        graph = parse_dot(dot_source)

        # 3. Create pipeline context with goal from the prompt
        #    (needed by transforms for variable expansion)
        pipeline_context = PipelineContext()
        if prompt:
            pipeline_context.set("graph.goal", prompt)

        # 4. Apply transforms BEFORE validation (spec Section 9.1)
        from .transforms import apply_transforms
        apply_transforms(graph, pipeline_context)

        # 5. Validate the transformed graph
        validate_or_raise(graph)
```

**Step 2: Remove duplicate transforms call from `engine.py`**

In `engine.py`, find these lines (around 91-95):

```python
        # Initialize context with graph attributes
        self._initialize_context(goal)

        # Apply transforms (variable expansion, stylesheet) before execution
        apply_transforms(self.graph, self.context)
```

Replace with:

```python
        # Initialize context with graph attributes
        self._initialize_context(goal)

        # NOTE: Transforms are already applied by the orchestrator before
        # validation (spec Section 9.1: parse -> transform -> validate).
        # Do NOT apply transforms again here.
```

**Step 3: Remove unused import from `engine.py`**

In `engine.py`, find and remove this import (line 38):

```python
from .transforms import apply_transforms
```

**Step 4: Renumber comments in `__init__.py`**

Update the subsequent comments in `__init__.py execute()` to reflect the new numbering:
- Old `# 4. Create pipeline context` -> now `# 3`
- Old `# 5. Set up logs directory` -> now `# 6`
- Old `# 6. Resolve backend` -> now `# 7`
- Old `# 7. Register handlers` -> now `# 8`
- Old `# 8. Run the engine` -> now `# 9`
- Old `# 9. Return the final outcome` -> now `# 10`

**Step 5: Run all existing tests to verify nothing breaks**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/ -x --tb=short -q`

Expected: All tests PASS. Some tests may need minor adjustments if they relied on transforms happening inside engine.run() -- check test_engine.py and test_pipeline_e2e.py specifically.

**Step 6: Run the new tests again**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor && python -m pytest modules/loop-pipeline/tests/test_transforms.py -xvs`

Expected: All PASS

**Step 7: Commit**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor
git add modules/loop-pipeline/amplifier_module_loop_pipeline/__init__.py
git add modules/loop-pipeline/amplifier_module_loop_pipeline/engine.py
git commit -m "fix: apply transforms before validation (H-7, spec Section 9.1)

Moves apply_transforms() from engine.run() into
PipelineOrchestrator.execute(), between parse and validate.

This ensures stylesheets and variable expansion take effect
before validation rules check the graph, matching the spec's
prepare_pipeline() order: parse -> transform -> validate."
```

---

## Backward Compatibility

- **Low risk.** The transforms (variable expansion and stylesheet) are idempotent. Running them earlier just means validation sees a more complete graph.
- **Potential issue:** If any test creates a `PipelineEngine` directly (bypassing `PipelineOrchestrator`) and relies on transforms being applied inside `run()`, that test will break. Search for `PipelineEngine(` in tests and verify each test either: (a) pre-applies transforms, or (b) uses a graph that doesn't need transforms.

## Dependencies

- None. This is a self-contained reordering.

## PR Details

- **Branch:** `track1/1b1-transform-ordering`
- **Title:** `fix: apply transforms before validation (H-7)`
- **Labels:** `track1`, `pipeline`, `spec-compliance`
