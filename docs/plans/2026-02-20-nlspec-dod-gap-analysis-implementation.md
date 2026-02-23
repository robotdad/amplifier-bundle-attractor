# NLSpec/DoD Gap Analysis for Attractor (attractor-next) Implementation Plan

**Date:** 2026-02-20
**Audience:** Junior engineer with zero context (friendly and explicit)
**Design doc:** `docs/plans/2026-02-20-nlspec-dod-gap-analysis-design.md`

---

## Goal
Produce a **fresh, evidence-driven, per-DoD checklist** gap analysis report for the three NLSpec documents. The report must show **status + evidence/gap notes for every DoD item**, following the existing report style.

## Required Ordering (Do not reorder)
1) **Spec ingestion**
2) **Evidence inventory**
3) **Requirement-to-evidence mapping**
4) **Report output**
5) **Validation/completeness check**

## Scope Boundaries (Hard Rules)
- **No implementation changes**. This is **analysis-only**.
- **Baseline analysis only** (no remediation plans or code fixes).
- **Evidence sources limited to:**
  - `amplifier-bundle-attractor`
  - `unified-llm-client`
  - `amplifier-module-loop-agent`
  - `amplifier-module-loop-pipeline`
- **Design-only evidence without tests = `PARTIAL`.**
- Evidence outside the allowed repos must be **flagged as out-of-scope**.
- **Every DoD item must include:**
  - Status (PASS / PARTIAL / FAIL / OUT-OF-SCOPE)
  - Evidence or gap note
- Ambiguous requirements must include an **Interpretation** note.
- Include **test evidence** when available.

## Codebase Patterns to Follow
- Follow the existing markdown style in:
  - `docs/reports/spec-gap-analysis-v2.md`
  - `docs/reports/adversarial-spec-review.md`
- Use **file-path + line-range** evidence citations (example: `modules/loop-agent/agent.py:120-178`).
- Use a **DoD checklist table** with columns:
  - `| DoD Item | Status | Evidence | Notes |` (add **Interpretation** column only if needed).

## Key Files and Directories
### Specs (source of truth)
- `specs/attractor-spec.md`
- `specs/coding-agent-loop-spec.md`
- `specs/unified-llm-spec.md`
- Canonical versions (for cross-checking wording):
  - `specs/canonical/attractor-spec-canonical.md`
  - `specs/canonical/coding-agent-loop-spec-canonical.md`
  - `specs/canonical/unified-llm-spec-canonical.md`

### Output Report (new)
- `docs/reports/2026-02-20-nlspec-dod-gap-analysis.md`

### Evidence Repos (allowed)
- `amplifier-bundle-attractor`
- `../unified-llm-client`
- `modules/loop-agent`
- `modules/loop-pipeline`

### Prior Reports (reference for formatting)
- `docs/reports/spec-gap-analysis-v2.md`
- `docs/reports/adversarial-spec-review.md`

---

## Report Template Snippets (Use These)

### Report Header (match spec-gap-analysis-v2 style)
```
# NLSpec DoD Gap Analysis — Attractor (attractor-next)

**Date:** 2026-02-20
**Scope:** Baseline DoD gap analysis across Attractor, Coding Agent Loop, and Unified LLM specs. Evidence limited to amplifier-bundle-attractor, unified-llm-client, amplifier-module-loop-agent, amplifier-module-loop-pipeline.
**Specs analyzed:**
- Attractor Spec (NLSpec)
- Coding Agent Loop Spec (NLSpec)
- Unified LLM Spec (NLSpec)

---
```

### DoD Checklist Table
```
| DoD Item | Status | Evidence | Notes |
|---|---|---|---|
| <requirement text> | PASS | `modules/loop-agent/agent.py:120-178`, `tests/test_agent.py:40-88` | Verified runtime behavior; tests cover success + failure path. |
| <requirement text> | PARTIAL | `docs/designs/loop-agent.md:10-42` | Design-only evidence; no tests. |
| <requirement text> | FAIL | — | No implementation or tests found in allowed repos. |
```

### Optional Interpretation Column (only when needed)
```
| DoD Item | Status | Evidence | Notes | Interpretation |
|---|---|---|---|---|
| <ambiguous requirement> | PARTIAL | `modules/loop-pipeline/pipeline.py:210-240` | Meets part of requirement. | Interpreted “durable” as “retries on transient failure.” |
```

---

# Implementation Plan (TDD-style Tasks)

> “TDD” here means each task has: **Goal → Steps → Commands → Expected Output → Test/Validation**. The “test” step is the **validation/completeness check** for analysis tasks.

## Task 1 — Spec Ingestion
**Goal:** Build a clean checklist of all DoD items from the three specs.

**Steps:**
1) Open each spec file and extract every DoD requirement (exact wording).
2) Keep DoD items grouped by spec and section headings.
3) Store the extracted items in a working outline (temporary scratch notes are fine; do not commit scratch files).

**Commands:**
```bash
ls specs
sed -n '1,200p' specs/attractor-spec.md
sed -n '1,200p' specs/coding-agent-loop-spec.md
sed -n '1,200p' specs/unified-llm-spec.md
```

**Expected Output:**
- You can list **every DoD item** for each spec.
- Each item is associated with a spec section heading.

**Test / Validation (Completeness Check):**
- Confirm **no DoD headings or checklists were skipped**.
- Cross-check with canonical spec versions for wording mismatches.

---

