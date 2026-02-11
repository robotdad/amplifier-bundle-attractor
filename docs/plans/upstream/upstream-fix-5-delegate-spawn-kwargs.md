# Upstream Fix 5: Reconcile `tool-delegate` Spawn Kwargs with `PreparedBundle.spawn()`

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Formally reconcile the kwargs that `tool-delegate` sends to the spawn function with the parameters that `PreparedBundle.spawn()` accepts, so the contract is explicit and documented rather than relying on silent kwarg dropping.
**Architecture:** Update `PreparedBundle.spawn()` to accept `provider_preferences` (already useful) and document the app-layer contract for `tool_inheritance`, `hook_inheritance`, and `self_delegation_depth`. Update tool-delegate's docstring to clarify which kwargs are spawn-level vs app-level.
**Tech Stack:** Python, amplifier-foundation bundle.py, tool-delegate module

---

## Problem Statement

`tool-delegate` sends 10 kwargs to the spawn function at lines 853-864:

```python
spawn_coro = spawn_fn(
    agent_name=agent_name,
    instruction=effective_instruction,
    parent_session=parent_session,
    agent_configs=agents,
    sub_session_id=sub_session_id,
    tool_inheritance=tool_inheritance,           # spawn() doesn't accept
    hook_inheritance=hook_inheritance,            # spawn() doesn't accept
    orchestrator_config=orchestrator_config,
    provider_preferences=provider_preferences,   # spawn() DOES accept
    self_delegation_depth=child_self_delegation_depth,  # spawn() doesn't accept
)
```

`PreparedBundle.spawn()` accepts 7 parameters (lines 1130-1142):

```python
async def spawn(
    self,
    child_bundle: Bundle,
    instruction: str,
    *,
    compose: bool = True,
    parent_session: Any = None,
    session_id: str | None = None,
    orchestrator_config: dict[str, Any] | None = None,
    parent_messages: list[dict[str, Any]] | None = None,
    session_cwd: Path | None = None,
    provider_preferences: list[ProviderPreference] | None = None,
) -> dict[str, Any]:
```

**The mismatch:**

| Kwarg | tool-delegate sends? | spawn() accepts? | CLI handles? |
|---|---|---|---|
| `agent_name` | Yes (used to resolve bundle) | No (bundle already resolved) | Yes |
| `instruction` | Yes | Yes | Yes |
| `parent_session` | Yes | Yes | Yes |
| `agent_configs` | Yes (used to resolve bundle) | No (bundle already resolved) | Yes |
| `sub_session_id` | Yes | Yes (as `session_id`) | Yes |
| `orchestrator_config` | Yes | Yes | Yes |
| `parent_messages` | Yes | Yes | Yes |
| `provider_preferences` | Yes | Yes | Yes |
| `tool_inheritance` | Yes | **No** | Yes (custom handling) |
| `hook_inheritance` | Yes | **No** | Yes (custom handling) |
| `self_delegation_depth` | Yes | **No** | Yes (custom handling) |

The contract works today because:
1. The CLI's `spawn_sub_session()` (the real spawn capability, lines 273-287 in `session_spawner.py`) accepts all 13 kwargs
2. `tool-delegate` calls the spawn capability, not `PreparedBundle.spawn()` directly
3. The spawn capability resolves `agent_name` → Bundle, then calls `prepared.spawn()` with only the params it accepts

But if someone writes a new app using `PreparedBundle.spawn()` directly (or uses the example from Fix 4), the 3 missing kwargs would need to be handled at the app layer.

## Root Cause

**Two separate layers with overlapping but different responsibilities:**

1. **`PreparedBundle.spawn()`** — The library-level spawn. Takes a pre-resolved `Bundle` and creates a child session. Doesn't know about agent names, tool inheritance, or depth limiting.

2. **The spawn capability** (app-layer) — Registered by the app (CLI, API server, etc.). Takes raw kwargs from tool-delegate, resolves agent names → Bundles, handles inheritance/depth, then delegates to `PreparedBundle.spawn()`.

This is actually the correct architecture — the library handles session creation, the app handles policy. But it's not documented.

