# E2E Pipeline Tests Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Add pipeline-mode E2E tests that exercise all 3 DOT fixtures (`simple_file_creation.dot`, `plan_implement_review.dot`, `conditional_routing.dot`) via the existing `attractor-e2e-pipeline-anthropic` profile, so the E2E suite covers both agent-only and pipeline orchestration.

**Architecture:** Extend `tests/e2e/run_e2e.sh` with a new `run_pipeline_test` helper that (1) runs `amplifier init --yes` once to resolve local module sources, (2) invokes `amplifier run` with the pipeline profile and per-test `dot_file` overrides, and (3) validates output artifacts. The pipeline currently uses `DirectProviderBackend` fallback since `session.spawn` isn't registered by `amplifier run`; this is acceptable for Phase 1C (Track 2 fixes spawn).

**Tech Stack:** Bash (E2E script), Amplifier CLI, DOT fixtures, YAML profiles

---

## Problem Statement

The E2E test script (`tests/e2e/run_e2e.sh`) only runs 3 tests, all using `--mode single` (agent-only). A pipeline E2E profile exists at `profiles/attractor-e2e-pipeline-anthropic.yaml` and 3 DOT fixtures exist in `tests/e2e/fixtures/`, but NONE are invoked by any E2E test. This means the pipeline orchestrator (loop-pipeline) has zero E2E coverage.

## Root Cause

1. The E2E script was written for agent-only mode and never extended for pipeline mode.
2. The pipeline profile uses `source: ./modules/loop-pipeline` (local path), which requires `amplifier init --yes` before `amplifier run` -- the E2E script doesn't do this.
3. The pipeline profile hardcodes `dot_file: ./tests/e2e/fixtures/simple_file_creation.dot`, so testing other fixtures requires either config overrides or per-fixture profiles.
4. No one added pipeline test cases to the script.

## Dependencies

