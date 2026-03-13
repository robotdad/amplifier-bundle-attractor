"""Tests for admissions.dot -- Project Readiness Evaluation pipeline.

Verifies that examples/dev-machine/foundry/admissions.dot is correct per spec:
- 10 nodes: start (Mdiamond), gate1-5 (folder), compile_assessment (codergen/box),
  verdict_gate (diamond), 3 done terminals (Msquare: done_proceed, done_caution, done_not_ready)
- All 5 folder nodes reference ../../patterns/conversational-gate.dot
- Each folder node has context.gate_topic, context.gate_criteria, context.gate_output_path
- Gate topics: DECOMPOSABILITY, CORRECTNESS, ARCHITECTURE, TOOLCHAIN, SPEC
- Gate criteria contain scoring thresholds (75%, 50%)
- compile_assessment references all 5 gate output files, scoring thresholds,
  .dev-machine-assessment.md, and preferred_label routing instruction
- verdict_gate has 3 conditional edges: proceed, caution, not_ready
- Sequential flow: start -> gate1 -> gate2 -> gate3 -> gate4 -> gate5
                           -> compile_assessment -> verdict_gate

Source material:
- amplifier-bundle-dev-machine/modes/admissions.md (115 lines)
- amplifier-bundle-dev-machine/context/gate-criteria.md (195 lines)
- amplifier-bundle-dev-machine/agents/admissions-advisor.md (58 lines)

Test file: modules/loop-pipeline/tests/test_foundry_admissions.py
DOT file: examples/dev-machine/foundry/admissions.dot
"""

from __future__ import annotations

import os

from amplifier_module_loop_pipeline.dot_parser import parse_dot

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_TESTS_DIR = os.path.dirname(__file__)
# From modules/loop-pipeline/tests/ -> up 3 levels -> amplifier-bundle-attractor/ -> examples/
_EXAMPLES_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "..", "..", "examples"))
_ADMISSIONS_DOT = os.path.join(
    _EXAMPLES_DIR, "dev-machine", "foundry", "admissions.dot"
)


def _load() -> str:
    with open(_ADMISSIONS_DOT) as f:
        return f.read()


def _graph():
    return parse_dot(_load())


# ===========================================================================
# TestAdmissionsParse -- admissions.dot structural tests
# ===========================================================================


