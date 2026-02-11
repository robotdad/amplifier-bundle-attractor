# Track 3: MEDIUM and LOW Gap Catalog

> **Status:** Draft
> **Created:** 2026-02-10
> **Source:** Adversarial review findings (24 MEDIUM, 22 LOW)
> **Scope:** All non-critical spec-compliance gaps across loop-agent and loop-pipeline modules

---

## Summary

| Severity | Count | Effort S | Effort M | Effort L |
|----------|-------|----------|----------|----------|
| MEDIUM   | 24    | 10       | 10       | 4        |
| LOW      | 22    | 14       | 6        | 2        |
| **Total**| **46**| **24**   | **16**   | **6**    |

### Priority Distribution

| Priority    | MEDIUM | LOW | Total |
|-------------|--------|-----|-------|
| Do first    | 10     | 4   | 14    |
| Do later    | 10     | 12  | 22    |
| Defer       | 4      | 6   | 10    |
| **Total**   | **24** | **22** | **46** |

### Recommended Execution Order

Work through these in themed batches, prioritizing "Do first" items within each batch:

1. **Batch A — Agent Loop Core** (M-1, M-5, M-6, M-7, M-8, L-22): These affect runtime correctness and safety of the agent loop. ~1 day.
2. **Batch B — Pipeline Graph Model** (M-9, M-10, M-11, L-1, L-2, L-3, L-4, L-5, L-6): DOT parser strictness and graph type safety. ~1 day.
3. **Batch C — Handler Compliance** (M-12, M-13, M-14, M-15, M-16, M-17, M-18, L-11, L-16, L-18): Node handlers matching spec behavior. ~1.5 days.
4. **Batch D — Pipeline Infrastructure** (M-19, M-20, M-21, M-22, M-23, M-24, L-7, L-8, L-9, L-10, L-12, L-13, L-14, L-15, L-17): Status format, transforms, fidelity, checkpoints, artifacts. ~2 days.
5. **Batch E — Remaining & Deferred** (M-2, M-3, M-4, L-19, L-20, L-21): Polish, optional features, and items dependent on external work. As time permits.

**Estimated total:** ~6-7 working days for Do first + Do later items.

---

## 1. Agent Loop Completeness

Findings related to `modules/loop-agent/` (agent_session.py, subagent_tools.py, config.py, events.py, loop_detection.py, messages.py, state.py, etc.)

---

### M-1: Missing response_id capture

- **Description:** `AssistantTurn.response_id` is always `None`. The provider response includes a response ID but it is never captured and stored on the turn object.
- **Module:** `loop-agent` / `agent_session.py`, `turns.py`
- **Effort:** S (< 30 min)
- **Priority:** Do first
- **Fix:** After receiving a provider response, extract the response ID from the provider result and assign it to `AssistantTurn.response_id`. Ensure all provider adapters surface this field.

---

### M-2: Loop detection message format wrong

- **Description:** The loop-detection warning message injected into context uses different wording than the spec's exact prescribed text.
- **Module:** `loop-agent` / `loop_detection.py`
- **Effort:** S (< 30 min)
- **Priority:** Do later
- **Fix:** Replace the current warning string with the exact wording from the spec. Add a test that asserts the message text matches verbatim.

---

### M-3: Missing TOOL_CALL_OUTPUT_DELTA event

- **Description:** The event system has no `TOOL_CALL_OUTPUT_DELTA` event type for incremental streaming of tool output as it is produced.
- **Module:** `loop-agent` / `events.py`
- **Effort:** M (30 min - 2 hrs)
- **Priority:** Defer
- **Fix:** Add a `TOOL_CALL_OUTPUT_DELTA` variant to the event enum and emit it from tool execution as stdout/stderr chunks arrive. This requires plumbing streaming reads from subprocess execution through the event bus. Low urgency because most consumers wait for final output.

---

### M-4: Config max_tool_rounds default 200 but spec says per-provider

