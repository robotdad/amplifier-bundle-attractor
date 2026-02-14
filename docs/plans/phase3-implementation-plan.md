# Phase 3 "Do Now" Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Expand the amplifier-core error hierarchy with 8 new error types and add a shared retry utility, both purely additive with zero breaking changes.

**Architecture:** Two PRs targeting the `amplifier-core` repo. PR 1 adds 8 new `LLMError` subclasses to `llm_errors.py` and a `PROVIDER_RETRY` event constant to `events.py`. PR 2 adds a `retry.py` utility module under `amplifier_core/utils/` with `RetryConfig`, `retry_with_backoff()`, and `classify_error_message()`. Both PRs are additive-only — no existing code is modified, no existing tests change.

**Tech Stack:** Python 3.12+, pytest, asyncio, dataclasses, amplifier-core

**Repos:**
- `amplifier-core` at `/home/bkrabach/dev/attractor-next/amplifier-core`

**Design doc:** `amplifier-bundle-attractor/docs/plans/phase3-upstream-design.md`

---

## PR 1: Error Hierarchy Expansion

**Branch:** `feature/error-hierarchy-expansion`

### Task 1.1: Write failing tests for new error types

**Files:**
- Modify: `tests/test_llm_errors.py`

**Dependencies:** None
**Effort:** S

The existing test file (`tests/test_llm_errors.py`, 257 lines) tests the 7 current error types. We append new test classes to this file. Do NOT modify any existing test code.

**Step 1: Add imports for the 8 new error types**

At the top of `tests/test_llm_errors.py`, extend the existing import block. The current import block (lines 4-13) is:

```python
from amplifier_core.llm_errors import (
    AuthenticationError,
    ContentFilterError,
    ContextLengthError,
    InvalidRequestError,
    LLMError,
    LLMTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
)
```

Replace it with:

```python
from amplifier_core.llm_errors import (
    AbortError,
    AccessDeniedError,
    AuthenticationError,
    ConfigurationError,
    ContentFilterError,
    ContextLengthError,
    InvalidRequestError,
    InvalidToolCallError,
    LLMError,
    LLMTimeoutError,
    NetworkError,
    NotFoundError,
    ProviderUnavailableError,
    QuotaExceededError,
    RateLimitError,
    StreamError,
)
```

**Step 2: Append test classes for new leaf error types**

Append the following after the last class (`TestImportFromCore`) at the end of the file:

