# Manual E2E Tests

End-to-end tests for the Attractor bundle. These require a real LLM provider
(Anthropic API key) and are run manually in a shadow environment or local dev setup.

## Prerequisites

- `amplifier` CLI installed and on PATH
- `ANTHROPIC_API_KEY` set in environment
- Working directory with write access (tests create files)

## Agent Tests (E2E 1-3)

Use profile: `profiles/attractor-e2e-anthropic.yaml`

These tests exercise the single-turn agent loop (`loop-agent`) with real tool calls.

### E2E Test 1: Agent creates a file

```bash
mkdir -p /tmp/e2e-test1 && cd /tmp/e2e-test1
amplifier run -B "file://<BUNDLE_ROOT>/profiles/attractor-e2e-anthropic.yaml" \
  --mode single \
  "Create a file called hello.py that prints Hello World. Use the write_file tool."
```

**Expected result:**
- `hello.py` exists in the working directory
- Contains `print` statement with "Hello World" (or similar)
- Verify: `test -f hello.py && grep -qi hello hello.py`

### E2E Test 2: Agent reads and edits a file

```bash
mkdir -p /tmp/e2e-test2 && cd /tmp/e2e-test2
echo "print('original content')" > existing.py
amplifier run -B "file://<BUNDLE_ROOT>/profiles/attractor-e2e-anthropic.yaml" \
  --mode single \
  "Read the file existing.py, then edit it to also print 'added line'. Use read_file then edit_file."
```

**Expected result:**
- `existing.py` contains both "original" and "added" text
- Verify: `grep -q 'original' existing.py && grep -q 'added' existing.py`

### E2E Test 3: Agent runs a shell command

```bash
mkdir -p /tmp/e2e-test3 && cd /tmp/e2e-test3
amplifier run -B "file://<BUNDLE_ROOT>/profiles/attractor-e2e-anthropic.yaml" \
  --mode single \
  "Run the command 'echo hello_from_shell' using the bash tool and tell me the output." \
  2>&1 | tee output.log
```

**Expected result:**
- Agent invokes the bash/shell tool
- Output log contains "hello_from_shell"
- Verify: `grep -q 'hello_from_shell' output.log`

## Pipeline Tests (E2E 4-6)

Use profile: `profiles/attractor-e2e-pipeline-anthropic.yaml`

These tests exercise the DOT graph-driven pipeline (`loop-pipeline`). Each test
uses a different DOT fixture. Pipeline tests take longer (2-5 minutes) since they
make multiple sequential LLM calls.

**Note:** The pipeline profile defaults to `simple_file_creation.dot`. For tests 5
and 6, override the `dot_file` config or create separate profile copies.

### E2E Test 4: Simple pipeline (single node)

DOT fixture: `tests/e2e/fixtures/simple_file_creation.dot`

```bash
mkdir -p /tmp/e2e-test4 && cd /tmp/e2e-test4
amplifier run -B "file://<BUNDLE_ROOT>/profiles/attractor-e2e-pipeline-anthropic.yaml" \
  --mode single \
  "Run the pipeline"
```