- Existing agent E2E tests must continue to pass (don't break the 3 existing tests).
- Requires `ANTHROPIC_API_KEY` in environment (same as existing tests).
- The pipeline uses `DirectProviderBackend` fallback (C-3 from adversarial review) -- this is a known limitation, not a blocker.

---

### Task 1: Add `amplifier init` Setup Step to E2E Script

**Files:**
- Modify: `tests/e2e/run_e2e.sh`

**Step 1: Add init step after WORK_DIR setup**

After the `cd "$WORK_DIR"` line and before the first `echo "========="` banner, add an initialization block:

```bash
# Initialize bundle so local module sources (./modules/*) are resolved
echo "Initializing bundle for local module resolution..."
cd "$BUNDLE_ROOT"
amplifier init --yes 2>&1 | tail -5
cd "$WORK_DIR"
```

This ensures `./modules/loop-pipeline` and other local sources are properly set up before any pipeline test runs. The agent-only tests don't need this (they use git sources), but it's harmless.

**Step 2: Verify existing tests still pass**

Run:
```bash
cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor && bash tests/e2e/run_e2e.sh
```
Expected: All 3 existing agent tests pass. The `amplifier init` step completes without error.

**Step 3: Commit**
```
feat(e2e): add amplifier init step for local module resolution

The pipeline E2E profile uses local source paths (./modules/loop-pipeline)
which require amplifier init --yes before amplifier run. Add this as a
setup step before the test suite runs.

Part of: Track 1 Phase 1C - E2E pipeline test coverage (H-14)
```

---

### Task 2: Add `run_pipeline_test` Helper Function

**Files:**
- Modify: `tests/e2e/run_e2e.sh`

**Step 1: Add the `run_pipeline_test` function after the existing `run_test` function**

```bash
run_pipeline_test() {
    local name="$1"
    local dot_fixture="$2"
    local check="$3"
    local timeout="${4:-180}"

    echo ""
    echo "--- PIPELINE TEST: $name ---"
    local test_dir="$WORK_DIR/$name"
    mkdir -p "$test_dir"
    cd "$test_dir"

    # Run pipeline with the E2E pipeline profile, overriding dot_file via env
    # The pipeline profile points to ./modules/loop-pipeline (local source)
    if timeout "$timeout" amplifier run \
        -B "file://$BUNDLE_ROOT/profiles/attractor-e2e-pipeline-anthropic.yaml" \
        --config "session.orchestrator.config.dot_file=$BUNDLE_ROOT/tests/e2e/fixtures/$dot_fixture" \
        "Execute the pipeline" 2>&1 | tee "$test_dir/output.log"; then
        if eval "$check"; then
            echo "PASS: $name"
            PASS=$((PASS + 1))
        else
            echo "FAIL: $name (check failed)"
            FAIL=$((FAIL + 1))
        fi
    else
        local exit_code=$?
        if [ "$exit_code" -eq 124 ]; then
            echo "FAIL: $name (timeout after ${timeout}s)"
        else
            echo "FAIL: $name (amplifier run failed with exit $exit_code)"
        fi
        FAIL=$((FAIL + 1))
    fi
    cd "$WORK_DIR"
}
```

Key design decisions:
- Uses `timeout` command to prevent runaway LLM loops (default 180s).
- Overrides `dot_file` via `--config` flag so we can reuse the single pipeline profile for all 3 fixtures.
- If `--config` flag doesn't support dot-path override, we'll create per-fixture profiles in Task 3 instead.

**Step 2: Verify script parses correctly**

Run:
```bash
bash -n /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor/tests/e2e/run_e2e.sh
```
Expected: No syntax errors (exit 0).

**Step 3: Commit**
```
feat(e2e): add run_pipeline_test helper function

Adds a reusable helper for pipeline E2E tests that:
- Runs amplifier with the pipeline profile
- Overrides dot_file per fixture
- Adds timeout protection (default 180s)
- Captures output logs for verification

Part of: Track 1 Phase 1C - E2E pipeline test coverage (H-14)
```

---

### Task 3: Create Per-Fixture Pipeline Profiles (Fallback)

This task is only needed if `--config` dot-path override (from Task 2) doesn't work with `amplifier run`. If it does work, skip this task.

**Files:**
- Create: `profiles/attractor-e2e-pipeline-plan-review.yaml`
- Create: `profiles/attractor-e2e-pipeline-conditional.yaml`

**Step 1: Create the plan-implement-review profile**

Copy `profiles/attractor-e2e-pipeline-anthropic.yaml` and change only the `dot_file` line:

```yaml
bundle:
  name: attractor-e2e-pipeline-plan-review
  version: 0.1.0
  description: E2E test profile - pipeline with plan/implement/review fixture

includes:
  - bundle: attractor:behaviors/attractor-core

providers:
  - module: provider-anthropic
    source: git+https://github.com/microsoft/amplifier-module-provider-anthropic@main
    config:
      default_model: claude-sonnet-4-20250514
  - module: provider-mock
    source: git+https://github.com/microsoft/amplifier-module-provider-mock@main

session:
  orchestrator:
    module: loop-pipeline
    source: ./modules/loop-pipeline
    config:
      dot_file: ./tests/e2e/fixtures/plan_implement_review.dot

tools:
  - module: tool-filesystem
    source: git+https://github.com/microsoft/amplifier-module-tool-filesystem@main
  - module: tool-bash
    source: git+https://github.com/microsoft/amplifier-module-tool-bash@main
    config:
      timeout: 120
  - module: tool-search
    source: git+https://github.com/microsoft/amplifier-module-tool-search@main

context:
  - path: context/system-anthropic.md
    role: system
```

**Step 2: Create the conditional-routing profile**

Same as above but with:
```yaml
bundle:
  name: attractor-e2e-pipeline-conditional
  ...
  dot_file: ./tests/e2e/fixtures/conditional_routing.dot
```

**Step 3: Verify profiles parse**

Run:
```bash
cat profiles/attractor-e2e-pipeline-plan-review.yaml | python3 -c "import sys,yaml; yaml.safe_load(sys.stdin); print('OK')"
cat profiles/attractor-e2e-pipeline-conditional.yaml | python3 -c "import sys,yaml; yaml.safe_load(sys.stdin); print('OK')"
```
Expected: Both print "OK".

**Step 4: Commit**
```
feat(e2e): add per-fixture pipeline profiles

Create dedicated pipeline profiles for each DOT fixture, as a fallback
if --config dot-path override isn't supported by amplifier run.

Part of: Track 1 Phase 1C - E2E pipeline test coverage (H-14)
```

---

### Task 4: Add Pipeline E2E Test - Simple File Creation

**Files:**
- Modify: `tests/e2e/run_e2e.sh`

**Step 1: Add the simple file creation pipeline test after the existing agent tests**

```bash
# =========================================
# Pipeline E2E Tests
# =========================================
echo ""
echo "========================================="
echo "Pipeline E2E Tests"
echo "========================================="

# Pipeline Test 1: Simple file creation (single-node pipeline)
# Fixture: simple_file_creation.dot
# Graph: start -> implement -> done
# The implement node should create hello.py with "Hello World"
run_pipeline_test "pipeline_simple_file" \
    "simple_file_creation.dot" \
    "test -f hello.py && grep -qi 'hello' hello.py"
```

The `simple_file_creation.dot` fixture has one `implement` node with `goal_gate=true` that should create `hello.py`. The check verifies the file exists and contains "hello".

**Step 2: Run the test**

Run:
```bash
cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor && bash tests/e2e/run_e2e.sh
```
Expected: The pipeline test runs (may take 30-60s for LLM call), `hello.py` is created in the test working directory.

**Step 3: Commit**
```
feat(e2e): add pipeline test for simple file creation fixture

Tests the simplest pipeline path: start -> implement -> done.
Validates that the pipeline orchestrator can execute a single-node
workflow and produce the expected output file.

Part of: Track 1 Phase 1C - E2E pipeline test coverage (H-14)
```

---

### Task 5: Add Pipeline E2E Test - Plan/Implement/Review

**Files:**
- Modify: `tests/e2e/run_e2e.sh`

**Step 1: Add the multi-step pipeline test**

```bash
# Pipeline Test 2: Plan -> Implement -> Validate (multi-step pipeline)
# Fixture: plan_implement_review.dot
# Graph: start -> plan -> implement -> validate -> done
# The implement node should create test_math.py with add(a,b) function
run_pipeline_test "pipeline_plan_review" \
    "plan_implement_review.dot" \
    "test -f test_math.py && grep -q 'def add' test_math.py" \
    240
```

The `plan_implement_review.dot` fixture has 3 action nodes: plan, implement (with `goal_gate=true`), validate. The check verifies `test_math.py` was created with the `add` function. Timeout is 240s since this involves 3 LLM calls.

**Step 2: Run the test**

Run:
```bash
cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor && bash tests/e2e/run_e2e.sh
```
Expected: Pipeline executes all 3 nodes, `test_math.py` exists with `def add`.

**Step 3: Commit**
```
feat(e2e): add pipeline test for plan/implement/review fixture

Tests a multi-step pipeline: start -> plan -> implement -> validate -> done.
Validates that the pipeline orchestrator executes nodes sequentially and
the implement node produces the expected test_math.py output.

Part of: Track 1 Phase 1C - E2E pipeline test coverage (H-14)
```

---

### Task 6: Add Pipeline E2E Test - Conditional Routing

**Files:**
- Modify: `tests/e2e/run_e2e.sh`

**Step 1: Add the conditional routing pipeline test**

```bash
# Pipeline Test 3: Conditional routing (diamond gate with retry loop)
# Fixture: conditional_routing.dot
# Graph: start -> implement -> test -> gate -> done (or gate -> implement retry)
# The implement node should create calc.py with multiply(a,b) function
run_pipeline_test "pipeline_conditional" \
    "conditional_routing.dot" \
    "test -f calc.py && grep -q 'def multiply' calc.py" \
    300
```

The `conditional_routing.dot` fixture has a diamond gate node. If the test passes, it goes to `done`; if it fails, it retries `implement`. The check verifies `calc.py` was created with `multiply`. Timeout is 300s since retries are possible.

**Step 2: Run the test**

Run:
```bash
cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor && bash tests/e2e/run_e2e.sh
```
Expected: Pipeline executes, `calc.py` exists with `def multiply`. The gate node routes to `done` on success.

**Step 3: Commit**
```
feat(e2e): add pipeline test for conditional routing fixture

Tests a pipeline with conditional branching: start -> implement -> test ->
gate -> done (or retry). Validates the pipeline orchestrator handles
diamond gates and conditional edge routing.

Part of: Track 1 Phase 1C - E2E pipeline test coverage (H-14)
```

---

### Task 7: Update Results Summary and Final Validation

**Files:**
- Modify: `tests/e2e/run_e2e.sh`

**Step 1: Add a summary section for pipeline tests**

Before the final results banner, add:

```bash
echo ""
echo "========================================="
echo "Combined Results: $PASS passed, $FAIL failed"
echo "  (Agent tests + Pipeline tests)"
echo "========================================="
```

Update the existing results banner to be labeled "Agent E2E Tests" by adding a label before the agent test section:

```bash
echo ""
echo "========================================="
echo "Agent E2E Tests"
echo "========================================="
```

**Step 2: Verify the full script runs end-to-end**

Run:
```bash
cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor && bash tests/e2e/run_e2e.sh
```
Expected: 6 tests total (3 agent + 3 pipeline). Output shows both sections with labeled results. `exit $FAIL` at the end returns the correct count.

**Step 3: Commit**
```
feat(e2e): finalize E2E test suite with combined agent + pipeline coverage

Complete the E2E test expansion:
- 3 agent-only tests (existing, unchanged)
- 3 pipeline tests (new: simple, plan-review, conditional)
- Labeled sections for agent vs pipeline tests
- Combined pass/fail summary

Closes: Track 1 Phase 1C task 1C.2 - E2E pipeline test coverage (H-14)
```

---

## PR Details

**Title:** feat(e2e): add pipeline E2E tests for all 3 DOT fixtures (H-14)

**Description:**
The E2E test suite only covered agent-only mode (3 tests using `--mode single`). The pipeline orchestrator had zero E2E coverage despite having a profile and 3 DOT fixtures ready.

This PR:
- Adds `amplifier init --yes` setup step for local module resolution
- Adds `run_pipeline_test` helper with timeout protection
- Adds 3 pipeline E2E tests covering all fixtures:
  - `simple_file_creation.dot` - single-node pipeline
  - `plan_implement_review.dot` - multi-step sequential pipeline
  - `conditional_routing.dot` - diamond gate with retry loop
- Creates per-fixture profiles as fallback (if `--config` override unsupported)

Known limitation: Pipeline uses `DirectProviderBackend` fallback since `session.spawn` isn't registered by `amplifier run`. This is tracked in Track 2.

**Labels:** `track-1`, `phase-1c`, `e2e`, `testing`
**Branch:** `track1/1c2-e2e-pipeline-tests`
