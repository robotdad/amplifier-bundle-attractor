# Standalone Repos Deprecation Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Deprecate the stale standalone repos (`amplifier-module-loop-agent` and `amplifier-module-loop-pipeline`) in favor of the authoritative bundle copies at `amplifier-bundle-attractor/modules/`, adding deprecation READMEs, archival notices, and preventing future drift.

**Architecture:** The bundle copy (`amplifier-bundle-attractor/modules/loop-agent/` and `modules/loop-pipeline/`) is the source of truth. The standalone repos at `amplifier-module-loop-agent/` and `amplifier-module-loop-pipeline/` have diverged significantly (e.g., 499-line vs 713-line `agent_session.py`, missing `subagent_tools.py`). Rather than attempt a risky sync, we deprecate the standalone repos with clear README notices pointing to the bundle, archive them on GitHub, and ensure all development continues in-bundle.

**Tech Stack:** Git, GitHub CLI, Markdown, YAML (pyproject.toml)

---

## Problem Statement

Two standalone module repos have diverged from their authoritative bundle copies:

| File | Standalone `loop-agent` | Bundle `modules/loop-agent` | Delta |
|------|------------------------|-----------------------------|-------|
| `agent_session.py` | 499 lines | 713 lines | +214 lines (streaming, provider resolution, 5-layer prompt) |
| `subagent_tools.py` | **missing entirely** | 366 lines | Completely absent |
| `__init__.py` | 109 lines | 130 lines | +21 lines |
| Test files | 13 test files | 21 test files | 8 new test files in bundle |

| File | Standalone `loop-pipeline` | Bundle `modules/loop-pipeline` | Delta |
|------|---------------------------|-------------------------------|-------|
| `backend.py` | 135 lines | 482 lines | +347 lines (fidelity backend) |
| `handlers/parallel.py` | 165 lines | 281 lines | +116 lines |
| `handlers/manager_loop.py` | 84 lines | 198 lines | +114 lines |
| `__init__.py` | 122 lines | 299 lines | +177 lines |
| Test files | 21 test files | 28 test files | 7 new test files in bundle |

## Root Cause

The standalone repos were created first as individual module repositories. When the bundle was created, the modules were copied in and subsequent development continued exclusively in the bundle. No sync mechanism was established, so the standalone repos became stale.

## Decision: Deprecate (Not Sync)

The adversarial review recommends deprecation because:
1. The bundle is already the source of truth for all active development.
2. Syncing would require reconciling diverged code paths (risky, labor-intensive).
3. The standalone repos serve no purpose if the bundle contains the authoritative copy.
4. Amplifier's module system resolves local `source: ./modules/loop-*` paths from the bundle.

## Dependencies

- GitHub admin access to archive repos (or org-level permissions).
- No downstream consumers should be importing from the standalone repos (verify in Task 1).

---

### Task 1: Verify No External Consumers of Standalone Repos

**Files:**
- None (investigation only)

**Step 1: Search for references to standalone repo URLs**

Search GitHub and the local codebase for any imports or references to the standalone repos:

```bash
# Check if any profile or bundle YAML references the standalone repos
cd /home/bkrabach/dev/attractor-next
grep -r "amplifier-module-loop-agent" amplifier-bundle-attractor/ --include="*.yaml" --include="*.yml" --include="*.toml" | grep -v ".venv"
grep -r "amplifier-module-loop-pipeline" amplifier-bundle-attractor/ --include="*.yaml" --include="*.yml" --include="*.toml" | grep -v ".venv"

# Check if any other repo in the workspace references them
grep -r "amplifier-module-loop-agent" . --include="*.yaml" --include="*.yml" --include="*.md" --include="*.toml" | grep -v ".venv" | grep -v "amplifier-module-loop-agent/"
grep -r "amplifier-module-loop-pipeline" . --include="*.yaml" --include="*.yml" --include="*.md" --include="*.toml" | grep -v ".venv" | grep -v "amplifier-module-loop-pipeline/"
```