```python


class TestNotFoundError:
    """Tests for NotFoundError."""

    def test_instantiation(self) -> None:
        err = NotFoundError("Model gpt-99 not found", provider="openai", status_code=404)
        assert str(err) == "Model gpt-99 not found"
        assert err.provider == "openai"
        assert err.status_code == 404

    def test_inherits_from_llm_error(self) -> None:
        err = NotFoundError("not found")
        assert isinstance(err, LLMError)
        assert isinstance(err, Exception)

    def test_not_retryable_by_default(self) -> None:
        err = NotFoundError("not found")
        assert err.retryable is False

    def test_caught_by_except_llm_error(self) -> None:
        with pytest.raises(LLMError):
            raise NotFoundError("not found")


class TestStreamError:
    """Tests for StreamError."""

    def test_retryable_by_default(self) -> None:
        err = StreamError("Connection dropped mid-stream")
        assert err.retryable is True

    def test_inherits_from_llm_error(self) -> None:
        err = StreamError("stream broke")
        assert isinstance(err, LLMError)

    def test_retryable_override(self) -> None:
        err = StreamError("corrupt", retryable=False)
        assert err.retryable is False

    def test_caught_by_except_llm_error(self) -> None:
        with pytest.raises(LLMError):
            raise StreamError("stream broke")


class TestAbortError:
    """Tests for AbortError."""

    def test_not_retryable_by_default(self) -> None:
        err = AbortError("User cancelled")
        assert err.retryable is False

    def test_inherits_from_llm_error(self) -> None:
        err = AbortError("cancelled")
        assert isinstance(err, LLMError)

    def test_caught_by_except_llm_error(self) -> None:
        with pytest.raises(LLMError):
            raise AbortError("cancelled")


class TestInvalidToolCallError:
    """Tests for InvalidToolCallError."""

    def test_not_retryable_by_default(self) -> None:
        err = InvalidToolCallError("Bad JSON in arguments")
        assert err.retryable is False

    def test_tool_name_and_raw_arguments(self) -> None:
        err = InvalidToolCallError(
            "Failed to parse arguments",
            tool_name="read_file",
            raw_arguments='{"path": broken}',
        )
        assert err.tool_name == "read_file"
        assert err.raw_arguments == '{"path": broken}'

    def test_tool_name_defaults_to_none(self) -> None:
        err = InvalidToolCallError("bad call")
        assert err.tool_name is None
        assert err.raw_arguments is None

    def test_inherits_from_llm_error(self) -> None:
        err = InvalidToolCallError("bad call")
        assert isinstance(err, LLMError)

    def test_accepts_provider_and_status_code(self) -> None:
        err = InvalidToolCallError(
            "bad call",
            tool_name="foo",
            raw_arguments="bar",
            provider="anthropic",
            status_code=400,
        )
        assert err.provider == "anthropic"
        assert err.status_code == 400

    def test_caught_by_except_llm_error(self) -> None:
        with pytest.raises(LLMError):
            raise InvalidToolCallError("bad")


class TestConfigurationError:
    """Tests for ConfigurationError."""

    def test_not_retryable_by_default(self) -> None:
        err = ConfigurationError("Missing API key")
        assert err.retryable is False

    def test_inherits_from_llm_error(self) -> None:
        err = ConfigurationError("bad config")
        assert isinstance(err, LLMError)

    def test_caught_by_except_llm_error(self) -> None:
        with pytest.raises(LLMError):
            raise ConfigurationError("bad config")


class TestAccessDeniedError:
    """Tests for AccessDeniedError (subclass of AuthenticationError)."""

    def test_not_retryable_by_default(self) -> None:
        err = AccessDeniedError("Forbidden")
        assert err.retryable is False

    def test_inherits_from_authentication_error(self) -> None:
        err = AccessDeniedError("forbidden")
        assert isinstance(err, AuthenticationError)

    def test_inherits_from_llm_error(self) -> None:
        err = AccessDeniedError("forbidden")
        assert isinstance(err, LLMError)

    def test_caught_by_except_authentication_error(self) -> None:
        """Backward compat: existing `except AuthenticationError:` catches this."""
        with pytest.raises(AuthenticationError):
            raise AccessDeniedError("forbidden")

    def test_caught_by_except_llm_error(self) -> None:
        with pytest.raises(LLMError):
            raise AccessDeniedError("forbidden")


class TestNetworkError:
    """Tests for NetworkError (subclass of ProviderUnavailableError)."""

    def test_retryable_by_default(self) -> None:
        """Inherits retryable=True from ProviderUnavailableError."""
        err = NetworkError("DNS resolution failed")
        assert err.retryable is True

    def test_inherits_from_provider_unavailable(self) -> None:
        err = NetworkError("connection refused")
        assert isinstance(err, ProviderUnavailableError)

    def test_inherits_from_llm_error(self) -> None:
        err = NetworkError("connection refused")
        assert isinstance(err, LLMError)

    def test_caught_by_except_provider_unavailable(self) -> None:
        """Backward compat: existing `except ProviderUnavailableError:` catches this."""
        with pytest.raises(ProviderUnavailableError):
            raise NetworkError("connection refused")

    def test_caught_by_except_llm_error(self) -> None:
        with pytest.raises(LLMError):
            raise NetworkError("connection refused")


class TestQuotaExceededError:
    """Tests for QuotaExceededError (subclass of RateLimitError)."""

    def test_not_retryable_by_default(self) -> None:
        """Unlike parent RateLimitError (retryable=True), QuotaExceededError defaults to False."""
        err = QuotaExceededError("Monthly quota exhausted")
        assert err.retryable is False

    def test_inherits_from_rate_limit_error(self) -> None:
        err = QuotaExceededError("quota exceeded")
        assert isinstance(err, RateLimitError)

    def test_inherits_from_llm_error(self) -> None:
        err = QuotaExceededError("quota exceeded")
        assert isinstance(err, LLMError)

    def test_has_retry_after(self) -> None:
        """Inherits retry_after from RateLimitError."""
        err = QuotaExceededError("quota exceeded", retry_after=3600.0)
        assert err.retry_after == 3600.0

    def test_caught_by_except_rate_limit_error(self) -> None:
        """Backward compat: existing `except RateLimitError:` catches this."""
        with pytest.raises(RateLimitError):
            raise QuotaExceededError("quota exceeded")

    def test_caught_by_except_llm_error(self) -> None:
        with pytest.raises(LLMError):
            raise QuotaExceededError("quota exceeded")

    def test_retryable_can_be_overridden(self) -> None:
        err = QuotaExceededError("quota exceeded", retryable=True)
        assert err.retryable is True


class TestNewErrorsInAllSubtypesCheck:
    """Verify all 15 error types are caught by except LLMError."""

    def test_all_types_are_llm_errors(self) -> None:
        errors = [
            # Original 7
            RateLimitError("rate limited"),
            AuthenticationError("bad key"),
            ContextLengthError("too long"),
            ContentFilterError("blocked"),
            InvalidRequestError("bad request"),
            ProviderUnavailableError("down"),
            LLMTimeoutError("timed out"),
            # New 8
            NotFoundError("not found"),
            StreamError("stream broke"),
            AbortError("cancelled"),
            InvalidToolCallError("bad tool call"),
            ConfigurationError("bad config"),
            AccessDeniedError("forbidden"),
            NetworkError("connection refused"),
            QuotaExceededError("quota exceeded"),
        ]
        for err in errors:
            assert isinstance(err, LLMError), f"{type(err).__name__} is not an LLMError"
            assert isinstance(err, Exception)


class TestNewErrorsImportFromCore:
    """Verify all 8 new error types are importable from amplifier_core."""

    def test_import_new_types_from_top_level(self) -> None:
        import amplifier_core

        new_error_names = [
            "NotFoundError",
            "StreamError",
            "AbortError",
            "InvalidToolCallError",
            "ConfigurationError",
            "AccessDeniedError",
            "NetworkError",
            "QuotaExceededError",
        ]
        for name in new_error_names:
            assert hasattr(amplifier_core, name), (
                f"{name} not exported from amplifier_core"
            )
            cls = getattr(amplifier_core, name)
            assert issubclass(cls, Exception), f"{name} is not an Exception subclass"
            assert issubclass(cls, LLMError), f"{name} is not an LLMError subclass"
```

**Step 3: Run tests to verify they fail**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-core && uv run pytest tests/test_llm_errors.py -v --tb=short`

Expected: FAIL — `ImportError: cannot import name 'AbortError' from 'amplifier_core.llm_errors'`

**Step 4: Commit failing tests**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-core
git add tests/test_llm_errors.py
git commit -m "test: add failing tests for 8 new error types"
```

