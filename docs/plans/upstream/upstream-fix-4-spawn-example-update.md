# Upstream Fix 4: Update Spawn Capability Reference Example

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Update the reference `spawn_capability` in `examples/07_full_workflow.py` to accept the full set of kwargs that `tool-delegate` sends, so developers using the example as a template get working spawn behavior.
**Architecture:** Add the 4 missing kwargs to the example's function signature and forward them to `PreparedBundle.spawn()`. Also add `**kwargs` as a catch-all for future additions.
**Tech Stack:** Python, amplifier-foundation examples

---

## Problem Statement

The reference `spawn_capability` in `examples/07_full_workflow.py` accepts only 7 parameters:

```python
async def spawn_capability(
    agent_name: str,
    instruction: str,
    parent_session: Any,
    agent_configs: dict[str, dict[str, Any]],
    sub_session_id: str | None = None,
    orchestrator_config: dict[str, Any] | None = None,
    parent_messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
```

But `tool-delegate` sends **10 kwargs** at lines 853-864:

```python
spawn_coro = spawn_fn(
    agent_name=agent_name,
    instruction=effective_instruction,
    parent_session=parent_session,
    agent_configs=agents,
    sub_session_id=sub_session_id,
    tool_inheritance=tool_inheritance,        # NOT in example
    hook_inheritance=hook_inheritance,         # NOT in example
    orchestrator_config=orchestrator_config,
    provider_preferences=provider_preferences, # NOT in example
    self_delegation_depth=child_self_delegation_depth, # NOT in example
)
```

Anyone using the example as a template will get a `TypeError: unexpected keyword argument` when tool-delegate tries to spawn a child session.

## Root Cause

**File:** `amplifier-foundation/examples/07_full_workflow.py`
**Lines:** 225-274

The example was written before tool-delegate added `tool_inheritance`, `hook_inheritance`, `provider_preferences`, and `self_delegation_depth` support. The production CLI version (`session_spawner.py:273-287`) accepts all 13 kwargs — the example diverged.

## The Fix

Update the example to accept and forward all kwargs that tool-delegate sends, plus a `**kwargs` catch-all for future-proofing.

---

### Task 1: Update the example's spawn_capability signature

**Files:**
- Modify: `amplifier-foundation/examples/07_full_workflow.py:225-274`

**Step 1: Write a test that validates the example compiles with new signature**

```python
# This is a documentation/example file, so the "test" is verifying
# the signature matches what tool-delegate sends.
# tests/test_example_spawn_signature.py

def test_spawn_capability_accepts_delegate_kwargs():
    """The example spawn_capability should accept all kwargs tool-delegate sends."""
    import inspect
    # Import or parse the example to get the spawn_capability signature
    # Verify these parameters are accepted:
    required_params = [
        "agent_name", "instruction", "parent_session", "agent_configs",
    ]
    optional_params = [
        "sub_session_id", "orchestrator_config", "parent_messages",
        "tool_inheritance", "hook_inheritance",
        "provider_preferences", "self_delegation_depth",
    ]
    # Assert all are in the signature (or **kwargs is present)
```

**Step 2: Apply the fix**

```python
# BEFORE (lines 225-232):
async def spawn_capability(
    agent_name: str,
    instruction: str,
    parent_session: Any,
    agent_configs: dict[str, dict[str, Any]],
    sub_session_id: str | None = None,
    orchestrator_config: dict[str, Any] | None = None,
    parent_messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:

# AFTER:
async def spawn_capability(
    agent_name: str,
    instruction: str,
    parent_session: Any,
    agent_configs: dict[str, dict[str, Any]],
    sub_session_id: str | None = None,
    orchestrator_config: dict[str, Any] | None = None,
    parent_messages: list[dict[str, Any]] | None = None,
    # Additional kwargs from tool-delegate:
    tool_inheritance: dict[str, list[str]] | None = None,
    hook_inheritance: dict[str, list[str]] | None = None,
    provider_preferences: list | None = None,
    self_delegation_depth: int = 0,
    **kwargs: Any,  # Future-proof: accept any new kwargs without crashing
) -> dict[str, Any]:
```

