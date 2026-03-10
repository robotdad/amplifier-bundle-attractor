# Attractor Investigation Fixes & Gemini E2E Tests Design

## Goal

Fix 4 confirmed issues from the Parallax Discovery investigation of amplifier-bundle-attractor's spec fidelity, and close the zero-E2E-test gap for Gemini.

## Background

A Parallax Discovery investigation surfaced multiple spec-fidelity issues in Attractor. Four have been confirmed as genuine defects requiring fixes:

- **D-05**: Timeout defaults misaligned with spec for OpenAI and Gemini agents
- **D-07**: OpenAI agents don't use the native `apply_patch` tool type that models are trained against
- **D-08**: Fidelity degradation after checkpoint resume is permanent instead of one-hop
- **NF-03**: `_extract_required_providers()` returns empty, breaking provider validation

Additionally, while Anthropic has E2E test coverage, Gemini has zero E2E tests — a gap that should be closed alongside these fixes.

## Approach

Sequential execution: fix all 4 confirmed issues first, run the existing 2,239 tests after each fix to confirm no regressions, then build Gemini E2E tests modeled on existing Anthropic test patterns. All work on `main` branch, PR at the end.

## Architecture

The fixes span 3 repositories, with the native `apply_patch` work (D-07) being the most architecturally significant — it threads through the provider, tool, and agent configuration layers:

```
OpenAI Responses API
  |  {"type": "apply_patch"}  <-- built-in tool type
  v
amplifier-module-provider-openai
  |  Parses apply_patch_call responses
  |  Gated on apply_patch.engine == "native" capability
  v
amplifier-bundle-filesystem (apply_patch tool, native engine)
  |  Registers apply_patch.engine: native capability
  |  Accepts pre-parsed {type, path, diff} operations
  v
amplifier-bundle-execution-environments (NEW: env_apply_patch)
  |  Dispatches through EnvironmentRegistry
  |  Reads/writes via backend.read_file()/write_file()
  |  Applies V4A diff in-memory (vendored apply_diff.py)
  v
Isolated environment (Docker, SSH, etc.)
```

## Components

### Fix D-05 — Timeout Alignment

**Problem:** OpenAI and Gemini agent configs set `default_command_timeout_ms: 120000` and bash tool timeout to 120s, but the spec calls for 10s defaults. Anthropic is already correct at 120s per its own spec allowance.

**Changes (config only, no code):**

| File | Field | Before | After |
|------|-------|--------|-------|
| `agents/attractor-agent-openai.yaml` | `default_command_timeout_ms` | `120000` | `10000` |
| `agents/attractor-agent-openai.yaml` | tool-bash `timeout` | `120` | `10` |
| `agents/attractor-agent-gemini.yaml` | `default_command_timeout_ms` | `120000` | `10000` |
| `agents/attractor-agent-gemini.yaml` | tool-bash `timeout` | `120` | `10` |

**Risk:** Low. Existing tests are mock-based and timeout-agnostic. No test changes needed.

---

### Fix D-07 — Native `apply_patch` End-to-End

**Problem:** OpenAI models are trained against the built-in `apply_patch` tool type in the Responses API, where the model emits structured `apply_patch_call` objects with `{type, path, diff}`. Attractor currently sends `apply_patch` as a regular function tool with a JSON schema, forcing the model to format entire V4A envelopes as string arguments — suboptimal and not what the model is trained against.

**Current state across the stack:**

| Layer | Component | Native Support |
|-------|-----------|----------------|
| Provider | `amplifier-module-provider-openai` | Full — sends `{"type": "apply_patch"}`, parses `apply_patch_call` responses, submits `apply_patch_call_output` results. Gated behind `coordinator.get_capability("apply_patch.engine") == "native"` |
| Tool (host) | `amplifier-bundle-filesystem` `apply_patch` | Full — native engine takes pre-parsed `{type, path, diff}`; registers `apply_patch.engine: native` capability |
| Tool (isolated) | `amplifier-bundle-execution-environments` | **Missing** — no `env_apply_patch` at all |
| Agent config | `amplifier-bundle-attractor` | Uses custom `tool-apply-patch` (function engine, raw V4A strings) |