---

### Task 1.2: Add 8 error classes to `llm_errors.py`

**Files:**
- Modify: `amplifier_core/llm_errors.py`

**Dependencies:** Task 1.1
**Effort:** S

The current file ends at line 147 with `LLMTimeoutError`. Append all 8 new classes after line 147. Do NOT modify any existing code above line 147.

**Step 1: Append new error classes to `llm_errors.py`**

Add the following after the closing line of `LLMTimeoutError` (after line 147):

```python


# ---- New error types (Phase 3, purely additive) ----


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
    succeeded -- the failure happened mid-stream.
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
    This is not a failure -- it's cooperative cancellation via CancellationToken
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


class AccessDeniedError(AuthenticationError):
    """Permission denied (HTTP 403).

    Distinct from AuthenticationError (401) -- credentials are valid but
    lack sufficient permissions for the requested operation.

    Backward compatible: ``except AuthenticationError:`` still catches this.
    """

    pass


class NetworkError(ProviderUnavailableError):
    """Connection-level network failure.

    Retryable by default (inherits from ProviderUnavailableError).

    Distinct from ProviderUnavailableError (which covers HTTP 5xx responses)
    because no HTTP response was received at all -- the connection failed.

    Examples:
        - DNS resolution failure
        - TCP connection refused
        - TLS handshake failure
        - Connection reset by peer

    Backward compatible: ``except ProviderUnavailableError:`` still catches this.
    """

    pass


class QuotaExceededError(RateLimitError):
    """Billing or usage quota exhausted.

    Non-retryable by default (unlike parent RateLimitError which IS retryable).
    Quota exhaustion means the account has hit a hard spending or usage limit,
    not a transient rate limit that clears after a delay.

    Backward compatible: ``except RateLimitError:`` still catches this.
    """

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        provider: str | None = None,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            retry_after=retry_after,
            provider=provider,
            status_code=status_code,
            retryable=retryable,
        )
```

**Step 2: Run the tests**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-core && uv run pytest tests/test_llm_errors.py -v --tb=short`

Expected: Most new tests PASS. The `TestNewErrorsImportFromCore` tests still FAIL because `__init__.py` doesn't export them yet.

**Step 3: Commit**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-core
git add amplifier_core/llm_errors.py
git commit -m "feat: add 8 new LLMError subclasses (Phase 3 error hierarchy)"
```

---

### Task 1.3: Export new types from `__init__.py`

**Files:**
- Modify: `amplifier_core/__init__.py`

**Dependencies:** Task 1.2
**Effort:** S

The current `__init__.py` has error imports on lines 25-32 and `__all__` error entries on lines 111-119. We add to both sections.

**Step 1: Add imports for the 8 new error types**

The current import block for errors (lines 25-32) is:

```python
from .llm_errors import AuthenticationError
from .llm_errors import ContentFilterError
from .llm_errors import ContextLengthError
from .llm_errors import InvalidRequestError
from .llm_errors import LLMError
from .llm_errors import LLMTimeoutError
from .llm_errors import ProviderUnavailableError
from .llm_errors import RateLimitError
```

Replace it with (alphabetical order):

```python
from .llm_errors import AbortError
from .llm_errors import AccessDeniedError
from .llm_errors import AuthenticationError
from .llm_errors import ConfigurationError
from .llm_errors import ContentFilterError
from .llm_errors import ContextLengthError
from .llm_errors import InvalidRequestError
from .llm_errors import InvalidToolCallError
from .llm_errors import LLMError
from .llm_errors import LLMTimeoutError
from .llm_errors import NetworkError
from .llm_errors import NotFoundError
from .llm_errors import ProviderUnavailableError
from .llm_errors import QuotaExceededError
from .llm_errors import RateLimitError
from .llm_errors import StreamError
```

**Step 2: Add new types to `__all__`**

The current `__all__` error block (lines 111-119) is:

```python
    # LLM error taxonomy
    "LLMError",
    "RateLimitError",
    "AuthenticationError",
    "ContextLengthError",
    "ContentFilterError",
    "InvalidRequestError",
    "ProviderUnavailableError",
    "LLMTimeoutError",
```

Replace it with:

```python
    # LLM error taxonomy
    "LLMError",
    "RateLimitError",
    "AuthenticationError",
    "ContextLengthError",
    "ContentFilterError",
    "InvalidRequestError",
    "ProviderUnavailableError",
    "LLMTimeoutError",
    # Phase 3 additions
    "AbortError",
    "AccessDeniedError",
    "ConfigurationError",
    "InvalidToolCallError",
    "NetworkError",
    "NotFoundError",
    "QuotaExceededError",
    "StreamError",
```

**Step 3: Run tests**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-core && uv run pytest tests/test_llm_errors.py -v --tb=short`

Expected: ALL PASS (including `TestNewErrorsImportFromCore`)

**Step 4: Commit**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-core
git add amplifier_core/__init__.py
git commit -m "feat: export 8 new error types from amplifier_core public API"
```

---

### Task 1.4: Add `PROVIDER_RETRY` event constant

**Files:**
- Modify: `amplifier_core/events.py`
- Create: `tests/test_events_provider_retry.py`

**Dependencies:** None (independent of error hierarchy tasks)
**Effort:** S

Both the Anthropic provider (`__init__.py:1159`) and vLLM provider (`__init__.py:793`) already emit `"provider:retry"` as a hardcoded string. We formalize this as a constant.

**Step 1: Write failing test**

Create `tests/test_events_provider_retry.py`:

```python
"""Tests for PROVIDER_RETRY event constant."""

from amplifier_core.events import ALL_EVENTS, PROVIDER_RETRY


class TestProviderRetryEvent:
    """Tests for the PROVIDER_RETRY event constant."""

    def test_value(self) -> None:
        assert PROVIDER_RETRY == "provider:retry"

    def test_in_all_events(self) -> None:
        assert PROVIDER_RETRY in ALL_EVENTS
```

**Step 2: Run test to verify it fails**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-core && uv run pytest tests/test_events_provider_retry.py -v --tb=short`

Expected: FAIL — `ImportError: cannot import name 'PROVIDER_RETRY'`

**Step 3: Add constant to `events.py`**

In `amplifier_core/events.py`, after the `PROVIDER_ERROR` line (line 26), add:

```python
PROVIDER_RETRY = "provider:retry"
```

So the "Provider calls" section becomes:

```python
# Provider calls (LLMs)
PROVIDER_REQUEST = "provider:request"
PROVIDER_RESPONSE = "provider:response"
PROVIDER_ERROR = "provider:error"
PROVIDER_RETRY = "provider:retry"
```

Then add `PROVIDER_RETRY` to the `ALL_EVENTS` list. Insert it after the `PROVIDER_ERROR` entry (line 96):

```python
    PROVIDER_ERROR,
    PROVIDER_RETRY,
```

**Step 4: Run test to verify it passes**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-core && uv run pytest tests/test_events_provider_retry.py -v --tb=short`

Expected: PASS

**Step 5: Commit**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-core
git add amplifier_core/events.py tests/test_events_provider_retry.py
git commit -m "feat: add PROVIDER_RETRY event constant"
```

---

### Task 1.5: Run full test suite

**Files:** None (verification only)

**Dependencies:** Tasks 1.1-1.4
**Effort:** S

**Step 1: Run full amplifier-core test suite**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-core && uv run pytest tests/ -v --tb=short`

Expected: ALL PASS. Zero existing tests should break — all changes are purely additive.