Expected: No YAML profiles use `git+https://...amplifier-module-loop-agent` or `git+https://...amplifier-module-loop-pipeline` as a source. All references should be `source: ./modules/loop-agent` or `source: ./modules/loop-pipeline` (local paths).

**Step 2: Check GitHub for downstream forks/dependents**

```bash
# If gh CLI is available:
gh api repos/microsoft/amplifier-module-loop-agent --jq '.forks_count, .stargazers_count, .open_issues_count' 2>/dev/null || echo "Repo not found or no access"
gh api repos/microsoft/amplifier-module-loop-pipeline --jq '.forks_count, .stargazers_count, .open_issues_count' 2>/dev/null || echo "Repo not found or no access"
```

Expected: Zero or minimal forks/stars, confirming no significant external usage.

**Step 3: Commit**

No commit needed (investigation only). Document findings in PR description.

---

### Task 2: Add Deprecation README to Standalone `loop-agent` Repo

**Files:**
- Modify: `/home/bkrabach/dev/attractor-next/amplifier-module-loop-agent/README.md`

**Step 1: Read the current README**

```bash
cat /home/bkrabach/dev/attractor-next/amplifier-module-loop-agent/README.md
```

**Step 2: Replace README with deprecation notice**

Write the following content to `README.md`:

```markdown
# amplifier-module-loop-agent

> **DEPRECATED**: This standalone repository is no longer maintained.

## Where to Find the Active Code

The authoritative, actively-developed version of `loop-agent` lives inside the Attractor bundle:

```
amplifier-bundle-attractor/modules/loop-agent/
```

**Repository:** [microsoft/amplifier-bundle-attractor](https://github.com/microsoft/amplifier-bundle-attractor)
**Path:** `modules/loop-agent/`

## Why This Repo Is Deprecated

This standalone repo was the original home for `loop-agent`, but all active development moved to the bundle copy. The two copies diverged significantly:

- Bundle `agent_session.py`: 713 lines (streaming, provider resolution, 5-layer prompt)
- This repo's `agent_session.py`: 499 lines (missing features)
- Bundle has `subagent_tools.py` (366 lines) -- this repo does not
- Bundle has 21 test files -- this repo has 13

The bundle copy is the source of truth.

## For Bundle Users

If your Amplifier profile references `loop-agent`, use a local source path:

```yaml
session:
  orchestrator:
    module: loop-agent
    source: ./modules/loop-agent
```

Do NOT use `git+https://github.com/microsoft/amplifier-module-loop-agent` as a source.

## Archive Status

This repository has been archived. No further commits, issues, or PRs will be accepted.
```

**Step 3: Verify the file**

```bash
head -5 /home/bkrabach/dev/attractor-next/amplifier-module-loop-agent/README.md
```
Expected: First line is `# amplifier-module-loop-agent`, second line is blank, third starts with `> **DEPRECATED**`.

**Step 4: Commit (in the standalone repo)**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-module-loop-agent
git add README.md
git commit -m "docs: deprecate standalone repo in favor of bundle copy

This standalone repository has diverged significantly from the
authoritative copy in amplifier-bundle-attractor/modules/loop-agent/.
All active development continues in the bundle.

Key divergence:
- agent_session.py: 499 lines here vs 713 lines in bundle
- subagent_tools.py: missing here, 366 lines in bundle
- 13 test files here vs 21 in bundle

See README for migration guidance.

Part of: Track 1 Phase 1C - standalone repo deprecation (H-12)"
```

---

### Task 3: Add Deprecation README to Standalone `loop-pipeline` Repo

**Files:**
- Modify: `/home/bkrabach/dev/attractor-next/amplifier-module-loop-pipeline/README.md`

**Step 1: Read the current README**

```bash
cat /home/bkrabach/dev/attractor-next/amplifier-module-loop-pipeline/README.md
```

**Step 2: Replace README with deprecation notice**

Write the following content to `README.md`:

```markdown
# amplifier-module-loop-pipeline

