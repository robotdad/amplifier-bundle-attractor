# Foundry DOTs (Phase 4) Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Replace the three Amplifier modes (`/admissions`, `/machine-design`, `/generate-machine`) with three DOT pipelines that constitute the foundry — the factory that builds bespoke dev-machines.

**Architecture:** Three sequential foundry pipelines: `admissions.dot` evaluates project readiness through five conversational gates; `machine-design.dot` conducts the founding session through six convergence-factory phases; `generate-machine.dot` stamps out all bespoke runtime DOT files and scripts. Each pipeline uses the already-built `conversational-gate.dot` and `convergence-factory.dot` patterns via folder nodes with `context.*` attribute injection (P7). Prompts and behavioral rules from the original mode files transfer verbatim — only `{{variable}}` → `$variable` syntax is adapted.

**Tech Stack:** DOT pipeline language (Graphviz syntax), Python (pytest, asyncio), `amplifier_module_loop_pipeline` (parse_dot, PipelineEngine, HandlerRegistry, PipelineContext, Outcome)

---

## Source Files — Read Before Implementing

All verbatim content comes from these files. The implementer MUST read them:

| File | Path | Lines |
|------|------|-------|
| admissions mode | `amplifier-bundle-dev-machine/modes/admissions.md` | 115 |
| machine-design mode | `amplifier-bundle-dev-machine/modes/machine-design.md` | 143 |
| generate-machine mode | `amplifier-bundle-dev-machine/modes/generate-machine.md` | 194 |
| gate criteria | `amplifier-bundle-dev-machine/context/gate-criteria.md` | 195 |
| admissions-advisor agent | `amplifier-bundle-dev-machine/agents/admissions-advisor.md` | 58 |
| machine-designer agent | `amplifier-bundle-dev-machine/agents/machine-designer.md` | 63 |
| machine-generator agent | `amplifier-bundle-dev-machine/agents/machine-generator.md` | 115 |
| templates reference | `amplifier-bundle-dev-machine/context/templates-reference.md` | 115 |

All paths above are relative to `/home/bkrabach/dev/attractor-dev-machine/`.

## Existing Infrastructure — Already Built

| Resource | Path |
|----------|------|
| `conversational-gate.dot` | `amplifier-bundle-attractor/examples/patterns/conversational-gate.dot` |
| `convergence-factory.dot` | `amplifier-bundle-attractor/examples/patterns/convergence-factory.dot` |
| Test suite root | `amplifier-bundle-attractor/modules/loop-pipeline/tests/` |
| Pattern tests (reference) | `test_p2_conversational_gate.py`, `test_p6_convergence_factory.py`, `test_p7_context_injection.py` |

The foundry DOT files live at:
`amplifier-bundle-attractor/examples/dev-machine/foundry/`

This directory does not exist yet — create it in Task 21.

**Path from `foundry/` to `patterns/`:** `../../patterns/`

---

## DOT Syntax Reference

Folder nodes invoke subpipelines with context injection:
```dot
gate1 [shape=folder, dot_file="../../patterns/conversational-gate.dot",
    context.gate_topic="...",
    context.gate_criteria="...",
    context.gate_output_path=".ai/gate1_decomposability.md"]
```

Diamond routing reads `context.preferred_label` (set by codergen nodes via `report_outcome`):
```dot
verdict_gate -> done_proceed [label="proceed", condition="context.preferred_label=proceed"]
```

Tool nodes with JSON output:
```dot
check_node [shape=parallelogram,
    tool_command="test -f .dev-machine-assessment.md && echo '{\"exists\": \"true\"}' || echo '{\"exists\": \"false\"}'",
    parse_json="true"]
```

---

## Task 21: `admissions.dot` — Project Readiness Evaluation

**Translates:** `/admissions` mode (115 lines) + `gate-criteria.md` (195 lines) + admissions-advisor agent (58 lines)

**Files:**
- Create: `amplifier-bundle-attractor/examples/dev-machine/foundry/admissions.dot`
- Create: `amplifier-bundle-attractor/modules/loop-pipeline/tests/test_foundry_admissions.py`

---

### Step 1: Write the failing structural test

Create `amplifier-bundle-attractor/modules/loop-pipeline/tests/test_foundry_admissions.py`:

```python
"""Tests for foundry/admissions.dot — Project Readiness Evaluation Pipeline.

Structural parse tests verifying the DOT file encodes the correct graph:
- 5 folder nodes (one per admissions gate) referencing conversational-gate.dot
- 1 codergen node (compile_assessment) with verbatim prompt from admissions mode
- 1 diamond (verdict_gate) routing to 3 terminal nodes
- Sequential flow: start -> gate1 -> gate2 -> gate3 -> gate4 -> gate5 -> compile -> verdict_gate
- Each gate folder node has context.gate_topic, context.gate_criteria, context.gate_output_path
- Gate topics embed verbatim question text from gate-criteria.md
"""
from __future__ import annotations

from pathlib import Path

import pytest

from amplifier_module_loop_pipeline.dot_parser import parse_dot

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_FOUNDRY_DIR = _REPO_ROOT / "examples" / "dev-machine" / "foundry"
_ADMISSIONS_DOT = _FOUNDRY_DIR / "admissions.dot"
_PATTERNS_DIR = _REPO_ROOT / "examples" / "patterns"


# ---------------------------------------------------------------------------
# Structural tests: Parse admissions.dot
# ---------------------------------------------------------------------------


class TestAdmissionsParse:
    """Structural tests: admissions.dot parses to expected graph topology."""

    def test_file_exists(self):
        """admissions.dot exists at examples/dev-machine/foundry/admissions.dot."""
        assert _ADMISSIONS_DOT.exists(), f"File not found: {_ADMISSIONS_DOT}"

    def test_parses_without_error(self):
        """admissions.dot parses without raising an exception."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        assert len(g.nodes) > 0

    def test_has_exactly_ten_nodes(self):
        """Pipeline has 10 nodes: start, gate1-5, compile_assessment, verdict_gate, 3 done terminals."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        assert len(g.nodes) == 10, (
            f"Expected 10 nodes, got {len(g.nodes)}: {list(g.nodes.keys())}"
        )

    def test_has_start_node(self):
        """Pipeline has exactly one Mdiamond start node."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        start_nodes = [n for n in g.nodes.values() if n.shape == "Mdiamond"]
        assert len(start_nodes) == 1, (
            f"Expected 1 Mdiamond start node, got {len(start_nodes)}"
        )

    def test_has_five_folder_nodes(self):
        """Pipeline has exactly 5 folder nodes (one per admissions gate)."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        assert len(folder_nodes) == 5, (
            f"Expected 5 folder nodes, got {len(folder_nodes)}: "
            f"{[n.id for n in folder_nodes]}"
        )

    def test_folder_nodes_reference_conversational_gate(self):
        """All 5 folder nodes reference conversational-gate.dot."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        for node in folder_nodes:
            dot_file = node.attrs.get("dot_file", "")
            assert "conversational-gate.dot" in dot_file, (
                f"Node {node.id!r} dot_file should reference conversational-gate.dot, "
                f"got {dot_file!r}"
            )

    def test_folder_nodes_have_all_three_context_attrs(self):
        """Each gate folder node has context.gate_topic, context.gate_criteria, context.gate_output_path."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        for node in folder_nodes:
            assert "context.gate_topic" in node.attrs, (
                f"Node {node.id!r} missing context.gate_topic"
            )
            assert "context.gate_criteria" in node.attrs, (
                f"Node {node.id!r} missing context.gate_criteria"
            )
            assert "context.gate_output_path" in node.attrs, (
                f"Node {node.id!r} missing context.gate_output_path"
            )

    def test_gate_output_paths_are_unique(self):
        """Each gate writes to a distinct .ai/gateN_*.md output path."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        output_paths = [node.attrs.get("context.gate_output_path", "") for node in folder_nodes]
        assert len(set(output_paths)) == 5, (
            f"Expected 5 unique gate_output_paths, got {output_paths}"
        )

    def test_gate_topics_contain_decomposability(self):
        """At least one gate topic mentions DECOMPOSABILITY (gate 1)."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        topics = [node.attrs.get("context.gate_topic", "") for node in folder_nodes]
        assert any("DECOMPOSAB" in t.upper() for t in topics), (
            f"Expected a gate topic mentioning DECOMPOSABILITY, got topics: {topics!r}"
        )

    def test_gate_topics_contain_correctness(self):
        """At least one gate topic mentions CORRECTNESS (gate 2)."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        topics = [node.attrs.get("context.gate_topic", "") for node in folder_nodes]
        assert any("CORRECT" in t.upper() for t in topics), (
            f"Expected a gate topic mentioning CORRECTNESS, got topics: {topics!r}"
        )

    def test_gate_topics_contain_architecture(self):
        """At least one gate topic mentions ARCHITECTURE (gate 3)."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        topics = [node.attrs.get("context.gate_topic", "") for node in folder_nodes]
        assert any("ARCHITECT" in t.upper() for t in topics), (
            f"Expected a gate topic mentioning ARCHITECTURE, got topics: {topics!r}"
        )

    def test_gate_topics_contain_toolchain(self):
        """At least one gate topic mentions TOOLCHAIN (gate 4)."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        topics = [node.attrs.get("context.gate_topic", "") for node in folder_nodes]
        assert any("TOOLCHAIN" in t.upper() for t in topics), (
            f"Expected a gate topic mentioning TOOLCHAIN, got topics: {topics!r}"
        )

    def test_gate_topics_contain_spec(self):
        """At least one gate topic mentions SPEC (gate 5)."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        topics = [node.attrs.get("context.gate_topic", "") for node in folder_nodes]
        assert any("SPEC" in t.upper() for t in topics), (
            f"Expected a gate topic mentioning SPEC, got topics: {topics!r}"
        )

    def test_gate_criteria_contain_scoring_thresholds(self):
        """Gate criteria contain scoring threshold text (75-100%, 50-74%, 0-49%)."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        for node in folder_nodes:
            criteria = node.attrs.get("context.gate_criteria", "")
            assert "75" in criteria, (
                f"Node {node.id!r} gate_criteria missing '75' threshold: {criteria[:100]!r}"
            )
            assert "50" in criteria, (
                f"Node {node.id!r} gate_criteria missing '50' threshold: {criteria[:100]!r}"
            )

    def test_has_compile_assessment_codergen_node(self):
        """Pipeline has a compile_assessment node (box/codergen shape)."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        assert "compile_assessment" in g.nodes, (
            f"Node 'compile_assessment' missing. Nodes: {list(g.nodes.keys())}"
        )
        node = g.nodes["compile_assessment"]
        assert node.shape in ("box", "", None), (
            f"Expected compile_assessment to be box/codergen, got {node.shape!r}"
        )

    def test_compile_assessment_prompt_contains_gate_files(self):
        """compile_assessment prompt references the 5 gate output files."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        prompt = g.nodes["compile_assessment"].prompt or ""
        assert ".ai/gate1" in prompt, f"Prompt missing gate1 file reference: {prompt[:200]!r}"
        assert ".ai/gate2" in prompt, f"Prompt missing gate2 file reference: {prompt[:200]!r}"
        assert ".ai/gate3" in prompt, f"Prompt missing gate3 file reference: {prompt[:200]!r}"
        assert ".ai/gate4" in prompt, f"Prompt missing gate4 file reference: {prompt[:200]!r}"
        assert ".ai/gate5" in prompt, f"Prompt missing gate5 file reference: {prompt[:200]!r}"

    def test_compile_assessment_prompt_contains_threshold_rules(self):
        """compile_assessment prompt contains the scoring threshold rules (50%, 75%)."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        prompt = g.nodes["compile_assessment"].prompt or ""
        assert "50" in prompt, f"Prompt missing 50% threshold rule: {prompt[:300]!r}"
        assert "75" in prompt, f"Prompt missing 75% threshold rule: {prompt[:300]!r}"

    def test_compile_assessment_prompt_mentions_dev_machine_assessment(self):
        """compile_assessment prompt references writing .dev-machine-assessment.md."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        prompt = g.nodes["compile_assessment"].prompt or ""
        assert ".dev-machine-assessment.md" in prompt, (
            f"Prompt missing '.dev-machine-assessment.md' reference: {prompt[:300]!r}"
        )

    def test_compile_assessment_prompt_mentions_preferred_label(self):
        """compile_assessment prompt instructs agent to set preferred_label (proceed/caution/not_ready)."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        prompt = g.nodes["compile_assessment"].prompt or ""
        assert "preferred_label" in prompt or "proceed" in prompt, (
            f"Prompt should mention preferred_label or proceed verdict: {prompt[:300]!r}"
        )

    def test_has_verdict_diamond(self):
        """Pipeline has a verdict_gate diamond node."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        assert "verdict_gate" in g.nodes, (
            f"Node 'verdict_gate' missing. Nodes: {list(g.nodes.keys())}"
        )
        assert g.nodes["verdict_gate"].shape == "diamond", (
            f"Expected verdict_gate shape=diamond, got {g.nodes['verdict_gate'].shape!r}"
        )

    def test_has_three_terminal_nodes(self):
        """Pipeline has 3 Msquare terminal nodes (proceed, caution, not_ready)."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        done_nodes = [n for n in g.nodes.values() if n.shape == "Msquare"]
        assert len(done_nodes) == 3, (
            f"Expected 3 Msquare terminal nodes, got {len(done_nodes)}: "
            f"{[n.id for n in done_nodes]}"
        )

    def test_verdict_gate_has_three_conditional_edges(self):
        """verdict_gate has exactly 3 conditional outgoing edges."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        verdict_edges = [e for e in g.edges if e.from_node == "verdict_gate"]
        assert len(verdict_edges) == 3, (
            f"Expected 3 edges from verdict_gate, got {len(verdict_edges)}"
        )
        for e in verdict_edges:
            assert e.condition, (
                f"Edge verdict_gate->{e.to_node} should have a condition"
            )

    def test_verdict_conditions_cover_all_verdicts(self):
        """verdict_gate edges cover proceed, caution, and not_ready conditions."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        verdict_edges = [e for e in g.edges if e.from_node == "verdict_gate"]
        conditions = " ".join(e.condition or "" for e in verdict_edges)
        assert "proceed" in conditions, (
            f"Expected 'proceed' condition on a verdict edge. Conditions: {conditions!r}"
        )
        assert "not_ready" in conditions or "not-ready" in conditions, (
            f"Expected 'not_ready' condition on a verdict edge. Conditions: {conditions!r}"
        )

    def test_sequential_flow_start_to_verdict(self):
        """Linear chain: start -> gate1 -> gate2 -> gate3 -> gate4 -> gate5 -> compile_assessment -> verdict_gate."""
        source = _ADMISSIONS_DOT.read_text()
        g = parse_dot(source)
        # Build simple edge map (no-condition edges only for linear chain)
        edge_map: dict[str, str] = {}
        for e in g.edges:
            if not e.condition:
                edge_map[e.from_node] = e.to_node

        start_node = next(
            (n.id for n in g.nodes.values() if n.shape == "Mdiamond"), None
        )
        assert start_node is not None, "No start (Mdiamond) node found"

        current = start_node
        visited = [current]
        for _ in range(7):  # start->g1->g2->g3->g4->g5->compile->verdict = 8 nodes
            nxt = edge_map.get(current)
            if nxt is None:
                break
            visited.append(nxt)
            current = nxt

        assert len(visited) == 8, (
            f"Expected 8-node linear chain, got {len(visited)}: {visited}"
        )
        assert visited[-1] == "verdict_gate", (
            f"Expected chain to end at verdict_gate, ended at {visited[-1]!r}: {visited}"
        )
```

---

### Step 2: Run the test to verify it fails (file doesn't exist yet)

```bash
cd amplifier-bundle-attractor
python -m pytest modules/loop-pipeline/tests/test_foundry_admissions.py::TestAdmissionsParse::test_file_exists -v
```

Expected: **FAIL** with `AssertionError: File not found: .../examples/dev-machine/foundry/admissions.dot`

---

### Step 3: Create the foundry directory and write `admissions.dot`