**Step 2: Run python quality checks**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-core && uv run ruff check amplifier_core/ && uv run ruff format --check amplifier_core/`

Expected: Clean (no lint errors, no formatting issues).

---

## PR 2: Retry Utility

**Branch:** `feature/retry-utility`  
**Base:** PR 1's branch (needs the new error types)

### Task 2.1: Write failing tests for `RetryConfig`

**Files:**
- Create: `tests/test_retry.py`

**Dependencies:** PR 1 merged (needs new error types)
**Effort:** S

**Step 1: Create test file with `RetryConfig` tests**

Create `tests/test_retry.py`:

```python
"""Tests for amplifier_core.utils.retry module."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from amplifier_core.llm_errors import (
    AuthenticationError,
    ConfigurationError,
    ContentFilterError,
    ContextLengthError,
    InvalidRequestError,
    LLMError,
    LLMTimeoutError,
    NetworkError,
    NotFoundError,
    ProviderUnavailableError,
    QuotaExceededError,
    RateLimitError,
)
from amplifier_core.utils.retry import (
    RetryConfig,
    classify_error_message,
    retry_with_backoff,
)


class TestRetryConfig:
    """Tests for RetryConfig defaults and construction."""

    def test_defaults(self) -> None:
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.min_delay == 1.0
        assert config.max_delay == 60.0
        assert config.jitter == 0.2
        assert config.backoff_multiplier == 2.0
        assert config.honor_retry_after is True

    def test_custom_values(self) -> None:
        config = RetryConfig(
            max_retries=5,
            min_delay=0.5,
            max_delay=30.0,
            jitter=0.1,
            backoff_multiplier=3.0,
            honor_retry_after=False,
        )
        assert config.max_retries == 5
        assert config.min_delay == 0.5
        assert config.max_delay == 30.0
        assert config.jitter == 0.1
        assert config.backoff_multiplier == 3.0
        assert config.honor_retry_after is False

    def test_zero_retries(self) -> None:
        config = RetryConfig(max_retries=0)
        assert config.max_retries == 0
```

**Step 2: Run test to verify it fails**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-core && uv run pytest tests/test_retry.py::TestRetryConfig -v --tb=short`

Expected: FAIL — `ModuleNotFoundError: No module named 'amplifier_core.utils.retry'`

**Step 3: Commit**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-core
git add tests/test_retry.py
git commit -m "test: add failing tests for RetryConfig"
```

---

### Task 2.2: Write failing tests for `retry_with_backoff()`

**Files:**
- Modify: `tests/test_retry.py`

**Dependencies:** Task 2.1
**Effort:** M

**Step 1: Append retry_with_backoff test class to `tests/test_retry.py`**

Append after the `TestRetryConfig` class:

```python


class TestRetryWithBackoff:
    """Tests for retry_with_backoff() async function."""

    @pytest.mark.asyncio
    async def test_succeeds_first_try(self) -> None:
        """No retry needed when operation succeeds."""
        operation = AsyncMock(return_value="success")
        result = await retry_with_backoff(operation)
        assert result == "success"
        assert operation.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_retryable_error(self) -> None:
        """Retries on retryable LLMError, succeeds on attempt 2."""
        operation = AsyncMock(
            side_effect=[
                ProviderUnavailableError("down", retryable=True),
                "success",
            ]
        )
        config = RetryConfig(max_retries=3, min_delay=0.01, max_delay=0.1)
        result = await retry_with_backoff(operation, config)
        assert result == "success"
        assert operation.call_count == 2

    @pytest.mark.asyncio
    async def test_respects_max_retries(self) -> None:
        """Gives up after max_retries attempts."""
        error = ProviderUnavailableError("still down", retryable=True)
        operation = AsyncMock(side_effect=error)
        config = RetryConfig(max_retries=2, min_delay=0.01, max_delay=0.1)
        with pytest.raises(ProviderUnavailableError, match="still down"):
            await retry_with_backoff(operation, config)
        # 1 initial + 2 retries = 3 total calls
        assert operation.call_count == 3

    @pytest.mark.asyncio
    async def test_does_not_retry_non_retryable(self) -> None:
        """Non-retryable errors raise immediately without retry."""
        error = AuthenticationError("bad key")
        operation = AsyncMock(side_effect=error)
        config = RetryConfig(max_retries=3, min_delay=0.01)
        with pytest.raises(AuthenticationError, match="bad key"):
            await retry_with_backoff(operation, config)
        assert operation.call_count == 1

    @pytest.mark.asyncio
    async def test_does_not_retry_non_llm_error(self) -> None:
        """Non-LLMError exceptions pass through immediately."""
        operation = AsyncMock(side_effect=ValueError("not an LLM error"))
        config = RetryConfig(max_retries=3, min_delay=0.01)
        with pytest.raises(ValueError, match="not an LLM error"):
            await retry_with_backoff(operation, config)
        assert operation.call_count == 1

    @pytest.mark.asyncio
    async def test_respects_retry_after(self) -> None:
        """Uses RateLimitError.retry_after when available."""
        error = RateLimitError("too fast", retry_after=0.05, retryable=True)
        operation = AsyncMock(side_effect=[error, "ok"])
        config = RetryConfig(max_retries=3, min_delay=0.01, max_delay=1.0)
        result = await retry_with_backoff(operation, config)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_backoff_increases(self) -> None:
        """Delay increases exponentially between retries."""
        delays: list[float] = []

        async def on_retry(attempt: int, delay: float, error: LLMError) -> None:
            delays.append(delay)

        error = ProviderUnavailableError("down", retryable=True)
        operation = AsyncMock(side_effect=[error, error, error, "success"])
        config = RetryConfig(
            max_retries=3, min_delay=1.0, max_delay=100.0, jitter=0.0
        )
        result = await retry_with_backoff(operation, config, on_retry=on_retry)
        assert result == "success"
        # With jitter=0: delays should be 1.0, 2.0, 4.0
        assert len(delays) == 3
        assert delays[0] == pytest.approx(1.0)
        assert delays[1] == pytest.approx(2.0)
        assert delays[2] == pytest.approx(4.0)

    @pytest.mark.asyncio
    async def test_jitter_applied(self) -> None:
        """Delays vary when jitter > 0."""
        delays: list[float] = []

        async def on_retry(attempt: int, delay: float, error: LLMError) -> None:
            delays.append(delay)

        error = ProviderUnavailableError("down", retryable=True)
        operation = AsyncMock(side_effect=[error, error, "success"])
        config = RetryConfig(max_retries=3, min_delay=1.0, jitter=0.2)
        await retry_with_backoff(operation, config, on_retry=on_retry)
        # First delay should be around 1.0 +/- 20%
        assert 0.7 <= delays[0] <= 1.3

    @pytest.mark.asyncio
    async def test_on_retry_callback_called(self) -> None:
        """on_retry callback receives attempt number, delay, and error."""
        callback_args: list[tuple[int, float, LLMError]] = []

        async def on_retry(attempt: int, delay: float, error: LLMError) -> None:
            callback_args.append((attempt, delay, error))

        error = ProviderUnavailableError("down", retryable=True)
        operation = AsyncMock(side_effect=[error, "success"])
        config = RetryConfig(max_retries=3, min_delay=0.01)
        await retry_with_backoff(operation, config, on_retry=on_retry)
        assert len(callback_args) == 1
        attempt, delay, err = callback_args[0]
        assert attempt == 1
        assert delay > 0
        assert err is error

    @pytest.mark.asyncio
    async def test_raises_final_error_after_exhaustion(self) -> None:
        """After all retries exhausted, raises the last error."""
        errors = [
            ProviderUnavailableError("fail 1", retryable=True),
            ProviderUnavailableError("fail 2", retryable=True),
            ProviderUnavailableError("fail 3", retryable=True),
        ]
        operation = AsyncMock(side_effect=errors)
        config = RetryConfig(max_retries=2, min_delay=0.01)
        with pytest.raises(ProviderUnavailableError, match="fail 3"):
            await retry_with_backoff(operation, config)

    @pytest.mark.asyncio
    async def test_zero_max_retries_no_retry(self) -> None:
        """With max_retries=0, the operation is called once and errors propagate."""
        error = ProviderUnavailableError("down", retryable=True)
        operation = AsyncMock(side_effect=error)
        config = RetryConfig(max_retries=0, min_delay=0.01)
        with pytest.raises(ProviderUnavailableError):
            await retry_with_backoff(operation, config)
        assert operation.call_count == 1

    @pytest.mark.asyncio
    async def test_delay_capped_at_max_delay(self) -> None:
        """Delay never exceeds max_delay."""
        delays: list[float] = []

        async def on_retry(attempt: int, delay: float, error: LLMError) -> None:
            delays.append(delay)

        error = ProviderUnavailableError("down", retryable=True)
        operation = AsyncMock(
            side_effect=[error, error, error, error, error, "success"]
        )
        config = RetryConfig(
            max_retries=5, min_delay=10.0, max_delay=25.0, jitter=0.0
        )
        await retry_with_backoff(operation, config, on_retry=on_retry)
        # 10, 20, 25(capped), 25(capped), 25(capped)
        for d in delays:
            assert d <= 25.0

    @pytest.mark.asyncio
    async def test_default_config_when_none(self) -> None:
        """Uses default RetryConfig when config=None."""
        error = ProviderUnavailableError("down", retryable=True)
        operation = AsyncMock(side_effect=[error, "ok"])
        # Passing config=None should use defaults (works, doesn't crash)
        result = await retry_with_backoff(operation, None)
        assert result == "ok"
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-core && uv run pytest tests/test_retry.py::TestRetryWithBackoff -v --tb=short`

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Commit**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-core
git add tests/test_retry.py
git commit -m "test: add failing tests for retry_with_backoff()"
```

---

### Task 2.3: Write failing tests for `classify_error_message()`

**Files:**
- Modify: `tests/test_retry.py`

**Dependencies:** Task 2.1
**Effort:** S

**Step 1: Append classify_error_message tests to `tests/test_retry.py`**

Append after `TestRetryWithBackoff`:

```python


class TestClassifyErrorMessage:
    """Tests for classify_error_message() heuristic classifier."""

    def test_context_length_keywords(self) -> None:
        assert classify_error_message("context length exceeded") is ContextLengthError
        assert classify_error_message("too many tokens for model") is ContextLengthError
        assert classify_error_message("maximum context length") is ContextLengthError

    def test_rate_limit_keywords(self) -> None:
        assert classify_error_message("rate limit exceeded") is RateLimitError
        assert classify_error_message("too many requests") is RateLimitError

    def test_authentication_keywords(self) -> None:
        assert classify_error_message("authentication failed") is AuthenticationError
        assert classify_error_message("invalid api key") is AuthenticationError
        assert classify_error_message("unauthorized access") is AuthenticationError

    def test_not_found_keywords(self) -> None:
        assert classify_error_message("model not found") is NotFoundError
        assert classify_error_message("endpoint not found") is NotFoundError

    def test_content_filter_keywords(self) -> None:
        assert classify_error_message("content filter triggered") is ContentFilterError
        assert classify_error_message("blocked by safety filter") is ContentFilterError

    def test_unknown_message_returns_base(self) -> None:
        assert classify_error_message("something unknown happened") is LLMError

    def test_case_insensitive(self) -> None:
        assert classify_error_message("RATE LIMIT EXCEEDED") is RateLimitError
        assert classify_error_message("Context Length Exceeded") is ContextLengthError

    def test_status_code_overrides_message(self) -> None:
        """Status code takes priority when available."""
        # Message says "rate limit" but status is 404
        assert classify_error_message("rate limit", status_code=404) is NotFoundError
        assert classify_error_message("something", status_code=401) is AuthenticationError
        assert classify_error_message("something", status_code=403) is AccessDeniedError
        assert classify_error_message("something", status_code=429) is RateLimitError
        assert classify_error_message("something", status_code=413) is ContextLengthError

    def test_status_code_5xx(self) -> None:
        assert classify_error_message("error", status_code=500) is ProviderUnavailableError
        assert classify_error_message("error", status_code=502) is ProviderUnavailableError
        assert classify_error_message("error", status_code=503) is ProviderUnavailableError

    def test_status_code_400_falls_through_to_message(self) -> None:
        """400 is ambiguous -- fall through to message classification."""
        assert classify_error_message("context length exceeded", status_code=400) is ContextLengthError
        assert classify_error_message("unknown error", status_code=400) is InvalidRequestError
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-core && uv run pytest tests/test_retry.py::TestClassifyErrorMessage -v --tb=short`

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Commit**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-core
git add tests/test_retry.py
git commit -m "test: add failing tests for classify_error_message()"
```

---

### Task 2.4: Implement `RetryConfig` and `classify_error_message()`

**Files:**
- Create: `amplifier_core/utils/retry.py`

**Dependencies:** Tasks 2.1, 2.3
**Effort:** S

**Step 1: Create `amplifier_core/utils/retry.py` with `RetryConfig` and `classify_error_message()`**

Create the file `amplifier_core/utils/retry.py`:

```python
"""Shared retry utilities for LLM provider operations.