class TestAdmissionsParse:
    """Tests for admissions.dot parse correctness and structural requirements."""

    # -----------------------------------------------------------------------
    # AC-1: File exists
    # -----------------------------------------------------------------------

    def test_file_exists(self):
        """admissions.dot exists at examples/dev-machine/foundry/admissions.dot."""
        assert os.path.isfile(_ADMISSIONS_DOT), (
            f"admissions.dot not found at {_ADMISSIONS_DOT}"
        )

    # -----------------------------------------------------------------------
    # AC-2: Parses without error
    # -----------------------------------------------------------------------

    def test_parses_without_error(self):
        """admissions.dot parses without raising exceptions."""
        graph = _graph()
        assert graph is not None

    # -----------------------------------------------------------------------
    # AC-3: Exactly 10 nodes
    # -----------------------------------------------------------------------

    def test_has_exactly_ten_nodes(self):
        """Exactly 11 nodes: start, gate1-5, compile_assessment, verdict_gate, 3 done terminals.

        Note: the spec description lists 11 distinct node elements
        (start + 5 gates + compile_assessment + verdict_gate + 3 terminals = 11).
        """
        graph = _graph()
        assert len(graph.nodes) == 11, (
            f"Expected 11 nodes, got {len(graph.nodes)}: {list(graph.nodes.keys())}"
        )

    # -----------------------------------------------------------------------
    # AC-4: start node exists with Mdiamond shape
    # -----------------------------------------------------------------------

    def test_has_start_node(self):
        """start node exists with shape=Mdiamond."""
        graph = _graph()
        assert "start" in graph.nodes, (
            f"Node 'start' not found. Nodes: {list(graph.nodes.keys())}"
        )
        assert graph.nodes["start"].shape == "Mdiamond", (
            f"Expected start shape=Mdiamond, got {graph.nodes['start'].shape!r}"
        )

    # -----------------------------------------------------------------------
    # AC-5: Exactly 5 folder nodes
    # -----------------------------------------------------------------------

    def test_has_five_folder_nodes(self):
        """Exactly 5 folder nodes (gate1-gate5)."""
        graph = _graph()
        folder_nodes = [n for n in graph.nodes.values() if n.shape == "folder"]
        assert len(folder_nodes) == 5, (
            f"Expected 5 folder nodes, got {len(folder_nodes)}: "
            f"{[n.id for n in folder_nodes]}"
        )

    # -----------------------------------------------------------------------
    # AC-6: All folder nodes reference conversational-gate.dot
    # -----------------------------------------------------------------------

    def test_folder_nodes_reference_conversational_gate(self):
        """All folder nodes reference ../../patterns/conversational-gate.dot."""
        graph = _graph()
        folder_nodes = [n for n in graph.nodes.values() if n.shape == "folder"]
        for node in folder_nodes:
            dot_file = node.attrs.get("dot_file", "")
            assert "conversational-gate.dot" in dot_file, (
                f"Node {node.id!r} dot_file should reference conversational-gate.dot, "
                f"got {dot_file!r}"
            )

    # -----------------------------------------------------------------------
    # AC-7: Each folder node has all three context attrs
    # -----------------------------------------------------------------------

    def test_folder_nodes_have_all_three_context_attrs(self):
        """Each folder node has context.gate_topic, context.gate_criteria, context.gate_output_path."""
        graph = _graph()
        folder_nodes = [n for n in graph.nodes.values() if n.shape == "folder"]
        for node in folder_nodes:
            assert "context.gate_topic" in node.attrs, (
                f"Node {node.id!r} missing context.gate_topic attr"
            )
            assert "context.gate_criteria" in node.attrs, (
                f"Node {node.id!r} missing context.gate_criteria attr"
            )
            assert "context.gate_output_path" in node.attrs, (
                f"Node {node.id!r} missing context.gate_output_path attr"
            )

    # -----------------------------------------------------------------------
    # AC-8: Gate output paths are unique
    # -----------------------------------------------------------------------

    def test_gate_output_paths_are_unique(self):
        """Each gate has a unique context.gate_output_path."""
        graph = _graph()
        folder_nodes = [n for n in graph.nodes.values() if n.shape == "folder"]
        paths = [
            node.attrs.get("context.gate_output_path", "") for node in folder_nodes
        ]
        assert len(paths) == len(set(paths)), (
            f"Expected all gate output paths to be unique, got duplicates: {paths}"
        )

    # -----------------------------------------------------------------------
    # AC-9..13: Gate topics cover all 5 areas
    # -----------------------------------------------------------------------

    def test_gate_topics_contain_decomposability(self):
        """At least one gate topic contains DECOMPOSABILITY."""
        graph = _graph()
        folder_nodes = [n for n in graph.nodes.values() if n.shape == "folder"]
        topics = [node.attrs.get("context.gate_topic", "") for node in folder_nodes]
        assert any("DECOMPOSABILITY" in t for t in topics), (
            f"Expected DECOMPOSABILITY in a gate topic. Topics: {topics}"
        )

    def test_gate_topics_contain_correctness(self):
        """At least one gate topic contains CORRECTNESS."""
        graph = _graph()
        folder_nodes = [n for n in graph.nodes.values() if n.shape == "folder"]
        topics = [node.attrs.get("context.gate_topic", "") for node in folder_nodes]
        assert any("CORRECTNESS" in t for t in topics), (
            f"Expected CORRECTNESS in a gate topic. Topics: {topics}"
        )

    def test_gate_topics_contain_architecture(self):
        """At least one gate topic contains ARCHITECTURE."""
        graph = _graph()
        folder_nodes = [n for n in graph.nodes.values() if n.shape == "folder"]
        topics = [node.attrs.get("context.gate_topic", "") for node in folder_nodes]
        assert any("ARCHITECTURE" in t for t in topics), (
            f"Expected ARCHITECTURE in a gate topic. Topics: {topics}"
        )

    def test_gate_topics_contain_toolchain(self):
        """At least one gate topic contains TOOLCHAIN."""
        graph = _graph()
        folder_nodes = [n for n in graph.nodes.values() if n.shape == "folder"]
        topics = [node.attrs.get("context.gate_topic", "") for node in folder_nodes]
        assert any("TOOLCHAIN" in t for t in topics), (
            f"Expected TOOLCHAIN in a gate topic. Topics: {topics}"
        )

    def test_gate_topics_contain_spec(self):
        """At least one gate topic contains SPEC."""
        graph = _graph()
        folder_nodes = [n for n in graph.nodes.values() if n.shape == "folder"]
        topics = [node.attrs.get("context.gate_topic", "") for node in folder_nodes]
        assert any("SPEC" in t for t in topics), (
            f"Expected SPEC in a gate topic. Topics: {topics}"
        )

    # -----------------------------------------------------------------------
    # AC-14: Gate criteria contain scoring thresholds
    # -----------------------------------------------------------------------

    def test_gate_criteria_contain_scoring_thresholds(self):
        """Gate criteria contain scoring thresholds (75% and 50%)."""
        graph = _graph()
        folder_nodes = [n for n in graph.nodes.values() if n.shape == "folder"]
        all_criteria = " ".join(
            node.attrs.get("context.gate_criteria", "") for node in folder_nodes
        )
        assert "75" in all_criteria, (
            f"Expected '75' (75%) threshold in gate criteria. "
            f"Criteria (first 300 chars): {all_criteria[:300]}"
        )
        assert "50" in all_criteria, (
            f"Expected '50' (50%) threshold in gate criteria. "
            f"Criteria (first 300 chars): {all_criteria[:300]}"
        )

    # -----------------------------------------------------------------------
    # AC-15: compile_assessment is a codergen node (box/default shape)
    # -----------------------------------------------------------------------

    def test_has_compile_assessment_codergen_node(self):
        """compile_assessment node exists with codergen (box/default) shape."""
        graph = _graph()
        assert "compile_assessment" in graph.nodes, (
            f"Node 'compile_assessment' not found. Nodes: {list(graph.nodes.keys())}"
        )
        node = graph.nodes["compile_assessment"]
        # codergen nodes have box or default (empty/None) shape
        assert node.shape in ("box", "rectangle", None, ""), (
            f"Expected compile_assessment to be a codergen (box/default) node, "
            f"got shape={node.shape!r}"
        )

    # -----------------------------------------------------------------------
    # AC-16: compile_assessment prompt references all 5 gate output files
    # -----------------------------------------------------------------------

    def test_compile_assessment_prompt_contains_gate_files(self):
        """compile_assessment prompt references all 5 gate output files."""
        graph = _graph()
        node = graph.nodes.get("compile_assessment")
        assert node is not None, "compile_assessment node not found"
        prompt = node.prompt or ""
        for i in range(1, 6):
            assert f"gate{i}" in prompt, (
                f"Expected reference to gate{i} file in compile_assessment prompt. "
                f"Prompt (first 400 chars): {prompt[:400]}"
            )

    # -----------------------------------------------------------------------
    # AC-17: compile_assessment prompt contains threshold rules
    # -----------------------------------------------------------------------

    def test_compile_assessment_prompt_contains_threshold_rules(self):
        """compile_assessment prompt contains scoring threshold rules (50%, 75%)."""
        graph = _graph()
        node = graph.nodes.get("compile_assessment")
        assert node is not None, "compile_assessment node not found"
        prompt = node.prompt or ""
        assert "50" in prompt, (
            f"Expected '50' (50%) threshold rule in compile_assessment prompt. "
            f"Prompt (first 400 chars): {prompt[:400]}"
        )
        assert "75" in prompt, (
            f"Expected '75' (75%) threshold rule in compile_assessment prompt. "
            f"Prompt (first 400 chars): {prompt[:400]}"
        )

    # -----------------------------------------------------------------------
    # AC-18: compile_assessment prompt mentions .dev-machine-assessment.md
    # -----------------------------------------------------------------------

    def test_compile_assessment_prompt_mentions_dev_machine_assessment(self):
        """compile_assessment prompt mentions .dev-machine-assessment.md."""
        graph = _graph()
        node = graph.nodes.get("compile_assessment")
        assert node is not None, "compile_assessment node not found"
        prompt = node.prompt or ""
        assert ".dev-machine-assessment.md" in prompt, (
            f"Expected '.dev-machine-assessment.md' in compile_assessment prompt. "
            f"Prompt (first 400 chars): {prompt[:400]}"
        )

    # -----------------------------------------------------------------------
    # AC-19: compile_assessment prompt mentions preferred_label
    # -----------------------------------------------------------------------

    def test_compile_assessment_prompt_mentions_preferred_label(self):
        """compile_assessment prompt mentions preferred_label routing instruction."""
        graph = _graph()
        node = graph.nodes.get("compile_assessment")
        assert node is not None, "compile_assessment node not found"
        prompt = node.prompt or ""
        assert "preferred_label" in prompt, (
            f"Expected 'preferred_label' in compile_assessment prompt. "
            f"Prompt (first 400 chars): {prompt[:400]}"
        )

    # -----------------------------------------------------------------------
    # AC-20: verdict_gate has diamond shape
    # -----------------------------------------------------------------------

    def test_has_verdict_diamond(self):
        """verdict_gate node exists with shape=diamond."""
        graph = _graph()
        assert "verdict_gate" in graph.nodes, (
            f"Node 'verdict_gate' not found. Nodes: {list(graph.nodes.keys())}"
        )
        assert graph.nodes["verdict_gate"].shape == "diamond", (
            f"Expected verdict_gate shape=diamond, "
            f"got {graph.nodes['verdict_gate'].shape!r}"
        )

    # -----------------------------------------------------------------------
    # AC-21: Exactly 3 terminal (Msquare) nodes
    # -----------------------------------------------------------------------

    def test_has_three_terminal_nodes(self):
        """Exactly 3 Msquare terminal nodes (done_proceed, done_caution, done_not_ready)."""
        graph = _graph()
        terminal_nodes = [n for n in graph.nodes.values() if n.shape == "Msquare"]
        assert len(terminal_nodes) == 3, (
            f"Expected 3 Msquare terminal nodes, got {len(terminal_nodes)}: "
            f"{[n.id for n in terminal_nodes]}"
        )

    # -----------------------------------------------------------------------
    # AC-22: verdict_gate has 3 conditional outgoing edges
    # -----------------------------------------------------------------------

    def test_verdict_gate_has_three_conditional_edges(self):
        """verdict_gate has exactly 3 conditional outgoing edges."""
        graph = _graph()
        verdict_edges = [e for e in graph.edges if e.from_node == "verdict_gate"]
        assert len(verdict_edges) == 3, (
            f"Expected 3 edges from verdict_gate, got {len(verdict_edges)}: "
            f"{[(e.to_node, e.label) for e in verdict_edges]}"
        )
        for e in verdict_edges:
            assert e.condition, (
                f"Edge verdict_gate->{e.to_node} should have a condition, "
                f"got condition={e.condition!r}"
            )

    # -----------------------------------------------------------------------
    # AC-23: verdict conditions cover proceed, caution, not_ready
    # -----------------------------------------------------------------------

    def test_verdict_conditions_cover_all_verdicts(self):
        """verdict_gate edges cover proceed, caution, and not_ready conditions."""
        graph = _graph()
        verdict_edges = [e for e in graph.edges if e.from_node == "verdict_gate"]
        labels = {e.label for e in verdict_edges}
        assert "proceed" in labels, (
            f"Expected 'proceed' label in verdict_gate edges, got {labels}"
        )
        assert "caution" in labels, (
            f"Expected 'caution' label in verdict_gate edges, got {labels}"
        )
        assert "not_ready" in labels, (
            f"Expected 'not_ready' label in verdict_gate edges, got {labels}"
        )

    # -----------------------------------------------------------------------
    # AC-24: Sequential flow start -> gate1 -> ... -> verdict_gate
    # -----------------------------------------------------------------------

    def test_sequential_flow_start_to_verdict(self):
        """Sequential 8-node chain: start->gate1->gate2->gate3->gate4->gate5->compile_assessment->verdict_gate."""
        graph = _graph()
        # Build edge map: from_node -> list of to_nodes
        edge_map: dict[str, list[str]] = {}
        for e in graph.edges:
            edge_map.setdefault(e.from_node, []).append(e.to_node)

        # Walk the chain starting from 'start' (7 hops to reach verdict_gate)
        current = "start"
        chain = [current]
        for _ in range(7):
            next_nodes = edge_map.get(current, [])
            if not next_nodes:
                break
            # For sequential nodes (start, gate1-5, compile_assessment),
            # there is exactly one outgoing edge; we stop before verdict_gate's 3 edges
            current = next_nodes[0]
            chain.append(current)

        assert len(chain) == 8, (
            f"Expected 8-node chain (start->...->verdict_gate), "
            f"got {len(chain)}: {chain}"
        )
        assert chain[0] == "start", f"Chain should start with 'start', got {chain[0]}"
        assert chain[-1] == "verdict_gate", (
            f"Chain should end with 'verdict_gate', got {chain[-1]}"
        )
        # Verify all required nodes are in the chain
        for required in [
            "gate1",
            "gate2",
            "gate3",
            "gate4",
            "gate5",
            "compile_assessment",
        ]:
            assert required in chain, (
                f"'{required}' not found in sequential chain: {chain}"
            )