**Expected result:**
- Pipeline executes: start -> implement -> done
- `hello.py` is created (the implement node's prompt asks for it)
- Agent session spawned for the `implement` node completes successfully
- Verify: `test -f hello.py && python3 hello.py | grep -qi hello`

### E2E Test 5: Multi-stage pipeline (plan/implement/review)

DOT fixture: `tests/e2e/fixtures/plan_implement_review.dot`

Requires modifying the pipeline profile's `dot_file` to point to this fixture,
or passing config override.

```
Pipeline graph: start -> plan -> implement -> validate -> done
```

**Expected result:**
- All 4 nodes execute in sequence
- `plan` node produces a brief plan (visible in agent output)
- `implement` node creates `test_math.py` with `add(a, b)` function
- `validate` node runs `python3 test_math.py` and reports pass/fail
- Verify: `test -f test_math.py && python3 test_math.py`

### E2E Test 6: Conditional routing pipeline

DOT fixture: `tests/e2e/fixtures/conditional_routing.dot`

Requires modifying the pipeline profile's `dot_file` to point to this fixture.

```
Pipeline graph: start -> implement -> test -> gate
  gate -> done         [condition="outcome=success"]
  gate -> implement    [condition="outcome!=success", label="Retry"]
```

**Expected result:**
- `implement` node creates `calc.py` with `multiply(a, b)` function
- `test` node runs `python3 calc.py` and checks for "PASS" output
- `gate` node routes to `done` on success (or retries `implement` on failure)
- Pipeline terminates at `done`
- Verify: `test -f calc.py && python3 calc.py | grep -q PASS`

## Timeout Guidance

| Test Type | Typical Duration | Suggested Timeout |
|-----------|-----------------|-------------------|
| Agent (E2E 1-3) | 30-90s | 120s |
| Pipeline single-node (E2E 4) | 60-120s | 300s |
| Pipeline multi-stage (E2E 5-6) | 120-300s | 600s |

## Troubleshooting

- **"No provider configured"**: Check `ANTHROPIC_API_KEY` is set
- **Tool call failures**: Ensure the working directory is writable
- **Pipeline hangs**: Check that `dot_file` path resolves correctly relative to the profile
- **Timeout**: Pipeline tests make multiple LLM calls; increase timeout or check network

---

## Gemini Agent Tests (G1-G4)

Use profile: `profiles/attractor-e2e-gemini.yaml`

### Prerequisites

- `GOOGLE_API_KEY` set in environment
- `amplifier` CLI installed and on PATH

### Run all Gemini agent tests via pytest

```bash
GOOGLE_API_KEY=your-key uv run pytest tests/e2e/test_gemini_agent.py -v
```

### G1: Basic invocation

```bash
mkdir -p /tmp/e2e-g1 && cd /tmp/e2e-g1
amplifier run -B "file://<BUNDLE_ROOT>/profiles/attractor-e2e-gemini.yaml" \
  --mode single \
  "Write a one-sentence explanation of what a Python list comprehension is. No file creation needed."
```

**Expected result:** Agent responds with a coherent explanation; exit code 0.

### G2: Agent creates a file

```bash
mkdir -p /tmp/e2e-g2 && cd /tmp/e2e-g2
amplifier run -B "file://<BUNDLE_ROOT>/profiles/attractor-e2e-gemini.yaml" \
  --mode single \
  "Create a file called hello.py that prints 'Hello from Gemini'. Use the write_file tool."
```

**Expected result:**
- `hello.py` exists in the working directory
- Contains a `print` statement referencing Gemini or hello
- Verify: `test -f hello.py && grep -qi 'gemini\|hello' hello.py`

### G3: Agent uses web_search tool

```bash
mkdir -p /tmp/e2e-g3 && cd /tmp/e2e-g3
amplifier run -B "file://<BUNDLE_ROOT>/profiles/attractor-e2e-gemini.yaml" \
  --mode single \
  "Use the web_search tool to search for 'Python 3.12 release date' and tell me the year it was released." \
  2>&1 | tee output.log
```

**Expected result:**
- Agent invokes the `web_search` tool
- Output contains "2023" or "3.12"
- Verify: `grep -q '2023\|3\.12' output.log`

### G4: Agent reads then edits a file

```bash
mkdir -p /tmp/e2e-g4 && cd /tmp/e2e-g4
echo "print('original content')" > existing.py
amplifier run -B "file://<BUNDLE_ROOT>/profiles/attractor-e2e-gemini.yaml" \
  --mode single \
  "Read the file existing.py, then edit it to also print 'added line'. Use read_file then edit_file."
```

**Expected result:**
- `existing.py` contains both "original" and "added" text
- Verify: `grep -q 'original' existing.py && grep -q 'added' existing.py`

---

## Gemini Pipeline Tests (P1)

Use profile: `profiles/attractor-e2e-pipeline-gemini.yaml`

### Run Gemini pipeline test via pytest

```bash
GOOGLE_API_KEY=your-key uv run pytest tests/e2e/test_gemini_pipeline.py -v
```

### P1: Simple pipeline (single node, Gemini)

DOT fixture: `tests/e2e/fixtures/simple_file_creation.dot`

```bash
mkdir -p /tmp/e2e-p1 && cd /tmp/e2e-p1
amplifier run -B "file://<BUNDLE_ROOT>/profiles/attractor-e2e-pipeline-gemini.yaml" \
  --mode single \
  "Run the pipeline"
```

**Expected result:**
- Pipeline executes: start -> implement -> done
- `hello.py` is created by the Gemini agent session spawned for `implement`
- Verify: `test -f hello.py && python3 hello.py | grep -qi hello`

---

## Gemini Timeout Guidance

| Test | Typical Duration | Suggested Timeout |
|------|-----------------|-------------------|
| G1 Basic invocation | 20-60s | 180s |
| G2 Creates file | 30-90s | 180s |
| G3 Web search | 30-90s | 180s |
| G4 Read then edit | 30-90s | 180s |
| P1 Pipeline (single node) | 90-180s | 600s |

## Gemini Troubleshooting

- **"No provider configured"** or **"API key missing"**: Check `GOOGLE_API_KEY` is exported
- **`web_search` not available**: Confirm `tool-search` is included in the profile (it is in `attractor-e2e-gemini.yaml`)
- **`tool-web` errors**: The Gemini profile includes `tool-web` for URL fetching; ensure network access
- **Pipeline hangs**: Check that `dot_file` path resolves correctly and that `GOOGLE_API_KEY` is visible to the spawned agent sub-sessions
- **Timeout**: Gemini pipeline tests spawn full agent sessions per node; 600s is the recommended ceiling