## The Fix

A three-part approach:

1. **Document the contract** — Add docstrings to both `tool-delegate` and `PreparedBundle.spawn()` explaining the two-layer architecture
2. **Add `self_delegation_depth` to spawn()** — This one IS useful at the library level (it should be forwarded to the child session's config)
3. **Keep tool/hook_inheritance at app layer** — These are policy decisions about what the child inherits, which varies by app

---

### Task 1: Document the spawn contract in tool-delegate

**Files:**
- Modify: `amplifier-foundation/modules/tool-delegate/amplifier_module_tool_delegate/__init__.py:845-870`

**Step 1: Add contract documentation**

Find the section where `spawn_fn` is called (around line 853). Add a docstring comment explaining the contract:

```python
# The spawn function is an app-layer capability registered on the coordinator.
# It receives ALL kwargs below, but not all are handled by PreparedBundle.spawn().
#
# Kwargs handled by PreparedBundle.spawn():
#   - instruction, parent_session, session_id (as sub_session_id),
#     orchestrator_config, parent_messages, provider_preferences
#
# Kwargs handled by the app-layer spawn capability:
#   - agent_name: Resolved to a Bundle by the app
#   - agent_configs: Used by the app to find agent configuration
#   - tool_inheritance: App-layer policy for tool filtering
#   - hook_inheritance: App-layer policy for hook filtering
#   - self_delegation_depth: Forwarded to child session config
#
# See session_spawner.py in amplifier-app-cli for the reference
# app-layer implementation that handles all kwargs.
spawn_coro = spawn_fn(
    agent_name=agent_name,
    instruction=effective_instruction,
    ...
)
```

**Step 2: Commit**

```bash
cd amplifier-foundation
git checkout -b docs/spawn-contract-clarity
git add modules/tool-delegate/amplifier_module_tool_delegate/__init__.py
git commit -m "docs: clarify spawn kwargs contract between tool-delegate and app layer"
```

---

### Task 2: Add `self_delegation_depth` forwarding to `PreparedBundle.spawn()`

**Files:**
- Modify: `amplifier-foundation/amplifier_foundation/bundle.py:1130-1142`
- Test: `amplifier-foundation/tests/test_spawn_depth.py`

**Step 1: Write the failing test**

```python
# tests/test_spawn_depth.py
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_spawn_forwards_self_delegation_depth_to_child_config():
    """spawn() should forward self_delegation_depth to the child session's
    orchestrator config so depth-limiting tools can read it."""
    # ... setup PreparedBundle ...
    # result = await prepared.spawn(
    #     child_bundle, "instruction",
    #     self_delegation_depth=3,
    # )
    # Assert the child session's orchestrator config has self_delegation_depth=3


@pytest.mark.asyncio
async def test_spawn_default_depth_is_zero():
    """When self_delegation_depth is not provided, default to 0."""
    # Assert child session config has self_delegation_depth=0 or omitted
```

**Step 2: Run test to verify it fails**

Run: `cd amplifier-foundation && uv run pytest tests/test_spawn_depth.py -v`
Expected: FAIL — spawn() doesn't accept self_delegation_depth

**Step 3: Update spawn() signature**

```python
# BEFORE (line 1130-1142):
async def spawn(
    self,
    child_bundle: Bundle,
    instruction: str,
    *,
    compose: bool = True,
    parent_session: Any = None,
    session_id: str | None = None,
    orchestrator_config: dict[str, Any] | None = None,
    parent_messages: list[dict[str, Any]] | None = None,
    session_cwd: Path | None = None,
    provider_preferences: list[ProviderPreference] | None = None,
) -> dict[str, Any]:

# AFTER:
async def spawn(
    self,
    child_bundle: Bundle,
    instruction: str,
    *,
    compose: bool = True,
    parent_session: Any = None,
    session_id: str | None = None,
    orchestrator_config: dict[str, Any] | None = None,
    parent_messages: list[dict[str, Any]] | None = None,
    session_cwd: Path | None = None,
    provider_preferences: list[ProviderPreference] | None = None,
    self_delegation_depth: int = 0,
) -> dict[str, Any]:
```

**Step 4: Forward depth to child orchestrator config**

In the method body, around lines 1217-1224 where `orchestrator_config` is merged:

```python
# AFTER orchestrator_config merge (add):
if self_delegation_depth > 0:
    if "config" not in child_mount_plan.get("orchestrator", {}):
        child_mount_plan.setdefault("orchestrator", {})["config"] = {}
    child_mount_plan["orchestrator"]["config"]["self_delegation_depth"] = self_delegation_depth
```

**Step 5: Run tests**

Run: `cd amplifier-foundation && uv run pytest tests/test_spawn_depth.py -v`
Expected: PASS

**Step 6: Commit**

```bash
cd amplifier-foundation
git add amplifier_foundation/bundle.py tests/test_spawn_depth.py
git commit -m "feat: add self_delegation_depth parameter to spawn()

PreparedBundle.spawn() now accepts self_delegation_depth and forwards it
to the child session's orchestrator config. This enables depth-limiting
tools to enforce maximum recursion depth across spawned sessions."
```

---

### Task 3: Add docstring to PreparedBundle.spawn() clarifying the two-layer contract

**Files:**
- Modify: `amplifier-foundation/amplifier_foundation/bundle.py:1143-1160` (docstring area)

**Step 1: Update the docstring**

```python
async def spawn(self, child_bundle, instruction, ...) -> dict[str, Any]:
    """Spawn a child agent session from a bundle.

    This is the library-level spawn method. It creates a child AmplifierSession,
    mounts modules from the bundle, executes the instruction, and returns the result.

    The app layer (CLI, API server) typically wraps this in a "spawn capability"
    function that handles additional concerns:
    - Resolving agent_name → Bundle (this method takes a pre-resolved Bundle)
    - tool_inheritance / hook_inheritance (filtering which parent tools/hooks
      the child inherits — this is app-layer policy)
    - agent_configs (used by the app to look up agent configuration)

    See amplifier-app-cli/session_spawner.py for the reference production
    implementation of a full spawn capability.

    Args:
        child_bundle: The Bundle to spawn
        instruction: Task instruction for the child agent
        compose: Whether to compose with parent bundle (default True)
        parent_session: The parent AmplifierSession for lineage tracking
        session_id: Session ID for resumption
        orchestrator_config: Override orchestrator config
        parent_messages: Parent context messages to inherit
        session_cwd: Working directory for the child session
        provider_preferences: Provider/model preference list
        self_delegation_depth: Current delegation depth for depth limiting

    Returns:
        dict with keys: output (str), session_id (str),
        and (after Fix 3) status (str), turn_count (int|None), metadata (dict)
    """
```

**Step 2: Commit**

```bash
cd amplifier-foundation
git add amplifier_foundation/bundle.py
git commit -m "docs: clarify spawn() two-layer contract in docstring"
```

---

## Test Plan

| Test Case | What It Validates |
|---|---|
| `self_delegation_depth=3` forwarded to child config | New parameter works |
| Default depth is 0 | Backward compatible |
| Existing spawn calls without new param | All continue to work |
| tool-delegate kwargs docstring accurate | Documentation clarity |

## Backward Compatibility

- **Adding `self_delegation_depth` to spawn():** New keyword-only parameter with default `0`. All existing callers that don't pass it are unaffected.
- **Docstring additions:** Zero code change, pure documentation.
- **tool-delegate comment:** Zero behavioral change.

## PR Details

| Detail | Value |
|---|---|
| **Target repo** | `microsoft/amplifier-foundation` |
| **Branch** | `docs/spawn-contract-clarity` |
| **Commit messages** | 3 commits: docs on tool-delegate, feat on spawn depth, docs on spawn docstring |
| **Scope** | ~30 lines across 2 files + tests |

## Dependencies

- **Blocks:** Attractor Track 2 (sessions all the way down) — needs clear spawn contract
- **Blocked by:** Nothing — can start immediately
- **Can combine with Fix 3 and Fix 4** into a single amplifier-foundation PR since all three modify the same repo
- **Priority:** P2 — medium impact, moderate effort
