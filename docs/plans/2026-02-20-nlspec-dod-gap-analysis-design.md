---
# NLSpec/DoD Gap Analysis for Attractor (attractor-next) Design

## Goal
Produce a fresh, evidence-driven NLSpec/DoD gap analysis for attractor-next across the Attractor, Coding-Agent-Loop, and Unified-LLM specs, captured as a single canonical report.

## Background
We need a defensible, up-to-date baseline of compliance against the latest StrongDM NLSpec/DoD. The authoritative spec source is the strongdm/attractor submodule (updated to origin/main, HEAD 2f892efd63ee7c11f038856b90aae57c067b77c2). This baseline will drive subsequent execution planning, but no implementation work begins until the baseline exists.

## Approach
Use a full, evidence-driven per-DoD checklist. For every DoD item in the three specs, map explicit evidence from code, tests, or docs, or mark the item as Partial/Missing with a concise gap note. Ambiguous requirements will include a recorded interpretation. The output is a single report file at amplifier-bundle-attractor/docs/reports/2026-02-20-nlspec-dod-gap-analysis.md.

## Architecture
This phase is a structured analysis pipeline that consumes the updated specs, inventories evidence across attractor-next repositories, maps requirements to evidence, and emits a single canonical report. It is designed to be traceable, auditable, and ready to inform the next planning phase.

## Components
### Spec Source of Truth
- Canonical spec source: strongdm/attractor (latest origin/main).
- Extract DoD items from:
  - attractor-spec.md
  - coding-agent-loop-spec.md
  - unified-llm-spec.md
- Each DoD item becomes a checklist row with an ID, verbatim requirement, and spec reference.

### Evidence Inventory
- Evidence sources limited to attractor-next repos:
  - amplifier-bundle-attractor
  - unified-llm-client
  - amplifier-module-loop-agent
  - amplifier-module-loop-pipeline
- Evidence recorded as file paths, line ranges, and brief rationale for code/tests/docs.

### Requirement-to-Evidence Mapping
- For each DoD item, assign status:
  - Met (clear evidence exists)
  - Partial (some evidence, incomplete)
  - Missing (no evidence)
- Partial/Missing items include concise gap notes describing what is absent.

### Report Output
- Single canonical report:
  - amplifier-bundle-attractor/docs/reports/2026-02-20-nlspec-dod-gap-analysis.md
- Organized by spec section with a full per-DoD checklist, evidence pointers, and gap notes.

## Data Flow
1) Spec ingestion: extract all DoD items from the three spec files in strongdm/attractor.
2) Evidence inventory: build a catalog of relevant code/tests/docs in the defined repos.
3) Requirement-to-evidence mapping: map each DoD item to evidence and assign Met/Partial/Missing with notes.
4) Report output: emit the full checklist report grouped by spec with evidence pointers and gaps.

## Error Handling
- Ambiguous requirements: document the chosen interpretation explicitly in the report.
- Design-only evidence without tests: mark as Partial.
- Evidence found outside the defined repos: cite it but flag as out-of-scope for this workspace.

## Testing Strategy
This phase does not add tests. The report will identify missing or partial items and include the intended validation method (unit/integration/doc update) to drive future test work. The report is complete only when every DoD item has a status and evidence pointer.

## Scope Boundaries
- Focus exclusively on attractor-next as the canonical working version; attractor-start remains a historical pointer only.
- No implementation work begins until the baseline report is complete and validated.
- Evidence is limited to the defined repos; broader ecosystem evidence is out-of-scope unless explicitly flagged.

## Open Questions
None.
---