## Task 2 — Evidence Inventory
**Goal:** Collect all candidate evidence in allowed repos (code, docs, tests), including line ranges.

**Steps:**
1) Scan allowed repos for likely evidence locations (modules, docs, tests).
2) Note key files and test locations that map to DoD items.
3) Capture line ranges for each evidence reference.

**Commands:**
```bash
ls modules
ls tests
ls ../unified-llm-client/tests
ls modules/loop-agent/tests
ls modules/loop-pipeline/tests
```

**Expected Output:**
- A list of **candidate evidence files** per repo.
- Line-range references prepared for citations (format: `path:line-line`).

**Test / Validation (Completeness Check):**
- Confirm every DoD item has **at least one candidate evidence location** or a deliberate gap note.

---

## Task 3 — Requirement-to-Evidence Mapping
**Goal:** Map every DoD item to evidence (or mark missing/out-of-scope), using the required status rules.

**Steps:**
1) For each DoD item, find matching evidence in allowed repos.
2) Assign status:
   - **PASS** = implemented + test evidence present
   - **PARTIAL** = design-only or incomplete implementation, or implementation without tests
   - **FAIL** = no evidence in allowed repos
   - **OUT-OF-SCOPE** = evidence exists outside allowed repos
3) If a requirement is ambiguous, add **Interpretation** column with the chosen interpretation.
4) Capture exact line ranges for evidence citations.

**Commands:**
```bash
# Example: open files to capture exact line ranges
sed -n '1,200p' modules/loop-agent/agent.py
sed -n '1,200p' ../unified-llm-client/tests/dod/test_*.py
```

**Expected Output:**
- Every DoD item has: **Status + Evidence + Notes** (and Interpretation if needed).

**Test / Validation (Completeness Check):**
- Spot-check that **every DoD item appears exactly once** in the mapping.
- Verify that **design-only evidence is marked PARTIAL**.

---

## Task 4 — Report Output
**Goal:** Produce the final report file with the required header and DoD tables.

**Steps:**
1) Create the report file at the required path.
2) Add the header (Date / Scope / Specs analyzed).
3) Add a section per spec with a DoD checklist table.
4) Ensure the table column format matches the existing reports.
5) Ensure evidence citations use `path:line-range` style.

**Commands:**
```bash
cat <<'EOF' > docs/reports/2026-02-20-nlspec-dod-gap-analysis.md
# NLSpec DoD Gap Analysis — Attractor (attractor-next)

**Date:** 2026-02-20
**Scope:** Baseline DoD gap analysis across Attractor, Coding Agent Loop, and Unified LLM specs. Evidence limited to amplifier-bundle-attractor, unified-llm-client, amplifier-module-loop-agent, amplifier-module-loop-pipeline.
**Specs analyzed:**
- Attractor Spec (NLSpec)
- Coding Agent Loop Spec (NLSpec)
- Unified LLM Spec (NLSpec)

---

## Attractor Spec — DoD Checklist

| DoD Item | Status | Evidence | Notes |
|---|---|---|---|
| <item> | <PASS/PARTIAL/FAIL/OUT-OF-SCOPE> | <path:line-range> | <note> |

## Coding Agent Loop Spec — DoD Checklist

| DoD Item | Status | Evidence | Notes |
|---|---|---|---|
| <item> | <PASS/PARTIAL/FAIL/OUT-OF-SCOPE> | <path:line-range> | <note> |

## Unified LLM Spec — DoD Checklist

| DoD Item | Status | Evidence | Notes |
|---|---|---|---|
| <item> | <PASS/PARTIAL/FAIL/OUT-OF-SCOPE> | <path:line-range> | <note> |
EOF
```

**Expected Output:**
- Report file created with required header and per-spec tables.

**Test / Validation (Completeness Check):**
- Ensure **no empty sections** and **every DoD item is represented**.
- Confirm evidence citations are present for PASS/PARTIAL items.

---

## Task 5 — Validation / Completeness Check
**Goal:** Final pass to confirm the report meets all requirements and is consistent.

**Steps:**
1) Verify the report matches the required header and table format.
2) Confirm every DoD item from all specs is present.
3) Confirm status rules were applied consistently.
4) Confirm ambiguous items have Interpretation notes.

**Commands:**
```bash
sed -n '1,200p' docs/reports/2026-02-20-nlspec-dod-gap-analysis.md
```

**Expected Output:**
- Report is complete, consistent, and ready for review.

**Test / Validation (Completeness Check):**
- Checklist:
  - [ ] Every DoD item has status + evidence/gap note
  - [ ] Design-only evidence = PARTIAL
  - [ ] Evidence outside allowed repos flagged as OUT-OF-SCOPE
  - [ ] Ambiguous requirements include Interpretation
  - [ ] Evidence citations are `path:line-range`

---

## Commit Steps
> Only after the report is complete and validated.

**Commands:**
```bash
git status --short

git add docs/reports/2026-02-20-nlspec-dod-gap-analysis.md

git commit -m "docs: add NLSpec DoD gap analysis report"
```

**Expected Output:**
- Clean git status with the report staged and committed.

---

## Success Criteria
- A complete, per-DoD checklist report exists at:
  - `docs/reports/2026-02-20-nlspec-dod-gap-analysis.md`
- Every DoD item includes **Status + Evidence/Notes**.
- Evidence is limited to the allowed repos, with out-of-scope flagged.
- Formatting matches the existing report style.