Provides:
- RetryConfig: Configuration dataclass for retry behavior.
- retry_with_backoff: Async retry loop with exponential backoff.
- classify_error_message: Heuristic error classifier for provider error strings.

These are mechanism, not policy. Providers and modules decide when
and how to use them.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from amplifier_core.llm_errors import (
    AccessDeniedError,
    AuthenticationError,
    ContentFilterError,
    ContextLengthError,
    InvalidRequestError,
    LLMError,
    NotFoundError,
    ProviderUnavailableError,
    RateLimitError,
)

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior.

    Follows exponential backoff with jitter. Respects
    ``RateLimitError.retry_after`` when ``honor_retry_after`` is True.
    Only retries errors where ``LLMError.retryable`` is True.
    """

    max_retries: int = 3
    """Maximum retry attempts. 0 means no retries (single attempt). Total calls = max_retries + 1."""

    min_delay: float = 1.0
    """Initial delay in seconds before the first retry."""

    max_delay: float = 60.0
    """Maximum delay between retries in seconds."""

    jitter: float = 0.2
    """Jitter factor (0.0-1.0). Applied as +/- jitter * delay."""

    backoff_multiplier: float = 2.0
    """Exponential backoff factor. Delay = min_delay * (multiplier ^ attempt)."""

    honor_retry_after: bool = True
    """If True, use max(calculated_delay, retry_after) for RateLimitError."""


def classify_error_message(
    message: str,
    *,
    status_code: int | None = None,
    provider: str | None = None,
) -> type[LLMError]:
    """Classify an error message string into the most specific LLMError subclass.

    This centralizes the string-matching heuristics that all providers duplicate.
    Providers can use this as a fallback when they can't determine the error type
    from the SDK's native exception type.

    Status code takes priority when available (except 400, which is ambiguous
    and falls through to message-based classification).

    Args:
        message: The error message to classify.
        status_code: HTTP status code, if available.
        provider: Provider name for context (unused in classification, reserved).

    Returns:
        The most specific LLMError subclass matching the error.
    """
    # Status code takes priority for unambiguous codes
    if status_code is not None:
        if status_code == 401:
            return AuthenticationError
        if status_code == 403:
            return AccessDeniedError
        if status_code == 404:
            return NotFoundError
        if status_code == 413:
            return ContextLengthError
        if status_code == 429:
            return RateLimitError
        if status_code >= 500:
            return ProviderUnavailableError
        # 400/422 are ambiguous -- fall through to message classification

    # Message-based classification (lowercased)
    msg = message.lower()

    # Order matters: more specific patterns first
    if "context length" in msg or "too many tokens" in msg or "maximum context" in msg:
        return ContextLengthError

    if "rate limit" in msg or "too many requests" in msg:
        return RateLimitError

    if "authentication" in msg or "api key" in msg or "unauthorized" in msg:
        return AuthenticationError

    if "not found" in msg:
        return NotFoundError

    if "content filter" in msg or "safety" in msg or "blocked" in msg:
        return ContentFilterError

    # 400/422 with no specific message match -> InvalidRequestError
    if status_code is not None and status_code in (400, 422):
        return InvalidRequestError

    return LLMError
```

**Step 2: Run `RetryConfig` and `classify_error_message` tests**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-core && uv run pytest tests/test_retry.py::TestRetryConfig tests/test_retry.py::TestClassifyErrorMessage -v --tb=short`

Expected: ALL PASS

**Step 3: Commit**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-core
git add amplifier_core/utils/retry.py
git commit -m "feat: add RetryConfig and classify_error_message()"
```

---

### Task 2.5: Implement `retry_with_backoff()`

**Files:**
- Modify: `amplifier_core/utils/retry.py`

**Dependencies:** Task 2.4
**Effort:** M

**Step 1: Add the `retry_with_backoff()` function to `amplifier_core/utils/retry.py`**

Insert the following function after `RetryConfig` and before `classify_error_message`. Place it between the `RetryConfig` class and the `classify_error_message` function:

```python


async def retry_with_backoff(
    operation: Callable[..., Awaitable[T]],
    config: RetryConfig | None = None,
    *,
    on_retry: Callable[[int, float, LLMError], Awaitable[None]] | None = None,
) -> T:
    """Execute an async operation with retry on retryable LLMErrors.

    Args:
        operation: Async callable to execute (no args -- use functools.partial
            or lambda to bind arguments).
        config: Retry configuration. Uses defaults if None.
        on_retry: Optional async callback called before each retry sleep with
            (attempt, delay, error). Use for event emission, logging, etc.

    Returns:
        The result of a successful operation call.

    Raises:
        LLMError: The final error after all retries exhausted, or a
            non-retryable error immediately.
        Exception: Any non-LLMError exception from the operation (no retry).
    """
    if config is None:
        config = RetryConfig()

    last_error: LLMError | None = None

    for attempt in range(config.max_retries + 1):
        try:
            return await operation()
        except LLMError as e:
            last_error = e

            # Non-retryable: raise immediately
            if not e.retryable:
                raise

            # Out of retries: raise
            if attempt >= config.max_retries:
                raise

            # Calculate delay: min_delay * multiplier^attempt, capped at max_delay
            delay = config.min_delay * (config.backoff_multiplier ** attempt)
            delay = min(delay, config.max_delay)

            # Respect retry_after from RateLimitError
            if (
                config.honor_retry_after
                and isinstance(e, RateLimitError)
                and e.retry_after is not None
            ):
                delay = max(delay, e.retry_after)

            # Apply jitter: delay * (1 +/- jitter)
            if config.jitter > 0:
                jitter_range = delay * config.jitter
                delay += random.uniform(-jitter_range, jitter_range)  # noqa: S311
                delay = max(0.0, delay)  # Never negative

            # Notify callback (attempt is 0-indexed, report as 1-indexed)
            if on_retry is not None:
                await on_retry(attempt + 1, delay, e)

            await asyncio.sleep(delay)

    # Unreachable, but satisfies type checker
    assert last_error is not None  # noqa: S101
    raise last_error
```

**Step 2: Run all retry tests**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-core && uv run pytest tests/test_retry.py -v --tb=short`

Expected: ALL PASS

**Step 3: Commit**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-core
git add amplifier_core/utils/retry.py
git commit -m "feat: add retry_with_backoff() async retry utility"
```

---

### Task 2.6: Export retry utilities

**Files:**
- Modify: `amplifier_core/utils/__init__.py`
- Modify: `amplifier_core/__init__.py`

**Dependencies:** Task 2.5
**Effort:** S

**Step 1: Export from `amplifier_core/utils/__init__.py`**

The current file (5 lines) is:

```python
"""Utility functions for Amplifier core."""

from .truncate import SENSITIVE_KEYS, redact_secrets, truncate_values

__all__ = ["truncate_values", "redact_secrets", "SENSITIVE_KEYS"]
```

Replace it with:

```python
"""Utility functions for Amplifier core."""

from .retry import RetryConfig, classify_error_message, retry_with_backoff
from .truncate import SENSITIVE_KEYS, redact_secrets, truncate_values

__all__ = [
    "truncate_values",
    "redact_secrets",
    "SENSITIVE_KEYS",
    "RetryConfig",
    "retry_with_backoff",
    "classify_error_message",
]
```

**Step 2: Add top-level exports to `amplifier_core/__init__.py`**

Add these imports to `amplifier_core/__init__.py`, after the existing utils-related imports (there are none currently — add them after line 67, which is the `wait_for` import):

```python
from .utils.retry import RetryConfig
from .utils.retry import classify_error_message
from .utils.retry import retry_with_backoff
```

Add these to the `__all__` list. Place them after the "Testing utilities" section:

```python
    # Retry utilities
    "RetryConfig",
    "retry_with_backoff",
    "classify_error_message",
```

**Step 3: Write a test to verify top-level import**

Create `tests/test_retry_exports.py`:

```python
"""Tests for retry utility exports from amplifier_core."""


class TestRetryExports:
    """Verify retry utilities are importable from amplifier_core."""

    def test_import_from_top_level(self) -> None:
        import amplifier_core

        assert hasattr(amplifier_core, "RetryConfig")
        assert hasattr(amplifier_core, "retry_with_backoff")
        assert hasattr(amplifier_core, "classify_error_message")

    def test_import_from_utils(self) -> None:
        from amplifier_core.utils import (
            RetryConfig,
            classify_error_message,
            retry_with_backoff,
        )

        assert RetryConfig is not None
        assert retry_with_backoff is not None
        assert classify_error_message is not None

    def test_import_from_utils_retry(self) -> None:
        from amplifier_core.utils.retry import (
            RetryConfig,
            classify_error_message,
            retry_with_backoff,
        )

        assert RetryConfig is not None
        assert retry_with_backoff is not None
        assert classify_error_message is not None
```

**Step 4: Run export tests**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-core && uv run pytest tests/test_retry_exports.py -v --tb=short`

Expected: ALL PASS

**Step 5: Commit**

```bash
cd /home/bkrabach/dev/attractor-next/amplifier-core
git add amplifier_core/utils/__init__.py amplifier_core/__init__.py tests/test_retry_exports.py
git commit -m "feat: export retry utilities from amplifier_core public API"
```

---

### Task 2.7: Run full test suite and quality checks

**Files:** None (verification only)

**Dependencies:** Tasks 2.1-2.6
**Effort:** S

**Step 1: Run full test suite**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-core && uv run pytest tests/ -v --tb=short`

Expected: ALL PASS. Zero existing tests should break.

**Step 2: Run quality checks**

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-core && uv run ruff check amplifier_core/ tests/ && uv run ruff format --check amplifier_core/ tests/`

Expected: Clean.

**Step 3: Verify pytest-asyncio is available**

The `retry_with_backoff` tests use `@pytest.mark.asyncio`. If the test runner complains, check `pyproject.toml` for `pytest-asyncio` in dev dependencies. If missing:

Run: `cd /home/bkrabach/dev/attractor-next/amplifier-core && uv add --dev pytest-asyncio`

Then re-run tests.

---

## Future Work (NOT part of this plan, captured for reference)

### Provider Updates (one per provider, AFTER PR 1+2 merge)

For each provider (anthropic, openai, gemini, vllm, ollama):
1. Replace copy-pasted `_calculate_retry_delay()` with `from amplifier_core.utils.retry import retry_with_backoff`
2. Replace the retry loop with `retry_with_backoff(lambda: self._do_complete(request), config, on_retry=self._emit_retry_event)`
3. Use `classify_error_message()` as fallback in error translation
4. Use new error types where appropriate (403 -> `AccessDeniedError`, model-not-found -> `NotFoundError`, etc.)
5. Run provider tests to verify no breakage

Estimated: ~80 lines removed per provider, ~10 lines added.

### Attractor Bundle Integration

Update Attractor bundle profiles to set retry config if desired (or rely on provider defaults).

---

## Summary

| Task | PR | Files | Effort | Dependencies |
|------|----|-------|--------|-------------|
| 1.1 Failing tests for error types | 1 | `tests/test_llm_errors.py` | S | None |
| 1.2 Add 8 error classes | 1 | `amplifier_core/llm_errors.py` | S | 1.1 |
| 1.3 Export from `__init__.py` | 1 | `amplifier_core/__init__.py` | S | 1.2 |
| 1.4 `PROVIDER_RETRY` event | 1 | `amplifier_core/events.py`, `tests/test_events_provider_retry.py` | S | None |
| 1.5 Full test suite | 1 | None | S | 1.1-1.4 |
| 2.1 Failing tests: RetryConfig | 2 | `tests/test_retry.py` | S | PR 1 |
| 2.2 Failing tests: retry_with_backoff | 2 | `tests/test_retry.py` | M | 2.1 |
| 2.3 Failing tests: classify_error_message | 2 | `tests/test_retry.py` | S | 2.1 |
| 2.4 Implement RetryConfig + classify | 2 | `amplifier_core/utils/retry.py` | S | 2.1, 2.3 |
| 2.5 Implement retry_with_backoff | 2 | `amplifier_core/utils/retry.py` | M | 2.4 |
| 2.6 Export retry utilities | 2 | `amplifier_core/utils/__init__.py`, `amplifier_core/__init__.py`, `tests/test_retry_exports.py` | S | 2.5 |
| 2.7 Full test suite | 2 | None | S | 2.1-2.6 |