**Changes across 3 repos:**

#### Layer 1: `amplifier-bundle-execution-environments` — New `env_apply_patch` tool

- Add `env_apply_patch` dispatch tool following the same pattern as other `env_*` tools in `dispatch.py`
- Accepts `instance` parameter, routes through `EnvironmentRegistry`
- Supports both formats:
  - **Native format**: Pre-parsed `{type, path, diff}` operations from OpenAI Responses API
  - **Function format**: Raw V4A envelope strings from any LLM
- Implementation: reads file via `backend.read_file()`, applies V4A diff in-memory, writes back via `backend.write_file()`
- Vendor `apply_diff.py` from `amplifier-bundle-filesystem` — it's pure string-in/string-out with zero I/O dependencies, Apache-2.0 licensed

#### Layer 2: `amplifier-bundle-attractor` — OpenAI host agent switch

- Replace the custom `tool-apply-patch` module reference with `amplifier-bundle-filesystem`'s `apply_patch` (native engine) in `agents/attractor-agent-openai.yaml`
- This activates the `apply_patch.engine: native` coordinator capability
- The OpenAI provider already responds to this capability — no provider changes needed
- Anthropic and Gemini agents are **unaffected** (they continue using `edit_file`)

#### Layer 3: `amplifier-bundle-attractor` — OpenAI isolated agent wiring

- Update `agents/attractor-agent-openai-isolated.yaml` to include `env_apply_patch` from the execution-environments bundle
- Update `context/isolated-environment-guidance.md` to map `apply_patch -> env_apply_patch`

**Net result:** OpenAI models get the built-in `apply_patch` tool type they're trained against — structured `{type, path, diff}` operations via the Responses API — on both host and isolated environments.

**No changes to `amplifier-bundle-filesystem` or `amplifier-module-provider-openai`** — both are already correct.

---

### Fix D-08 — One-Hop Fidelity Degradation

**Problem:** When M-23 checkpoint resume triggers fidelity degradation (from `full` to `degraded`), it's permanent for the rest of the pipeline run. The intended behavior is one-hop only: degrade for the first node after resume, then restore to `full`.

**Changes:**

- **File:** `modules/loop-pipeline/amplifier_module_loop_pipeline/engine.py`
- **Location:** After the M-23 degradation logic at ~line 698
- Add a `_fidelity_degraded_hop` flag that tracks whether the degradation has been applied
- After the first node executes post-resume, restore `graph.default_fidelity` to `"full"`

**Test changes:**

- Update existing test `TestM23CheckpointFidelityDegradation` to verify one-hop behavior:
  - First node after resume runs at degraded fidelity
  - Second node after resume runs at full fidelity

---

### Fix NF-03 — `_extract_required_providers()` Returns Empty

**Problem:** `_extract_required_providers()` in `tool-pipeline-run` always returns an empty set, which means provider validation is silently skipped — pipelines can start without required providers being available.

**Changes:**

- **File:** `modules/tool-pipeline-run/amplifier_module_tool_pipeline_run/__init__.py`
- Implement provider extraction by:
  - Parsing `llm_provider` node attributes from the DOT source
  - Parsing `model_stylesheet` rules to extract provider references
- 3 existing failing tests already define the expected behavior — they become the verification that this fix is correct

---

### Gemini E2E Tests

**Problem:** Gemini has zero E2E test coverage. Anthropic has ~7 E2E tests covering basic invocation, tool usage, multi-turn, and pipeline execution.

**Location:** `amplifier-bundle-attractor/tests/e2e/`

**Environment gating:** Tests gated behind `GOOGLE_API_KEY` with a skip decorator if not set, following the same pattern as Anthropic tests gating behind `ANTHROPIC_API_KEY`.

**Tests:**