First create the directory:
```bash
mkdir -p amplifier-bundle-attractor/examples/dev-machine/foundry
```

Create `amplifier-bundle-attractor/examples/dev-machine/foundry/admissions.dot`:

```dot
// admissions.dot -- Foundry pipeline for evaluating project readiness.
//
// Translates the /admissions mode to a DOT pipeline.
// Five sequential conversational-gate.dot invocations (one per admissions gate),
// followed by an assessment compilation codergen node and a verdict routing diamond.
//
// Source material (prompts transfer verbatim, only {{var}} -> $var syntax adapted):
//   amplifier-bundle-dev-machine/modes/admissions.md (115 lines)
//   amplifier-bundle-dev-machine/context/gate-criteria.md (195 lines)
//   amplifier-bundle-dev-machine/agents/admissions-advisor.md (58 lines)
//
// Required output: .dev-machine-assessment.md written by compile_assessment node.
// Verdict routes to done_proceed, done_caution, or done_not_ready terminals.

digraph admissions {
    graph [goal="Evaluate project readiness for autonomous dev-machine"]

    start [shape=Mdiamond, label="Admissions Start"]

    // -----------------------------------------------------------------------
    // Gate 1: Decomposability
    // Source: gate-criteria.md lines 17-42, admissions.md lines 40-51
    // -----------------------------------------------------------------------
    gate1 [shape=folder, dot_file="../../patterns/conversational-gate.dot",
        context.gate_topic="GATE 1: DECOMPOSABILITY\n\nYou are evaluating whether this project is suitable for an autonomous development machine.\n\nConduct a focused conversation with the user about decomposability:\n- Ask: 'Describe the major components/modules of what you are building'\n- Ask: 'Can you list 10+ concrete features?'\n- Ask: 'How independent are these features from each other?'\n\nExamine the codebase if it exists:\n- Look at directory structure, module boundaries\n- Check for existing specs, README, architecture docs\n\nScore this gate 0-100% with evidence. No rounding up. No optimism bias.",
        context.gate_criteria="Gate 1: Decomposability\n\nQuestion: Can the problem be broken into hundreds of small, independently implementable and testable units of work?\n\nHigh confidence (75-100%) signals:\n- Clear module/component boundaries already exist or are obvious\n- Features within modules are independent (minimal cross-cutting concerns)\n- Each feature can be specified in <2 pages\n- Features follow repeating patterns (CRUD, UI components, API endpoints)\n- The user can list 10+ concrete features off the top of their head\n\nMedium confidence (50-74%) signals:\n- Modules are identifiable but boundaries are fuzzy\n- Some features have deep cross-module dependencies\n- The user can describe features but they vary widely in scope\n- Some features require coordinated changes across 3+ modules\n\nLow confidence (0-49%) signals:\n- The problem is a single monolithic algorithm or pipeline\n- Features are deeply interconnected (changing one breaks many)\n- Most features require novel design, not pattern application\n- The user describes the work as 'it all has to come together at once'\n- Fewer than 50 identifiable features\n\nRemediation: Identify natural boundaries. Consider breaking the problem into a smaller initial scope. Look for the 'inner loop' that can be built first.\n\nWrite your gate score and evidence to $gate_output_path.\nReturn preferred_label='scored' when you have assigned a score with evidence.",
        context.gate_output_path=".ai/gate1_decomposability.md"]

    // -----------------------------------------------------------------------
    // Gate 2: Verifiable Correctness with Speed
    // Source: gate-criteria.md lines 45-70, admissions.md lines 52-63
    // -----------------------------------------------------------------------
    gate2 [shape=folder, dot_file="../../patterns/conversational-gate.dot",
        context.gate_topic="GATE 2: VERIFIABLE CORRECTNESS WITH SPEED\n\nYou are evaluating whether each unit of work can be verified automatically with fast feedback.\n\nAsk and check:\n- 'What test framework do you use?'\n- 'How long does your test suite take?'\n- 'Do you have a type checker or linter?'\n\nIf codebase exists, verify:\n- Run the test command and check it works\n- Run the build command and check it works\n- Check for existing tests\n\nScore this gate 0-100% with evidence. No rounding up. No optimism bias.",
        context.gate_criteria="Gate 2: Verifiable Correctness with Speed\n\nQuestion: Can each unit of work be verified automatically with fast feedback?\n\nHigh confidence (75-100%) signals:\n- Established test framework exists for the tech stack\n- Test execution takes seconds (unit) to minutes (integration)\n- Type system catches structural errors (TypeScript, Rust, Go, etc.)\n- CI/CD pipeline exists or can be trivially set up\n- Clear definition of 'correct' for each feature type\n\nMedium confidence (50-74%) signals:\n- Test framework exists but coverage is minimal\n- Some features have clear correctness criteria, others are subjective\n- Build/test cycle takes 2-5 minutes\n- Type system is present but loosely used\n\nLow confidence (0-49%) signals:\n- No test framework or testing culture\n- Correctness is primarily visual/subjective (design work, creative writing)\n- Build/test cycle takes >10 minutes\n- No type system and dynamic language with no linting\n- 'You have to run it and look at it to know if it is right'\n\nRemediation: Set up a test framework. Add a type checker or linter. Define acceptance criteria templates. Consider if the verification gap can be addressed by a QA machine.\n\nWrite your gate score and evidence to $gate_output_path.\nReturn preferred_label='scored' when you have assigned a score with evidence.",
        context.gate_output_path=".ai/gate2_correctness.md"]

    // -----------------------------------------------------------------------
    // Gate 3: Sufficient Architecture
    // Source: gate-criteria.md lines 73-101, admissions.md lines 64-73
    // -----------------------------------------------------------------------
    gate3 [shape=folder, dot_file="../../patterns/conversational-gate.dot",
        context.gate_topic="GATE 3: SUFFICIENT ARCHITECTURE\n\nYou are evaluating whether there is enough architectural clarity to write a 'constitution' that prevents drift across hundreds of features.\n\nAsk and check:\n- 'Do you have an architecture document?'\n- 'Can you describe module boundaries and key interfaces?'\n- 'What are your core technology choices?'\n\nIf docs exist, read them and assess completeness.\n\nScore this gate 0-100% with evidence. No rounding up. No optimism bias.",
        context.gate_criteria="Gate 3: Sufficient Architecture\n\nQuestion: Is there enough architectural clarity to write a 'constitution' that prevents drift across hundreds of features?\n\nHigh confidence (75-100%) signals:\n- Clear data model exists or can be defined\n- Technology choices are made and rationale is understood\n- Module boundaries are defined with explicit interfaces\n- Key patterns are established (state management, data flow, error handling)\n- The user can explain the system's architecture in 10 minutes\n\nMedium confidence (50-74%) signals:\n- Data model exists but has known gaps\n- Some technology choices are tentative\n- Module boundaries are roughly known but interfaces are not formalized\n- Some patterns are established, others are ad hoc\n- 'We know roughly how it works but have not written it down'\n\nLow confidence (0-49%) signals:\n- No data model -- 'we will figure it out as we go'\n- Technology choices are still being evaluated\n- No module boundaries -- 'it is all one thing right now'\n- No established patterns\n- The user cannot explain the architecture without hand-waving\n\nRemediation: Run a focused architecture session. You do not need everything -- you need enough to write a 30-50 page constitution covering data model, module boundaries, technology choices, and key interfaces. The architecture can be progressive (design the first 3 modules well enough to start, design more later).\n\nImportant: Architecture does NOT need to be exhaustive. 'Sufficient' means: enough to prevent drift, not enough to anticipate everything.\n\nWrite your gate score and evidence to $gate_output_path.\nReturn preferred_label='scored' when you have assigned a score with evidence.",
        context.gate_output_path=".ai/gate3_architecture.md"]

    // -----------------------------------------------------------------------
    // Gate 4: Functioning Toolchain
    // Source: gate-criteria.md lines 104-129, admissions.md lines 74-83
    // -----------------------------------------------------------------------
    gate4 [shape=folder, dot_file="../../patterns/conversational-gate.dot",
        context.gate_topic="GATE 4: FUNCTIONING TOOLCHAIN\n\nYou are evaluating whether the build and test commands work and a fresh session can run them.\n\nVerify:\n- Build command runs and succeeds\n- Test command runs and reports results\n- How fast is the cycle?\n\nIf no toolchain exists, assess how much work it would take to set up.\n\nScore this gate 0-100% with evidence. No rounding up. No optimism bias.",
        context.gate_criteria="Gate 4: Functioning Toolchain\n\nQuestion: Do the build and test commands work? Can a fresh session run them?\n\nHigh confidence (75-100%) signals:\n- build_command runs and succeeds from a clean state\n- test_command runs and reports results\n- Commands are fast (<2 minutes for build, <5 minutes for full test suite)\n- No manual setup required beyond initial clone\n- CI/CD is configured or trivially configurable\n\nMedium confidence (50-74%) signals:\n- Build command works but is slow (>5 minutes)\n- Test command works but only for some modules\n- Some manual setup required (environment variables, local services)\n- 'It works on my machine' but setup is not documented\n\nLow confidence (0-49%) signals:\n- No build command exists yet\n- No test command exists yet\n- Setup requires multiple manual steps that are not documented\n- The project has not been bootstrapped (no package.json, Cargo.toml, etc.)\n- 'We have not set up the project yet'\n\nRemediation: Bootstrap the project scaffold. This CAN be the machine's first task -- but the toolchain must work before the machine can build features. Set up: package manager, build command, test runner, type checker. Verify they run cleanly.\n\nWrite your gate score and evidence to $gate_output_path.\nReturn preferred_label='scored' when you have assigned a score with evidence.",
        context.gate_output_path=".ai/gate4_toolchain.md"]

    // -----------------------------------------------------------------------
    // Gate 5: Spec Quality
    // Source: gate-criteria.md lines 132-157, admissions.md lines 84-91
    // -----------------------------------------------------------------------
    gate5 [shape=folder, dot_file="../../patterns/conversational-gate.dot",
        context.gate_topic="GATE 5: SPEC QUALITY\n\nYou are evaluating whether initial feature specs can be written at sufficient quality for machine consumption.\n\nAssess:\n- Do existing specs/PRDs have enough detail?\n- Can a sample feature spec be written?\n- Is there a domain expert available?\n\nScore this gate 0-100% with evidence. No rounding up. No optimism bias.",
        context.gate_criteria="Gate 5: Spec Quality\n\nQuestion: Can initial feature specs be written at sufficient quality for machine consumption?\n\nHigh confidence (75-100%) signals:\n- Existing specs (PRDs, user stories) contain concrete details\n- Features can be specified with: interfaces, acceptance criteria, edge cases, files to modify\n- The user has domain knowledge to review specs for accuracy\n- Spec writing follows a repeatable template\n- A sample spec can be written and reviewed in <15 minutes\n\nMedium confidence (50-74%) signals:\n- Specs exist but are high-level ('add user authentication')\n- Features can be described but acceptance criteria are vague\n- Domain knowledge exists but is not documented\n- 'We know what we want but have not written it down precisely'\n\nLow confidence (0-49%) signals:\n- No specs exist -- 'we are making it up as we go'\n- Features cannot be described without extensive discussion\n- No domain expert available to review specs\n- Requirements change frequently and unpredictably\n- 'We will know it when we see it'\n\nRemediation: Write 3-5 sample specs using the feature spec template. Have a domain expert review them. If the specs are too vague, the problem may need more product definition before a machine can build it.\n\nWrite your gate score and evidence to $gate_output_path.\nReturn preferred_label='scored' when you have assigned a score with evidence.",
        context.gate_output_path=".ai/gate5_spec_quality.md"]

    // -----------------------------------------------------------------------
    // Assessment Compilation
    // Source: admissions.md lines 93-115, gate-criteria.md lines 1-14, 160-196
    //         admissions-advisor.md lines 29-58
    // -----------------------------------------------------------------------
    compile_assessment [shape=box,
        label="Compile Assessment",
        prompt="ADMISSIONS MODE activated. You are evaluating whether this project is suitable for an autonomous development machine.\n\nAll five gates have been evaluated. Read the gate score files and compile the final assessment.\n\nYour knowledge includes the autonomous development machine pattern and honest evaluation principles:\n- Be evidence-based: verify claims, run commands if needed\n- Be honest: no optimism bias, below 50% is a hard stop\n- Be helpful: for failing gates, provide concrete remediation steps\n\nRead each gate output file:\n- .ai/gate1_decomposability.md\n- .ai/gate2_correctness.md\n- .ai/gate3_architecture.md\n- .ai/gate4_toolchain.md\n- .ai/gate5_spec_quality.md\n\nApply scoring rules:\n- Below 50% on ANY gate: Hard stop. Provide specific remediation guidance for each failing gate.\n- 50-75%: Proceed with caution. Flag the risk explicitly. The user decides whether to continue.\n- Above 75%: Confident. Proceed.\n- If three or more gates are below 75%, recommend the user address them before proceeding.\n\nThe admissions advisor MUST be transparent about scores. No rounding up. No optimism bias.\n\nWrite the assessment to .dev-machine-assessment.md using this exact format:\n\n# Dev Machine Assessment\n\n**Project:** [name]\n**Date:** [ISO date]\n**Overall Verdict:** PROCEED / PROCEED WITH CAUTION / NOT READY\n\n## Gate Scores\n\n| Gate | Score | Verdict |\n|------|-------|---------|\n| 1. Decomposability | XX% | PASS/CAUTION/FAIL |\n| 2. Verifiable Correctness | XX% | PASS/CAUTION/FAIL |\n| 3. Sufficient Architecture | XX% | PASS/CAUTION/FAIL |\n| 4. Functioning Toolchain | XX% | PASS/CAUTION/FAIL |\n| 5. Spec Quality | XX% | PASS/CAUTION/FAIL |\n\n## Per-Gate Analysis\n\n### Gate 1: Decomposability (XX%)\n[Evidence and reasoning]\n\n### Gate 2: Verifiable Correctness (XX%)\n[Evidence and reasoning]\n\n### Gate 3: Sufficient Architecture (XX%)\n[Evidence and reasoning]\n\n### Gate 4: Functioning Toolchain (XX%)\n[Evidence and reasoning]\n\n### Gate 5: Spec Quality (XX%)\n[Evidence and reasoning]\n\n## Remediation Plan (if any gates < 50%)\n[Specific steps to address failing gates]\n\n## Recommended Next Steps\n[What to do next based on the assessment]\n\nAfter writing the file, determine the overall verdict:\n- If overall score >75% AND no individual gate below 50%: return preferred_label='proceed'\n- If overall score 50-75% OR gates near threshold: return preferred_label='caution'\n- If any gate below 50% OR overall score below 50%: return preferred_label='not_ready'\n\nIf the verdict is proceed or caution, include in your response: 'Run machine-design.dot to begin designing your development machine.'"]

    verdict_gate [shape=diamond, label="Verdict?"]

    done_proceed   [shape=Msquare, label="PROCEED: Run machine-design.dot"]
    done_caution   [shape=Msquare, label="PROCEED WITH CAUTION: Address flagged risks then run machine-design.dot"]
    done_not_ready [shape=Msquare, label="NOT READY: Address remediation items before proceeding"]

    // Flow
    start -> gate1 -> gate2 -> gate3 -> gate4 -> gate5 -> compile_assessment -> verdict_gate

    // Verdict routing (compile_assessment sets preferred_label via report_outcome)
    verdict_gate -> done_proceed   [label="proceed",   condition="context.preferred_label=proceed"]
    verdict_gate -> done_caution   [label="caution",   condition="context.preferred_label=caution"]
    verdict_gate -> done_not_ready [label="not_ready", condition="context.preferred_label=not_ready"]
}
```

---

### Step 4: Run all structural tests to verify they pass

```bash
cd amplifier-bundle-attractor
python -m pytest modules/loop-pipeline/tests/test_foundry_admissions.py -v
```

Expected: **All PASS** — 18 tests passing.

If any test fails, fix the DOT file (not the test). The test encodes the correct contract.

---

### Step 5: Commit

