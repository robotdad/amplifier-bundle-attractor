# E2E System Prompt Integration Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Add the production system prompt to the E2E test profile so tests run with the real 65-line Claude Code-aligned persona instead of the 5-word fallback "You are a coding agent."
**Architecture:** The E2E profile (`profiles/attractor-e2e-anthropic.yaml`) is missing a top-level `context:` section that the production profile has. This is a single YAML addition that references the existing `context/system-anthropic.md` file. The `session.context` key (module reference for `context-simple`) is unrelated to the top-level `context:` key (static file includes).
**Tech Stack:** Amplifier bundle YAML profile configuration

---

## Problem Statement

The E2E test profile `profiles/attractor-e2e-anthropic.yaml` has no top-level `context:` section. The production profile (`attractor-profile-anthropic.yaml`) includes:

```yaml
context:
  - path: context/system-anthropic.md
    role: system
```

Without this, E2E tests use the kernel's hardcoded fallback system prompt ("You are a coding agent."), which means tests never exercise the real persona, tool-use instructions, or behavioral guardrails defined in the 65-line system prompt.

## Root Cause

The E2E profile was created as a minimal test configuration and the `context:` section was never added. The `session.context` key (which IS present) is a module reference for `context-simple` and serves a completely different purpose from the top-level `context:` key.

## Dependencies

- `context/system-anthropic.md` must exist at the bundle root (it does, 65 lines)
- The `context-simple` module must support resolving `context:` paths (it does in production)
- No code changes required; YAML-only fix

---

### Task 1: Add Top-Level Context Section to E2E Profile

**Files:**
- Modify: `profiles/attractor-e2e-anthropic.yaml`

**Step 1: Add the `context:` section to the E2E profile**

Add a top-level `context:` key after the `bundle:` section and before `providers:`. Insert the following block at line 5 (after the `description` line, before the blank line preceding `providers:`):

```yaml
context:
  - path: context/system-anthropic.md
    role: system
```

The resulting file should have this structure (showing only the relevant top portion):

```yaml
bundle:
  name: attractor-e2e-anthropic
  version: 0.1.0
  description: E2E test profile - Anthropic agent (no pipeline)

context:
  - path: context/system-anthropic.md
    role: system

providers:
  - module: provider-anthropic
    source: git+https://github.com/microsoft/amplifier-module-provider-anthropic@main
    config:
      default_model: claude-sonnet-4-20250514
```

Everything below `providers:` remains unchanged.

**Step 2: Validate YAML syntax**

Run:
```bash
python3 -c "import yaml; yaml.safe_load(open('profiles/attractor-e2e-anthropic.yaml'))" && echo "YAML OK"
```
Expected: `YAML OK` with no errors.

**Step 3: Verify context file exists at referenced path**

Run:
```bash
test -f context/system-anthropic.md && wc -l context/system-anthropic.md
```
Expected: File exists, approximately 65 lines.

**Step 4: Verify the context section matches production profile format**

Run:
```bash
diff <(grep -A2 '^context:' attractor-profile-anthropic.yaml) <(grep -A2 '^context:' profiles/attractor-e2e-anthropic.yaml)
```
Expected: No diff (both context sections are identical).

**Step 5: Commit**

```
fix(e2e): add system prompt context to E2E test profile

The E2E profile was missing the top-level `context:` section,
causing tests to run with the kernel fallback prompt instead of
the 65-line production system prompt. This meant E2E tests never
exercised the real persona or behavioral guardrails.

Add the same `context/system-anthropic.md` reference used by the
production profile.
```

---

## PR Details

- **Branch:** `track1/1c1-e2e-system-prompt`
- **Title:** fix(e2e): add system prompt context to E2E test profile
- **Labels:** track-1, e2e, config
- **Priority:** H-13
- **Estimated time:** 2 minutes