> **DEPRECATED**: This standalone repository is no longer maintained.

## Where to Find the Active Code

The authoritative, actively-developed version of `loop-pipeline` lives inside the Attractor bundle:

```
amplifier-bundle-attractor/modules/loop-pipeline/
```

**Repository:** [microsoft/amplifier-bundle-attractor](https://github.com/microsoft/amplifier-bundle-attractor)
**Path:** `modules/loop-pipeline/`

## Why This Repo Is Deprecated

This standalone repo was the original home for `loop-pipeline`, but all active development moved to the bundle copy. The two copies diverged significantly:

- Bundle `backend.py`: 482 lines (fidelity backend) -- this repo has 135 lines
- Bundle `handlers/parallel.py`: 281 lines -- this repo has 165 lines
- Bundle `handlers/manager_loop.py`: 198 lines -- this repo has 84 lines
- Bundle has 28 test files -- this repo has 21

The bundle copy is the source of truth.

## For Bundle Users

If your Amplifier profile references `loop-pipeline`, use a local source path:

```yaml
session:
  orchestrator:
    module: loop-pipeline
    source: ./modules/loop-pipeline
```

Do NOT use `git+https://github.com/microsoft/amplifier-module-loop-pipeline` as a source.

## Archive Status

This repository has been archived. No further commits, issues, or PRs will be accepted.
```

**Step 3: Verify the file**

```bash
head -5 /home/bkrabach/dev/attractor-next/amplifier-module-loop-pipeline/README.md
```
Expected: First line is `# amplifier-module-loop-pipeline`, third line starts with `> **DEPRECATED**`.

**Step 4: Commit (in the standalone repo)**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-module-loop-pipeline
git add README.md
git commit -m "docs: deprecate standalone repo in favor of bundle copy

This standalone repository has diverged significantly from the
authoritative copy in amplifier-bundle-attractor/modules/loop-pipeline/.
All active development continues in the bundle.

Key divergence:
- backend.py: 135 lines here vs 482 lines in bundle
- handlers/parallel.py: 165 vs 281 lines
- handlers/manager_loop.py: 84 vs 198 lines
- 21 test files here vs 28 in bundle

See README for migration guidance.

Part of: Track 1 Phase 1C - standalone repo deprecation (H-12)"
```

---

### Task 4: Add Deprecation Warning to Standalone pyproject.toml Files

**Files:**
- Modify: `/home/bkrabach/dev/attractor-next/amplifier-module-loop-agent/pyproject.toml`
- Modify: `/home/bkrabach/dev/attractor-next/amplifier-module-loop-pipeline/pyproject.toml`

**Step 1: Read both pyproject.toml files**

```bash
cat /home/bkrabach/dev/attractor-next/amplifier-module-loop-agent/pyproject.toml
cat /home/bkrabach/dev/attractor-next/amplifier-module-loop-pipeline/pyproject.toml
```

**Step 2: Add deprecation classifiers and update descriptions**

For `amplifier-module-loop-agent/pyproject.toml`, update the `description` field and add a classifier:

```toml
description = "DEPRECATED - Use amplifier-bundle-attractor/modules/loop-agent/ instead"
classifiers = [
    "Development Status :: 7 - Inactive",
]
```

Do the same for `amplifier-module-loop-pipeline/pyproject.toml`:

```toml
description = "DEPRECATED - Use amplifier-bundle-attractor/modules/loop-pipeline/ instead"
classifiers = [
    "Development Status :: 7 - Inactive",
]
```

**Step 3: Verify TOML is still valid**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-module-loop-agent && python3 -c "import tomllib; tomllib.load(open('pyproject.toml','rb')); print('OK')"
cd /home/bkrabach/dev/attractor-next/amplifier-module-loop-pipeline && python3 -c "import tomllib; tomllib.load(open('pyproject.toml','rb')); print('OK')"
```
Expected: Both print "OK".

**Step 4: Commit (in each standalone repo)**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-module-loop-agent
git add pyproject.toml
git commit -m "chore: mark pyproject.toml as deprecated (Development Status :: 7 - Inactive)

Part of: Track 1 Phase 1C - standalone repo deprecation (H-12)"

cd /home/bkrabach/dev/attractor-next/amplifier-module-loop-pipeline
git add pyproject.toml
git commit -m "chore: mark pyproject.toml as deprecated (Development Status :: 7 - Inactive)

Part of: Track 1 Phase 1C - standalone repo deprecation (H-12)"
```

---

### Task 5: Archive Standalone Repos on GitHub

**Files:**
- None (GitHub API operations only)

**Step 1: Push deprecation commits to both repos**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-module-loop-agent
git push origin main

cd /home/bkrabach/dev/attractor-next/amplifier-module-loop-pipeline
git push origin main
```

**Step 2: Archive the repos via GitHub CLI**

```bash
gh repo archive microsoft/amplifier-module-loop-agent --yes 2>/dev/null || echo "Archive manually at: https://github.com/microsoft/amplifier-module-loop-agent/settings"
gh repo archive microsoft/amplifier-module-loop-pipeline --yes 2>/dev/null || echo "Archive manually at: https://github.com/microsoft/amplifier-module-loop-pipeline/settings"
```

If `gh repo archive` isn't available or requires admin permissions, archive manually:
1. Go to repo Settings > General > Danger Zone > Archive this repository.

**Step 3: Verify archive status**

```bash
gh repo view microsoft/amplifier-module-loop-agent --json isArchived --jq '.isArchived' 2>/dev/null || echo "Check manually"
gh repo view microsoft/amplifier-module-loop-pipeline --json isArchived --jq '.isArchived' 2>/dev/null || echo "Check manually"
```
Expected: Both return `true`.

**Step 4: No commit needed** (this is a GitHub operation, not a code change).

---

### Task 6: Add "Source of Truth" Notice to Bundle Module READMEs

**Files:**
- Create: `/home/bkrabach/dev/attractor-next/amplifier-bundle-attractor/modules/loop-agent/README.md`
- Create: `/home/bkrabach/dev/attractor-next/amplifier-bundle-attractor/modules/loop-pipeline/README.md`

**Step 1: Create the loop-agent bundle README**

```markdown
# loop-agent (Amplifier Module)

This is the **authoritative source** for the `loop-agent` module.

## Location

This module lives at `amplifier-bundle-attractor/modules/loop-agent/` and is the only maintained copy.

## Formerly

Previously maintained as a standalone repo at `amplifier-module-loop-agent` (now archived/deprecated).

## Usage

Reference this module in your Amplifier profile with a local source path:

```yaml
session:
  orchestrator:
    module: loop-agent
    source: ./modules/loop-agent
```

## Development

All changes to `loop-agent` should be made here in the bundle. Run tests with:

```bash
cd modules/loop-agent
uv run pytest tests/ -v
```
```

**Step 2: Create the loop-pipeline bundle README**

Same structure, adjusted for `loop-pipeline`:

```markdown
# loop-pipeline (Amplifier Module)

This is the **authoritative source** for the `loop-pipeline` module.

## Location

This module lives at `amplifier-bundle-attractor/modules/loop-pipeline/` and is the only maintained copy.

## Formerly

Previously maintained as a standalone repo at `amplifier-module-loop-pipeline` (now archived/deprecated).

## Usage

Reference this module in your Amplifier profile with a local source path:

```yaml
session:
  orchestrator:
    module: loop-pipeline
    source: ./modules/loop-pipeline
    config:
      dot_file: ./path/to/your/workflow.dot
```

## Development

All changes to `loop-pipeline` should be made here in the bundle. Run tests with:

```bash
cd modules/loop-pipeline
uv run pytest tests/ -v
```
```

**Step 3: Verify files exist**

```bash
test -f /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor/modules/loop-agent/README.md && echo "OK"
test -f /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor/modules/loop-pipeline/README.md && echo "OK"
```
Expected: Both print "OK".

**Step 4: Commit (in the bundle repo)**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor
git add modules/loop-agent/README.md modules/loop-pipeline/README.md
git commit -m "docs: add source-of-truth READMEs to bundle module copies

Mark the bundle copies of loop-agent and loop-pipeline as the
authoritative source, noting that the former standalone repos
have been deprecated and archived.

Part of: Track 1 Phase 1C - standalone repo deprecation (H-12)"
```

---

### Task 7: Verify No Profile References Standalone Repos

**Files:**
- Potentially modify: any `profiles/*.yaml` that references standalone git URLs

**Step 1: Search all profiles for standalone git references**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-bundle-attractor
grep -rn "amplifier-module-loop-agent" profiles/ || echo "No references found (good)"
grep -rn "amplifier-module-loop-pipeline" profiles/ || echo "No references found (good)"
```

Expected: No matches. All profiles should use `source: ./modules/loop-agent` or `source: ./modules/loop-pipeline`.

**Step 2: If references are found, update them**

Replace any `source: git+https://github.com/microsoft/amplifier-module-loop-agent@...` with `source: ./modules/loop-agent`.

Replace any `source: git+https://github.com/microsoft/amplifier-module-loop-pipeline@...` with `source: ./modules/loop-pipeline`.

**Step 3: Verify profiles still parse**

```bash
for f in profiles/*.yaml; do
    python3 -c "import yaml; yaml.safe_load(open('$f')); print('OK: $f')"
done
```
Expected: All print "OK".

**Step 4: Commit (only if changes were made)**

```
fix(profiles): replace standalone repo git URLs with local module paths

Update any remaining profile references from git+https://...amplifier-module-loop-*
to local source paths (./modules/loop-*), since standalone repos are deprecated.

Part of: Track 1 Phase 1C - standalone repo deprecation (H-12)
```

---

## PR Details

Three PRs total (one per repo):

### PR 1: `amplifier-module-loop-agent` (standalone repo)

**Title:** docs: deprecate standalone repo in favor of bundle copy (H-12)

**Description:**
This standalone repository has diverged significantly from the authoritative copy in `amplifier-bundle-attractor/modules/loop-agent/`. All active development continues in the bundle.

Key divergence:
- `agent_session.py`: 499 lines here vs 713 lines in bundle
- `subagent_tools.py`: missing here, 366 lines in bundle
- 13 test files here vs 21 in bundle

Changes:
- Replace README with deprecation notice and migration guidance
- Mark pyproject.toml as `Development Status :: 7 - Inactive`
- Recommend archiving this repo after merge

**Labels:** `deprecation`, `track-1`, `phase-1c`
**Branch:** `deprecate-standalone`

### PR 2: `amplifier-module-loop-pipeline` (standalone repo)

**Title:** docs: deprecate standalone repo in favor of bundle copy (H-12)

**Description:**
Same as PR 1, adjusted for loop-pipeline. Key divergence:
- `backend.py`: 135 lines here vs 482 lines in bundle
- `handlers/parallel.py`: 165 vs 281 lines
- 21 test files here vs 28 in bundle

**Labels:** `deprecation`, `track-1`, `phase-1c`
**Branch:** `deprecate-standalone`

### PR 3: `amplifier-bundle-attractor` (bundle repo)

**Title:** docs: add source-of-truth READMEs for bundled loop modules (H-12)

**Description:**
Adds README files to `modules/loop-agent/` and `modules/loop-pipeline/` marking them as the authoritative source, now that the standalone repos have been deprecated. Also verifies no profiles reference the old standalone git URLs.

**Labels:** `documentation`, `track-1`, `phase-1c`
**Branch:** `track1/1c3-standalone-repo-deprecation`