**Step 3: Update the spawn() call inside the function**

Find the line (approximately 267) where `prepared.spawn()` is called. Forward the new kwargs:

```python
# BEFORE (approximately line 267):
result = await prepared.spawn(
    child_bundle,
    instruction,
    compose=True,
    parent_session=parent_session,
    session_id=sub_session_id,
    orchestrator_config=orchestrator_config,
    parent_messages=parent_messages,
)

# AFTER:
result = await prepared.spawn(
    child_bundle,
    instruction,
    compose=True,
    parent_session=parent_session,
    session_id=sub_session_id,
    orchestrator_config=orchestrator_config,
    parent_messages=parent_messages,
    provider_preferences=provider_preferences,
)
# Note: tool_inheritance, hook_inheritance, and self_delegation_depth
# are app-layer concerns not handled by PreparedBundle.spawn().
# They would need custom handling here if the app wants to support them.
# For now, they are accepted but not forwarded (matching CLI behavior).
```

**Step 4: Add a comment explaining the contract**

```python
# Add a docstring note:
"""Spawn capability registered on the session coordinator.

This is the reference implementation for the session.spawn capability.
The production CLI version (session_spawner.py) has additional handling
for tool_inheritance, hook_inheritance, and self_delegation_depth.

Args:
    agent_name: Name of the agent to spawn (e.g., 'foundation:explorer')
    instruction: Task instruction for the child agent
    parent_session: The parent AmplifierSession
    agent_configs: Agent configuration dict from the coordinator
    sub_session_id: Optional session ID for resumption
    orchestrator_config: Optional orchestrator config overrides
    parent_messages: Optional parent context messages to inherit
    tool_inheritance: Tool inheritance config (app-layer, not used here)
    hook_inheritance: Hook inheritance config (app-layer, not used here)
    provider_preferences: Provider/model preference list for child
    self_delegation_depth: Current delegation depth for depth limiting
    **kwargs: Accept future additions without breaking
"""
```

**Step 5: Commit**

```bash
cd amplifier-foundation
git checkout -b fix/spawn-example-signature
git add examples/07_full_workflow.py
git commit -m "fix: update spawn_capability example to accept tool-delegate kwargs

The example spawn_capability was missing 4 kwargs that tool-delegate
sends on every spawn call: tool_inheritance, hook_inheritance,
provider_preferences, and self_delegation_depth. Added all 4 plus a
**kwargs catch-all for future-proofing.

provider_preferences is forwarded to PreparedBundle.spawn(). The others
are app-layer concerns documented but not forwarded (matching the
note that production CLI has fuller handling)."
```

---

## Test Plan

| Test Case | What It Validates |
|---|---|
| Example compiles without syntax errors | Basic correctness |
| Signature accepts all 10 kwargs from tool-delegate | No TypeError at runtime |
| `**kwargs` catches any future additions | Forward compatibility |
| Existing calls with only 7 kwargs still work | Backward compatibility |

## Backward Compatibility

- **Zero risk.** All new parameters have defaults. Existing code that calls the example's spawn_capability with the old 7-param set continues to work identically.
- **`**kwargs` catch-all** ensures that even if tool-delegate adds more params in the future, the example won't crash.

## PR Details

| Detail | Value |
|---|---|
| **Target repo** | `microsoft/amplifier-foundation` |
| **Branch** | `fix/spawn-example-signature` |
| **Commit message** | `fix: update spawn_capability example to accept tool-delegate kwargs` |
| **Scope** | ~20 lines changed in 1 example file |

## Dependencies

- **Blocks:** Developer guidance accuracy — anyone using the example as a template
- **Blocked by:** Nothing — can start immediately
- **Related:** Fix 5 (delegate spawn kwargs reconciliation) addresses the broader contract question
- **Can combine with Fix 3** (spawn enrichment) into a single PR if preferred, since both modify amplifier-foundation
- **Priority:** P2 — medium impact, trivial effort