- **Description:** `max_tool_rounds` is a single global default (200) instead of being configurable per provider as the spec requires.
- **Module:** `loop-agent` / `config.py`
- **Effort:** M (30 min - 2 hrs)
- **Priority:** Do later
- **Fix:** Restructure config so `max_tool_rounds` can be specified at the provider level with the global value as a fallback. Update config loading to merge provider-specific overrides.

---

### M-5: No ToolRegistry class

- **Description:** Tools are accessed via a plain `dict[str, Tool]` instead of through a dedicated `ToolRegistry` class as specified. This prevents future features like tool namespacing, dynamic registration, and conflict detection.
- **Module:** `loop-agent` / `agent_session.py`
- **Effort:** M (30 min - 2 hrs)
- **Priority:** Do first
- **Fix:** Introduce a `ToolRegistry` class that wraps the dict with `register()`, `get()`, `list()`, and `has()` methods. Replace all direct dict access in `agent_session.py`. The registry should enforce unique names and support bulk registration.

---

### M-6: Missing env-var filtering in tool execution

- **Description:** When executing shell-based tools, environment variables are passed through unfiltered. Sensitive variables (API keys, tokens) can leak into tool output that gets sent to the LLM.
- **Module:** `loop-agent` / `agent_session.py`
- **Effort:** M (30 min - 2 hrs)
- **Priority:** Do first
- **Fix:** Before spawning a subprocess for tool execution, filter the environment against a configurable allowlist/denylist. Default denylist should include common secret patterns (`*_KEY`, `*_SECRET`, `*_TOKEN`, `*_PASSWORD`). Log a warning when variables are scrubbed.

---

### M-7: Shallow shutdown (no SIGTERM to running processes)

- **Description:** The `shutdown()` method only sets the session state to STOPPED but does not send SIGTERM/SIGKILL to any running tool subprocesses. Orphaned processes can persist after shutdown.
- **Module:** `loop-agent` / `agent_session.py`
- **Effort:** M (30 min - 2 hrs)
- **Priority:** Do first
- **Fix:** Track spawned subprocess PIDs in a set. On `shutdown()`, iterate the set and send SIGTERM, wait a short grace period, then SIGKILL any survivors. Use process groups where possible for clean tree termination.

---

### M-8: No `model` field on spawn_agent tool

- **Description:** The `spawn_agent` tool definition does not include a `model` parameter, so callers cannot override which model a subagent uses. All subagents inherit the parent's model.
- **Module:** `loop-agent` / `subagent_tools.py`
- **Effort:** S (< 30 min)
- **Priority:** Do first
- **Fix:** Add an optional `model` string parameter to the `spawn_agent` tool schema. When provided, pass it to the subagent session config to override the default provider/model selection.

---

### L-22: Pre/post tool call hooks missing

- **Description:** The spec defines `pre_tool_call` and `post_tool_call` hook points that fire before and after each tool execution. These are not implemented.
- **Module:** `loop-agent` / `agent_session.py`
- **Effort:** M (30 min - 2 hrs)
- **Priority:** Do later
- **Fix:** Add `pre_tool_call(tool_name, arguments)` and `post_tool_call(tool_name, arguments, result)` hook invocations around tool execution in the agent loop. Both hooks should be able to modify or block the call.

---

## 2. Pipeline Completeness