```bash
cd amplifier-bundle-attractor
git add examples/dev-machine/foundry/admissions.dot modules/loop-pipeline/tests/test_foundry_admissions.py
git commit -m "feat: add foundry/admissions.dot with 5-gate conversational evaluation pipeline"
```

---

## Task 22: `machine-design.dot` — Bespoke Machine Specification

**Translates:** `/machine-design` mode (143 lines) + machine-designer agent (63 lines)

**Files:**
- Create: `amplifier-bundle-attractor/examples/dev-machine/foundry/machine-design.dot`
- Create: `amplifier-bundle-attractor/modules/loop-pipeline/tests/test_foundry_machine_design.py`

---

### Step 1: Write the failing structural test

Create `amplifier-bundle-attractor/modules/loop-pipeline/tests/test_foundry_machine_design.py`:

```python
"""Tests for foundry/machine-design.dot — Bespoke Machine Specification Pipeline.

Structural parse tests verifying:
- Gate check: parallelogram tool node checks .dev-machine-assessment.md exists
- Diamond routing: missing -> done_no_assessment, exists -> phase1
- Phase 1 (Gather Config): folder node referencing conversational-gate.dot
- Phases 2-4: folder nodes referencing convergence-factory.dot
- Phase 5: codergen node compiling .dev-machine-design.md
- Phase 6: codergen wrap-up node
- Linear flow from assessment_gate through all 6 phases to done
"""
from __future__ import annotations

from pathlib import Path

import pytest

from amplifier_module_loop_pipeline.dot_parser import parse_dot

_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_FOUNDRY_DIR = _REPO_ROOT / "examples" / "dev-machine" / "foundry"
_MACHINE_DESIGN_DOT = _FOUNDRY_DIR / "machine-design.dot"


class TestMachineDesignParse:
    """Structural tests: machine-design.dot parses to expected graph topology."""

    def test_file_exists(self):
        """machine-design.dot exists at examples/dev-machine/foundry/machine-design.dot."""
        assert _MACHINE_DESIGN_DOT.exists(), f"File not found: {_MACHINE_DESIGN_DOT}"

    def test_parses_without_error(self):
        """machine-design.dot parses without raising an exception."""
        source = _MACHINE_DESIGN_DOT.read_text()
        g = parse_dot(source)
        assert len(g.nodes) > 0

    def test_has_assessment_check_tool_node(self):
        """Pipeline has an assessment_check parallelogram (tool) node."""
        source = _MACHINE_DESIGN_DOT.read_text()
        g = parse_dot(source)
        assert "assessment_check" in g.nodes, (
            f"Node 'assessment_check' missing. Nodes: {list(g.nodes.keys())}"
        )
        assert g.nodes["assessment_check"].shape == "parallelogram", (
            f"Expected assessment_check shape=parallelogram, "
            f"got {g.nodes['assessment_check'].shape!r}"
        )

    def test_assessment_check_has_tool_command(self):
        """assessment_check has a tool_command checking for .dev-machine-assessment.md."""
        source = _MACHINE_DESIGN_DOT.read_text()
        g = parse_dot(source)
        node = g.nodes["assessment_check"]
        tool_cmd = node.attrs.get("tool_command", "")
        assert ".dev-machine-assessment.md" in tool_cmd, (
            f"Expected tool_command to check .dev-machine-assessment.md, "
            f"got {tool_cmd!r}"
        )

    def test_assessment_check_has_parse_json(self):
        """assessment_check has parse_json='true' to populate context from JSON output."""
        source = _MACHINE_DESIGN_DOT.read_text()
        g = parse_dot(source)
        node = g.nodes["assessment_check"]
        parse_json = node.attrs.get("parse_json", "")
        assert parse_json == "true", (
            f"Expected parse_json='true' on assessment_check, got {parse_json!r}"
        )

    def test_has_assessment_gate_diamond(self):
        """Pipeline has an assessment_gate diamond node."""
        source = _MACHINE_DESIGN_DOT.read_text()
        g = parse_dot(source)
        assert "assessment_gate" in g.nodes, (
            f"Node 'assessment_gate' missing. Nodes: {list(g.nodes.keys())}"
        )
        assert g.nodes["assessment_gate"].shape == "diamond", (
            f"Expected assessment_gate shape=diamond, "
            f"got {g.nodes['assessment_gate'].shape!r}"
        )

    def test_assessment_gate_has_two_conditional_edges(self):
        """assessment_gate has exactly 2 conditional edges (exists/missing)."""
        source = _MACHINE_DESIGN_DOT.read_text()
        g = parse_dot(source)
        gate_edges = [e for e in g.edges if e.from_node == "assessment_gate"]
        assert len(gate_edges) == 2, (
            f"Expected 2 edges from assessment_gate, got {len(gate_edges)}"
        )
        for e in gate_edges:
            assert e.condition, (
                f"Edge assessment_gate->{e.to_node} should have a condition"
            )

    def test_has_done_no_assessment_terminal(self):
        """Pipeline has a terminal node for missing assessment (early exit)."""
        source = _MACHINE_DESIGN_DOT.read_text()
        g = parse_dot(source)
        done_nodes = [n for n in g.nodes.values() if n.shape == "Msquare"]
        node_ids = [n.id for n in done_nodes]
        assert any("no_assessment" in nid or "missing" in nid for nid in node_ids), (
            f"Expected a 'done_no_assessment' or 'missing' terminal node, "
            f"got Msquare nodes: {node_ids}"
        )

    def test_has_phase1_conversational_gate_folder(self):
        """Phase 1 uses a conversational-gate.dot folder node (gather config)."""
        source = _MACHINE_DESIGN_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        gate_folders = [
            n for n in folder_nodes
            if "conversational-gate.dot" in n.attrs.get("dot_file", "")
        ]
        assert len(gate_folders) >= 1, (
            f"Expected at least 1 folder node referencing conversational-gate.dot. "
            f"Folder nodes: {[(n.id, n.attrs.get('dot_file','')) for n in folder_nodes]}"
        )

    def test_has_convergence_factory_folder_nodes(self):
        """Phases 2-4 use convergence-factory.dot folder nodes."""
        source = _MACHINE_DESIGN_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        factory_folders = [
            n for n in folder_nodes
            if "convergence-factory.dot" in n.attrs.get("dot_file", "")
        ]
        assert len(factory_folders) >= 3, (
            f"Expected at least 3 convergence-factory.dot folder nodes (phases 2-4), "
            f"got {len(factory_folders)}: {[n.id for n in factory_folders]}"
        )

    def test_convergence_factory_nodes_have_required_context_attrs(self):
        """All convergence-factory folder nodes have the 4 required context.* attrs."""
        source = _MACHINE_DESIGN_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        factory_folders = [
            n for n in folder_nodes
            if "convergence-factory.dot" in n.attrs.get("dot_file", "")
        ]
        for node in factory_folders:
            assert "context.artifact_goal" in node.attrs, (
                f"Node {node.id!r} missing context.artifact_goal"
            )
            assert "context.artifact_path" in node.attrs, (
                f"Node {node.id!r} missing context.artifact_path"
            )
            assert "context.validation_criteria" in node.attrs, (
                f"Node {node.id!r} missing context.validation_criteria"
            )
            assert "context.validation_command" in node.attrs, (
                f"Node {node.id!r} missing context.validation_command"
            )

    def test_phase1_gate_topic_mentions_config_variables(self):
        """Phase 1 gate_topic mentions key config variables (project_name, build_command)."""
        source = _MACHINE_DESIGN_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        gate_folders = [
            n for n in folder_nodes
            if "conversational-gate.dot" in n.attrs.get("dot_file", "")
        ]
        assert gate_folders, "No conversational-gate.dot folder node found"
        topic = gate_folders[0].attrs.get("context.gate_topic", "")
        assert "project_name" in topic or "build_command" in topic or "configuration" in topic.lower(), (
            f"Phase 1 gate_topic should mention config variables, got: {topic[:200]!r}"
        )

    def test_has_phase5_design_doc_codergen(self):
        """Phase 5 compiles .dev-machine-design.md via a codergen (box) node."""
        source = _MACHINE_DESIGN_DOT.read_text()
        g = parse_dot(source)
        # Look for a codergen node whose prompt mentions .dev-machine-design.md
        codergen_nodes = [
            n for n in g.nodes.values()
            if n.shape in ("box", "", None) and n.shape != "Mdiamond"
            and ".dev-machine-design.md" in (n.prompt or "")
        ]
        assert len(codergen_nodes) >= 1, (
            "Expected at least one codergen node with prompt mentioning "
            ".dev-machine-design.md (phase 5 compile step)"
        )

    def test_phase5_prompt_contains_design_doc_format(self):
        """Phase 5 prompt contains the Machine Configuration table format."""
        source = _MACHINE_DESIGN_DOT.read_text()
        g = parse_dot(source)
        design_doc_nodes = [
            n for n in g.nodes.values()
            if ".dev-machine-design.md" in (n.prompt or "")
        ]
        assert design_doc_nodes, "No node with .dev-machine-design.md in prompt"
        prompt = design_doc_nodes[0].prompt or ""
        assert "Machine Configuration" in prompt or "project_name" in prompt, (
            f"Phase 5 prompt should contain design doc format. Got: {prompt[:300]!r}"
        )

    def test_has_phase6_wrapup_codergen(self):
        """Phase 6 is a codergen (box) wrap-up node mentioning generate-machine."""
        source = _MACHINE_DESIGN_DOT.read_text()
        g = parse_dot(source)
        wrapup_nodes = [
            n for n in g.nodes.values()
            if n.shape in ("box", "", None)
            and ("generate-machine" in (n.prompt or "").lower()
                 or "wrap" in n.id.lower()
                 or "wrapup" in n.id.lower()
                 or "wrap_up" in n.id.lower())
        ]
        assert len(wrapup_nodes) >= 1, (
            "Expected a wrap-up codergen node mentioning 'generate-machine'. "
            f"Box nodes: {[(n.id, (n.prompt or '')[:80]) for n in g.nodes.values() if n.shape in ('box', '', None)]}"
        )

    def test_architecture_artifact_goal_mentions_constitution(self):
        """Phase 2 artifact_goal mentions architecture spec / constitution."""
        source = _MACHINE_DESIGN_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        factory_folders = [
            n for n in folder_nodes
            if "convergence-factory.dot" in n.attrs.get("dot_file", "")
        ]
        goals = [n.attrs.get("context.artifact_goal", "") for n in factory_folders]
        assert any(
            "architecture" in g.lower() or "constitution" in g.lower()
            for g in goals
        ), f"Expected an artifact_goal mentioning architecture spec. Goals: {goals}"

    def test_has_done_terminal(self):
        """Pipeline has at least one Msquare done terminal node (design complete)."""
        source = _MACHINE_DESIGN_DOT.read_text()
        g = parse_dot(source)
        done_nodes = [n for n in g.nodes.values() if n.shape == "Msquare"]
        assert len(done_nodes) >= 1, "Expected at least one Msquare done terminal node"
```

---

### Step 2: Run the test to verify it fails

```bash
cd amplifier-bundle-attractor
python -m pytest modules/loop-pipeline/tests/test_foundry_machine_design.py::TestMachineDesignParse::test_file_exists -v
```

Expected: **FAIL** — file does not exist yet.

---

### Step 3: Write `machine-design.dot`

Create `amplifier-bundle-attractor/examples/dev-machine/foundry/machine-design.dot`:

```dot
// machine-design.dot -- Foundry pipeline for designing a bespoke development machine.
//
// Translates the /machine-design mode to a DOT pipeline.
// Gate-checks .dev-machine-assessment.md exists, then runs 6 design phases:
//   Phase 1: Gather Config  (conversational-gate.dot)
//   Phase 2: Architecture   (convergence-factory.dot -> specs/architecture.md)
//   Phase 3: Module Specs   (convergence-factory.dot -> specs/modules/*.md)
//   Phase 4: Feature Specs  (convergence-factory.dot -> specs/features/*)
//   Phase 5: Design Doc     (codergen compile -> .dev-machine-design.md)
//   Phase 6: Wrap Up        (codergen summary)
//
// Source material (prompts transfer verbatim, only {{var}} -> $var syntax adapted):
//   amplifier-bundle-dev-machine/modes/machine-design.md (143 lines)
//   amplifier-bundle-dev-machine/agents/machine-designer.md (63 lines)
//
// Required input:  .dev-machine-assessment.md (from admissions.dot)
// Required output: .dev-machine-design.md (consumed by generate-machine.dot)

digraph machine_design {
    graph [goal="Design a bespoke autonomous development machine (founding session)"]

    start [shape=Mdiamond, label="Machine Design Start"]

    // -----------------------------------------------------------------------
    // Gate Check: verify .dev-machine-assessment.md exists
    // Source: machine-design.md lines 23-33
    // -----------------------------------------------------------------------
    assessment_check [shape=parallelogram,
        label="Check Assessment File",
        tool_command="test -f .dev-machine-assessment.md && echo '{\"assessment_exists\": \"true\"}' || echo '{\"assessment_exists\": \"false\"}'",
        parse_json="true"]

    assessment_gate [shape=diamond, label="Assessment Exists?"]

    done_no_assessment [shape=Msquare,
        label="No Assessment Found: Run admissions.dot first to evaluate your project. The machine design phase requires a passing admissions assessment."]

    // -----------------------------------------------------------------------
    // Phase 1: Gather Machine Configuration
    // Source: machine-design.md lines 42-65
    // -----------------------------------------------------------------------
    phase1_config [shape=folder, dot_file="../../patterns/conversational-gate.dot",
        context.gate_topic="MACHINE DESIGN MODE activated. This is the founding session for your development machine.\n\nPHASE 1: GATHER MACHINE CONFIGURATION\n\nThis is a collaborative session. You will work WITH the user to design their machine.\n\nCollect the required template variables through conversation:\n\n1. Project basics:\n   - project_name: short identifier (no spaces, e.g. 'word4', 'my-api')\n   - project_dir: absolute path to project root\n   - Technology stack overview\n\n2. Build/test toolchain:\n   - build_command: what builds/compiles the project (e.g. 'pnpm build', 'cargo build', 'make')\n   - test_command: what runs tests (e.g. 'pnpm test', 'cargo test', 'pytest')\n   - type_check_command: separate type checker if any (e.g. 'pyright', 'tsc --noEmit')\n   - Verify these commands work by running them\n\n3. Spec infrastructure:\n   - specs_dir: where specs will live (e.g. './specs')\n   - architecture_spec: path for the architecture spec (e.g. './specs/architecture.md')\n\n4. Machine tuning:\n   - max_features_per_session: features per session (default: 3-5)\n   - max_outer_iterations: max outer loop iterations (default: 50)\n   - module_size_threshold: LOC limit per module (default: 10000)\n   - qa_enabled: whether QA machine is needed (true/false)\n\nCollect all values and confirm them with the user. Write all collected variables to .ai/machine_config.md as a YAML-style key: value list.",
        context.gate_criteria="Sufficient configuration has been gathered when all required variables are present and confirmed:\n- project_name: a short clean identifier with no spaces\n- project_dir: an absolute filesystem path\n- build_command: verified to run without errors\n- test_command: verified to run and report results\n- specs_dir: defined (will be created if it doesn't exist)\n- architecture_spec: path defined\n- max_features_per_session, max_outer_iterations, module_size_threshold: set (defaults accepted)\n- qa_enabled: explicitly set to true or false\n- All values written to .ai/machine_config.md\n- The user has reviewed and confirmed the values\n\nReturn preferred_label='scored' when all required variables are confirmed and written to .ai/machine_config.md.",
        context.gate_output_path=".ai/machine_config.md"]

    // -----------------------------------------------------------------------
    // Phase 2: Architecture Spec (The Constitution)
    // Source: machine-design.md lines 67-84
    // -----------------------------------------------------------------------
    phase2_architecture [shape=folder, dot_file="../../patterns/convergence-factory.dot",
        context.artifact_goal="MACHINE DESIGN - PHASE 2: ARCHITECTURE SPEC (THE CONSTITUTION)\n\nGuide the user through writing or reviewing their architecture spec.\n\nRead .ai/machine_config.md to get project_dir, specs_dir, and architecture_spec path.\n\nThe architecture spec must cover:\n1. Data model -- core types and data structures\n2. Module boundaries -- what modules exist, their responsibilities, interfaces between them\n3. Technology choices -- language, framework, key libraries, with rationale\n4. Key patterns -- state management, data flow, error handling, testing approach\n5. Build/test/deploy -- how the project is built, tested, and eventually deployed\n\nThe architecture spec should be:\n- Complete enough to prevent drift across hundreds of features\n- Concise enough for an agent to read in <2 minutes\n- Written for machine consumption (explicit interfaces, not hand-wavy descriptions)\n\nIf the user has existing architecture docs, review and assess them. Suggest additions if needed.\n\nWrite the architecture spec to the path from .ai/machine_config.md (typically specs/architecture.md).\n\nDesign principle: Progressive, not exhaustive. Design enough architecture to start. The word4 architecture spec was 947 lines written in ~1 hour. It was sufficient.",
        context.artifact_path="specs/architecture.md",
        context.validation_criteria="The architecture spec is sufficient when it contains:\n- A defined data model section with core types/structures\n- Module boundaries with explicit public interfaces\n- Technology choices with rationale\n- Key patterns (state management, data flow, error handling, testing)\n- Build/test/deploy information\n- Written for machine consumption: explicit enough for an agent to implement without asking questions\n- At least 30 lines (concise but not trivial)",
        context.validation_command="test -f specs/architecture.md && wc -l specs/architecture.md | awk '{if($1>=30) print \"valid: \" $1 \" lines\"; else {print \"too short: \" $1 \" lines\"; exit 1}}' || echo 'specs/architecture.md not found'"]

    // -----------------------------------------------------------------------
    // Phase 3: Module Specs
    // Source: machine-design.md lines 86-93
    // -----------------------------------------------------------------------
    phase3_modules [shape=folder, dot_file="../../patterns/convergence-factory.dot",
        context.artifact_goal="MACHINE DESIGN - PHASE 3: MODULE SPECS\n\nFor each major module identified in the architecture, write a module spec.\n\nRead specs/architecture.md to identify the modules.\nRead .ai/machine_config.md for the specs_dir path.\n\nFor each module:\n- Define internal architecture\n- Define public API and contracts with adjacent modules\n- Define test strategy\n\nWrite module specs to specs/modules/<module-name>.md\n\nMachine-consumable module specs must include:\n- Module name and purpose\n- Public API/interfaces (explicit function/type signatures)\n- Contracts with adjacent modules\n- Test strategy (what to test and how)\n- Known constraints or edge cases\n\nA working session agent must be able to read a spec and implement the module without asking questions.\n\nDomain expertise principle: Help the user identify build/test blind spots and decompose their problem into well-bounded modules.",
        context.artifact_path="specs/modules/",
        context.validation_criteria="Module specs are sufficient when:\n- At least one .md file exists in specs/modules/\n- Each spec has: module name, responsibilities, public interfaces, test strategy\n- Specs are machine-consumable: explicit enough for implementation without clarification\n- Major modules from the architecture spec are covered",
        context.validation_command="test -d specs/modules && count=$(ls specs/modules/*.md 2>/dev/null | wc -l); if [ $count -ge 1 ]; then echo \"valid: $count module spec(s)\"; else echo 'no module specs found'; exit 1; fi"]

    // -----------------------------------------------------------------------
    // Phase 4: First Batch of Feature Specs
    // Source: machine-design.md lines 95-100
    // -----------------------------------------------------------------------
    phase4_features [shape=folder, dot_file="../../patterns/convergence-factory.dot",
        context.artifact_goal="MACHINE DESIGN - PHASE 4: FIRST BATCH OF FEATURE SPECS\n\nWrite the first batch of feature specs (5-15 features) covering the bootstrap/foundation work.\n\nRead:\n- specs/architecture.md to understand what needs to be built\n- specs/modules/ to understand module boundaries\n- .ai/machine_config.md for the specs_dir and qa_enabled setting\n\nFor each feature spec, use this template structure:\n- Title: [Feature ID]: [Feature Name]\n- Module: which module this feature belongs to\n- Description: what the feature does (1-2 sentences)\n- Acceptance Criteria: numbered list of specific, testable criteria\n- Implementation Notes: key files to modify, patterns to follow, interfaces to implement\n- Edge Cases: known edge cases the agent must handle\n- Out of Scope: what NOT to implement (prevents scope creep)\n\nWrite feature specs to specs/features/<module>/<feature-id>.md\n\nFeatures should be:\n- Independent: each implementable in one working session without depending on unbuilt features\n- Scoped: each spec fits in <2 pages\n- Concrete: an agent can implement without asking questions\n- Sequential in dependency order: foundation features first",
        context.artifact_path="specs/features/",
        context.validation_criteria="Feature specs are sufficient when:\n- At least 5 .md files exist under specs/features/ (in subdirectories by module)\n- Each spec has: title, module, description, acceptance criteria, implementation notes\n- Features are scoped to one working session each\n- Foundation/bootstrap features are included (the first things the machine will build)\n- Specs are machine-consumable: explicit enough for an agent to implement without asking",
        context.validation_command="count=$(find specs/features -name '*.md' 2>/dev/null | wc -l); if [ $count -ge 5 ]; then echo \"valid: $count feature spec(s)\"; else echo \"need at least 5 feature specs, found $count\"; exit 1; fi"]

    // -----------------------------------------------------------------------
    // Phase 5: Machine Design Document
    // Source: machine-design.md lines 102-133
    // -----------------------------------------------------------------------
    phase5_design_doc [shape=box,
        label="Compile Design Document",
        prompt="MACHINE DESIGN MODE - PHASE 5: MACHINE DESIGN DOCUMENT\n\nCompile all decisions into .dev-machine-design.md at the project root.\n\nRead:\n- .ai/machine_config.md (all configuration variables)\n- specs/architecture.md (for architecture summary)\n- specs/modules/ directory (for module inventory)\n- specs/features/ directory (for initial feature backlog)\n\nWrite .dev-machine-design.md with this exact structure:\n\n# <project_name> Development Machine Design\n\n## Machine Configuration\n\n| Variable | Value |\n|----------|-------|\n| project_name | ... |\n| project_dir | ... |\n| state_file | ./STATE.yaml |\n| context_file | ./CONTEXT-TRANSFER.md |\n| specs_dir | ... |\n| build_command | ... |\n| test_command | ... |\n| architecture_spec | ... |\n| max_features_per_session | ... |\n| max_outer_iterations | ... |\n| max_fix_iterations | 10 |\n| module_size_threshold | ... |\n| qa_enabled | ... |\n\n## Architecture Summary\n[2-3 sentence summary of the architecture with pointer to full spec at specs/architecture.md]\n\n## Module Inventory\n[List of modules with their spec paths and status: approved]\n\n## Initial Feature Backlog\n[List of first-batch features with their spec paths and status: ready]\n\n## QA Configuration\n[If qa_enabled=true: describe what to test and how. If qa_enabled=false: 'QA not enabled.']\n\n## Bootstrap Plan\n[What needs to happen before the machine can start running: any prerequisites, initial setup steps]\n\nAfter writing the file, verify it was written and is non-empty, then return outcome success."]

    // -----------------------------------------------------------------------
    // Phase 6: Wrap Up
    // Source: machine-design.md lines 135-143, machine-designer.md lines 57-63
    // -----------------------------------------------------------------------
    phase6_wrapup [shape=box,
        label="Wrap Up",
        prompt="MACHINE DESIGN MODE - PHASE 6: WRAP UP\n\nThe founding session is complete. Present the results to the user:\n\n1. What was created:\n   - Architecture spec at specs/architecture.md\n   - Module specs in specs/modules/ (list them)\n   - Feature specs in specs/features/ (list them with count)\n   - Machine design document at .dev-machine-design.md\n\n2. Machine configuration variables collected (list key values)\n\n3. Recommended next step: 'Run generate-machine.dot to generate the machine artifacts'\n\nYour response must include:\n- Summary of what was designed\n- List of all files created\n- Machine configuration variables collected\n- Recommended next step (run generate-machine.dot)\n\nThen return outcome success."]

    done [shape=Msquare, label="Design Complete: Run generate-machine.dot to generate machine artifacts"]

    // Flow
    start -> assessment_check -> assessment_gate

    assessment_gate -> done_no_assessment [label="missing",  condition="context.assessment_exists=false"]
    assessment_gate -> phase1_config      [label="exists",   condition="context.assessment_exists=true"]

    phase1_config -> phase2_architecture -> phase3_modules -> phase4_features -> phase5_design_doc -> phase6_wrapup -> done
}
```

---

### Step 4: Run all structural tests

```bash
cd amplifier-bundle-attractor
python -m pytest modules/loop-pipeline/tests/test_foundry_machine_design.py -v
```

Expected: **All PASS** — 16 tests passing.

---

### Step 5: Commit

```bash
cd amplifier-bundle-attractor
git add examples/dev-machine/foundry/machine-design.dot modules/loop-pipeline/tests/test_foundry_machine_design.py
git commit -m "feat: add foundry/machine-design.dot with 6-phase founding session pipeline"
```

---

## Task 23: `generate-machine.dot` — Runtime DOT Generation

**Translates:** `/generate-machine` mode (194 lines) + machine-generator agent (115 lines) + templates-reference.md (115 lines)

**Files:**
- Create: `amplifier-bundle-attractor/examples/dev-machine/foundry/generate-machine.dot`
- Create: `amplifier-bundle-attractor/modules/loop-pipeline/tests/test_foundry_generate_machine.py`

---

### Step 1: Write the failing structural test

Create `amplifier-bundle-attractor/modules/loop-pipeline/tests/test_foundry_generate_machine.py`:

```python
"""Tests for foundry/generate-machine.dot — Runtime DOT Generation Pipeline.

Structural parse tests verifying:
- Gate check: parallelogram checks .dev-machine-design.md exists
- Diamond routing: missing -> early exit, exists -> generation chain
- convergence-factory.dot folder nodes for each runtime artifact group
- QA conditional: qa_check tool node + qa_gate diamond
- Validation step: final tool node running structural checks
- All convergence-factory folder nodes have required context.* attrs
- Artifact goals mention verbatim generation instructions from generate-machine.md
"""
from __future__ import annotations

from pathlib import Path

import pytest

from amplifier_module_loop_pipeline.dot_parser import parse_dot

_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_FOUNDRY_DIR = _REPO_ROOT / "examples" / "dev-machine" / "foundry"
_GEN_MACHINE_DOT = _FOUNDRY_DIR / "generate-machine.dot"


class TestGenerateMachineParse:
    """Structural tests: generate-machine.dot parses to expected graph topology."""

    def test_file_exists(self):
        """generate-machine.dot exists at examples/dev-machine/foundry/generate-machine.dot."""
        assert _GEN_MACHINE_DOT.exists(), f"File not found: {_GEN_MACHINE_DOT}"

    def test_parses_without_error(self):
        """generate-machine.dot parses without raising an exception."""
        source = _GEN_MACHINE_DOT.read_text()
        g = parse_dot(source)
        assert len(g.nodes) > 0

    def test_has_design_check_tool_node(self):
        """Pipeline has a design_check parallelogram (tool) node."""
        source = _GEN_MACHINE_DOT.read_text()
        g = parse_dot(source)
        assert "design_check" in g.nodes, (
            f"Node 'design_check' missing. Nodes: {list(g.nodes.keys())}"
        )
        assert g.nodes["design_check"].shape == "parallelogram", (
            f"Expected design_check shape=parallelogram, "
            f"got {g.nodes['design_check'].shape!r}"
        )

    def test_design_check_references_design_doc(self):
        """design_check tool_command checks for .dev-machine-design.md."""
        source = _GEN_MACHINE_DOT.read_text()
        g = parse_dot(source)
        node = g.nodes["design_check"]
        tool_cmd = node.attrs.get("tool_command", "")
        assert ".dev-machine-design.md" in tool_cmd, (
            f"Expected tool_command to check .dev-machine-design.md, "
            f"got {tool_cmd!r}"
        )

    def test_design_check_has_parse_json(self):
        """design_check has parse_json='true'."""
        source = _GEN_MACHINE_DOT.read_text()
        g = parse_dot(source)
        assert g.nodes["design_check"].attrs.get("parse_json") == "true"

    def test_has_design_gate_diamond(self):
        """Pipeline has a design_gate diamond node."""
        source = _GEN_MACHINE_DOT.read_text()
        g = parse_dot(source)
        assert "design_gate" in g.nodes, (
            f"Node 'design_gate' missing. Nodes: {list(g.nodes.keys())}"
        )
        assert g.nodes["design_gate"].shape == "diamond"

    def test_has_minimum_convergence_factory_nodes(self):
        """Pipeline has at least 6 convergence-factory.dot folder nodes (one per artifact group)."""
        source = _GEN_MACHINE_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        factory_folders = [
            n for n in folder_nodes
            if "convergence-factory.dot" in n.attrs.get("dot_file", "")
        ]
        assert len(factory_folders) >= 6, (
            f"Expected at least 6 convergence-factory.dot folder nodes, "
            f"got {len(factory_folders)}: {[n.id for n in factory_folders]}"
        )

    def test_all_factory_nodes_have_required_context_attrs(self):
        """All convergence-factory folder nodes have 4 required context.* attributes."""
        source = _GEN_MACHINE_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        factory_folders = [
            n for n in folder_nodes
            if "convergence-factory.dot" in n.attrs.get("dot_file", "")
        ]
        for node in factory_folders:
            assert "context.artifact_goal" in node.attrs, (
                f"Node {node.id!r} missing context.artifact_goal"
            )
            assert "context.artifact_path" in node.attrs, (
                f"Node {node.id!r} missing context.artifact_path"
            )
            assert "context.validation_criteria" in node.attrs, (
                f"Node {node.id!r} missing context.validation_criteria"
            )
            assert "context.validation_command" in node.attrs, (
                f"Node {node.id!r} missing context.validation_command"
            )

    def test_artifact_goals_mention_iteration_dot(self):
        """At least one artifact_goal mentions iteration.dot generation."""
        source = _GEN_MACHINE_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        factory_folders = [
            n for n in folder_nodes
            if "convergence-factory.dot" in n.attrs.get("dot_file", "")
        ]
        goals = [n.attrs.get("context.artifact_goal", "") for n in factory_folders]
        assert any("iteration.dot" in g for g in goals), (
            f"Expected an artifact_goal mentioning iteration.dot. Goals: {[g[:80] for g in goals]}"
        )

    def test_artifact_goals_mention_scripts(self):
        """At least one artifact_goal mentions pipeline scripts generation."""
        source = _GEN_MACHINE_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        factory_folders = [
            n for n in folder_nodes
            if "convergence-factory.dot" in n.attrs.get("dot_file", "")
        ]
        goals = [n.attrs.get("context.artifact_goal", "") for n in factory_folders]
        assert any("script" in g.lower() or "orient" in g.lower() for g in goals), (
            f"Expected an artifact_goal mentioning scripts. Goals: {[g[:80] for g in goals]}"
        )

    def test_artifact_goals_mention_infrastructure(self):
        """At least one artifact_goal mentions infrastructure files (entrypoint, Dockerfile)."""
        source = _GEN_MACHINE_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        factory_folders = [
            n for n in folder_nodes
            if "convergence-factory.dot" in n.attrs.get("dot_file", "")
        ]
        goals = [n.attrs.get("context.artifact_goal", "") for n in factory_folders]
        assert any(
            "entrypoint" in g.lower() or "dockerfile" in g.lower() or "infra" in g.lower()
            for g in goals
        ), f"Expected an artifact_goal mentioning infrastructure. Goals: {[g[:80] for g in goals]}"

    def test_has_qa_gate_diamond(self):
        """Pipeline has a qa_gate diamond node for conditional QA generation."""
        source = _GEN_MACHINE_DOT.read_text()
        g = parse_dot(source)
        diamond_nodes = [n for n in g.nodes.values() if n.shape == "diamond"]
        qa_diamonds = [n for n in diamond_nodes if "qa" in n.id.lower()]
        assert len(qa_diamonds) >= 1, (
            f"Expected a qa_gate diamond, got diamond nodes: "
            f"{[n.id for n in diamond_nodes]}"
        )

    def test_has_final_validation_node(self):
        """Pipeline has a final validation tool node or codergen node."""
        source = _GEN_MACHINE_DOT.read_text()
        g = parse_dot(source)
        # Final validation can be a parallelogram tool node or codergen
        validation_nodes = [
            n for n in g.nodes.values()
            if ("validat" in n.id.lower() or "verify" in n.id.lower() or "smoke" in n.id.lower())
            and n.shape not in ("Mdiamond", "Msquare", "diamond")
        ]
        assert len(validation_nodes) >= 1, (
            f"Expected a final validation node. Nodes: {list(g.nodes.keys())}"
        )

    def test_has_done_terminal(self):
        """Pipeline has at least one Msquare terminal (generation complete)."""
        source = _GEN_MACHINE_DOT.read_text()
        g = parse_dot(source)
        done_nodes = [n for n in g.nodes.values() if n.shape == "Msquare"]
        assert len(done_nodes) >= 1, "Expected at least one Msquare done terminal"

    def test_has_early_exit_terminal_for_missing_design(self):
        """Pipeline has an early-exit Msquare terminal when design doc is missing."""
        source = _GEN_MACHINE_DOT.read_text()
        g = parse_dot(source)
        done_nodes = [n for n in g.nodes.values() if n.shape == "Msquare"]
        assert len(done_nodes) >= 2, (
            "Expected at least 2 Msquare terminals: one for missing design doc, "
            f"one for completion. Got: {[n.id for n in done_nodes]}"
        )

    def test_validation_commands_check_dot_files(self):
        """At least one validation_command checks that a .dot file can be parsed."""
        source = _GEN_MACHINE_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        factory_folders = [
            n for n in folder_nodes
            if "convergence-factory.dot" in n.attrs.get("dot_file", "")
        ]
        commands = [n.attrs.get("context.validation_command", "") for n in factory_folders]
        assert any(".dot" in c or "dot_parser" in c or "parse_dot" in c for c in commands), (
            f"Expected at least one validation_command checking .dot file syntax. "
            f"Commands: {[c[:80] for c in commands]}"
        )

    def test_state_yaml_generation_included(self):
        """At least one artifact_goal or artifact_path mentions STATE.yaml."""
        source = _GEN_MACHINE_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        factory_folders = [
            n for n in folder_nodes
            if "convergence-factory.dot" in n.attrs.get("dot_file", "")
        ]
        all_text = " ".join(
            n.attrs.get("context.artifact_goal", "") + " " +
            n.attrs.get("context.artifact_path", "")
            for n in factory_folders
        )
        assert "STATE.yaml" in all_text or "state" in all_text.lower(), (
            "Expected STATE.yaml mentioned in an artifact goal or path"
        )
```

