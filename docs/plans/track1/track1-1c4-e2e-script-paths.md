# E2E Script Path Resolution Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Replace the hardcoded absolute path in `tests/e2e/run_e2e.sh` with dynamic resolution from the script's location so the E2E runner works in any environment.
**Architecture:** The script currently hardcodes `BUNDLE_ROOT="/workspace/microsoft/amplifier-bundle-attractor"` which only works in one specific container. Replace with standard shell idiom `$(cd "$(dirname "$0")" && pwd)` to derive the bundle root relative to the script's own location (`tests/e2e/` is two levels below bundle root).
**Tech Stack:** Bash, POSIX shell path resolution

---

## Problem Statement

Line 4 of `tests/e2e/run_e2e.sh` contains:

```bash
BUNDLE_ROOT="/workspace/microsoft/amplifier-bundle-attractor"
```

This is a hardcoded container/workspace-specific path. The script fails in any other environment (local dev, CI, different container mounts) because the path doesn't exist.

## Root Cause

The script was written for a specific workspace container layout and the path was never parameterized. Since the script lives at `tests/e2e/run_e2e.sh`, the bundle root is always exactly two directory levels up from the script location.

## Dependencies

- No dependencies on other tasks
- The fix is self-contained within one file
- Must preserve all other script behavior (the rest of the script uses `$BUNDLE_ROOT` and should work unchanged)

---

### Task 1: Replace Hardcoded Path with Relative Resolution

**Files:**
- Modify: `tests/e2e/run_e2e.sh`

**Step 1: Replace the hardcoded `BUNDLE_ROOT` assignment**

Find line 4:
```bash
BUNDLE_ROOT="/workspace/microsoft/amplifier-bundle-attractor"
```

Replace with:
```bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUNDLE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
```

This resolves the script's own directory first, then navigates two levels up to reach the bundle root. Both use `cd && pwd` to produce clean absolute paths with no `..` segments.

**Step 2: Verify the script parses correctly**

Run:
```bash
bash -n tests/e2e/run_e2e.sh && echo "Syntax OK"
```
Expected: `Syntax OK` with no parse errors.

**Step 3: Verify path resolution produces the correct bundle root**

Run:
```bash
cd tests/e2e && SCRIPT_DIR="$(cd "$(dirname "./run_e2e.sh")" && pwd)" && echo "$(cd "$SCRIPT_DIR/../.." && pwd)"
```
Expected: Output is the absolute path to `amplifier-bundle-attractor/` (the bundle root directory).

**Step 4: Verify no other hardcoded paths remain in the script**

Run:
```bash
grep -n '/workspace/' tests/e2e/run_e2e.sh
```
Expected: No matches (zero output).

**Step 5: Commit**

```
fix(e2e): use relative path resolution in run_e2e.sh

Replace hardcoded BUNDLE_ROOT="/path/to/..." with
dynamic resolution from the script's own location. The script
lives at tests/e2e/, so the bundle root is two levels up.

This makes the E2E runner portable across local dev, CI, and
container environments.
```

---

## PR Details

- **Branch:** `track1/1c4-e2e-script-paths`
- **Title:** fix(e2e): use relative path resolution in run_e2e.sh
- **Labels:** track-1, e2e, portability
- **Priority:** LOW
- **Estimated time:** 2 minutes