Findings related to `modules/loop-pipeline/` (engine.py, graph.py, dot_parser.py, validation.py, conditions.py, stylesheet.py, transforms.py, fidelity.py, checkpoint.py, retry.py, artifacts.py, interviewer.py, handlers/*.py).

### 2a. Graph Model & DOT Parser

---

### M-9: DOT parser more permissive than spec (accepts space-separated attrs)

- **Description:** The DOT parser accepts `[key1=val1 key2=val2]` (space-separated) when the spec requires `[key1=val1, key2=val2]` (comma-separated). This means invalid DOT input is silently accepted.
- **Module:** `loop-pipeline` / `dot_parser.py`
- **Effort:** S (< 30 min)
- **Priority:** Do first
- **Fix:** Modify the attribute-list parser to require commas between key-value pairs. Add a parse error when attributes are space-separated without commas.

---

### M-10: Node attributes not first-class fields (12 of 17 in generic dict)

- **Description:** Only 5 of 17 spec-defined node attributes are named fields on the `Node` class. The remaining 12 live in a generic `attrs: dict` bag, losing type safety, IDE autocompletion, and default-value enforcement.
- **Module:** `loop-pipeline` / `graph.py`
- **Effort:** M (30 min - 2 hrs)
- **Priority:** Do first
- **Fix:** Promote all 17 spec-defined attributes to typed fields on the `Node` dataclass with appropriate defaults. Keep `attrs: dict` only for user-defined extension attributes. Update all handler code that reads from `attrs` to use the named fields.

---

### M-11: Terminal node allows multiple exits (spec says exactly one)

- **Description:** Validation checks that terminal nodes have `>= 1` outgoing edges instead of `== 1`. The spec requires exactly one exit edge from terminal nodes (to the implicit end).
- **Module:** `loop-pipeline` / `validation.py`
- **Effort:** S (< 30 min)
- **Priority:** Do first
- **Fix:** Change the terminal-node edge count validation from `>= 1` to `== 1`. Update the error message to clarify that terminal nodes must have exactly one exit.

---

### L-1: DOT float parsing edge case (.5 not parsed)

- **Description:** Leading-dot floats like `.5` are not recognized by the DOT number parser; only `0.5` works.
- **Module:** `loop-pipeline` / `dot_parser.py`
- **Effort:** S (< 30 min)
- **Priority:** Do later
- **Fix:** Update the number regex in the DOT parser to accept optional leading digit: `\d*\.\d+` in addition to `\d+\.?\d*`.

---

### L-2: Subgraph class derivation missing

- **Description:** When parsing DOT `subgraph` blocks, the parser does not derive the `class` attribute from the subgraph name (e.g., `subgraph cluster_foo` should set `class=cluster`).
- **Module:** `loop-pipeline` / `dot_parser.py`
- **Effort:** S (< 30 min)
- **Priority:** Do later
- **Fix:** After parsing a subgraph name, extract the prefix before the first underscore and assign it as the `class` attribute if not explicitly provided.

---

### L-3: Undirected edge detection fragile

- **Description:** The parser distinguishes directed (`->`) and undirected (`--`) edges by string match, but doesn't enforce that a `digraph` uses only `->` and a `graph` uses only `--`.
- **Module:** `loop-pipeline` / `dot_parser.py`
- **Effort:** S (< 30 min)
- **Priority:** Defer
- **Fix:** Track the graph type (`digraph` vs `graph`) during parsing and emit a parse error if the wrong edge operator is used.

---

### L-4: Edge attributes not first-class

- **Description:** Edge objects store all attributes in a generic dict rather than having typed fields for spec-defined edge attributes (label, condition, weight, etc.).
- **Module:** `loop-pipeline` / `graph.py`
- **Effort:** M (30 min - 2 hrs)
- **Priority:** Do later
- **Fix:** Add typed fields for the spec-defined edge attributes to the `Edge` dataclass. Mirror the approach used when fixing M-10 for nodes.

---

### L-5: Graph attributes not first-class

- **Description:** Graph-level attributes (title, description, fidelity, etc.) are stored in a generic dict instead of typed fields.
- **Module:** `loop-pipeline` / `graph.py`
- **Effort:** M (30 min - 2 hrs)
- **Priority:** Do later
- **Fix:** Add typed fields for spec-defined graph-level attributes to the `Graph` dataclass with appropriate defaults. Keep generic dict for extensions.

---

### L-6: extra_rules parameter missing on validate()

- **Description:** The `validate()` function does not accept an `extra_rules` parameter for user-defined validation rules, as specified.
- **Module:** `loop-pipeline` / `validation.py`
- **Effort:** S (< 30 min)
- **Priority:** Do later
- **Fix:** Add an `extra_rules: list[Callable] = []` parameter to `validate()`. After running built-in rules, iterate and call each extra rule, collecting any returned errors.

---

### 2b. Conditions & Engine

---

### L-7: Bare key truthiness not in BNF grammar

- **Description:** The condition evaluator supports bare key truthiness checks (e.g., `approved` meaning `approved == true`) in code but the BNF grammar definition doesn't include this production rule.
- **Module:** `loop-pipeline` / `conditions.py`
- **Effort:** S (< 30 min)
- **Priority:** Do later
- **Fix:** Add the bare-key-truthiness production to the BNF grammar documentation. Ensure the parser explicitly handles this case rather than falling through accidentally.

---

### L-8: Start node fallback to id="start" missing

- **Description:** The engine does not fall back to finding a node with `id="start"` when no node has the `start=true` attribute set.
- **Module:** `loop-pipeline` / `engine.py`
- **Effort:** S (< 30 min)
- **Priority:** Do first
- **Fix:** In the start-node resolution logic, after checking for `start=true`, add a fallback that looks for a node with `id="start"`. Emit a debug log when fallback is used.

---

### L-17: Variable expansion duplicated in 3 places

- **Description:** Template variable expansion (`${var}` substitution) is implemented independently in 3 different locations, risking inconsistency.
- **Module:** `loop-pipeline` / `engine.py` + others
- **Effort:** M (30 min - 2 hrs)
- **Priority:** Do first
- **Fix:** Extract variable expansion into a single shared utility function. Replace all three call sites with calls to this function. Add tests for edge cases (nested vars, missing vars, recursive expansion).

---

### 2c. Handlers

---

### M-12: Human handler returns preferred_label instead of suggested_next_ids

- **Description:** The human handler's routing mechanism returns a `preferred_label` string instead of `suggested_next_ids: list[str]` as specified. This breaks the engine's edge-selection contract.
- **Module:** `loop-pipeline` / `handlers/human.py`
- **Effort:** M (30 min - 2 hrs)
- **Priority:** Do first
- **Fix:** Change the human handler to return `suggested_next_ids` in its result. Map the user's choice to the corresponding edge target node IDs. Update the engine's edge selection to consume this field.

---

### M-13: Human handler SKIPPED returns SUCCESS instead of FAIL

- **Description:** When a human node is skipped (no interviewer available or user declines), the handler returns `SUCCESS` status. The spec mandates `FAIL` for skipped human nodes.
- **Module:** `loop-pipeline` / `handlers/human.py`
- **Effort:** S (< 30 min)
- **Priority:** Do first
- **Fix:** Change the SKIPPED path's return status from `SUCCESS` to `FAIL`. Update any tests that assert `SUCCESS` on skip.

---

### M-14: Manager loop default max_cycles 10 vs spec's 1000

- **Description:** The manager loop handler defaults to `max_cycles=10`, but the spec prescribes a default of 1000. This causes premature termination for complex multi-step pipelines.
- **Module:** `loop-pipeline` / `handlers/manager_loop.py`
- **Effort:** S (< 30 min)
- **Priority:** Do first
- **Fix:** Change the default value of `max_cycles` from `10` to `1000`. Add a comment referencing the spec section.

---

### M-15: Manager loop steering is superficial (context key, not file write)

- **Description:** Manager loop steering passes direction via a context dictionary key. The spec requires writing a steering file to the stage's working directory so downstream tools can read it.
- **Module:** `loop-pipeline` / `handlers/manager_loop.py`
- **Effort:** M (30 min - 2 hrs)
- **Priority:** Do later
- **Fix:** After generating the steering directive, write it as a JSON file to `{stage_dir}/steering.json`. Continue also setting the context key for backward compatibility. Downstream handlers should prefer the file.

---

### M-16: Tool handler ignores node timeout attribute

- **Description:** When a tool-type node has a `timeout` attribute, the tool handler does not enforce it. Commands run indefinitely regardless of the configured timeout.
- **Module:** `loop-pipeline` / `handlers/tool.py`
- **Effort:** M (30 min - 2 hrs)
- **Priority:** Do first
- **Fix:** Read the `timeout` attribute from the node (falling back to a sensible default). Pass it to the subprocess execution as a timeout parameter. On timeout expiry, kill the process and return a FAIL result with a timeout error message.

---

### M-17: Fan-in handler has no LLM-based evaluation path

- **Description:** The fan-in handler always uses heuristic logic to aggregate parallel branch results. The spec describes an optional LLM-judge evaluation path for complex aggregation scenarios.
- **Module:** `loop-pipeline` / `handlers/fan_in.py`
- **Effort:** L (2+ hrs)
- **Priority:** Defer
- **Fix:** Add a `judge` attribute to fan-in nodes. When present, instantiate an agent session with the specified model, pass all branch results as context, and use the LLM's judgment to produce the aggregated outcome. Fall back to heuristic when no judge is configured.

---

### M-18: Retry doesn't classify errors as retryable/terminal

- **Description:** The retry handler treats all exceptions identically. The spec distinguishes retryable errors (transient failures like timeouts, rate limits) from terminal errors (invalid config, auth failures) that should not be retried.
- **Module:** `loop-pipeline` / `retry.py`
- **Effort:** M (30 min - 2 hrs)
- **Priority:** Do later
- **Fix:** Define a classification function or exception hierarchy that marks errors as retryable or terminal. In the retry loop, only retry retryable errors; propagate terminal errors immediately. Default classification: timeouts and rate-limit errors are retryable; everything else is terminal.

---

### L-11: auto_status attribute not implemented

- **Description:** The `auto_status` node attribute (which controls automatic status.json updates) is defined in the spec but not read or acted upon by any handler.
- **Module:** `loop-pipeline` / `handlers/codergen.py`
- **Effort:** S (< 30 min)
- **Priority:** Do later
- **Fix:** Read the `auto_status` attribute in the codergen handler. When true, auto-write status.json after each major step. When false or absent, skip auto-updates.

---

### L-16: Fan-in ranking includes SKIPPED status

- **Description:** When ranking parallel branch outcomes, the fan-in handler includes branches with SKIPPED status in its calculations, potentially skewing the aggregate result.
- **Module:** `loop-pipeline` / `handlers/fan_in.py`
- **Effort:** S (< 30 min)
- **Priority:** Do later
- **Fix:** Filter out branches with SKIPPED status before computing the aggregate ranking. Only SUCCESS and FAIL branches should participate in scoring.

---

### L-18: Handler fallback masks config errors

- **Description:** When a handler cannot be resolved for a node type, the system falls back to a default handler silently. This masks configuration errors where a node type is misspelled or its handler is not registered.
- **Module:** `loop-pipeline` / `handlers/__init__.py`
- **Effort:** S (< 30 min)
- **Priority:** Do first
- **Fix:** Log a warning when falling back to the default handler. Include the unresolved node type in the warning message so users can diagnose typos.

---

### 2d. Pipeline Infrastructure

---

### M-19: Status.json fields don't match spec (status vs outcome, missing fields)

- **Description:** The written `status.json` uses `status` where the spec says `outcome`, and is missing several spec-required fields. External tools that parse status.json according to the spec will break.
- **Module:** `loop-pipeline` / `handlers/codergen.py`, `engine.py`
- **Effort:** M (30 min - 2 hrs)
- **Priority:** Do first
- **Fix:** Rename the `status` field to `outcome`. Add all missing spec-required fields (elapsed_time, node_id, attempt, error_message, etc.) with appropriate values. Maintain a `status` alias temporarily for backward compatibility if needed.

---

### M-20: No formal Transform interface (custom transforms impossible)

- **Description:** The transform system hardcodes exactly two transforms. There is no `Transform` protocol/interface that users can implement to register custom transforms.
- **Module:** `loop-pipeline` / `transforms.py`
- **Effort:** M (30 min - 2 hrs)
- **Priority:** Do later
- **Fix:** Define a `Transform` protocol with an `apply(graph: Graph) -> Graph` method. Refactor the two existing transforms to implement it. Add a registration mechanism so users can provide custom transforms via config.

---

### M-21: Shape-name selectors missing from stylesheet

- **Description:** The stylesheet selector system supports `*`, `.class`, and `#id` selectors but not bare shape-name selectors (e.g., `box` to match all nodes with `shape=box`).
- **Module:** `loop-pipeline` / `stylesheet.py`
- **Effort:** S (< 30 min)
- **Priority:** Do later
- **Fix:** Add a shape-name selector type to the stylesheet parser. When a selector matches no class/id prefix, treat it as a shape-name match against the node's `shape` attribute.

---

### M-22: Fidelity mode validation silently degrades (typos become compact)

- **Description:** If an invalid fidelity mode string is provided (e.g., `"ful"` instead of `"full"`), the system silently falls back to `compact` mode with no warning. Typos go undetected.
- **Module:** `loop-pipeline` / `fidelity.py`
- **Effort:** S (< 30 min)
- **Priority:** Do first
- **Fix:** Validate the fidelity mode string against the set of known modes. If invalid, raise a `ValueError` (or emit a warning and use the default, with the invalid value logged). Never silently degrade.

---

### M-23: Checkpoint resume doesn't degrade fidelity (spec says full -> summary:high)

- **Description:** When resuming from a checkpoint, the engine attempts to use the same fidelity mode as the original run. The spec says resumed runs should degrade from `full` to `summary:high` because the full session context is lost.
- **Module:** `loop-pipeline` / `engine.py`
- **Effort:** S (< 30 min)
- **Priority:** Do first
- **Fix:** In the checkpoint-resume code path, check if the original fidelity was `full`. If so, override it to `summary:high` and log a message explaining the degradation. Other fidelity modes pass through unchanged.

---

### M-24: Missing ConsoleInterviewer and RecordingInterviewer

- **Description:** The spec defines 5 interviewer implementations, but only 3 exist. `ConsoleInterviewer` (stdin/stdout interaction) and `RecordingInterviewer` (replay from recorded responses) are missing.
- **Module:** `loop-pipeline` / `interviewer.py`
- **Effort:** L (2+ hrs)
- **Priority:** Defer
- **Fix:** Implement `ConsoleInterviewer` that reads from stdin and writes to stdout for interactive CLI use. Implement `RecordingInterviewer` that takes a list of pre-recorded responses and replays them in order (for testing and CI). Both must implement the existing `Interviewer` protocol.

---

### L-9: Checkpoint completed_nodes is dict vs spec's list

- **Description:** The checkpoint stores `completed_nodes` as a dict (mapping node_id to result) but the spec defines it as a list of node IDs.
- **Module:** `loop-pipeline` / `checkpoint.py`
- **Effort:** S (< 30 min)
- **Priority:** Do later
- **Fix:** Change `completed_nodes` to a list of node IDs in the checkpoint schema. Store detailed results separately if needed (e.g., in a `node_results` dict). Update serialization/deserialization.

---

### L-10: Checkpoint missing logs field

- **Description:** The checkpoint data structure does not include a `logs` field for storing execution log entries, as specified.
- **Module:** `loop-pipeline` / `checkpoint.py`
- **Effort:** S (< 30 min)
- **Priority:** Do later
- **Fix:** Add a `logs: list[str]` field to the checkpoint dataclass. Append key execution events (node start, node complete, errors) to the log during engine execution. Persist with the checkpoint.

---

### L-12: Artifact uses name vs artifact_id

- **Description:** Artifacts are keyed by `name` but the spec uses `artifact_id` as the primary identifier.
- **Module:** `loop-pipeline` / `artifacts.py`
- **Effort:** S (< 30 min)
- **Priority:** Do later
- **Fix:** Rename the `name` field/key to `artifact_id` throughout the artifact system. Add a `name` property as an alias if backward compatibility is needed temporarily.

---

### L-13: Artifact missing has/remove/clear methods

- **Description:** The artifact store only supports add and get operations. The spec also requires `has(id)`, `remove(id)`, and `clear()` methods.
- **Module:** `loop-pipeline` / `artifacts.py`
- **Effort:** S (< 30 min)
- **Priority:** Do later
- **Fix:** Add `has(artifact_id) -> bool`, `remove(artifact_id) -> None`, and `clear() -> None` methods to the artifact store class.

---

### L-14: Artifact store not thread-safe

- **Description:** The artifact store uses a plain dict with no locking. Concurrent handler access from parallel branches can cause race conditions.
- **Module:** `loop-pipeline` / `artifacts.py`
- **Effort:** S (< 30 min)
- **Priority:** Do first
- **Fix:** Wrap artifact store mutations in a `threading.Lock`. Acquire the lock in `add`, `remove`, and `clear`. Read operations (`get`, `has`) can be unprotected if the dict is only mutated under lock.

---

### L-15: condition_syntax check not implemented standalone

- **Description:** The spec describes a standalone `check_condition_syntax(expr)` function for validating condition expressions without evaluating them. This function does not exist.
- **Module:** `loop-pipeline` / `validation.py`
- **Effort:** S (< 30 min)
- **Priority:** Defer
- **Fix:** Extract the parsing phase of condition evaluation into a standalone `check_condition_syntax(expr: str) -> list[str]` function that returns parse errors without evaluating. Wire it into the validation pipeline.

---

### 2e. Interviewer

---

### L-20: Interviewer missing ask_multiple/inform methods

- **Description:** The `Interviewer` protocol is missing the `ask_multiple()` method (batch multiple questions) and `inform()` method (one-way notification to human) defined in the spec.
- **Module:** `loop-pipeline` / `interviewer.py`
- **Effort:** M (30 min - 2 hrs)
- **Priority:** Do later
- **Fix:** Add `ask_multiple(questions: list[Question]) -> list[Answer]` and `inform(message: str) -> None` to the Interviewer protocol. Implement in all existing interviewer classes. `ask_multiple` can default to sequential `ask()` calls; `inform` can default to logging.

---

## 3. Testing

---

### L-19: E2E script hardcoded path

- **Description:** The end-to-end test script uses a hardcoded absolute path, making it non-portable across developer machines and CI environments.
- **Module:** `loop-pipeline` / `tests/e2e/run_e2e.sh`
- **Effort:** S (< 30 min)
- **Priority:** Defer
- **Fix:** Covered by Track 1 (test infrastructure). Replace hardcoded path with a relative path or environment variable. Use `$(dirname "$0")` or `$PROJECT_ROOT` for base path resolution.

---

## 4. Infrastructure

---

### L-21: HTTP server mode missing

- **Description:** The spec describes an HTTP server mode for loop-agent that exposes the agent session over an HTTP API (for remote clients, web UIs, etc.). This entire feature is unimplemented.
- **Module:** `loop-agent` (whole feature)
- **Effort:** L (2+ hrs)
- **Priority:** Defer
- **Fix:** Implement an HTTP server wrapper around the agent session using a lightweight framework (e.g., aiohttp or FastAPI). Expose endpoints for: create session, send message, get events (SSE stream), list tools, shutdown. This is a large feature that should be its own track/milestone.

---

## Appendix: Quick Reference Table

| ID | Title | Module | Effort | Priority | Batch |
|----|-------|--------|--------|----------|-------|
| M-1 | Missing response_id capture | loop-agent | S | Do first | A |
| M-2 | Loop detection message format | loop-agent | S | Do later | E |
| M-3 | Missing TOOL_CALL_OUTPUT_DELTA | loop-agent | M | Defer | E |
| M-4 | max_tool_rounds not per-provider | loop-agent | M | Do later | E |
| M-5 | No ToolRegistry class | loop-agent | M | Do first | A |
| M-6 | Missing env-var filtering | loop-agent | M | Do first | A |
| M-7 | Shallow shutdown | loop-agent | M | Do first | A |
| M-8 | No model field on spawn_agent | loop-agent | S | Do first | A |
| M-9 | DOT parser too permissive | loop-pipeline | S | Do first | B |
| M-10 | Node attrs not first-class | loop-pipeline | M | Do first | B |
| M-11 | Terminal node multiple exits | loop-pipeline | S | Do first | B |
| M-12 | Human handler wrong routing | loop-pipeline | M | Do first | C |
| M-13 | Human SKIPPED returns SUCCESS | loop-pipeline | S | Do first | C |
| M-14 | Manager max_cycles 10 vs 1000 | loop-pipeline | S | Do first | C |
| M-15 | Manager steering superficial | loop-pipeline | M | Do later | C |
| M-16 | Tool handler ignores timeout | loop-pipeline | M | Do first | C |
| M-17 | Fan-in no LLM evaluation | loop-pipeline | L | Defer | C |
| M-18 | Retry no error classification | loop-pipeline | M | Do later | C |
| M-19 | Status.json field mismatch | loop-pipeline | M | Do first | D |
| M-20 | No Transform interface | loop-pipeline | M | Do later | D |
| M-21 | Shape-name selectors missing | loop-pipeline | S | Do later | D |
| M-22 | Fidelity silent degradation | loop-pipeline | S | Do first | D |
| M-23 | Checkpoint resume fidelity | loop-pipeline | S | Do first | D |
| M-24 | Missing 2 interviewers | loop-pipeline | L | Defer | D |
| L-1 | DOT float .5 edge case | loop-pipeline | S | Do later | B |
| L-2 | Subgraph class derivation | loop-pipeline | S | Do later | B |
| L-3 | Undirected edge detection | loop-pipeline | S | Defer | B |
| L-4 | Edge attrs not first-class | loop-pipeline | M | Do later | B |
| L-5 | Graph attrs not first-class | loop-pipeline | M | Do later | B |
| L-6 | extra_rules param missing | loop-pipeline | S | Do later | B |
| L-7 | Bare key truthiness BNF | loop-pipeline | S | Do later | D |
| L-8 | Start node fallback missing | loop-pipeline | S | Do first | D |
| L-9 | Checkpoint nodes dict vs list | loop-pipeline | S | Do later | D |
| L-10 | Checkpoint missing logs | loop-pipeline | S | Do later | D |
| L-11 | auto_status not implemented | loop-pipeline | S | Do later | C |
| L-12 | Artifact name vs artifact_id | loop-pipeline | S | Do later | D |
| L-13 | Artifact missing methods | loop-pipeline | S | Do later | D |
| L-14 | Artifact store not thread-safe | loop-pipeline | S | Do first | D |
| L-15 | condition_syntax standalone | loop-pipeline | S | Defer | D |
| L-16 | Fan-in includes SKIPPED | loop-pipeline | S | Do later | C |
| L-17 | Variable expansion duplicated | loop-pipeline | M | Do first | D |
| L-18 | Handler fallback masks errors | loop-pipeline | S | Do first | C |
| L-19 | E2E script hardcoded path | loop-pipeline | S | Defer | — |
| L-20 | Interviewer ask_multiple/inform | loop-pipeline | M | Do later | D |
| L-21 | HTTP server mode missing | loop-agent | L | Defer | — |
| L-22 | Pre/post tool call hooks | loop-agent | M | Do later | A |