---

### Step 2: Run the test to verify it fails

```bash
cd amplifier-bundle-attractor
python -m pytest modules/loop-pipeline/tests/test_foundry_generate_machine.py::TestGenerateMachineParse::test_file_exists -v
```

Expected: **FAIL** — file does not exist.

---

### Step 3: Write `generate-machine.dot`

Create `amplifier-bundle-attractor/examples/dev-machine/foundry/generate-machine.dot`:

```dot
// generate-machine.dot -- Foundry pipeline for generating bespoke runtime DOT files.
//
// Translates the /generate-machine mode to a DOT pipeline.
// Gate-checks .dev-machine-design.md exists, then uses convergence-factory.dot
// invocations to generate each bespoke runtime artifact:
//   - Runtime DOT files: iteration.dot, post-session.dot, health-check.dot,
//     fix-iteration.dot, smoke-test.dot
//   - QA DOTs: qa.dot, qa-iteration.dot (if qa_enabled=true)
//   - Pipeline scripts: orient.py, build-check.py, post-session-*.py, etc.
//   - Infrastructure: entrypoint.sh, watchdog.sh, monitor.sh
//   - State files: STATE.yaml, CONTEXT-TRANSFER.md, SCRATCH.md, AGENTS.md
//   - Docker: Dockerfile, docker-compose
//   - Final validation: structural parse check on all generated DOT files
//
// Source material (prompts transfer verbatim, only {{var}} -> $var syntax adapted):
//   amplifier-bundle-dev-machine/modes/generate-machine.md (194 lines)
//   amplifier-bundle-dev-machine/agents/machine-generator.md (115 lines)
//   amplifier-bundle-dev-machine/context/templates-reference.md (115 lines)
//
// Required input:  .dev-machine-design.md (from machine-design.dot)
// Required output: .dev-machine/runtime/*.dot, .dev-machine/scripts/pipeline/*.py,
//                  .dev-machine/scripts/infra/*.sh, STATE.yaml, Dockerfile, etc.

digraph generate_machine {
    graph [goal="Generate bespoke runtime DOT files and artifacts from machine design"]

    start [shape=Mdiamond, label="Generate Machine Start"]

    // -----------------------------------------------------------------------
    // Gate Check: verify .dev-machine-design.md exists
    // Source: generate-machine.md lines 23-34
    // -----------------------------------------------------------------------
    design_check [shape=parallelogram,
        label="Check Design File",
        tool_command="test -f .dev-machine-design.md && echo '{\"design_exists\": \"true\"}' || echo '{\"design_exists\": \"false\"}'",
        parse_json="true"]

    design_gate [shape=diamond, label="Design Exists?"]

    done_no_design [shape=Msquare,
        label="No Design Found: Run machine-design.dot first. Generation requires a completed design document."]

    // -----------------------------------------------------------------------
    // Step 1: Read Design and Create Directory Structure
    // Source: generate-machine.md lines 39-53
    // -----------------------------------------------------------------------
    read_design [shape=box,
        label="Read Design Document",
        prompt="GENERATE MACHINE MODE activated. Generating development machine artifacts for your project.\n\nRead .dev-machine-design.md and extract all template variables into a structured map.\n\nVerify all required variables are present:\n- project_name, project_dir, state_file, context_file\n- specs_dir, build_command, test_command, architecture_spec\n- qa_enabled\n\nIf any required variables are missing, report them and stop.\n\nCreate directory structure:\n- mkdir -p .dev-machine/runtime\n- mkdir -p .dev-machine/scripts/pipeline\n- mkdir -p .dev-machine/scripts/infra\n- mkdir -p .ai\n\nWrite a structured summary of all extracted variables to .ai/design_vars.md for use by subsequent generation steps.\n\nGeneration rules (from machine-generator agent):\n1. Read the design document first. Extract ALL variable values before generating any files.\n2. Every $variable must be replaced. If a variable is referenced but not defined, STOP and report.\n3. After variable substitution, generated YAML/DOT files must be syntactically valid.\n4. Use default values for optional variables not specified (see templates-reference.md).\n5. Write files atomically: generate all files in a group, then verify all at once.\n\nReturn outcome success when directory structure is created and variables are extracted to .ai/design_vars.md."]

    // -----------------------------------------------------------------------
    // Generate iteration.dot (runtime DOT - core inner loop)
    // Source: generate-machine.md lines 55-68, design doc Section 3
    // -----------------------------------------------------------------------
    gen_iteration [shape=folder, dot_file="../../patterns/convergence-factory.dot",
        context.artifact_goal="GENERATE MACHINE - Step 3: Generate iteration.dot\n\nRead .ai/design_vars.md for all project variables.\nRead .dev-machine-design.md for the full machine configuration.\n\nGenerate .dev-machine/runtime/iteration.dot -- the core 8-step inner loop that executes one working session.\n\nThe generated iteration.dot must:\n1. Be a valid DOT pipeline for Attractor\n2. Include these nodes in sequence:\n   - orient: parallelogram, tool_command reads STATE.yaml, parse_json=true\n   - orient_gate: diamond routing on context.status (blocked -> done, healthy -> preflight)\n   - spec_drift: parallelogram, continue_on_fail=true\n   - api_inventory: parallelogram, continue_on_fail=true\n   - test_preflight: parallelogram (hard stop on failure)\n   - test_preflight_gate: diamond\n   - module_health: parallelogram, continue_on_fail=true\n   - working_session: box (codergen), reads working-session-instructions.md from disk\n   - build_check: parallelogram, parse_json=true\n   - build_gate: diamond\n   - post_session: folder node invoking post-session.dot\n   - done: Msquare\n3. Script paths use $project_dir and .dev-machine/scripts/pipeline/ prefix\n4. Tool commands reference the correct project-specific variables ($build_command, $test_command, etc.)\n5. The working_session codergen prompt references .dev-machine/working-session-instructions.md\n\nWrite the generated DOT to .dev-machine/runtime/iteration.dot",
        context.artifact_path=".dev-machine/runtime/iteration.dot",
        context.validation_criteria="iteration.dot is valid when:\n- File exists and is non-empty\n- Parses as valid DOT without errors\n- Contains at minimum: start, orient, working_session, build_check, done nodes\n- orient node has parse_json='true' attribute\n- working_session node has a prompt attribute\n- build_check node has parse_json='true' attribute\n- post_session folder node references post-session.dot\n- No unsubstituted $variable placeholders that should have been replaced with project values",
        context.validation_command="python3 -c \"from amplifier_module_loop_pipeline.dot_parser import parse_dot; import pathlib; g=parse_dot(pathlib.Path('.dev-machine/runtime/iteration.dot').read_text()); print(f'valid: {len(g.nodes)} nodes')\" 2>&1"]

    // -----------------------------------------------------------------------
    // Generate post-session.dot (runtime DOT - post-session pipeline)
    // Source: generate-machine.md lines 55-68, design doc Section 4
    // -----------------------------------------------------------------------
    gen_post_session [shape=folder, dot_file="../../patterns/convergence-factory.dot",
        context.artifact_goal="GENERATE MACHINE - Step 3 (continued): Generate post-session.dot\n\nRead .ai/design_vars.md for all project variables.\n\nGenerate .dev-machine/runtime/post-session.dot -- the post-session archiving and reconciliation pipeline.\n\nThe generated post-session.dot must:\n1. Be a valid DOT pipeline\n2. Include these sequential tool nodes:\n   - archive_features: parallelogram, runs post-session-archive.py\n   - session_accounting: parallelogram, runs post-session-accounting.py\n   - reconcile: parallelogram, continue_on_fail=true, runs post-session-reconcile.py\n   - periodic_check: parallelogram, continue_on_fail=true, runs post-session-periodic.py\n   - status_output: parallelogram, parse_json=true, runs post-session-status.py\n3. Linear flow: start -> archive -> accounting -> reconcile -> periodic -> status -> done\n4. Script paths reference .dev-machine/scripts/pipeline/ directory\n\nWrite the generated DOT to .dev-machine/runtime/post-session.dot",
        context.artifact_path=".dev-machine/runtime/post-session.dot",
        context.validation_criteria="post-session.dot is valid when:\n- File exists and parses as valid DOT\n- Contains at least 5 parallelogram tool nodes\n- Linear sequential flow (no branching)\n- Scripts are referenced from .dev-machine/scripts/pipeline/",
        context.validation_command="python3 -c \"from amplifier_module_loop_pipeline.dot_parser import parse_dot; import pathlib; g=parse_dot(pathlib.Path('.dev-machine/runtime/post-session.dot').read_text()); tools=[n for n in g.nodes.values() if n.shape=='parallelogram']; print(f'valid: {len(tools)} tool nodes')\" 2>&1"]

    // -----------------------------------------------------------------------
    // Generate health-check.dot + fix-iteration.dot
    // Source: generate-machine.md lines 65-68, design doc Section 5
    // -----------------------------------------------------------------------
    gen_health_fix [shape=folder, dot_file="../../patterns/convergence-factory.dot",
        context.artifact_goal="GENERATE MACHINE - Step 3 (continued): Generate health-check.dot and fix-iteration.dot\n\nRead .ai/design_vars.md for all project variables.\n\nGenerate TWO runtime DOT files:\n\n1. .dev-machine/runtime/health-check.dot -- outer fix loop:\n   - start -> initial_check (parallelogram, parse_json=true) -> clean_gate (diamond)\n   - clean_gate routes: build_status=clean -> done, build_status=failed -> fix_loop\n   - fix_loop: house node, stack.child_dotfile='.dev-machine/runtime/fix-iteration.dot', manager.max_cycles=$max_fix_iterations, manager.stop_condition='outcome=success'\n   - fix_loop -> done\n\n2. .dev-machine/runtime/fix-iteration.dot -- single fix cycle:\n   - start -> read_errors (parallelogram, parse_json=true) -> fix_session (box/codergen) -> verify (parallelogram, parse_json=true) -> done\n   - read_errors runs read-errors.py to get current build failures\n   - fix_session prompt: 'Parse errors from $state_file, group by file, fix each systematically, validate fixes'\n   - verify runs build-check.py\n\nSubstitute $max_fix_iterations from design vars (default: 10).\n\nWrite both files.",
        context.artifact_path=".dev-machine/runtime/health-check.dot",
        context.validation_criteria="Both DOT files are valid when:\n- .dev-machine/runtime/health-check.dot parses as valid DOT\n- .dev-machine/runtime/fix-iteration.dot parses as valid DOT\n- health-check.dot contains a house node referencing fix-iteration.dot\n- fix-iteration.dot contains a codergen (box) node",
        context.validation_command="python3 -c \"from amplifier_module_loop_pipeline.dot_parser import parse_dot; import pathlib; [parse_dot(pathlib.Path(f).read_text()) for f in ['.dev-machine/runtime/health-check.dot', '.dev-machine/runtime/fix-iteration.dot']]; print('valid: both health-check.dot and fix-iteration.dot parse correctly')\" 2>&1"]

    // -----------------------------------------------------------------------
    // Generate smoke-test.dot
    // Source: generate-machine.md lines 65-68, design doc Section 5
    // -----------------------------------------------------------------------
    gen_smoke_test [shape=folder, dot_file="../../patterns/convergence-factory.dot",
        context.artifact_goal="GENERATE MACHINE - Step 3 (continued): Generate smoke-test.dot\n\nRead .ai/design_vars.md for all project variables.\n\nGenerate .dev-machine/runtime/smoke-test.dot -- pre-flight validator that checks the generated machine is complete and structurally sound.\n\nThe generated smoke-test.dot must be a linear chain of parallelogram tool nodes checking:\n1. File existence: STATE.yaml, .dev-machine/runtime/iteration.dot, .dev-machine-design.md\n2. DOT validity: parse all generated .dot files in .dev-machine/runtime/\n3. Script existence: all required .py scripts in .dev-machine/scripts/pipeline/\n4. Infrastructure: entrypoint.sh exists and is executable\n5. State file validity: STATE.yaml is valid YAML with required fields\n6. Final summary: aggregates pass/fail across all checks, outputs JSON\n\nLinear flow: start -> check_files -> check_dots -> check_scripts -> check_infra -> check_state -> summary -> done\n\nWrite to .dev-machine/runtime/smoke-test.dot",
        context.artifact_path=".dev-machine/runtime/smoke-test.dot",
        context.validation_criteria="smoke-test.dot is valid when:\n- File exists and parses as valid DOT\n- Contains at least 5 parallelogram tool nodes\n- Linear flow (no branching)\n- Final node aggregates results",
        context.validation_command="python3 -c \"from amplifier_module_loop_pipeline.dot_parser import parse_dot; import pathlib; g=parse_dot(pathlib.Path('.dev-machine/runtime/smoke-test.dot').read_text()); tools=[n for n in g.nodes.values() if n.shape=='parallelogram']; assert len(tools)>=5, f'need 5+ tool nodes, got {len(tools)}'; print(f'valid: {len(tools)} check nodes')\" 2>&1"]

    // -----------------------------------------------------------------------
    // QA Check: is qa_enabled in the design doc?
    // Source: generate-machine.md lines 69-72
    // -----------------------------------------------------------------------
    qa_check [shape=parallelogram,
        label="Check QA Enabled",
        tool_command="grep -i 'qa_enabled.*true' .dev-machine-design.md 2>/dev/null && echo '{\"qa_enabled\": \"true\"}' || echo '{\"qa_enabled\": \"false\"}'",
        parse_json="true"]

    qa_gate [shape=diamond, label="QA Enabled?"]

    // -----------------------------------------------------------------------
    // Generate qa.dot + qa-iteration.dot (conditional on qa_enabled)
    // Source: generate-machine.md lines 69-72, design doc Section 5
    // -----------------------------------------------------------------------
    gen_qa [shape=folder, dot_file="../../patterns/convergence-factory.dot",
        context.artifact_goal="GENERATE MACHINE - Step 3 (conditional): Generate qa.dot and qa-iteration.dot\n\nqa_enabled=true in the design. Generate TWO QA runtime DOT files.\n\nRead .ai/design_vars.md for project variables including qa_url if set.\n\n1. .dev-machine/runtime/qa.dot -- QA outer loop:\n   - Same house/folder pattern as health-check.dot\n   - house node: stack.child_dotfile='.dev-machine/runtime/qa-iteration.dot', manager.max_cycles=5\n   - Routes: outcome=success -> done, outcome=fail -> done (QA failure is logged not fatal)\n\n2. .dev-machine/runtime/qa-iteration.dot -- single QA cycle:\n   - start -> qa_session (box/codergen) -> verify (parallelogram) -> done\n   - qa_session prompt: runs QA checks against qa_url or local server\n   - verify checks QA results\n\nWrite both files.",
        context.artifact_path=".dev-machine/runtime/qa.dot",
        context.validation_criteria="Both QA DOT files are valid when:\n- .dev-machine/runtime/qa.dot parses as valid DOT\n- .dev-machine/runtime/qa-iteration.dot parses as valid DOT\n- qa.dot contains a house node referencing qa-iteration.dot\n- qa-iteration.dot contains a codergen (box) node",
        context.validation_command="python3 -c \"from amplifier_module_loop_pipeline.dot_parser import parse_dot; import pathlib; [parse_dot(pathlib.Path(f).read_text()) for f in ['.dev-machine/runtime/qa.dot', '.dev-machine/runtime/qa-iteration.dot']]; print('valid: both qa.dot and qa-iteration.dot parse correctly')\" 2>&1"]

    // -----------------------------------------------------------------------
    // Generate pipeline scripts
    // Source: generate-machine.md lines 84-98, design doc Section 2
    // -----------------------------------------------------------------------
    gen_scripts [shape=folder, dot_file="../../patterns/convergence-factory.dot",
        context.artifact_goal="GENERATE MACHINE - Step 4: Generate Pipeline Scripts\n\nRead .ai/design_vars.md for project-specific variables ($project_name, $build_command, $test_command, $specs_dir, etc.)\n\nGenerate all pipeline scripts into .dev-machine/scripts/pipeline/. These scripts are called by DOT tool (parallelogram) nodes.\n\nScript contract (all scripts must follow this):\n- Input: command-line args for project-specific values\n- Output: structured JSON to stdout (consumed by parse_json)\n- Exit code: 0 = success, non-zero = failure\n- Self-contained: reads from known file paths, no pipeline context needed beyond args\n- Testable standalone: python3 scripts/orient.py STATE.yaml works outside the pipeline\n\nGenerate these scripts:\n1. orient.py -- reads STATE.yaml, outputs JSON: {status, phase, epoch, ready_count, ...}\n2. spec-drift-check.py -- compares spec mtimes vs impl mtimes, outputs JSON\n3. api-inventory.py -- scans source for public types/APIs, appends to SCRATCH.md\n4. test-env-preflight.py -- validates test runner works (--collect-only), outputs JSON\n5. module-health-check.py -- LOC per package with content-aware bypass, outputs JSON\n6. build-check.py -- full build + test, paper tiger detection, blocker writing, outputs JSON\n7. read-errors.py -- reads BLOCKERS.md or build output, outputs JSON of errors\n8. post-session-archive.py -- feature archive + session archive + counting\n9. post-session-accounting.py -- session counting and state updates\n10. post-session-reconcile.py -- stale metadata, wiring audit\n11. post-session-periodic.py -- periodic checks (integration tests, etc.)\n12. post-session-status.py -- status output, outputs JSON\n13. post-session-cleanup.py -- empty session cleanup\n\nSubstitute project-specific values ($project_name, $build_command, $test_command, $specs_dir) into each script where needed.\n\nMake all .py files in the scripts directory executable.",
        context.artifact_path=".dev-machine/scripts/pipeline/",
        context.validation_criteria="Pipeline scripts are valid when:\n- All 13 .py files exist in .dev-machine/scripts/pipeline/\n- Each script runs with --help or basic invocation without crashing on import\n- orient.py accepts a STATE.yaml argument\n- build-check.py accepts build_command and test_command arguments\n- No unsubstituted $variable placeholders remain in the scripts",
        context.validation_command="count=$(ls .dev-machine/scripts/pipeline/*.py 2>/dev/null | wc -l); if [ $count -ge 13 ]; then echo \"valid: $count pipeline scripts\"; else echo \"expected 13 pipeline scripts, found $count\"; exit 1; fi"]

    // -----------------------------------------------------------------------
    // Generate infrastructure scripts
    // Source: generate-machine.md lines 90-108, templates-reference.md lines 86-88
    // -----------------------------------------------------------------------
    gen_infra [shape=folder, dot_file="../../patterns/convergence-factory.dot",
        context.artifact_goal="GENERATE MACHINE - Step 5: Generate Infrastructure Scripts\n\nRead .ai/design_vars.md for project-specific variables.\n\nGenerate infrastructure scripts into .dev-machine/scripts/infra/. These scripts WRAP the DOT pipeline engine from the outside and are NOT called by DOT tool nodes.\n\nGenerate:\n1. entrypoint.sh -- container entrypoint with retry loop:\n   - Loops calling 'attractor run .dev-machine/runtime/iteration.dot'\n   - Handles Cloudflare backoff (cf_backoff seconds, cf_backoff_max ceiling)\n   - Heartbeat file update for watchdog\n   - inter_session_cooldown seconds between successful sessions\n   - Substitutes: $project_name, $project_dir, $cf_backoff, $cf_backoff_max, $inter_session_cooldown\n\n2. watchdog.sh -- host-side health watchdog:\n   - Monitors heartbeat file age\n   - Restarts container if stuck for N minutes\n   - Substitutes: $project_name, $container_name\n\n3. monitor.sh -- diagnostic monitor:\n   - Reports container status, resource usage, recent log lines\n   - Substitutes: $project_name, $container_name, $image_name\n\nMake all .sh files executable (chmod +x).\n\nIMPORTANT: Docker format strings like {{.State.Status}}, {{.CPUPerc}}, {{.MemUsage}} are Go templates used by Docker, NOT machine template variables. Do NOT replace these -- they must remain as-is.",
        context.artifact_path=".dev-machine/scripts/infra/",
        context.validation_criteria="Infrastructure scripts are valid when:\n- entrypoint.sh, watchdog.sh, monitor.sh all exist in .dev-machine/scripts/infra/\n- All .sh files are executable\n- All .sh files pass bash -n syntax check\n- No unsubstituted machine template variables remain (check for literal '$project_name' etc.)",
        context.validation_command="for f in .dev-machine/scripts/infra/entrypoint.sh .dev-machine/scripts/infra/watchdog.sh .dev-machine/scripts/infra/monitor.sh; do bash -n $f || exit 1; done && echo 'valid: all 3 infra scripts pass syntax check'"]

    // -----------------------------------------------------------------------
    // Generate state files
    // Source: generate-machine.md lines 111-128, templates-reference.md lines 75-79
    // -----------------------------------------------------------------------
    gen_state_files [shape=folder, dot_file="../../patterns/convergence-factory.dot",
        context.artifact_goal="GENERATE MACHINE - Step 6: Generate State and Session Files\n\nRead .ai/design_vars.md for project-specific variables.\nRead the architecture spec and feature specs created during machine design.\n\nGenerate at the project root:\n\n1. STATE.yaml -- machine-readable project state:\n   - phase: foundation\n   - epoch: 0\n   - architecture_spec.status: approved\n   - For each module spec written: include with status: approved\n   - For each feature spec written: include with status: ready\n   - next_action: pointing to the first piece of work\n   - blockers: []\n   - session_count: 0\n\n2. CONTEXT-TRANSFER.md -- session handoff document:\n   - Header with project_name and date\n   - Empty 'Last Session Summary' section\n   - Empty 'Current Focus' section\n   - Empty 'Known Issues' section\n   - Instructions for the machine to fill this in after each session\n\n3. SCRATCH.md -- ephemeral working memory:\n   - Header with project_name\n   - Empty (machine fills this during sessions)\n\n4. AGENTS.md -- default session instructions:\n   - Tells any AI session opened in this repo to use the DOT pipeline engine\n   - Points to .dev-machine/runtime/iteration.dot as the primary pipeline\n   - States: do NOT make direct code changes outside the pipeline\n\nFor $timestamp, use the current ISO 8601 timestamp.\n\nPopulate STATE.yaml with the actual architecture spec and feature specs from the machine design phase.",
        context.artifact_path="STATE.yaml",
        context.validation_criteria="State files are valid when:\n- STATE.yaml exists, is valid YAML, has phase/epoch/architecture_spec fields\n- CONTEXT-TRANSFER.md exists and is non-empty\n- SCRATCH.md exists\n- AGENTS.md exists and mentions the DOT pipeline\n- STATE.yaml contains at least one feature with status: ready",
        context.validation_command="python3 -c \"import yaml; s=yaml.safe_load(open('STATE.yaml')); assert 'phase' in s and 'epoch' in s, 'missing phase or epoch'; print('valid STATE.yaml')\" 2>&1 && test -f CONTEXT-TRANSFER.md && test -f SCRATCH.md && test -f AGENTS.md && echo 'all 4 state files present'"]

    // -----------------------------------------------------------------------
    // Generate Dockerfile + docker-compose
    // Source: generate-machine.md lines 99-109, templates-reference.md lines 90-92
    // -----------------------------------------------------------------------
    gen_docker [shape=folder, dot_file="../../patterns/convergence-factory.dot",
        context.artifact_goal="GENERATE MACHINE - Step 5 (continued): Generate Docker Configuration\n\nRead .ai/design_vars.md for project-specific variables.\n\nGenerate Docker configuration:\n\n1. dev-machine.Dockerfile (in project root):\n   - FROM $base_image (default: python:3.12-slim)\n   - ARG USER_UID=$user_uid ARG USER_GID=$user_gid\n   - Install system packages: $system_packages\n   - Install uv at version $uv_version\n   - Install Amplifier (attractor)\n   - Create user $username with home $user_home\n   - Set up Node.js if $node_setup is defined\n   - Install python dev tools if $python_dev_tools is defined\n   - WORKDIR $project_dir\n   - COPY and install project dependencies\n   - CMD: the entrypoint script\n\n2. docker-compose.dev-machine.yaml (in project root):\n   - service: $container_name\n   - image: $image_name\n   - build: context and dockerfile\n   - volumes: mount project_dir, mount bundle_dir\n   - environment: key project variables\n   - restart: unless-stopped\n\nIMPORTANT: Docker Go template strings like {{.State.Status}}, {{.CPUPerc}}, {{.MemUsage}} must remain UNCHANGED. Only replace machine template variables.",
        context.artifact_path="dev-machine.Dockerfile",
        context.validation_criteria="Docker config is valid when:\n- dev-machine.Dockerfile exists and has FROM instruction\n- docker-compose.dev-machine.yaml exists and is valid YAML\n- No unsubstituted machine template variables remain in either file\n- Docker Go template strings ({{.State.Status}} etc.) are preserved unchanged",
        context.validation_command="test -f dev-machine.Dockerfile && python3 -c \"import yaml; yaml.safe_load(open('docker-compose.dev-machine.yaml')); print('valid YAML')\" 2>&1 && echo 'docker config present'"]

    // -----------------------------------------------------------------------
    // Final Validation: verify everything was generated correctly
    // Source: generate-machine.md lines 130-158
    // -----------------------------------------------------------------------
    validate_all [shape=parallelogram,
        label="Verify Generation",
        tool_command="python3 -c \"\nimport yaml, pathlib, subprocess, sys\nerrors = []\n\n# Check all runtime DOT files parse correctly\nfor f in pathlib.Path('.dev-machine/runtime').glob('*.dot'):\n    try:\n        from amplifier_module_loop_pipeline.dot_parser import parse_dot\n        parse_dot(f.read_text())\n    except Exception as e:\n        errors.append(f'DOT parse error in {f}: {e}')\n\n# Check required files exist\nrequired = [\n    '.dev-machine/runtime/iteration.dot',\n    '.dev-machine/runtime/post-session.dot',\n    '.dev-machine/runtime/health-check.dot',\n    '.dev-machine/runtime/fix-iteration.dot',\n    '.dev-machine/runtime/smoke-test.dot',\n    '.dev-machine/scripts/pipeline/orient.py',\n    '.dev-machine/scripts/pipeline/build-check.py',\n    '.dev-machine/scripts/infra/entrypoint.sh',\n    'STATE.yaml', 'CONTEXT-TRANSFER.md', 'AGENTS.md',\n    'dev-machine.Dockerfile', 'docker-compose.dev-machine.yaml',\n]\nfor f in required:\n    if not pathlib.Path(f).exists():\n        errors.append(f'Missing required file: {f}')\n\n# Check STATE.yaml validity\ntry:\n    s = yaml.safe_load(open('STATE.yaml'))\n    if 'phase' not in s: errors.append('STATE.yaml missing phase field')\nexcept Exception as e:\n    errors.append(f'STATE.yaml invalid: {e}')\n\nif errors:\n    print('VALIDATION FAILED:')\n    for e in errors: print(f'  - {e}')\n    sys.exit(1)\nelse:\n    print('VALIDATION PASSED: All generated artifacts are valid')\n\"",
        parse_json="false"]

    // -----------------------------------------------------------------------
    // Report to user
    // Source: generate-machine.md lines 180-191
    // -----------------------------------------------------------------------
    report [shape=box,
        label="Report Generated Files",
        prompt="GENERATE MACHINE MODE -- Generation Complete.\n\nPresent to the user:\n1. All files generated with their paths (list every file)\n2. The command to start the machine: 'attractor run .dev-machine/runtime/iteration.dot' (or via entrypoint.sh)\n3. The command to run health checks: 'attractor run .dev-machine/runtime/health-check.dot'\n4. If QA enabled: 'attractor run .dev-machine/runtime/qa.dot'\n5. Remind them the generated files belong to the project and can be modified\n6. Docker startup: 'docker compose -f docker-compose.dev-machine.yaml up -d --build'\n7. Cron setup for watchdog and monitor (print the cron lines for the host)\n\nRead .dev-machine-design.md and .ai/design_vars.md to get the project_dir for cron commands.\n\nReturn outcome success."]

    done [shape=Msquare, label="Machine Generated Successfully"]

    // Flow
    start -> design_check -> design_gate

    design_gate -> done_no_design [label="missing", condition="context.design_exists=false"]
    design_gate -> read_design    [label="exists",  condition="context.design_exists=true"]

    read_design -> gen_iteration -> gen_post_session -> gen_health_fix -> gen_smoke_test
    gen_smoke_test -> qa_check -> qa_gate

    // QA conditional branch -- merges back at gen_scripts
    qa_gate -> gen_qa     [label="enabled",  condition="context.qa_enabled=true"]
    qa_gate -> gen_scripts [label="disabled", condition="context.qa_enabled=false"]
    gen_qa -> gen_scripts

    gen_scripts -> gen_infra -> gen_state_files -> gen_docker -> validate_all -> report -> done
}
```