1. **Basic agent invocation** — Spawn `attractor-agent-gemini`, give it a simple coding task, verify it completes and produces output
2. **Gemini-specific tools** — Verify `edit_file`, `web_search`/`web_fetch` (Gemini uniquely gets `tool-web`)
3. **Pipeline execution** — Run a simple linear pipeline with Gemini as the provider via model stylesheet
4. **Multi-turn conversation** — Verify the agent can handle follow-up instructions

**New files:**

| File | Purpose |
|------|---------|
| `tests/e2e/test_gemini_agent.py` | Agent-level E2E tests (invocation, tools, multi-turn) |
| `tests/e2e/test_gemini_pipeline.py` | Pipeline-level E2E test |
| `profiles/attractor-e2e-gemini.yaml` | E2E test profile for Gemini (following pattern of `attractor-e2e-anthropic.yaml`) |

## Data Flow

### D-07 Native `apply_patch` — Request Flow

1. Amplifier sends tool list to OpenAI Responses API, including `{"type": "apply_patch"}` (built-in, not a function schema)
2. Model returns `apply_patch_call` with structured `{type: "create_file"|"update_file"|"delete_file", path, diff}`
3. Provider module parses the response into tool invocation with pre-parsed operations
4. `apply_patch` tool (native engine) receives `{type, path, diff}` — applies directly to host filesystem
5. For isolated environments: `env_apply_patch` receives same format, reads file via backend, applies V4A diff in-memory, writes via backend

### D-08 One-Hop Fidelity — State Flow

1. Pipeline hits checkpoint, suspends
2. Resume triggers M-23 degradation: `graph.default_fidelity = "degraded"`, sets `_fidelity_degraded_hop = True`
3. First node executes at degraded fidelity
4. After first node completes: check `_fidelity_degraded_hop`, restore `graph.default_fidelity = "full"`, clear flag
5. All subsequent nodes execute at full fidelity

## Error Handling

- **D-07 `env_apply_patch`**: If the V4A diff fails to apply (e.g., context mismatch), return a clear error message following the same pattern as the filesystem bundle's `apply_patch` — no partial writes
- **NF-03 provider extraction**: If DOT parsing fails or produces unexpected structure, fall back to returning an empty set (current behavior) with a warning log — don't block pipeline execution on a parsing failure
- **Gemini E2E tests**: Tests must handle API rate limits and transient failures gracefully with appropriate retry/skip decorators

## Testing Strategy

1. **After each fix**: Run existing 2,239 tests with `uv run pytest` to confirm no regressions
2. **D-07 `env_apply_patch`**: Add unit tests in the execution-environments bundle covering:
   - Native format `{type, path, diff}` operations (create, update, delete)
   - Raw V4A string format
   - Error cases (context mismatch, missing file for update)
3. **D-08**: Update existing `TestM23CheckpointFidelityDegradation` to verify one-hop restoration
4. **NF-03**: 3 existing failing tests become passing — they already define the expected behavior
5. **Gemini E2E**: Gated behind `GOOGLE_API_KEY` — CI skips if key not set; run manually to verify

## Repos Involved

| Repo | Changes | Fixes |
|------|---------|-------|
| `amplifier-bundle-attractor` | YAML configs, agent configs, guidance docs, engine.py, tool-pipeline-run, Gemini E2E tests | D-05, D-07, D-08, NF-03, Gemini E2E |
| `amplifier-bundle-execution-environments` | New `env_apply_patch` tool, vendored `apply_diff.py` | D-07 |
| `amplifier-bundle-filesystem` | No changes (already correct; source for `apply_diff.py` vendoring) | — |
| `amplifier-module-provider-openai` | No changes (already has full native `apply_patch` support) | — |

## Open Questions

1. Should the Attractor custom `tool-apply-patch` module be kept alongside the filesystem bundle's version, or fully replaced?
2. Should `env_apply_patch` also register the `apply_patch.engine: native` capability for isolated environments?
3. Should we add OpenAI E2E tests too while we're at it, or keep scope to Gemini only?
