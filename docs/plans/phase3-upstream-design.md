# Phase 3: Upstream amplifier-core Enhancements — Design Document

> **Status:** Design Complete, Ready for Implementation
> **Date:** 2026-02-14
> **Scope:** amplifier-core error hierarchy expansion + amplifier-module-retry
> **Baseline:** amplifier-core as of commit 69c70a1 (main branch)

---

## Table of Contents

1. [Current State of amplifier-core Contracts](#1-current-state-of-amplifier-core-contracts)
2. [Expert Consensus Summary](#2-expert-consensus-summary)
3. [Items to Do Now (Detailed Design)](#3-items-to-do-now-detailed-design)
   - [3.1 Retry Module](#31-retry-module-amplifier-module-retry)
   - [3.3 Error Hierarchy Expansion](#33-error-hierarchy-expansion)
4. [Items to Defer (Captured for Future)](#4-items-to-defer-captured-for-future)
   - [3.2 Streaming Provider Protocol](#42-streaming-provider-protocol)
   - [3.4 provider_options on ChatRequest](#44-provider_options-on-chatrequest)
   - [3.6 StreamEvent Taxonomy](#46-streamevent-taxonomy)
5. [Backward Compatibility Checklist](#5-backward-compatibility-checklist)
6. [Implementation Order](#6-implementation-order)

---

## 1. Current State of amplifier-core Contracts

This section captures the **exact** current state of every contract surface in amplifier-core that Phase 3 touches. This is the baseline we cannot break.

### 1.1 Provider Protocol (`interfaces.py:62-125`)

The `Provider` protocol defines 5 methods. All providers must structurally conform:

```python
@runtime_checkable
class Provider(Protocol):

    @property
    def name(self) -> str:
        """Provider name."""
        ...

    def get_info(self) -> ProviderInfo:
        """Get provider metadata.
        Returns: ProviderInfo with id, display_name, credential_env_vars, capabilities, defaults
        """
        ...

    async def list_models(self) -> list[ModelInfo]:
        """List available models for this provider.
        Returns: List of ModelInfo for available models
        """
        ...

    async def complete(self, request: ChatRequest, **kwargs) -> ChatResponse:
        """Generate completion from ChatRequest.
        Args: request (ChatRequest), **kwargs (provider-specific options)
        Returns: ChatResponse with content blocks, tool calls, usage
        """
        ...

    def parse_tool_calls(self, response: ChatResponse) -> list[ToolCall]:
        """Parse tool calls from ChatResponse.
        Returns: List of tool calls to execute
        """
        ...
```

**Key observations:**
- `complete()` accepts `**kwargs` as the escape hatch for provider-specific options
- No `stream()` method exists on the protocol today
- `parse_tool_calls()` is a separate method (not part of the response)
- The protocol uses `@runtime_checkable` for structural subtyping

### 1.2 Error Hierarchy (`llm_errors.py`, 147 lines)

Current hierarchy is **7 concrete types** rooted at `LLMError`:

```
LLMError (base)
    provider: str | None
    status_code: int | None
    retryable: bool = False
    ├── RateLimitError          (429, retryable=True by default)
    │       retry_after: float | None
    ├── AuthenticationError     (401/403, retryable=False by default)
    ├── ContextLengthError      (413, retryable=False by default)
    ├── ContentFilterError      (safety filter, retryable=False by default)
    ├── InvalidRequestError     (400/422, retryable=False by default)
    ├── ProviderUnavailableError(5xx, retryable=True by default)
    └── LLMTimeoutError         (timeout, retryable=True by default)
```

**Verbatim `LLMError.__init__` signature:**
```python
def __init__(
    self,
    message: str,
    *,
    provider: str | None = None,
    status_code: int | None = None,
    retryable: bool = False,
) -> None:
```

**`RateLimitError.__init__` signature (adds `retry_after`):**
```python
def __init__(
    self,
    message: str,
    *,
    retry_after: float | None = None,
    provider: str | None = None,
    status_code: int | None = None,
    retryable: bool = True,  # NOTE: default True, unlike base
) -> None:
```

**`ProviderUnavailableError.__init__` signature (overrides `retryable` default):**
```python
def __init__(
    self,
    message: str,
    *,
    provider: str | None = None,
    status_code: int | None = None,
    retryable: bool = True,  # NOTE: default True
) -> None:
```

**`LLMTimeoutError.__init__` signature (overrides `retryable` default):**
```python
def __init__(
    self,
    message: str,
    *,
    provider: str | None = None,
    status_code: int | None = None,
    retryable: bool = True,  # NOTE: default True
) -> None:
```

**`AuthenticationError`, `ContextLengthError`, `ContentFilterError`, `InvalidRequestError`:**
All are `pass` bodies — they inherit `LLMError.__init__` directly with `retryable=False` as default.

### 1.3 ChatRequest (`message_models.py:176-212`)

14 explicit fields plus `extra="allow"`:

```python
class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    messages: list[Message]                              # required
    tools: list[ToolSpec] | None = None
    response_format: ResponseFormat | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    conversation_id: str | None = None
    stream: bool | None = False
    metadata: dict[str, Any] | None = None
    model: str | None = None                             # per-request override
    tool_choice: str | dict[str, Any] | None = None
    stop: list[str] | None = None
    reasoning_effort: str | None = None
    timeout: float | None = None                         # per-request timeout
```

**Note:** `extra="allow"` means any additional fields passed at construction are preserved. This is the current escape hatch for provider-specific options — callers can do `ChatRequest(..., anthropic_beta=["..."])` and it gets through.

### 1.4 ChatResponse (`message_models.py:257-271`)

6 fields plus `extra="allow"`:

```python
class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    content: list[ContentBlockUnion]
    tool_calls: list[ToolCall] | None = None
    usage: Usage | None = None
    degradation: Degradation | None = None
    finish_reason: str | None = None
    metadata: dict[str, Any] | None = None
```

### 1.5 Usage (`message_models.py:225-244`)

6 fields plus `extra="allow"`:

```python
class Usage(BaseModel):
    model_config = ConfigDict(extra="allow")

    input_tokens: int                                    # required
    output_tokens: int                                   # required
    total_tokens: int                                    # required
    reasoning_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
```

### 1.6 Events (`events.py`, 127 lines)

38 canonical event constants organized by category:

| Category | Events |
|----------|--------|
| Session lifecycle | `SESSION_START`, `SESSION_START_DEBUG`, `SESSION_START_RAW`, `SESSION_END`, `SESSION_FORK`, `SESSION_FORK_DEBUG`, `SESSION_FORK_RAW`, `SESSION_RESUME`, `SESSION_RESUME_DEBUG`, `SESSION_RESUME_RAW` |
| Prompt lifecycle | `PROMPT_SUBMIT`, `PROMPT_COMPLETE` |
| Planning | `PLAN_START`, `PLAN_END` |
| Provider calls | `PROVIDER_REQUEST`, `PROVIDER_RESPONSE`, `PROVIDER_ERROR` |
| LLM calls | `LLM_REQUEST`, `LLM_REQUEST_DEBUG`, `LLM_REQUEST_RAW`, `LLM_RESPONSE`, `LLM_RESPONSE_DEBUG`, `LLM_RESPONSE_RAW` |
| Content streaming | `CONTENT_BLOCK_START`, `CONTENT_BLOCK_DELTA`, `CONTENT_BLOCK_END`, `THINKING_DELTA`, `THINKING_FINAL` |
| Tool invocations | `TOOL_PRE`, `TOOL_POST`, `TOOL_ERROR` |
| Context management | `CONTEXT_PRE_COMPACT`, `CONTEXT_POST_COMPACT`, `CONTEXT_COMPACTION`, `CONTEXT_INCLUDE` |
| Orchestrator | `ORCHESTRATOR_COMPLETE`, `EXECUTION_START`, `EXECUTION_END` |
| User notifications | `USER_NOTIFICATION` |
| Artifacts | `ARTIFACT_WRITE`, `ARTIFACT_READ` |
| Policy/Approvals | `POLICY_VIOLATION`, `APPROVAL_REQUIRED`, `APPROVAL_GRANTED`, `APPROVAL_DENIED` |
| Cancellation | `CANCEL_REQUESTED`, `CANCEL_COMPLETED` |

**Key streaming events already present:** `CONTENT_BLOCK_START`, `CONTENT_BLOCK_DELTA`, `CONTENT_BLOCK_END`, `THINKING_DELTA`, `THINKING_FINAL`.

### 1.7 Hook System (`hooks.py`, 289 lines)

The `HookRegistry` supports:
- **Registration:** `register(event, handler, priority, name) -> unregister_fn`
- **Emission:** `emit(event, data) -> HookResult`
- **Collection:** `emit_and_collect(event, data, timeout) -> list[Any]`

`HookResult` actions: `"continue"`, `"deny"`, `"modify"`, `"inject_context"`, `"ask_user"`.

**Critical observation for retry design:** The hook system fires events AFTER they happen (e.g., `PROVIDER_ERROR` fires after the error). A hook cannot intercept and retry a provider call — it can only observe, modify event data, deny, inject context, or ask the user. **The hook system is NOT the right integration point for retry logic.**

### 1.8 HookResult (`models.py:88-283`)

The `HookResult` model has fields for:
- Core action (`action`, `data`, `reason`)
- Context injection (`context_injection`, `context_injection_role`, `ephemeral`)
- Approval gates (`approval_prompt`, `approval_options`, `approval_timeout`, `approval_default`)
- Output control (`suppress_output`, `user_message`, `user_message_level`, `user_message_source`)
- Injection placement (`append_to_last_tool_result`)

---

## 2. Expert Consensus Summary

For each Phase 3 item, this table captures where the core expert (kernel internals) and amplifier expert (ecosystem patterns) agreed and disagreed, and the resolution.

| Item | Spec Requires | Core Expert | Amplifier Expert | Resolution |
|------|---------------|-------------|------------------|------------|
| **3.1 Retry** | RetryPolicy with exponential backoff, jitter, retry_after respect | Retry is POLICY, not mechanism. Core provides `LLMError.retryable` and `RateLimitError.retry_after` as mechanism. A retry MODULE implements policy. Should NOT be a hook — hooks fire after the fact. Provider wrapper (decorator) pattern is correct. | Agrees: module, not kernel. Agrees: decorator pattern wrapping `Provider.complete()`. Amplifier modules are the right layer for policy. | **Do now.** Build `amplifier-module-retry` as a provider wrapper (decorator pattern). NOT a hook module. Core already has all needed mechanism. |
| **3.2 Streaming** | Separate `stream()` method on ProviderAdapter | Don't touch Provider protocol now. Add `StreamingProvider` as separate protocol later. | Agrees: defer. Current `ChatRequest.stream=True` + capability negotiation works. Events infrastructure exists already. | **Defer.** No provider implements `stream()` today. Big design decision. Doesn't block Attractor. |
| **3.3 Errors** | 16-type hierarchy (SDKError → ProviderError → 9 subtypes, plus 5 non-provider errors) | Add 9 new subclasses. Subclass existing types where overlap exists (e.g., `NetworkError(ProviderUnavailableError)`). All backward compatible. | Current 7 are sufficient. Attributes cover the rest. Adding too many types increases maintenance burden. | **Do now (selective).** Add only the subclasses that provide genuine catch-clause value and are purely additive. Skip attribute-only variations. |
| **3.4 provider_options** | Explicit `provider_options: dict` field on Request | Add it — makes it discoverable and documented. | `extra="allow"` is sufficient today. Adding a typed field creates the illusion of structure for what is inherently unstructured. | **Defer.** `extra="allow"` works. If convention proves insufficient, add later. |
| **3.5 Structured output** | `generate_object()` with schema validation | Not relevant to core contracts. Layer 4 concern. | Agrees: out of scope for core. | **Out of scope.** |
| **3.6 StreamEvent** | Formal `StreamEvent` model with typed taxonomy | Add vocabulary to core now for consistency. | Prove at edges first. Don't formalize until streaming protocol is designed. | **Defer.** `events.py` already has streaming event constants. Formal model can wait. |

### Key Expert Agreement Points

1. **Retry is policy, core provides mechanism.** Both experts agree the kernel's job is done: `LLMError.retryable` and `RateLimitError.retry_after` give retry modules everything they need.

2. **Provider protocol is stable.** Neither expert recommends changing the 5-method Provider protocol now. Streaming deserves its own design phase.

3. **Error hierarchy expansion is safe if purely additive.** New subclasses of existing types don't break `except LLMError:` or `except RateLimitError:` — they're just more specific catches.

4. **Hook system is not for retry.** Both experts agree: hooks fire after events, they can't intercept and retry a provider call. The decorator/wrapper pattern is the correct approach.

### Key Expert Disagreement Points

1. **How many error types?** Core expert wants comprehensive coverage (9 new types). Amplifier expert wants minimal additions. Resolution: add the ones with genuine catch-clause value (8 new types), skip `NoObjectGeneratedError` (too specific to structured output which isn't designed yet).

2. **provider_options field.** Core expert wants it explicit. Amplifier expert says `extra="allow"` is enough. Resolution: defer — the current mechanism works and we can add the field later without breaking anything.

---

## 3. Items to Do Now (Detailed Design)

### 3.1 Retry Module (`amplifier-module-retry`)

#### 3.1.1 Design Rationale

**Why NOT a hook module:** The Amplifier hook system (`HookRegistry`) fires events AFTER actions occur. `PROVIDER_ERROR` fires after the error has already been raised. A hook handler receives `(event, data) -> HookResult` and can return actions like `"continue"`, `"deny"`, `"modify"`, `"inject_context"`, or `"ask_user"`. None of these actions tell the orchestrator "retry the provider call." The hook would need to somehow signal the orchestrator to re-invoke `provider.complete()`, which is not part of the hook contract.

**Why a provider wrapper (decorator pattern):** The retry module wraps any `Provider` instance, intercepting `complete()` calls and implementing retry logic transparently. This is:
- **Simple:** One class, wraps `complete()`, delegates everything else
- **Transparent:** Orchestrators and hooks see a normal Provider
- **Composable:** Can wrap any provider without modification
- **Protocol-compliant:** The wrapper itself satisfies the `Provider` protocol

#### 3.1.2 Module Structure

```
amplifier-module-retry/
├── pyproject.toml
├── amplifier_module_retry/
│   ├── __init__.py          # Public API: RetryProvider, RetryConfig
│   ├── retry_provider.py    # Core implementation
│   └── config.py            # RetryConfig model
└── tests/
    ├── test_retry_provider.py
    └── test_backoff.py
```

#### 3.1.3 RetryConfig

```python
from pydantic import BaseModel, Field


class RetryConfig(BaseModel):
    """Configuration for retry behavior.

    Follows the spec's RetryPolicy pattern:
    - Exponential backoff with jitter
    - Respects RateLimitError.retry_after
    - Only retries errors where LLMError.retryable is True
    """

    max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum retry attempts (0 = no retries). Total calls = max_retries + 1.",
    )
    base_delay: float = Field(
        default=1.0,
        gt=0,
        description="Initial delay in seconds before first retry.",
    )
    max_delay: float = Field(
        default=60.0,
        gt=0,
        description="Maximum delay between retries in seconds.",
    )
    backoff_multiplier: float = Field(
        default=2.0,
        ge=1.0,
        description="Exponential backoff factor. Delay = base_delay * (multiplier ^ attempt).",
    )
    jitter: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Jitter factor (0.0-1.0). Applied as +/- jitter * delay.",
    )
    retry_on: list[str] | None = Field(
        default=None,
        description=(
            "Error class names to retry on (e.g., ['RateLimitError', 'ProviderUnavailableError']). "
            "If None, retries all errors where retryable=True."
        ),
    )
```

#### 3.1.4 RetryProvider Implementation

```python
import asyncio
import logging
import random
from typing import Any

from amplifier_core.interfaces import Provider
from amplifier_core.llm_errors import LLMError, RateLimitError
from amplifier_core.message_models import ChatRequest, ChatResponse, ToolCall
from amplifier_core.models import ModelInfo, ProviderInfo

from .config import RetryConfig

logger = logging.getLogger(__name__)


class RetryProvider:
    """Wraps a Provider with retry/backoff logic.

    Transparent decorator: satisfies the Provider protocol by delegating
    all methods to the inner provider. Only `complete()` adds retry behavior.

    Usage:
        inner = AnthropicProvider(...)
        provider = RetryProvider(inner, RetryConfig(max_retries=3))
        # Use provider anywhere you'd use the inner provider
        response = await provider.complete(request)
    """

    def __init__(self, inner: Provider, config: RetryConfig | None = None) -> None:
        self._inner = inner
        self._config = config or RetryConfig()

    # --- Protocol delegation (pass-through) ---

    @property
    def name(self) -> str:
        return self._inner.name

    def get_info(self) -> ProviderInfo:
        return self._inner.get_info()

    async def list_models(self) -> list[ModelInfo]:
        return await self._inner.list_models()

    def parse_tool_calls(self, response: ChatResponse) -> list[ToolCall]:
        return self._inner.parse_tool_calls(response)

    # --- Retry-enhanced complete() ---

    async def complete(self, request: ChatRequest, **kwargs: Any) -> ChatResponse:
        """Call inner provider's complete() with retry logic.

        Retry behavior:
        1. Call inner.complete()
        2. On LLMError where retryable=True (and error type matches retry_on filter):
           a. If retry budget exhausted, re-raise
           b. Calculate delay: min(base_delay * multiplier^attempt, max_delay) +/- jitter
           c. If error is RateLimitError with retry_after, use max(calculated, retry_after)
           d. If retry_after > max_delay, re-raise (don't silently wait minutes)
           e. Sleep, then retry
        3. On non-retryable error or non-LLMError, re-raise immediately
        """
        last_error: LLMError | None = None

        for attempt in range(self._config.max_retries + 1):
            try:
                return await self._inner.complete(request, **kwargs)
            except LLMError as e:
                last_error = e

                # Check if error is retryable
                if not e.retryable:
                    logger.debug(
                        "Non-retryable error from %s (attempt %d): %s",
                        self._inner.name, attempt + 1, e,
                    )
                    raise

                # Check retry_on filter
                if not self._should_retry_error(e):
                    logger.debug(
                        "Error type %s not in retry_on filter, re-raising",
                        type(e).__name__,
                    )
                    raise

                # Check if we have retries left
                if attempt >= self._config.max_retries:
                    logger.warning(
                        "Max retries (%d) exhausted for %s: %s",
                        self._config.max_retries, self._inner.name, e,
                    )
                    raise

                # Calculate delay
                delay = self._calculate_delay(attempt, e)

                # If RateLimitError.retry_after exceeds max_delay, don't wait
                if isinstance(e, RateLimitError) and e.retry_after is not None:
                    if e.retry_after > self._config.max_delay:
                        logger.warning(
                            "retry_after (%.1fs) exceeds max_delay (%.1fs), re-raising",
                            e.retry_after, self._config.max_delay,
                        )
                        raise

                logger.info(
                    "Retrying %s (attempt %d/%d) after %.2fs: %s",
                    self._inner.name, attempt + 1, self._config.max_retries,
                    delay, e,
                )
                await asyncio.sleep(delay)

        # Should not reach here, but satisfy type checker
        assert last_error is not None  # noqa: S101
        raise last_error

    def _should_retry_error(self, error: LLMError) -> bool:
        """Check if this error type should be retried based on retry_on filter."""
        if self._config.retry_on is None:
            return True  # Retry all retryable errors
        return type(error).__name__ in self._config.retry_on

    def _calculate_delay(self, attempt: int, error: LLMError) -> float:
        """Calculate delay for the given retry attempt.

        Formula: min(base_delay * multiplier^attempt, max_delay) +/- jitter
        If RateLimitError with retry_after, use max(calculated, retry_after).
        """
        # Exponential backoff
        delay = self._config.base_delay * (
            self._config.backoff_multiplier ** attempt
        )
        delay = min(delay, self._config.max_delay)

        # Apply jitter: delay * (1 +/- jitter)
        if self._config.jitter > 0:
            jitter_range = delay * self._config.jitter
            delay += random.uniform(-jitter_range, jitter_range)  # noqa: S311
            delay = max(0.0, delay)  # Never negative

        # Respect retry_after from RateLimitError
        if isinstance(error, RateLimitError) and error.retry_after is not None:
            delay = max(delay, error.retry_after)

        return delay
```

#### 3.1.5 Integration Pattern

The retry module integrates at **provider mount time**, not at orchestrator call time:

```python
# In bundle/profile configuration:
from amplifier_module_retry import RetryProvider, RetryConfig

# Wrap any provider
inner_provider = AnthropicProvider(api_key="...")
provider = RetryProvider(inner_provider, RetryConfig(max_retries=3))

# Mount as normal — orchestrators see a standard Provider
session.mount_provider("anthropic", provider)
```

For Attractor bundle integration:
```python
# In attractor bundle setup, wrap the codergen backend's provider
retry_config = RetryConfig(
    max_retries=3,
    base_delay=1.0,
    max_delay=60.0,
    jitter=0.2,
)
provider = RetryProvider(raw_provider, retry_config)
```

#### 3.1.6 What This Does NOT Do

- **Does NOT modify amplifier-core.** Zero core changes needed.
- **Does NOT use the hook system.** Hooks can't retry provider calls.
- **Does NOT retry non-LLM errors.** Only catches `LLMError` subclasses.
- **Does NOT retry mid-stream.** If streaming is eventually added, mid-stream retry is a separate problem.
- **Does NOT implement circuit breaker.** That's a separate module concern.

#### 3.1.7 Test Plan

| Test Case | Description |
|-----------|-------------|
| `test_no_error` | Call succeeds first time, no retry behavior |
| `test_retryable_error_succeeds` | First call raises retryable error, second succeeds |
| `test_max_retries_exhausted` | All attempts fail, final error re-raised |
| `test_non_retryable_error` | Non-retryable error raises immediately, no retry |
| `test_non_llm_error_passthrough` | Non-LLMError exceptions pass through unchanged |
| `test_rate_limit_retry_after` | RateLimitError.retry_after is respected |
| `test_retry_after_exceeds_max` | retry_after > max_delay causes immediate re-raise |
| `test_exponential_backoff` | Delays increase exponentially |
| `test_jitter_applied` | Delays vary within jitter range |
| `test_retry_on_filter` | Only specified error types are retried |
| `test_delegation_passthrough` | `name`, `get_info`, `list_models`, `parse_tool_calls` delegate correctly |
| `test_protocol_compliance` | `isinstance(RetryProvider(...), Provider)` is True via structural subtyping |

---

### 3.3 Error Hierarchy Expansion

#### 3.3.1 Design Rationale

The canonical specs define a 16-type error hierarchy. amplifier-core currently has 7 types. The gap:

| Spec Type | Current Core Equivalent | Action |
|-----------|------------------------|--------|
| `SDKError` | `LLMError` | Already exists (different name, same role) |
| `ProviderError` | (implicit — all LLMError subtypes are provider errors) | Skip — would add a layer with no value |
| `AuthenticationError` | `AuthenticationError` | **Exists** |
| `AccessDeniedError` | (covered by AuthenticationError) | **Add as subclass of AuthenticationError** |
| `NotFoundError` | — | **Add** (new leaf) |
| `InvalidRequestError` | `InvalidRequestError` | **Exists** |
| `RateLimitError` | `RateLimitError` | **Exists** |
| `QuotaExceededError` | (covered by RateLimitError or separate) | **Add as subclass of RateLimitError** |
| `ServerError` | `ProviderUnavailableError` | **Exists** (different name) |
| `ContentFilterError` | `ContentFilterError` | **Exists** |
| `ContextLengthError` | `ContextLengthError` | **Exists** |
| `RequestTimeoutError` | `LLMTimeoutError` | **Exists** (different name) |
| `AbortError` | — | **Add** (new leaf) |
| `NetworkError` | (covered by ProviderUnavailableError) | **Add as subclass of ProviderUnavailableError** |
| `StreamError` | — | **Add** (new leaf) |
| `InvalidToolCallError` | — | **Add** (new leaf) |
| `ConfigurationError` | — | **Add** (new leaf) |
| `NoObjectGeneratedError` | — | **Skip** (structured output not designed yet) |

#### 3.3.2 New Error Classes

All new classes are **purely additive**. Existing `except LLMError:` catches still work because every new class inherits from `LLMError` (directly or via an existing subclass).

```python
# --- New leaf classes (genuine new error categories) ---

class NotFoundError(LLMError):
    """Model or endpoint not found (HTTP 404).

    Non-retryable: the resource doesn't exist, retrying won't help.

    Examples:
        - Model ID doesn't exist: "gpt-99" is not a valid model
        - Endpoint not found: wrong base_url configuration
        - Deployment not found: Azure OpenAI deployment deleted
    """
    pass


class StreamError(LLMError):
    """Connection dropped or corrupted during streaming.

    Retryable by default: stream interruptions are often transient
    (network blip, load balancer timeout, server-side reset).

    Distinct from ProviderUnavailableError because the initial connection
    succeeded — the failure happened mid-stream.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        status_code: int | None = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(
            message,
            provider=provider,
            status_code=status_code,
            retryable=retryable,
        )


class AbortError(LLMError):
    """Caller-initiated cancellation of an LLM request.

    Non-retryable by default: the caller explicitly requested cancellation.
    This is not a failure — it's cooperative cancellation via CancellationToken
    or abort signal.
    """
    pass


class InvalidToolCallError(LLMError):
    """Model produced a malformed tool call.

    Non-retryable by default: the model generated invalid JSON arguments
    or referenced a tool that doesn't exist. Retrying the same prompt will
    likely produce the same malformed output.

    Attributes:
        tool_name: Name of the tool the model tried to call.
        raw_arguments: The raw argument string before parsing failed.
    """

    def __init__(
        self,
        message: str,
        *,
        tool_name: str | None = None,
        raw_arguments: str | None = None,
        provider: str | None = None,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            provider=provider,
            status_code=status_code,
            retryable=retryable,
        )
        self.tool_name = tool_name
        self.raw_arguments = raw_arguments


class ConfigurationError(LLMError):
    """Misconfigured provider or SDK setup.

    Non-retryable: configuration problems require human intervention.

    Examples:
        - Missing API key
        - Invalid base_url
        - Unsupported model/provider combination
        - Missing required provider options
    """
    pass


# --- Subclasses of existing types (preserves catch clauses) ---

class AccessDeniedError(AuthenticationError):
    """Permission denied (HTTP 403).

    Distinct from AuthenticationError (401) — credentials are valid but
    lack sufficient permissions for the requested operation.

    Examples:
        - API key lacks access to a specific model
        - Organization policy blocks the request
        - IP not in allowlist

    Backward compatible: `except AuthenticationError:` still catches this.
    """
    pass


class NetworkError(ProviderUnavailableError):
    """Connection-level network failure.

    Retryable by default (inherits from ProviderUnavailableError).

    Distinct from ProviderUnavailableError (which covers HTTP 5xx responses)
    because no HTTP response was received at all — the connection failed.

    Examples:
        - DNS resolution failure
        - TCP connection refused
        - TLS handshake failure
        - Connection reset by peer

    Backward compatible: `except ProviderUnavailableError:` still catches this.
    """
    pass


class QuotaExceededError(RateLimitError):
    """Billing or usage quota exhausted.

    Non-retryable by default (unlike parent RateLimitError which IS retryable).
    Quota exhaustion means the account has hit a hard spending or usage limit,
    not a transient rate limit that clears after a delay.

    Examples:
        - Monthly token budget exhausted
        - Free tier limit reached
        - Organization spending cap hit

    Backward compatible: `except RateLimitError:` still catches this.
    """

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        provider: str | None = None,
        status_code: int | None = None,
        retryable: bool = False,  # NOTE: False, unlike parent RateLimitError
    ) -> None:
        super().__init__(
            message,
            retry_after=retry_after,
            provider=provider,
            status_code=status_code,
            retryable=retryable,
        )
```

#### 3.3.3 Updated Hierarchy (After Expansion)

```
LLMError (base)
    ├── RateLimitError              (429, retryable=True)
    │   └── QuotaExceededError      (quota, retryable=False)  ← NEW
    ├── AuthenticationError         (401/403)
    │   └── AccessDeniedError       (403 specifically)        ← NEW
    ├── ContextLengthError          (413)
    ├── ContentFilterError          (safety filter)
    ├── InvalidRequestError         (400/422)
    ├── ProviderUnavailableError    (5xx, retryable=True)
    │   └── NetworkError            (connection failure)      ← NEW
    ├── LLMTimeoutError             (timeout, retryable=True)
    ├── NotFoundError               (404)                     ← NEW
    ├── StreamError                 (mid-stream, retryable=True) ← NEW
    ├── AbortError                  (cancellation)            ← NEW
    ├── InvalidToolCallError        (bad tool call)           ← NEW
    └── ConfigurationError          (misconfigured)           ← NEW
```

**Total: 15 types** (7 existing + 8 new).

#### 3.3.4 HTTP Status Code Mapping (Updated)

Providers should use this mapping when translating HTTP errors:

| Status | Error Type | Retryable |
|--------|-----------|-----------|
| 400 | `InvalidRequestError` | False |
| 401 | `AuthenticationError` | False |
| 403 | `AccessDeniedError` | False |
| 404 | `NotFoundError` | False |
| 408 | `LLMTimeoutError` | True |
| 413 | `ContextLengthError` | False |
| 422 | `InvalidRequestError` | False |
| 429 | `RateLimitError` | True |
| 500 | `ProviderUnavailableError` | True |
| 502 | `ProviderUnavailableError` | True |
| 503 | `ProviderUnavailableError` | True |
| 504 | `ProviderUnavailableError` | True |
| Connection error (no HTTP) | `NetworkError` | True |

#### 3.3.5 What We Explicitly Skip

- **`NoObjectGeneratedError`** — Too specific to structured output (`generate_object()`) which amplifier-core doesn't have yet. When structured output is designed, this error can be added at that time.
- **`ServerError`** — Would be a rename/alias of `ProviderUnavailableError`. Not worth the churn. The existing name is fine.
- **`RequestTimeoutError`** — Would be a rename/alias of `LLMTimeoutError`. Same reasoning.

#### 3.3.6 `__init__.py` Exports

All new error classes must be added to `amplifier_core/__init__.py` exports:

```python
# Add to existing llm_errors imports:
from .llm_errors import AccessDeniedError
from .llm_errors import NotFoundError
from .llm_errors import NetworkError
from .llm_errors import QuotaExceededError
from .llm_errors import StreamError
from .llm_errors import AbortError
from .llm_errors import InvalidToolCallError
from .llm_errors import ConfigurationError
```

---

## 4. Items to Defer (Captured for Future)

### 4.2 Streaming Provider Protocol

**What the spec requires:** A separate `stream(request) -> AsyncIterator[StreamEvent]` method on the ProviderAdapter interface, with formal `StreamEvent` and `StreamEventType` models.

**Current state:** No `stream()` method on the Provider protocol. `ChatRequest.stream=True` flag exists but no provider implements streaming through the core protocol. Streaming events exist in `events.py` (`CONTENT_BLOCK_START/DELTA/END`, `THINKING_DELTA/FINAL`) but these are emitted by providers directly through the hook system, not returned from a `stream()` method.

**Core expert preference:** Add a separate `StreamingProvider` protocol:
```python
class StreamingProvider(Provider, Protocol):
    async def stream(self, request: ChatRequest, **kwargs) -> AsyncIterator[StreamEvent]:
        ...
```

**Amplifier expert preference:** Continue using `ChatRequest.stream=True` + capability negotiation. The existing content block events work. A formal StreamEvent model can wait.

**Why deferred:**
1. No provider module currently returns a stream from `complete()` — all streaming is done through event emission
2. Deciding between separate method vs. flag has significant API implications
3. Doesn't block Attractor — Attractor's codergen handler calls `complete()` and gets full responses
4. Streaming design should be done holistically, not piecemeal

**Captured for future design:**
- Consider `StreamingProvider` as an optional protocol extension
- Consider `StreamEvent` as a typed union model (mirroring the spec's StreamEventType enum)
- Consider backward compatibility: providers that don't implement `stream()` should still work
- Content block events in `events.py` are the building blocks for whatever design is chosen

### 4.4 `provider_options` on ChatRequest

**What the spec requires:** An explicit `provider_options: dict | None` field on the Request for passing provider-specific parameters.

**Current state:** `ChatRequest` has `extra="allow"` (ConfigDict), which means ANY additional keyword argument is accepted and preserved. Callers can already do:
```python
ChatRequest(
    messages=[...],
    anthropic_beta=["interleaved-thinking-2025-05-14"],  # just works
)
```

**Core expert:** Add an explicit `provider_options` field for discoverability.

**Amplifier expert:** `extra="allow"` is sufficient. A typed field creates false structure for inherently unstructured data.

**Why deferred:** The current mechanism works. Provider modules access their specific options from `request.model_extra` or `**kwargs`. Adding `provider_options` later is purely additive and won't break anything.

### 4.6 StreamEvent Taxonomy

**What the spec requires:** A formal `StreamEvent` record with typed fields and a `StreamEventType` enum (13 event types: `STREAM_START`, `TEXT_START`, `TEXT_DELTA`, etc.).

**Current state:** `events.py` already has streaming event constants (`CONTENT_BLOCK_START`, `CONTENT_BLOCK_DELTA`, `CONTENT_BLOCK_END`, `THINKING_DELTA`, `THINKING_FINAL`). These are string constants, not typed models.

**Why deferred:** A formal `StreamEvent` model should be designed alongside the streaming protocol (4.2). The current string-based events work for the existing provider implementations. Formalizing the model before the streaming protocol is designed risks creating a model that doesn't match the eventual protocol.

---

## 5. Backward Compatibility Checklist

### 5.1 Error Hierarchy Expansion

| Check | Status | Details |
|-------|--------|---------|
| Existing `except LLMError:` catches all new types | **Safe** | All new types inherit from `LLMError` |
| Existing `except RateLimitError:` catches `QuotaExceededError` | **Safe** | `QuotaExceededError` subclasses `RateLimitError` |
| Existing `except AuthenticationError:` catches `AccessDeniedError` | **Safe** | `AccessDeniedError` subclasses `AuthenticationError` |
| Existing `except ProviderUnavailableError:` catches `NetworkError` | **Safe** | `NetworkError` subclasses `ProviderUnavailableError` |
| Provider modules need updating? | **No** | Providers CAN use new types but existing raises still work |
| Orchestrator modules need updating? | **No** | Existing error handling still catches all errors |
| New types have correct `retryable` defaults? | **Verified** | See hierarchy in 3.3.3 |
| Change is purely additive (no modifications to existing classes)? | **Yes** | Only new classes appended to `llm_errors.py` |

**Tests to run after changes:**
```bash
# In amplifier-core:
pytest tests/

# In each provider module (verify no catch clause breakage):
cd amplifier-module-provider-anthropic && pytest
cd amplifier-module-provider-azure-openai && pytest
cd amplifier-module-provider-gemini && pytest
cd amplifier-module-provider-ollama && pytest
cd amplifier-module-provider-mock && pytest

# In orchestrator modules:
cd amplifier-module-loop-agent && pytest
cd amplifier-module-loop-basic && pytest
```

### 5.2 Retry Module

| Check | Status | Details |
|-------|--------|---------|
| Changes to amplifier-core? | **None** | New module, no core changes |
| Changes to existing modules? | **None** | Wraps providers at mount time |
| Provider protocol compliance? | **Verified** | RetryProvider satisfies all 5 Provider methods |
| Existing catch clauses affected? | **No** | RetryProvider re-raises the original error type after exhausting retries |

---

## 6. Implementation Order

### Step 1: Error Hierarchy Expansion (amplifier-core)

**Risk:** Zero — purely additive, no existing code changes.
**Effort:** ~1 hour.
**Dependencies:** None.
**Deliverable:** 8 new error classes in `llm_errors.py`, exported in `__init__.py`.

Tasks:
1. Add 8 new classes to `amplifier_core/llm_errors.py` (append after existing classes)
2. Add imports to `amplifier_core/__init__.py`
3. Write unit tests for new error classes (inheritance, `retryable` defaults, `isinstance` checks)
4. Run full amplifier-core test suite
5. Run provider module test suites to verify no breakage

### Step 2: Retry Module (new module)

**Risk:** Zero — new module, no changes to any existing code.
**Effort:** ~2 hours.
**Dependencies:** Step 1 (uses error hierarchy for type checking).
**Deliverable:** `amplifier-module-retry` package.

Tasks:
1. Create module directory structure
2. Implement `RetryConfig` (Pydantic model)
3. Implement `RetryProvider` (decorator pattern)
4. Write comprehensive tests (see test plan in 3.1.7)
5. Verify protocol compliance

### Step 3: Wire Retry into Attractor Bundle

**Risk:** Low — configuration change in bundle setup.
**Effort:** ~30 minutes.
**Dependencies:** Step 2.
**Deliverable:** Attractor's codergen backend wraps providers with RetryProvider.

Tasks:
1. Add `amplifier-module-retry` as dependency of attractor bundle
2. Wrap providers in codergen backend initialization
3. Configure default RetryConfig for Attractor use case

### Step 4: Test in Shadow Environment

**Risk:** Low — validation step.
**Effort:** ~1 hour.
**Dependencies:** Steps 1-3.
**Deliverable:** Verified working end-to-end with retry behavior.

Tasks:
1. Set up shadow environment with local amplifier-core + retry module
2. Run Attractor pipeline that triggers rate limits (mock or real)
3. Verify retry behavior in logs
4. Verify error hierarchy catch clauses work correctly
5. Verify no regression in non-retry paths

---

## Appendix A: Spec-to-Core Mapping Reference

This appendix maps the canonical spec's types to their amplifier-core equivalents for quick reference.

| Unified LLM Spec Type | amplifier-core Type | Notes |
|----------------------|---------------------|-------|
| `SDKError` | `LLMError` | Same role, different name |
| `ProviderError` | (implicit) | All LLMError subtypes are provider errors |
| `AuthenticationError` | `AuthenticationError` | Identical |
| `AccessDeniedError` | `AccessDeniedError` | **NEW** (subclass of AuthenticationError) |
| `NotFoundError` | `NotFoundError` | **NEW** |
| `InvalidRequestError` | `InvalidRequestError` | Identical |
| `RateLimitError` | `RateLimitError` | Identical |
| `QuotaExceededError` | `QuotaExceededError` | **NEW** (subclass of RateLimitError) |
| `ServerError` | `ProviderUnavailableError` | Different name, same semantics |
| `ContentFilterError` | `ContentFilterError` | Identical |
| `ContextLengthError` | `ContextLengthError` | Identical |
| `RequestTimeoutError` | `LLMTimeoutError` | Different name, same semantics |
| `AbortError` | `AbortError` | **NEW** |
| `NetworkError` | `NetworkError` | **NEW** (subclass of ProviderUnavailableError) |
| `StreamError` | `StreamError` | **NEW** |
| `InvalidToolCallError` | `InvalidToolCallError` | **NEW** |
| `NoObjectGeneratedError` | — | **DEFERRED** (structured output not designed) |
| `ConfigurationError` | `ConfigurationError` | **NEW** |

| Unified LLM Spec Type | amplifier-core Type | Notes |
|----------------------|---------------------|-------|
| `Request` | `ChatRequest` | Different name, same fields + `extra="allow"` |
| `Response` | `ChatResponse` | Different name, similar fields |
| `Usage` | `Usage` | Identical fields |
| `Message` | `Message` | Identical structure |
| `ToolCall` | `ToolCall` | Identical |
| `StreamEvent` | (event constants in events.py) | **DEFERRED** — no formal model yet |
| `StreamEventType` | (string constants) | **DEFERRED** |
| `ProviderAdapter` | `Provider` | Different name, similar but not identical methods |

## Appendix B: Retry Backoff Table

Reference table for default `RetryConfig` settings (`base_delay=1.0`, `multiplier=2.0`, `max_delay=60.0`, `jitter=0.2`):

| Attempt | Base Delay | With Jitter Range | After `retry_after=5.0s` |
|---------|------------|-------------------|--------------------------|
| 0 (1st retry) | 1.0s | 0.8s – 1.2s | 5.0s |
| 1 (2nd retry) | 2.0s | 1.6s – 2.4s | 5.0s |
| 2 (3rd retry) | 4.0s | 3.2s – 4.8s | 5.0s |
| 3 (4th retry) | 8.0s | 6.4s – 9.6s | 8.0s (calculated > retry_after) |
| 4 (5th retry) | 16.0s | 12.8s – 19.2s | 16.0s |
| 5 (6th retry) | 32.0s | 25.6s – 38.4s | 32.0s |
| 6 (7th retry) | 60.0s (capped) | 48.0s – 72.0s | 60.0s |