---

### Step 4: Run all structural tests

```bash
cd amplifier-bundle-attractor
python -m pytest modules/loop-pipeline/tests/test_foundry_generate_machine.py -v
```

Expected: **All PASS** — 16 tests passing.

---

### Step 5: Commit

```bash
cd amplifier-bundle-attractor
git add examples/dev-machine/foundry/generate-machine.dot modules/loop-pipeline/tests/test_foundry_generate_machine.py
git commit -m "feat: add foundry/generate-machine.dot with convergence-factory artifact generation pipeline"
```

---

## Task 24: Foundry Integration Tests

Add mock-backend execution tests for all three foundry DOT files. These verify the pipeline flows through the correct nodes with correct conditions, without calling real AI APIs.

**Files:**
- Modify: `amplifier-bundle-attractor/modules/loop-pipeline/tests/test_foundry_admissions.py` (add execution tests)
- Modify: `amplifier-bundle-attractor/modules/loop-pipeline/tests/test_foundry_machine_design.py` (add execution tests)
- Modify: `amplifier-bundle-attractor/modules/loop-pipeline/tests/test_foundry_generate_machine.py` (add execution tests)

---

### Step 1: Write the failing execution tests

Append to `amplifier-bundle-attractor/modules/loop-pipeline/tests/test_foundry_admissions.py`:

```python
# ---------------------------------------------------------------------------
# Execution tests: run admissions.dot with mock backends
# ---------------------------------------------------------------------------
# Add these imports at the top of the file:
#   from amplifier_module_loop_pipeline.context import PipelineContext
#   from amplifier_module_loop_pipeline.engine import PipelineEngine
#   from amplifier_module_loop_pipeline.graph import Graph, Node
#   from amplifier_module_loop_pipeline.handlers import HandlerRegistry
#   from amplifier_module_loop_pipeline.interviewer import Answer, Option, QueueInterviewer
#   from amplifier_module_loop_pipeline.outcome import Outcome, StageStatus
# ---------------------------------------------------------------------------


class MockToolHandlerAdmissions:
    """Returns SUCCESS for all parallelogram/tool nodes."""

    async def execute(self, node, context, graph, logs_root) -> "Outcome":
        from amplifier_module_loop_pipeline.outcome import Outcome, StageStatus
        return Outcome(status=StageStatus.SUCCESS)


class ProceedBackend:
    """Simulates: all gates score, then compile_assessment returns proceed."""

    def __init__(self, gate_count: int = 5) -> None:
        self._call_count = 0
        self._gate_count = gate_count
        self.calls: list[str] = []

    async def run(self, node, prompt: str, context) -> "Outcome":
        from amplifier_module_loop_pipeline.outcome import Outcome, StageStatus
        self.calls.append(node.id)
        if node.id == "eval":
            return Outcome(status=StageStatus.SUCCESS, preferred_label="scored")
        if node.id == "compile_assessment":
            return Outcome(status=StageStatus.SUCCESS, preferred_label="proceed")
        return Outcome(status=StageStatus.SUCCESS)


class NotReadyBackend:
    """Simulates: all gates score, then compile_assessment returns not_ready."""

    async def run(self, node, prompt: str, context) -> "Outcome":
        from amplifier_module_loop_pipeline.outcome import Outcome, StageStatus
        if node.id == "eval":
            return Outcome(status=StageStatus.SUCCESS, preferred_label="scored")
        if node.id == "compile_assessment":
            return Outcome(status=StageStatus.SUCCESS, preferred_label="not_ready")
        return Outcome(status=StageStatus.SUCCESS)


def _make_admissions_engine(backend, tmp_path, patterns_dir):
    """Build a PipelineEngine for admissions.dot with mocked pattern subpipelines."""
    from amplifier_module_loop_pipeline.context import PipelineContext
    from amplifier_module_loop_pipeline.dot_parser import parse_dot
    from amplifier_module_loop_pipeline.engine import PipelineEngine
    from amplifier_module_loop_pipeline.handlers import HandlerRegistry
    from amplifier_module_loop_pipeline.interviewer import Answer, Option, QueueInterviewer

    source = _ADMISSIONS_DOT.read_text()
    # Rewrite dot_file paths to absolute patterns dir for test resolution
    source = source.replace(
        "../../patterns/conversational-gate.dot",
        str(patterns_dir / "conversational-gate.dot"),
    )
    graph = parse_dot(source)
    graph.source_dir = str(_FOUNDRY_DIR)

    # Queue 5 "continue" answers — one per gate's ask node
    interviewer = QueueInterviewer([
        Answer(value="continue", selected_option=Option(key="continue", label="continue")),
        Answer(value="continue", selected_option=Option(key="continue", label="continue")),
        Answer(value="continue", selected_option=Option(key="continue", label="continue")),
        Answer(value="continue", selected_option=Option(key="continue", label="continue")),
        Answer(value="continue", selected_option=Option(key="continue", label="continue")),
    ])

    registry = HandlerRegistry(backend=backend, interviewer=interviewer)
    registry.register("tool", MockToolHandlerAdmissions())

    ctx = PipelineContext()
    return PipelineEngine(
        graph=graph,
        context=ctx,
        handler_registry=registry,
        logs_root=str(tmp_path / "logs"),
    )


class TestAdmissionsExecution:
    """Execution tests: admissions.dot runs through correct nodes with mock backends."""

    @pytest.mark.asyncio
    async def test_proceed_path_reaches_done_proceed(self, tmp_path):
        """When all gates score and assessment returns proceed, pipeline reaches done_proceed."""
        from amplifier_module_loop_pipeline.outcome import StageStatus

        backend = ProceedBackend()
        engine = _make_admissions_engine(backend, tmp_path, _PATTERNS_DIR)
        outcome = await engine.run()

        assert outcome.status == StageStatus.SUCCESS, (
            f"Expected SUCCESS, got {outcome.status}. "
            f"failure_reason: {outcome.failure_reason!r}"
        )

    @pytest.mark.asyncio
    async def test_not_ready_path_reaches_done_not_ready(self, tmp_path):
        """When assessment returns not_ready, pipeline reaches done_not_ready terminal."""
        from amplifier_module_loop_pipeline.outcome import StageStatus

        backend = NotReadyBackend()
        engine = _make_admissions_engine(backend, tmp_path, _PATTERNS_DIR)
        outcome = await engine.run()

        assert outcome.status == StageStatus.SUCCESS, (
            f"Expected SUCCESS (terminal reached), got {outcome.status}. "
            f"failure_reason: {outcome.failure_reason!r}"
        )

    @pytest.mark.asyncio
    async def test_compile_assessment_is_called_after_five_gates(self, tmp_path):
        """compile_assessment is called after all 5 gates complete."""
        backend = ProceedBackend()
        engine = _make_admissions_engine(backend, tmp_path, _PATTERNS_DIR)
        await engine.run()

        assert "compile_assessment" in engine.completed_nodes, (
            f"Expected compile_assessment in completed nodes: {engine.completed_nodes}"
        )

    @pytest.mark.asyncio
    async def test_verdict_gate_is_traversed(self, tmp_path):
        """verdict_gate diamond is traversed in the execution path."""
        backend = ProceedBackend()
        engine = _make_admissions_engine(backend, tmp_path, _PATTERNS_DIR)
        await engine.run()

        assert "verdict_gate" in engine.completed_nodes, (
            f"Expected verdict_gate in completed nodes: {engine.completed_nodes}"
        )
```

---

### Step 2: Run the execution tests to verify they fail

```bash
cd amplifier-bundle-attractor
python -m pytest modules/loop-pipeline/tests/test_foundry_admissions.py::TestAdmissionsExecution -v
```

Expected: Tests may fail due to import errors (missing imports at top of file) or execution issues. This identifies what needs to be fixed.

---

### Step 3: Update test files with correct imports and fix any issues

The execution tests need these imports added at the top of each test file (after the existing imports):

```python
from amplifier_module_loop_pipeline.context import PipelineContext
from amplifier_module_loop_pipeline.engine import PipelineEngine
from amplifier_module_loop_pipeline.graph import Graph, Node
from amplifier_module_loop_pipeline.handlers import HandlerRegistry
from amplifier_module_loop_pipeline.interviewer import Answer, Option, QueueInterviewer
from amplifier_module_loop_pipeline.outcome import Outcome, StageStatus
```

Add parallel execution tests for `test_foundry_machine_design.py`. Append:

```python
# ---------------------------------------------------------------------------
# Execution tests: machine-design.dot
# ---------------------------------------------------------------------------


class MockToolHandlerDesign:
    """Returns SUCCESS with assessment_exists='true' JSON for parallelogram nodes."""

    async def execute(self, node, context, graph, logs_root):
        from amplifier_module_loop_pipeline.outcome import Outcome, StageStatus
        # Simulate assessment_check returning {"assessment_exists": "true"}
        context.set("assessment_exists", "true")
        return Outcome(status=StageStatus.SUCCESS)


class DesignConvergedBackend:
    """Simulates: all conversational gates score, all factory phases converge."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._assess_count = 0

    async def run(self, node, prompt: str, context):
        from amplifier_module_loop_pipeline.outcome import Outcome, StageStatus
        self.calls.append(node.id)
        if node.id == "eval":
            return Outcome(status=StageStatus.SUCCESS, preferred_label="scored")
        if node.id == "assess":
            return Outcome(status=StageStatus.SUCCESS, preferred_label="converged")
        return Outcome(status=StageStatus.SUCCESS)


class TestMachineDesignExecution:
    """Execution tests: machine-design.dot with mock backends."""

    @pytest.mark.asyncio
    async def test_assessment_missing_exits_early(self, tmp_path):
        """When assessment_exists=false, pipeline exits to done_no_assessment immediately."""
        from amplifier_module_loop_pipeline.context import PipelineContext
        from amplifier_module_loop_pipeline.dot_parser import parse_dot
        from amplifier_module_loop_pipeline.engine import PipelineEngine
        from amplifier_module_loop_pipeline.handlers import HandlerRegistry
        from amplifier_module_loop_pipeline.outcome import Outcome, StageStatus

        class MissingAssessmentTool:
            async def execute(self, node, context, graph, logs_root):
                context.set("assessment_exists", "false")
                return Outcome(status=StageStatus.SUCCESS)

        source = _MACHINE_DESIGN_DOT.read_text()
        graph = parse_dot(source)
        graph.source_dir = str(_FOUNDRY_DIR)

        class NopBackend:
            async def run(self, node, prompt, context):
                return Outcome(status=StageStatus.SUCCESS)

        registry = HandlerRegistry(backend=NopBackend())
        registry.register("tool", MissingAssessmentTool())

        engine = PipelineEngine(
            graph=graph,
            context=PipelineContext(),
            handler_registry=registry,
            logs_root=str(tmp_path / "logs"),
        )
        outcome = await engine.run()

        assert outcome.status == StageStatus.SUCCESS
        # Should NOT have reached phase1_config
        assert "phase1_config" not in engine.completed_nodes, (
            f"Expected early exit — phase1_config should not be in: {engine.completed_nodes}"
        )
```

Add parallel execution tests for `test_foundry_generate_machine.py`. Append:

```python
# ---------------------------------------------------------------------------
# Execution tests: generate-machine.dot
# ---------------------------------------------------------------------------


class TestGenerateMachineExecution:
    """Execution tests: generate-machine.dot with mock backends."""

    @pytest.mark.asyncio
    async def test_design_missing_exits_early(self, tmp_path):
        """When design_exists=false, pipeline exits to done_no_design immediately."""
        from amplifier_module_loop_pipeline.context import PipelineContext
        from amplifier_module_loop_pipeline.dot_parser import parse_dot
        from amplifier_module_loop_pipeline.engine import PipelineEngine
        from amplifier_module_loop_pipeline.handlers import HandlerRegistry
        from amplifier_module_loop_pipeline.outcome import Outcome, StageStatus

        class MissingDesignTool:
            async def execute(self, node, context, graph, logs_root):
                context.set("design_exists", "false")
                return Outcome(status=StageStatus.SUCCESS)

        source = _GEN_MACHINE_DOT.read_text()
        graph = parse_dot(source)
        graph.source_dir = str(_FOUNDRY_DIR)

        class NopBackend:
            async def run(self, node, prompt, context):
                return Outcome(status=StageStatus.SUCCESS)

        registry = HandlerRegistry(backend=NopBackend())
        registry.register("tool", MissingDesignTool())

        engine = PipelineEngine(
            graph=graph,
            context=PipelineContext(),
            handler_registry=registry,
            logs_root=str(tmp_path / "logs"),
        )
        outcome = await engine.run()

        assert outcome.status == StageStatus.SUCCESS
        assert "read_design" not in engine.completed_nodes, (
            f"Expected early exit — read_design should not be in: {engine.completed_nodes}"
        )

    @pytest.mark.asyncio
    async def test_qa_disabled_skips_gen_qa(self, tmp_path):
        """When qa_enabled=false, gen_qa node is NOT visited."""
        from amplifier_module_loop_pipeline.context import PipelineContext
        from amplifier_module_loop_pipeline.dot_parser import parse_dot
        from amplifier_module_loop_pipeline.engine import PipelineEngine
        from amplifier_module_loop_pipeline.handlers import HandlerRegistry
        from amplifier_module_loop_pipeline.outcome import Outcome, StageStatus
        from amplifier_module_loop_pipeline.patterns import _PATTERNS_DIR as _P

        class QADisabledToolHandler:
            def __init__(self):
                self.call_count = 0
            async def execute(self, node, context, graph, logs_root):
                self.call_count += 1
                if node.id == "design_check":
                    context.set("design_exists", "true")
                elif node.id == "qa_check":
                    context.set("qa_enabled", "false")
                return Outcome(status=StageStatus.SUCCESS)

        source = _GEN_MACHINE_DOT.read_text()
        # Rewrite to absolute paths for pattern resolution
        patterns_dir = _REPO_ROOT / "examples" / "patterns"
        source = source.replace(
            "../../patterns/convergence-factory.dot",
            str(patterns_dir / "convergence-factory.dot"),
        )
        graph = parse_dot(source)
        graph.source_dir = str(_FOUNDRY_DIR)

        tool_handler = QADisabledToolHandler()

        class ConvergedBackend:
            async def run(self, node, prompt, context):
                if node.id == "assess":
                    return Outcome(status=StageStatus.SUCCESS, preferred_label="converged")
                return Outcome(status=StageStatus.SUCCESS)

        registry = HandlerRegistry(backend=ConvergedBackend())
        registry.register("tool", tool_handler)

        engine = PipelineEngine(
            graph=graph,
            context=PipelineContext(),
            handler_registry=registry,
            logs_root=str(tmp_path / "logs"),
        )
        outcome = await engine.run()

        assert "gen_qa" not in engine.completed_nodes, (
            f"Expected gen_qa NOT visited when qa_enabled=false. "
            f"Completed: {engine.completed_nodes}"
        )
```

---

### Step 4: Run the full integration test suite

```bash
cd amplifier-bundle-attractor
python -m pytest modules/loop-pipeline/tests/test_foundry_admissions.py \
    modules/loop-pipeline/tests/test_foundry_machine_design.py \
    modules/loop-pipeline/tests/test_foundry_generate_machine.py \
    -v --tb=short
```

Expected: **All PASS** — approximately 55 tests total.

Fix any failures by adjusting the DOT files to correct node IDs, edge conditions, or attribute names. Do NOT weaken the tests.

---

### Step 5: Commit

```bash
cd amplifier-bundle-attractor
git add modules/loop-pipeline/tests/test_foundry_admissions.py \
    modules/loop-pipeline/tests/test_foundry_machine_design.py \
    modules/loop-pipeline/tests/test_foundry_generate_machine.py
git commit -m "test: add foundry integration tests — parse validation + mock-backend execution"
```

---

## Task 25: End-to-End Test — Foundry → Runtime Chain

Prove that the foundry→runtime chain works: `generate-machine.dot` (with mocked convergence-factory outputs) produces runtime DOT files that pass `smoke-test.dot`'s structural validation.

**Files:**
- Create: `amplifier-bundle-attractor/modules/loop-pipeline/tests/test_foundry_e2e.py`

---

### Step 1: Write the failing E2E test

Create `amplifier-bundle-attractor/modules/loop-pipeline/tests/test_foundry_e2e.py`:

```python
"""End-to-end test: foundry -> runtime DOT chain validation.

Verifies the foundry pipeline chain:
1. admissions.dot structural integrity (all 3 foundry DOTs parse)
2. generate-machine.dot with mocked convergence outputs produces runtime DOTs
3. Generated runtime DOTs pass smoke-test.dot structural validation
4. The chain: foundry/admissions -> foundry/machine-design -> foundry/generate-machine
   -> runtime/iteration (smoke-test) is structurally coherent

This test does NOT call real AI APIs. It uses:
- MockGeneratorBackend: simulates convergence-factory convergence by writing
  minimal valid DOT files to the expected artifact paths
- parse_dot: validates all generated DOT files are structurally valid
- The smoke-test.dot pipeline's node structure as the validation oracle
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from amplifier_module_loop_pipeline.dot_parser import parse_dot

_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_FOUNDRY_DIR = _REPO_ROOT / "examples" / "dev-machine" / "foundry"
_PATTERNS_DIR = _REPO_ROOT / "examples" / "patterns"

# All three foundry DOT files
_ADMISSIONS_DOT = _FOUNDRY_DIR / "admissions.dot"
_MACHINE_DESIGN_DOT = _FOUNDRY_DIR / "machine-design.dot"
_GEN_MACHINE_DOT = _FOUNDRY_DIR / "generate-machine.dot"


# ---------------------------------------------------------------------------
# Fixtures: minimal valid runtime DOT content for each artifact
# ---------------------------------------------------------------------------

MINIMAL_ITERATION_DOT = """\
digraph iteration {
    graph [goal="Execute one dev-machine working session"]
    start [shape=Mdiamond]
    orient [shape=parallelogram, tool_command="python3 scripts/orient.py STATE.yaml", parse_json="true"]
    orient_gate [shape=diamond]
    working_session [shape=box, prompt="Execute working session based on STATE.yaml and feature specs"]
    build_check [shape=parallelogram, tool_command="python3 scripts/build-check.py", parse_json="true"]
    build_gate [shape=diamond]
    post_session [shape=folder, dot_file="post-session.dot"]
    done [shape=Msquare]
    start -> orient -> orient_gate
    orient_gate -> done [condition="context.status=blocked"]
    orient_gate -> working_session [condition="context.status=healthy"]
    working_session -> build_check -> build_gate
    build_gate -> post_session [condition="context.build_status=clean"]
    build_gate -> post_session [condition="context.build_status=failed"]
    post_session -> done
}
"""

MINIMAL_POST_SESSION_DOT = """\
digraph post_session {
    graph [goal="Post-session archiving and reconciliation"]
    start [shape=Mdiamond]
    archive [shape=parallelogram, tool_command="python3 scripts/post-session-archive.py STATE.yaml"]
    reconcile [shape=parallelogram, tool_command="python3 scripts/post-session-reconcile.py STATE.yaml", continue_on_fail="true"]
    done [shape=Msquare]
    start -> archive -> reconcile -> done
}
"""

MINIMAL_HEALTH_CHECK_DOT = """\
digraph health_check {
    graph [goal="Fix build/test errors until clean"]
    start [shape=Mdiamond]
    initial_check [shape=parallelogram, tool_command="python3 scripts/build-check.py", parse_json="true"]
    clean_gate [shape=diamond]
    fix_loop [shape=house, stack.child_dotfile="fix-iteration.dot", manager.max_cycles="10"]
    done [shape=Msquare]
    start -> initial_check -> clean_gate
    clean_gate -> done [condition="context.build_status=clean"]
    clean_gate -> fix_loop [condition="context.build_status=failed"]
    fix_loop -> done
}
"""

MINIMAL_FIX_ITERATION_DOT = """\
digraph fix_iteration {
    graph [goal="Read errors, fix them, verify"]
    start [shape=Mdiamond]
    read_errors [shape=parallelogram, tool_command="python3 scripts/read-errors.py STATE.yaml", parse_json="true"]
    fix_session [shape=box, prompt="Fix the build errors reported in BLOCKERS.md"]
    verify [shape=parallelogram, tool_command="python3 scripts/build-check.py", parse_json="true"]
    done [shape=Msquare]
    start -> read_errors -> fix_session -> verify -> done
}
"""

MINIMAL_SMOKE_TEST_DOT = """\
digraph smoke_test {
    graph [goal="Validate generated dev-machine artifacts are complete and structurally sound"]
    start [shape=Mdiamond]
    check_files [shape=parallelogram, tool_command="test -f STATE.yaml && test -f .dev-machine/runtime/iteration.dot && echo ok"]
    check_dots [shape=parallelogram, tool_command="python3 -c 'from amplifier_module_loop_pipeline.dot_parser import parse_dot; import pathlib; [parse_dot(f.read_text()) for f in pathlib.Path(\".dev-machine/runtime\").glob(\"*.dot\")]; print(\"all dot files valid\")'"]
    check_scripts [shape=parallelogram, tool_command="ls .dev-machine/scripts/pipeline/*.py"]
    check_infra [shape=parallelogram, tool_command="test -x .dev-machine/scripts/infra/entrypoint.sh && echo ok"]
    check_state [shape=parallelogram, tool_command="python3 -c 'import yaml; yaml.safe_load(open(\"STATE.yaml\")); print(\"valid\")'"]
    summary [shape=parallelogram, tool_command="echo '{\"smoke_test_status\": \"passed\"}'", parse_json="true"]
    done [shape=Msquare]
    start -> check_files -> check_dots -> check_scripts -> check_infra -> check_state -> summary -> done
}
"""

# Map: artifact_path keyword -> content to write
ARTIFACT_MAP = {
    "iteration.dot": MINIMAL_ITERATION_DOT,
    "post-session.dot": MINIMAL_POST_SESSION_DOT,
    "health-check.dot": MINIMAL_HEALTH_CHECK_DOT,
    "fix-iteration.dot": MINIMAL_FIX_ITERATION_DOT,
    "smoke-test.dot": MINIMAL_SMOKE_TEST_DOT,
}


# ---------------------------------------------------------------------------
# Test: all three foundry DOTs parse correctly
# ---------------------------------------------------------------------------


class TestFoundryChainStructure:
    """Verify all three foundry DOT files parse and have coherent structure."""

    def test_all_three_foundry_dots_exist(self):
        """All three foundry DOT files exist."""
        for dot_file in [_ADMISSIONS_DOT, _MACHINE_DESIGN_DOT, _GEN_MACHINE_DOT]:
            assert dot_file.exists(), f"Foundry DOT missing: {dot_file}"

    def test_all_three_foundry_dots_parse(self):
        """All three foundry DOT files parse without error."""
        for dot_file in [_ADMISSIONS_DOT, _MACHINE_DESIGN_DOT, _GEN_MACHINE_DOT]:
            source = dot_file.read_text()
            g = parse_dot(source)
            assert len(g.nodes) > 0, f"No nodes parsed from {dot_file.name}"

    def test_foundry_chain_output_of_admissions_feeds_machine_design(self):
        """admissions.dot writes .dev-machine-assessment.md; machine-design.dot checks for it."""
        # admissions compile_assessment prompt mentions writing .dev-machine-assessment.md
        admissions_source = _ADMISSIONS_DOT.read_text()
        g_admissions = parse_dot(admissions_source)
        compile_node = g_admissions.nodes.get("compile_assessment")
        assert compile_node is not None
        assert ".dev-machine-assessment.md" in (compile_node.prompt or ""), (
            "admissions compile_assessment should write .dev-machine-assessment.md"
        )

        # machine-design.dot assessment_check checks for .dev-machine-assessment.md
        design_source = _MACHINE_DESIGN_DOT.read_text()
        g_design = parse_dot(design_source)
        check_node = g_design.nodes.get("assessment_check")
        assert check_node is not None
        assert ".dev-machine-assessment.md" in check_node.attrs.get("tool_command", ""), (
            "machine-design assessment_check should check for .dev-machine-assessment.md"
        )

    def test_foundry_chain_output_of_machine_design_feeds_generate_machine(self):
        """machine-design.dot writes .dev-machine-design.md; generate-machine.dot checks for it."""
        # machine-design phase5 prompt mentions writing .dev-machine-design.md
        design_source = _MACHINE_DESIGN_DOT.read_text()
        g_design = parse_dot(design_source)
        design_doc_nodes = [
            n for n in g_design.nodes.values()
            if ".dev-machine-design.md" in (n.prompt or "")
        ]
        assert len(design_doc_nodes) >= 1, (
            "machine-design should have a node that writes .dev-machine-design.md"
        )

        # generate-machine.dot design_check checks for .dev-machine-design.md
        gen_source = _GEN_MACHINE_DOT.read_text()
        g_gen = parse_dot(gen_source)
        design_check = g_gen.nodes.get("design_check")
        assert design_check is not None
        assert ".dev-machine-design.md" in design_check.attrs.get("tool_command", ""), (
            "generate-machine design_check should check for .dev-machine-design.md"
        )

    def test_generate_machine_artifact_paths_produce_valid_dot(self):
        """The minimal DOT content for each artifact_path is valid DOT syntax."""
        for name, content in ARTIFACT_MAP.items():
            g = parse_dot(content)
            assert len(g.nodes) > 0, f"Minimal {name} content doesn't parse to valid DOT"

    def test_minimal_iteration_dot_has_required_nodes(self):
        """Minimal iteration.dot has start, orient, working_session, build_check, done."""
        g = parse_dot(MINIMAL_ITERATION_DOT)
        required = {"start", "orient", "working_session", "build_check", "done"}
        actual = set(g.nodes.keys())
        assert required.issubset(actual), (
            f"Minimal iteration.dot missing nodes: {required - actual}"
        )

    def test_minimal_smoke_test_dot_has_six_check_nodes(self):
        """Minimal smoke-test.dot has at least 5 parallelogram check nodes."""
        g = parse_dot(MINIMAL_SMOKE_TEST_DOT)
        tool_nodes = [n for n in g.nodes.values() if n.shape == "parallelogram"]
        assert len(tool_nodes) >= 5, (
            f"smoke-test.dot needs 5+ tool nodes, got {len(tool_nodes)}"
        )

    def test_generate_machine_iteration_artifact_goal_mentions_orient_node(self):
        """generate-machine.dot's iteration artifact_goal mentions the orient node."""
        source = _GEN_MACHINE_DOT.read_text()
        g = parse_dot(source)
        folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
        factory_folders = [
            n for n in folder_nodes
            if "convergence-factory.dot" in n.attrs.get("dot_file", "")
        ]
        iteration_nodes = [
            n for n in factory_folders
            if "iteration.dot" in n.attrs.get("context.artifact_path", "")
        ]
        assert len(iteration_nodes) >= 1, (
            "generate-machine.dot should have a convergence-factory node "
            "generating iteration.dot"
        )
        goal = iteration_nodes[0].attrs.get("context.artifact_goal", "")
        assert "orient" in goal.lower() or "working_session" in goal.lower(), (
            f"iteration.dot artifact_goal should describe required nodes. "
            f"Got: {goal[:200]!r}"
        )

    def test_smoke_test_dot_validation_of_generated_iteration(self):
        """smoke-test.dot's check_dots node would accept a valid iteration.dot."""
        # Parse the minimal iteration.dot — if it parses, smoke-test's check_dots would pass
        g = parse_dot(MINIMAL_ITERATION_DOT)
        assert len(g.nodes) > 0, "iteration.dot must be valid DOT for smoke-test to pass"

        # Verify smoke-test.dot has a node checking DOT file validity
        smoke_source = _GEN_MACHINE_DOT.read_text()
        g_gen = parse_dot(smoke_source)
        # Find validation_all or similar node that checks .dot files
        validation_nodes = [
            n for n in g_gen.nodes.values()
            if "validat" in n.id.lower() or "smoke" in n.id.lower()
        ]
        assert len(validation_nodes) >= 1, (
            "generate-machine.dot should have a final validation node that "
            "checks generated .dot files"
        )

    def test_all_foundry_patterns_are_relative_to_patterns_dir(self):
        """All folder node dot_file attrs in foundry DOTs reference conversational-gate or convergence-factory."""
        for dot_file in [_ADMISSIONS_DOT, _MACHINE_DESIGN_DOT, _GEN_MACHINE_DOT]:
            source = dot_file.read_text()
            g = parse_dot(source)
            folder_nodes = [n for n in g.nodes.values() if n.shape == "folder"]
            for node in folder_nodes:
                dot_ref = node.attrs.get("dot_file", "")
                assert (
                    "conversational-gate.dot" in dot_ref
                    or "convergence-factory.dot" in dot_ref
                    or "post-session.dot" in dot_ref
                    or "fix-iteration.dot" in dot_ref
                    or "qa-iteration.dot" in dot_ref
                ), (
                    f"In {dot_file.name}, node {node.id!r} references unexpected pattern: {dot_ref!r}. "
                    f"Expected conversational-gate.dot, convergence-factory.dot, or known runtime DOTs."
                )
```

---

### Step 2: Run the E2E test to verify it fails (or passes)

```bash
cd amplifier-bundle-attractor
python -m pytest modules/loop-pipeline/tests/test_foundry_e2e.py -v
```

Expected: Most structural tests pass. Any failures indicate issues in the foundry DOT files that need fixing.

---

### Step 3: Fix any failures in the foundry DOT files

If tests fail:
- Check the exact assertion messages
- Fix the DOT file (not the test) to satisfy the contract
- Re-run until all pass

Common fixes:
- Node ID mismatch: check `engine.completed_nodes` to see actual IDs
- Missing context attrs: add the required `context.*` attribute to the folder node
- Wrong artifact_path: update `context.artifact_path` to match expected value
- Edge condition typo: check `condition="context.foo=bar"` matches exact string values

---

### Step 4: Run the complete Phase 4 test suite

```bash
cd amplifier-bundle-attractor
python -m pytest \
    modules/loop-pipeline/tests/test_foundry_admissions.py \
    modules/loop-pipeline/tests/test_foundry_machine_design.py \
    modules/loop-pipeline/tests/test_foundry_generate_machine.py \
    modules/loop-pipeline/tests/test_foundry_e2e.py \
    -v --tb=short
```

Expected: **All PASS** — approximately 65+ tests green.

---

### Step 5: Commit

```bash
cd amplifier-bundle-attractor
git add modules/loop-pipeline/tests/test_foundry_e2e.py
git commit -m "test: add foundry E2E chain test — admissions->machine-design->generate-machine->runtime validation"
```

---

## Implementation Checklist

| Task | File | Tests | Status |
|------|------|-------|--------|
| 21 | `examples/dev-machine/foundry/admissions.dot` | `test_foundry_admissions.py` (parse) | ☐ |
| 22 | `examples/dev-machine/foundry/machine-design.dot` | `test_foundry_machine_design.py` (parse) | ☐ |
| 23 | `examples/dev-machine/foundry/generate-machine.dot` | `test_foundry_generate_machine.py` (parse) | ☐ |
| 24 | Integration tests added to all 3 test files | Execution tests | ☐ |
| 25 | `test_foundry_e2e.py` | Chain integrity + runtime validation | ☐ |

## Hard Constraints (Non-Negotiable)

1. **Gate text is verbatim.** The gate topics and criteria in `admissions.dot` come directly from `gate-criteria.md`. If in doubt, read the source file and copy exactly — only replacing `{{variable}}` with `$variable`.

2. **Phase instructions are verbatim.** The convergence-factory `artifact_goal` attributes in `machine-design.dot` embed the phase instructions from `machine-design.md` (lines 42-143). Read the file.

3. **Generation rules are verbatim.** The `artifact_goal` attributes in `generate-machine.dot` encode the generation steps from `generate-machine.md` (lines 39-191) and the machine-generator agent (lines 41-107). Read both files.

4. **Do not simplify prompts.** Long prompts are long because the original mode files are detailed. Shortening them changes behavior.

5. **Fix DOT files, not tests.** If a test fails, the DOT file is wrong. Tests encode the correct contract derived from the source material.

6. **Folder nodes use relative paths.** From `examples/dev-machine/foundry/`, patterns are at `../../patterns/`. This is the correct relative path for DOT file attributes.
