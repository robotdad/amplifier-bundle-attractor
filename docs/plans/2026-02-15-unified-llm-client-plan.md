# unified-llm-client Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Build a standalone, pip-installable Python library that faithfully implements the Attractor NLSpec "Unified LLM Client" specification — a provider-agnostic LLM client with `generate()`, `stream()`, `generate_object()`, middleware chains, typed error hierarchy, retry with backoff, model catalog, and provider adapters for OpenAI, Anthropic, and Gemini.

**Architecture:** A 4-layer Python library: Provider Adapters (SDK wrappers) → Provider Utilities (retry, errors) → Core Client (routing, middleware) → High-Level API (generate, stream, generate_object). Each adapter wraps its provider's native SDK directly (OpenAI Responses API, Anthropic Messages API, Gemini API). The library is NOT an Amplifier module — it's a standalone package imported by the Attractor bundle's orchestrator.

**Tech Stack:** Python 3.11+, hatchling build, pytest + pytest-asyncio, openai SDK, anthropic SDK, google-genai SDK, pydantic for types

**Design doc:** `docs/designs/unified-llm-client.md`
**Full spec:** `specs/unified-llm-spec.md`

---

## Dependency Map

```
Phase 1: Foundation
  Task 1  (scaffolding)
  Task 2  (Role, ContentKind enums)         ← Task 1
  Task 3  (data types: ImageData..etc)      ← Task 2
  Task 4  (ContentPart tagged union)        ← Task 3
  Task 5  (Message + constructors)          ← Task 4
  Task 6  (Usage + addition)               ← Task 2
  Task 7  (FinishReason, Warning, RateLimit)← Task 2
  Task 8  (Request, ResponseFormat)         ← Task 5, 6, 7
  Task 9  (Response + accessors)            ← Task 8
  Task 10 (Tool, ToolChoice, ToolCall, ToolResult) ← Task 2
  Task 11 (Streaming types)                 ← Task 9, 10
  Task 12 (Generation result types)         ← Task 11
  Task 13 (Config types)                    ← Task 2
  Task 14 (errors.py — full hierarchy)      ← Task 1

Phase 2: Utilities
  Task 15 (retry.py)                        ← Task 14, 13
  Task 16 (middleware.py)                   ← Task 8, 9
  Task 17 (catalog.py + models.json)        ← Task 13

Phase 3: Core Client
  Task 18 (ProviderAdapter interface)       ← Task 8, 9, 11
  Task 19 (Client class + routing)          ← Task 18, 14
  Task 20 (Client.from_env + default client)← Task 19
  Task 21 (Client middleware integration)   ← Task 19, 16

Phase 4: Anthropic Adapter
  Task 22 (request translation)             ← Task 18
  Task 23 (response translation)            ← Task 22
  Task 24 (error translation)               ← Task 22, 14
  Task 25 (complete() integration)          ← Task 23, 24
  Task 26 (streaming translation)           ← Task 25, 11
  Task 27 (prompt caching)                  ← Task 25

Phase 5: OpenAI Adapter
  Task 28 (request translation — Responses API) ← Task 18
  Task 29 (response translation)            ← Task 28
  Task 30 (error translation)               ← Task 28, 14
  Task 31 (complete() integration)          ← Task 29, 30
  Task 32 (streaming translation)           ← Task 31, 11
  Task 33 (reasoning tokens)                ← Task 31

Phase 6: Gemini Adapter
  Task 34 (request translation)             ← Task 18
  Task 35 (response translation)            ← Task 34
  Task 36 (error translation — incl gRPC)   ← Task 34, 14
  Task 37 (complete() integration)          ← Task 35, 36
  Task 38 (streaming translation)           ← Task 37, 11

Phase 7: High-Level API
  Task 39 (generate() — basic)              ← Task 19, 15
  Task 40 (generate() — tool loop)          ← Task 39, 10
  Task 41 (stream() — basic)                ← Task 39, 11
  Task 42 (stream() — tool loop)            ← Task 41, 40
  Task 43 (generate_object())               ← Task 39
  Task 44 (stream_object())                 ← Task 41, 43
  Task 45 (abort + timeout)                 ← Task 39, 41

Phase 8: OpenAI-Compatible Adapter
  Task 46 (openai_compat.py)                ← Task 18, 30

Phase 9: Public API + Polish
  Task 47 (__init__.py exports)             ← All above
  Task 48 (DoD tests 8.1-8.8)              ← Task 47
  Task 49 (DoD test 8.9 cross-provider)    ← Task 48
  Task 50 (DoD test 8.10 integration smoke)← Task 49
```

---

## Phase 1: Foundation — Project Scaffolding + Types + Errors

### Task 1: Project Scaffolding

**Files:**
- Create: `../unified-llm-client/pyproject.toml`
- Create: `../unified-llm-client/unified_llm/__init__.py`
- Create: `../unified-llm-client/unified_llm/py.typed`
- Create: `../unified-llm-client/tests/__init__.py`
- Create: `../unified-llm-client/tests/unit/__init__.py`
- Create: `../unified-llm-client/tests/adapter/__init__.py`
- Create: `../unified-llm-client/tests/dod/__init__.py`

**Depends on:** Nothing
**Effort:** ~3 min

#### Step 1: Create pyproject.toml

```toml
[project]
name = "unified-llm-client"
version = "0.1.0"
description = "Provider-agnostic LLM client — faithful implementation of the Attractor Unified LLM Client spec"
license = "MIT"
readme = "README.md"
requires-python = ">=3.11"
authors = [
    { name = "Microsoft MADE:Explorations Team" },
]
dependencies = [
    "openai>=1.0.0",
    "anthropic>=0.40.0",
    "google-genai>=1.40.0",
    "pydantic>=2.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.uv]
package = true

[tool.hatch.build.targets.wheel]
packages = ["unified_llm"]

[tool.hatch.metadata]
allow-direct-references = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--import-mode=importlib"
asyncio_mode = "strict"

[dependency-groups]
dev = [
    "pytest>=9.0.0",
    "pytest-asyncio>=1.3.0",
    "ruff>=0.14.0",
]
```

#### Step 2: Create empty __init__.py files

`unified_llm/__init__.py`:
```python
"""unified-llm-client: Provider-agnostic LLM client library."""
```

`unified_llm/py.typed` — empty marker file for PEP 561.

`tests/__init__.py`, `tests/unit/__init__.py`, `tests/adapter/__init__.py`, `tests/dod/__init__.py` — all empty files.

#### Step 3: Verify project scaffolding

```bash
cd ../unified-llm-client
uv sync
uv run pytest --co -q
```

Expected: no collection errors, 0 tests collected.

#### Step 4: Commit

```bash
git add -A && git commit -m "feat: scaffold unified-llm-client project"
```

---

### Task 2: Role and ContentKind Enums

**Files:**
- Create: `../unified-llm-client/unified_llm/types.py`
- Create: `../unified-llm-client/tests/unit/test_types.py`

**Depends on:** Task 1
**Effort:** ~3 min

#### Step 1: Write failing test

`tests/unit/test_types.py`:
```python
"""Tests for unified_llm.types — enums and data model."""

from unified_llm.types import ContentKind, Role


class TestRole:
    """Role enum covers all five spec-defined roles."""

    def test_all_five_roles_exist(self) -> None:
        assert Role.SYSTEM is not None
        assert Role.USER is not None
        assert Role.ASSISTANT is not None
        assert Role.TOOL is not None
        assert Role.DEVELOPER is not None

    def test_role_values_are_strings(self) -> None:
        assert Role.SYSTEM.value == "system"
        assert Role.USER.value == "user"
        assert Role.ASSISTANT.value == "assistant"
        assert Role.TOOL.value == "tool"
        assert Role.DEVELOPER.value == "developer"


class TestContentKind:
    """ContentKind enum covers all eight spec-defined kinds."""

    def test_all_eight_kinds_exist(self) -> None:
        expected = {
            "TEXT", "IMAGE", "AUDIO", "DOCUMENT",
            "TOOL_CALL", "TOOL_RESULT", "THINKING", "REDACTED_THINKING",
        }
        actual = {k.name for k in ContentKind}
        assert actual == expected

    def test_kind_values_are_lowercase(self) -> None:
        assert ContentKind.TEXT.value == "text"
        assert ContentKind.IMAGE.value == "image"
        assert ContentKind.TOOL_CALL.value == "tool_call"
        assert ContentKind.REDACTED_THINKING.value == "redacted_thinking"
```

#### Step 2: Run test — verify it fails

```bash
cd ../unified-llm-client
uv run pytest tests/unit/test_types.py -v
```

Expected: FAIL — `ImportError: cannot import name 'ContentKind' from 'unified_llm.types'`

#### Step 3: Implement enums

`unified_llm/types.py`:
```python
"""Data model types for the unified LLM client.

Implements all 30+ types from the Unified LLM Client Specification (Sections 3.1-3.14).
"""

from __future__ import annotations

from enum import Enum


# ---------------------------------------------------------------------------
# Section 3.2 — Role
# ---------------------------------------------------------------------------


class Role(str, Enum):
    """Five roles covering the semantics of all major providers."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    DEVELOPER = "developer"


# ---------------------------------------------------------------------------
# Section 3.4 — ContentKind
# ---------------------------------------------------------------------------


class ContentKind(str, Enum):
    """Tagged union discriminator for ContentPart."""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    DOCUMENT = "document"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    THINKING = "thinking"
    REDACTED_THINKING = "redacted_thinking"
```

#### Step 4: Run test — verify it passes

```bash
uv run pytest tests/unit/test_types.py -v
```

Expected: all PASS.

#### Step 5: Commit

```bash
git add -A && git commit -m "feat: add Role and ContentKind enums"
```

---

### Task 3: Content Data Structures

**Files:**
- Modify: `unified_llm/types.py`
- Modify: `tests/unit/test_types.py`

**Depends on:** Task 2
**Effort:** ~4 min

#### Step 1: Write failing tests

Append to `tests/unit/test_types.py`:
```python
from unified_llm.types import (
    AudioData,
    DocumentData,
    ImageData,
    ThinkingData,
    ToolCallData,
    ToolResultData,
)


class TestImageData:
    """Spec §3.5 — ImageData record."""

    def test_url_image(self) -> None:
        img = ImageData(url="https://example.com/photo.jpg")
        assert img.url == "https://example.com/photo.jpg"
        assert img.data is None
        assert img.media_type is None
        assert img.detail is None

    def test_data_image(self) -> None:
        img = ImageData(data=b"\x89PNG", media_type="image/png")
        assert img.data == b"\x89PNG"
        assert img.media_type == "image/png"

    def test_detail_hint(self) -> None:
        img = ImageData(url="https://example.com/x.jpg", detail="high")
        assert img.detail == "high"


class TestToolCallData:
    """Spec §3.5 — ToolCallData record."""

    def test_construction(self) -> None:
        tc = ToolCallData(
            id="call_123", name="get_weather",
            arguments={"city": "SF"}, type="function",
        )
        assert tc.id == "call_123"
        assert tc.name == "get_weather"
        assert tc.arguments == {"city": "SF"}
        assert tc.type == "function"

    def test_default_type_is_function(self) -> None:
        tc = ToolCallData(id="c1", name="foo", arguments={})
        assert tc.type == "function"


class TestToolResultData:
    """Spec §3.5 — ToolResultData record."""

    def test_construction(self) -> None:
        tr = ToolResultData(
            tool_call_id="call_123", content="72F and sunny", is_error=False,
        )
        assert tr.tool_call_id == "call_123"
        assert tr.content == "72F and sunny"
        assert tr.is_error is False

    def test_error_result(self) -> None:
        tr = ToolResultData(
            tool_call_id="c1", content="connection timeout", is_error=True,
        )
        assert tr.is_error is True


class TestThinkingData:
    """Spec §3.5 — ThinkingData record."""

    def test_thinking_with_signature(self) -> None:
        td = ThinkingData(
            text="Let me think step by step...",
            signature="sig_abc123",
            redacted=False,
        )
        assert td.text == "Let me think step by step..."
        assert td.signature == "sig_abc123"
        assert td.redacted is False

    def test_redacted_thinking(self) -> None:
        td = ThinkingData(text="", redacted=True)
        assert td.redacted is True
        assert td.signature is None


class TestAudioData:
    """Spec §3.5 — AudioData record."""

    def test_url_audio(self) -> None:
        ad = AudioData(url="https://example.com/audio.wav")
        assert ad.url == "https://example.com/audio.wav"
        assert ad.data is None


class TestDocumentData:
    """Spec §3.5 — DocumentData record."""

    def test_with_filename(self) -> None:
        dd = DocumentData(
            data=b"%PDF", media_type="application/pdf", file_name="report.pdf",
        )
        assert dd.file_name == "report.pdf"
```

#### Step 2: Run test — verify it fails

```bash
uv run pytest tests/unit/test_types.py::TestImageData -v
```

Expected: FAIL — `ImportError`

#### Step 3: Implement data structures

Append to `unified_llm/types.py`:
```python
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Section 3.5 — Content Data Structures
# ---------------------------------------------------------------------------


@dataclass
class ImageData:
    """Image as URL, base64, or file reference. Exactly one of url/data must be set."""

    url: str | None = None
    data: bytes | None = None
    media_type: str | None = None
    detail: str | None = None


@dataclass
class AudioData:
    """Audio as URL or raw bytes with media type."""

    url: str | None = None
    data: bytes | None = None
    media_type: str | None = None


@dataclass
class DocumentData:
    """Document (PDF, etc.) as URL, base64, or file reference."""

    url: str | None = None
    data: bytes | None = None
    media_type: str | None = None
    file_name: str | None = None


@dataclass
class ToolCallData:
    """A model-initiated tool invocation."""

    id: str
    name: str
    arguments: dict[str, Any] | str
    type: str = "function"


@dataclass
class ToolResultData:
    """The result of executing a tool call."""

    tool_call_id: str
    content: str | dict[str, Any]
    is_error: bool = False
    image_data: bytes | None = None
    image_media_type: str | None = None


@dataclass
class ThinkingData:
    """Model reasoning/thinking content."""

    text: str
    signature: str | None = None
    redacted: bool = False
```

#### Step 4: Run tests — verify all pass

```bash
uv run pytest tests/unit/test_types.py -v
```

Expected: all PASS.

#### Step 5: Commit

```bash
git add -A && git commit -m "feat: add content data structures (ImageData, AudioData, etc.)"
```

---

### Task 4: ContentPart Tagged Union

**Files:**
- Modify: `unified_llm/types.py`
- Modify: `tests/unit/test_types.py`

**Depends on:** Task 3
**Effort:** ~3 min

#### Step 1: Write failing tests

Append to `tests/unit/test_types.py`:
```python
from unified_llm.types import ContentPart


class TestContentPart:
    """Spec §3.3 — ContentPart tagged union."""

    def test_text_part(self) -> None:
        part = ContentPart(kind=ContentKind.TEXT, text="hello")
        assert part.kind == ContentKind.TEXT
        assert part.text == "hello"
        assert part.image is None

    def test_image_part(self) -> None:
        img = ImageData(url="https://example.com/img.png")
        part = ContentPart(kind=ContentKind.IMAGE, image=img)
        assert part.kind == ContentKind.IMAGE
        assert part.image is img

    def test_tool_call_part(self) -> None:
        tc = ToolCallData(id="c1", name="search", arguments={"q": "test"})
        part = ContentPart(kind=ContentKind.TOOL_CALL, tool_call=tc)
        assert part.kind == ContentKind.TOOL_CALL
        assert part.tool_call is tc

    def test_thinking_part(self) -> None:
        td = ThinkingData(text="Let me reason...", signature="sig1")
        part = ContentPart(kind=ContentKind.THINKING, thinking=td)
        assert part.kind == ContentKind.THINKING
        assert part.thinking is td

    def test_kind_accepts_arbitrary_string(self) -> None:
        """Spec says kind accepts String for extension."""
        part = ContentPart(kind="custom_provider_type", text="data")
        assert part.kind == "custom_provider_type"
```

#### Step 2: Run test — verify it fails

```bash
uv run pytest tests/unit/test_types.py::TestContentPart -v
```

Expected: FAIL — `ImportError`

#### Step 3: Implement ContentPart

Append to `unified_llm/types.py`:
```python
@dataclass
class ContentPart:
    """Tagged union for message content. The kind field determines which data field is populated.

    Spec §3.3: kind accepts both ContentKind enum values and arbitrary strings
    for provider-specific extension.
    """

    kind: ContentKind | str
    text: str | None = None
    image: ImageData | None = None
    audio: AudioData | None = None
    document: DocumentData | None = None
    tool_call: ToolCallData | None = None
    tool_result: ToolResultData | None = None
    thinking: ThinkingData | None = None
```

#### Step 4: Run tests — verify all pass

```bash
uv run pytest tests/unit/test_types.py -v
```

Expected: all PASS.

#### Step 5: Commit

```bash
git add -A && git commit -m "feat: add ContentPart tagged union"
```

---

### Task 5: Message with Convenience Constructors

**Files:**
- Modify: `unified_llm/types.py`
- Modify: `tests/unit/test_types.py`

**Depends on:** Task 4
**Effort:** ~4 min

#### Step 1: Write failing tests

Append to `tests/unit/test_types.py`:
```python
from unified_llm.types import Message


class TestMessage:
    """Spec §3.1 — Message record with convenience constructors."""

    def test_basic_construction(self) -> None:
        msg = Message(
            role=Role.USER,
            content=[ContentPart(kind=ContentKind.TEXT, text="Hello")],
        )
        assert msg.role == Role.USER
        assert len(msg.content) == 1
        assert msg.name is None
        assert msg.tool_call_id is None

    def test_text_accessor_concatenates(self) -> None:
        """Spec: .text returns concatenation of all TEXT parts."""
        msg = Message(
            role=Role.ASSISTANT,
            content=[
                ContentPart(kind=ContentKind.TEXT, text="Hello "),
                ContentPart(kind=ContentKind.TOOL_CALL, tool_call=ToolCallData(
                    id="c1", name="foo", arguments={},
                )),
                ContentPart(kind=ContentKind.TEXT, text="world"),
            ],
        )
        assert msg.text == "Hello world"

    def test_text_accessor_empty_when_no_text_parts(self) -> None:
        msg = Message(role=Role.ASSISTANT, content=[])
        assert msg.text == ""

    def test_system_constructor(self) -> None:
        msg = Message.system("You are helpful.")
        assert msg.role == Role.SYSTEM
        assert msg.content[0].kind == ContentKind.TEXT
        assert msg.content[0].text == "You are helpful."

    def test_user_constructor(self) -> None:
        msg = Message.user("What is 2+2?")
        assert msg.role == Role.USER
        assert msg.text == "What is 2+2?"

    def test_assistant_constructor(self) -> None:
        msg = Message.assistant("The answer is 4.")
        assert msg.role == Role.ASSISTANT
        assert msg.text == "The answer is 4."

    def test_tool_result_constructor(self) -> None:
        msg = Message.tool_result(
            tool_call_id="call_123", content="72F and sunny", is_error=False,
        )
        assert msg.role == Role.TOOL
        assert msg.tool_call_id == "call_123"
        assert msg.content[0].kind == ContentKind.TOOL_RESULT
        assert msg.content[0].tool_result is not None
        assert msg.content[0].tool_result.tool_call_id == "call_123"
        assert msg.content[0].tool_result.content == "72F and sunny"
```

#### Step 2: Run test — verify it fails

```bash
uv run pytest tests/unit/test_types.py::TestMessage -v
```

Expected: FAIL — `ImportError`

#### Step 3: Implement Message

Append to `unified_llm/types.py`:
```python
@dataclass
class Message:
    """The fundamental unit of conversation (Spec §3.1).

    A conversation is an ordered List[Message].
    """

    role: Role
    content: list[ContentPart]
    name: str | None = None
    tool_call_id: str | None = None

    @property
    def text(self) -> str:
        """Concatenate text from all TEXT content parts. Returns '' if none."""
        return "".join(
            part.text for part in self.content
            if part.kind == ContentKind.TEXT and part.text is not None
        )

    @classmethod
    def system(cls, text: str) -> Message:
        """Convenience constructor for system messages."""
        return cls(role=Role.SYSTEM, content=[ContentPart(kind=ContentKind.TEXT, text=text)])

    @classmethod
    def user(cls, text: str) -> Message:
        """Convenience constructor for user messages."""
        return cls(role=Role.USER, content=[ContentPart(kind=ContentKind.TEXT, text=text)])

    @classmethod
    def assistant(cls, text: str) -> Message:
        """Convenience constructor for assistant messages."""
        return cls(role=Role.ASSISTANT, content=[ContentPart(kind=ContentKind.TEXT, text=text)])

    @classmethod
    def tool_result(
        cls, *, tool_call_id: str, content: str | dict[str, Any], is_error: bool = False,
    ) -> Message:
        """Convenience constructor for tool result messages."""
        return cls(
            role=Role.TOOL,
            content=[ContentPart(
                kind=ContentKind.TOOL_RESULT,
                tool_result=ToolResultData(
                    tool_call_id=tool_call_id, content=content, is_error=is_error,
                ),
            )],
            tool_call_id=tool_call_id,
        )
```

#### Step 4: Run tests — verify all pass

```bash
uv run pytest tests/unit/test_types.py -v
```

Expected: all PASS.

#### Step 5: Commit

```bash
git add -A && git commit -m "feat: add Message with convenience constructors and .text accessor"
```

---

### Task 6: Usage with Addition Operator

**Files:**
- Modify: `unified_llm/types.py`
- Modify: `tests/unit/test_types.py`

**Depends on:** Task 2
**Effort:** ~3 min

#### Step 1: Write failing tests

Append to `tests/unit/test_types.py`:
```python
from unified_llm.types import Usage


class TestUsage:
    """Spec §3.9 — Usage with addition operator."""

    def test_basic_construction(self) -> None:
        u = Usage(input_tokens=100, output_tokens=50, total_tokens=150)
        assert u.input_tokens == 100
        assert u.output_tokens == 50
        assert u.total_tokens == 150

    def test_optional_fields_default_none(self) -> None:
        u = Usage(input_tokens=10, output_tokens=5, total_tokens=15)
        assert u.reasoning_tokens is None
        assert u.cache_read_tokens is None
        assert u.cache_write_tokens is None
        assert u.raw is None

    def test_addition_sums_integer_fields(self) -> None:
        a = Usage(input_tokens=100, output_tokens=50, total_tokens=150)
        b = Usage(input_tokens=200, output_tokens=80, total_tokens=280)
        result = a + b
        assert result.input_tokens == 300
        assert result.output_tokens == 130
        assert result.total_tokens == 430

    def test_addition_handles_optional_fields(self) -> None:
        """If either side is non-None, sum them (treating None as 0)."""
        a = Usage(input_tokens=10, output_tokens=5, total_tokens=15, reasoning_tokens=100)
        b = Usage(input_tokens=20, output_tokens=10, total_tokens=30, reasoning_tokens=None)
        result = a + b
        assert result.reasoning_tokens == 100

    def test_addition_both_none_stays_none(self) -> None:
        a = Usage(input_tokens=10, output_tokens=5, total_tokens=15)
        b = Usage(input_tokens=20, output_tokens=10, total_tokens=30)
        result = a + b
        assert result.reasoning_tokens is None
        assert result.cache_read_tokens is None

    def test_addition_both_present(self) -> None:
        a = Usage(
            input_tokens=10, output_tokens=5, total_tokens=15,
            cache_read_tokens=50, cache_write_tokens=10,
        )
        b = Usage(
            input_tokens=20, output_tokens=10, total_tokens=30,
            cache_read_tokens=30, cache_write_tokens=5,
        )
        result = a + b
        assert result.cache_read_tokens == 80
        assert result.cache_write_tokens == 15
```

#### Step 2: Run test — verify it fails

```bash
uv run pytest tests/unit/test_types.py::TestUsage -v
```

Expected: FAIL — `ImportError`

#### Step 3: Implement Usage

Append to `unified_llm/types.py`:
```python
def _add_optional(a: int | None, b: int | None) -> int | None:
    """Sum two optional ints: both None → None, else treat None as 0."""
    if a is None and b is None:
        return None
    return (a or 0) + (b or 0)


@dataclass
class Usage:
    """Token usage statistics (Spec §3.9). Supports addition for multi-step aggregation."""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    reasoning_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    raw: dict[str, Any] | None = None

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            reasoning_tokens=_add_optional(self.reasoning_tokens, other.reasoning_tokens),
            cache_read_tokens=_add_optional(self.cache_read_tokens, other.cache_read_tokens),
            cache_write_tokens=_add_optional(self.cache_write_tokens, other.cache_write_tokens),
        )
```

#### Step 4: Run tests — verify all pass

```bash
uv run pytest tests/unit/test_types.py -v
```

Expected: all PASS.

#### Step 5: Commit

```bash
git add -A && git commit -m "feat: add Usage with addition operator"
```

---

### Task 7: FinishReason, Warning, RateLimitInfo

**Files:**
- Modify: `unified_llm/types.py`
- Modify: `tests/unit/test_types.py`

**Depends on:** Task 2
**Effort:** ~3 min

#### Step 1: Write failing tests

Append to `tests/unit/test_types.py`:
```python
from unified_llm.types import FinishReason, RateLimitInfo, Warning


class TestFinishReason:
    """Spec §3.8 — Dual-representation finish reason."""

    def test_unified_reason(self) -> None:
        fr = FinishReason(reason="stop", raw="end_turn")
        assert fr.reason == "stop"
        assert fr.raw == "end_turn"

    def test_raw_defaults_none(self) -> None:
        fr = FinishReason(reason="tool_calls")
        assert fr.raw is None


class TestWarning:
    """Spec §3.11 — Warning record."""

    def test_basic(self) -> None:
        w = Warning(message="Token limit approaching", code="token_limit")
        assert w.message == "Token limit approaching"
        assert w.code == "token_limit"


class TestRateLimitInfo:
    """Spec §3.12 — RateLimitInfo from response headers."""

    def test_all_fields(self) -> None:
        rli = RateLimitInfo(
            requests_remaining=99, requests_limit=100,
            tokens_remaining=9000, tokens_limit=10000,
        )
        assert rli.requests_remaining == 99

    def test_all_optional(self) -> None:
        rli = RateLimitInfo()
        assert rli.requests_remaining is None
        assert rli.reset_at is None
```

#### Step 2: Run test — verify it fails

```bash
uv run pytest tests/unit/test_types.py::TestFinishReason -v
```

Expected: FAIL — `ImportError`

#### Step 3: Implement types

Append to `unified_llm/types.py`:
```python
from datetime import datetime


# ---------------------------------------------------------------------------
# Section 3.8 — FinishReason
# ---------------------------------------------------------------------------


@dataclass
class FinishReason:
    """Dual representation: unified reason + provider-specific raw value."""

    reason: str  # "stop", "length", "tool_calls", "content_filter", "error", "other"
    raw: str | None = None


# ---------------------------------------------------------------------------
# Section 3.11 — Warning
# ---------------------------------------------------------------------------


@dataclass
class Warning:
    """Non-fatal issue from the provider."""

    message: str
    code: str | None = None


# ---------------------------------------------------------------------------
# Section 3.12 — RateLimitInfo
# ---------------------------------------------------------------------------


@dataclass
class RateLimitInfo:
    """Rate limit metadata from provider response headers."""

    requests_remaining: int | None = None
    requests_limit: int | None = None
    tokens_remaining: int | None = None
    tokens_limit: int | None = None
    reset_at: datetime | None = None
```

#### Step 4: Run tests — verify all pass

```bash
uv run pytest tests/unit/test_types.py -v
```

Expected: all PASS.

#### Step 5: Commit

```bash
git add -A && git commit -m "feat: add FinishReason, Warning, RateLimitInfo types"
```

---

### Task 8: Request and ResponseFormat

**Files:**
- Modify: `unified_llm/types.py`
- Modify: `tests/unit/test_types.py`

**Depends on:** Task 5, 6, 7
**Effort:** ~3 min

#### Step 1: Write failing tests

Append to `tests/unit/test_types.py`:
```python
from unified_llm.types import Request, ResponseFormat


class TestResponseFormat:
    """Spec §3.10 — ResponseFormat."""

    def test_text_format(self) -> None:
        rf = ResponseFormat(type="text")
        assert rf.type == "text"
        assert rf.json_schema is None
        assert rf.strict is False

    def test_json_schema_format(self) -> None:
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        rf = ResponseFormat(type="json_schema", json_schema=schema, strict=True)
        assert rf.json_schema == schema
        assert rf.strict is True


class TestRequest:
    """Spec §3.6 — Request record."""

    def test_minimal_request(self) -> None:
        req = Request(
            model="claude-sonnet-4-20250514",
            messages=[Message.user("Hello")],
        )
        assert req.model == "claude-sonnet-4-20250514"
        assert len(req.messages) == 1
        assert req.provider is None
        assert req.tools is None
        assert req.temperature is None

    def test_full_request(self) -> None:
        req = Request(
            model="gpt-5.2",
            messages=[Message.user("test")],
            provider="openai",
            temperature=0.7,
            max_tokens=500,
            reasoning_effort="high",
            provider_options={"openai": {"reasoning": {"effort": "high"}}},
        )
        assert req.provider == "openai"
        assert req.temperature == 0.7
        assert req.max_tokens == 500
        assert req.reasoning_effort == "high"
```

#### Step 2: Run test — verify it fails

```bash
uv run pytest tests/unit/test_types.py::TestRequest -v
```

Expected: FAIL — `ImportError`

#### Step 3: Implement Request and ResponseFormat

Append to `unified_llm/types.py`:
```python
# ---------------------------------------------------------------------------
# Section 3.10 — ResponseFormat
# ---------------------------------------------------------------------------


@dataclass
class ResponseFormat:
    """Structured output format specification."""

    type: str  # "text", "json", "json_schema"
    json_schema: dict[str, Any] | None = None
    strict: bool = False


# ---------------------------------------------------------------------------
# Section 3.6 — Request
# ---------------------------------------------------------------------------


@dataclass
class Request:
    """The single input type for both complete() and stream() (Spec §3.6)."""

    model: str
    messages: list[Message]
    provider: str | None = None
    tools: list[Any] | None = None  # list[ToolDefinition] — forward ref resolved in Task 10
    tool_choice: Any | None = None  # ToolChoice — forward ref resolved in Task 10
    response_format: ResponseFormat | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stop_sequences: list[str] | None = None
    reasoning_effort: str | None = None
    metadata: dict[str, str] | None = None
    provider_options: dict[str, Any] | None = None
```

Note to implementer: The `tools` and `tool_choice` fields use `Any` temporarily and will be typed properly in Task 10 when Tool/ToolChoice are defined.

#### Step 4: Run tests — verify all pass

```bash
uv run pytest tests/unit/test_types.py -v
```

Expected: all PASS.

#### Step 5: Commit

```bash
git add -A && git commit -m "feat: add Request and ResponseFormat types"
```

---

### Task 9: Response with Convenience Accessors

**Files:**
- Modify: `unified_llm/types.py`
- Modify: `tests/unit/test_types.py`

**Depends on:** Task 8
**Effort:** ~4 min

#### Step 1: Write failing tests

Append to `tests/unit/test_types.py`:
```python
from unified_llm.types import Response


class TestResponse:
    """Spec §3.7 — Response with convenience accessors."""

    def _make_response(self) -> Response:
        return Response(
            id="resp_123",
            model="claude-sonnet-4-20250514",
            provider="anthropic",
            message=Message(
                role=Role.ASSISTANT,
                content=[
                    ContentPart(kind=ContentKind.THINKING, thinking=ThinkingData(
                        text="Reasoning here", signature="sig1",
                    )),
                    ContentPart(kind=ContentKind.TEXT, text="The answer is 42."),
                    ContentPart(kind=ContentKind.TOOL_CALL, tool_call=ToolCallData(
                        id="c1", name="calc", arguments={"expr": "6*7"},
                    )),
                ],
            ),
            finish_reason=FinishReason(reason="tool_calls", raw="tool_use"),
            usage=Usage(input_tokens=100, output_tokens=50, total_tokens=150),
        )

    def test_text_accessor(self) -> None:
        resp = self._make_response()
        assert resp.text == "The answer is 42."

    def test_tool_calls_accessor(self) -> None:
        resp = self._make_response()
        calls = resp.tool_calls
        assert len(calls) == 1
        assert calls[0].name == "calc"

    def test_reasoning_accessor(self) -> None:
        resp = self._make_response()
        assert resp.reasoning == "Reasoning here"

    def test_reasoning_none_when_absent(self) -> None:
        resp = Response(
            id="r1", model="m", provider="p",
            message=Message.assistant("Hello"),
            finish_reason=FinishReason(reason="stop"),
            usage=Usage(input_tokens=1, output_tokens=1, total_tokens=2),
        )
        assert resp.reasoning is None

    def test_raw_and_warnings_default(self) -> None:
        resp = Response(
            id="r1", model="m", provider="p",
            message=Message.assistant("Hi"),
            finish_reason=FinishReason(reason="stop"),
            usage=Usage(input_tokens=1, output_tokens=1, total_tokens=2),
        )
        assert resp.raw is None
        assert resp.warnings == []
        assert resp.rate_limit is None
```

#### Step 2: Run test — verify it fails

```bash
uv run pytest tests/unit/test_types.py::TestResponse -v
```

Expected: FAIL — `ImportError`

#### Step 3: Implement Response

Append to `unified_llm/types.py`:
```python
# ---------------------------------------------------------------------------
# Section 3.7 — Response
# ---------------------------------------------------------------------------


@dataclass
class Response:
    """Unified response from any provider (Spec §3.7)."""

    id: str
    model: str
    provider: str
    message: Message
    finish_reason: FinishReason
    usage: Usage
    raw: dict[str, Any] | None = None
    warnings: list[Warning] = field(default_factory=list)
    rate_limit: RateLimitInfo | None = None

    @property
    def text(self) -> str:
        """Concatenated text from all text parts."""
        return self.message.text

    @property
    def tool_calls(self) -> list[ToolCallData]:
        """Extracted tool calls from the message."""
        return [
            part.tool_call for part in self.message.content
            if part.kind == ContentKind.TOOL_CALL and part.tool_call is not None
        ]

    @property
    def reasoning(self) -> str | None:
        """Concatenated reasoning/thinking text, or None if absent."""
        parts = [
            part.thinking.text for part in self.message.content
            if part.kind in (ContentKind.THINKING, ContentKind.REDACTED_THINKING)
            and part.thinking is not None and part.thinking.text
        ]
        return "".join(parts) if parts else None
```

#### Step 4: Run tests — verify all pass

```bash
uv run pytest tests/unit/test_types.py -v
```

Expected: all PASS.

#### Step 5: Commit

```bash
git add -A && git commit -m "feat: add Response with .text, .tool_calls, .reasoning accessors"
```

---

### Task 10: Tool, ToolChoice, ToolCall, ToolResult

**Files:**
- Modify: `unified_llm/types.py`
- Modify: `tests/unit/test_types.py`

**Depends on:** Task 2
**Effort:** ~4 min

#### Step 1: Write failing tests

Append to `tests/unit/test_types.py`:
```python
from unified_llm.types import Tool, ToolCall, ToolChoice, ToolResult


class TestTool:
    """Spec §5.1 — Tool definition."""

    def test_passive_tool(self) -> None:
        t = Tool(
            name="get_weather",
            description="Get weather for a location",
            parameters={
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        )
        assert t.name == "get_weather"
        assert t.execute is None

    def test_active_tool(self) -> None:
        def handler(**kwargs: object) -> str:
            return "72F"

        t = Tool(
            name="get_weather",
            description="Get weather",
            parameters={"type": "object", "properties": {}},
            execute=handler,
        )
        assert t.execute is not None


class TestToolChoice:
    """Spec §5.3 — ToolChoice modes."""

    def test_auto_mode(self) -> None:
        tc = ToolChoice(mode="auto")
        assert tc.mode == "auto"
        assert tc.tool_name is None

    def test_named_mode(self) -> None:
        tc = ToolChoice(mode="named", tool_name="get_weather")
        assert tc.mode == "named"
        assert tc.tool_name == "get_weather"


class TestToolCall:
    """Spec §5.4 — ToolCall extracted from responses."""

    def test_construction(self) -> None:
        tc = ToolCall(id="call_1", name="search", arguments={"q": "test"})
        assert tc.raw_arguments is None

    def test_with_raw_arguments(self) -> None:
        tc = ToolCall(
            id="call_1", name="search",
            arguments={"q": "test"}, raw_arguments='{"q": "test"}',
        )
        assert tc.raw_arguments == '{"q": "test"}'


class TestToolResult:
    """Spec §5.4 — ToolResult from execute handlers."""

    def test_success_result(self) -> None:
        tr = ToolResult(tool_call_id="c1", content="72F", is_error=False)
        assert tr.is_error is False

    def test_error_result(self) -> None:
        tr = ToolResult(tool_call_id="c1", content="timeout", is_error=True)
        assert tr.is_error is True
```

#### Step 2: Run test — verify it fails

```bash
uv run pytest tests/unit/test_types.py::TestTool -v
```

Expected: FAIL — `ImportError`

#### Step 3: Implement tool types

Append to `unified_llm/types.py`:
```python
from collections.abc import Callable


# ---------------------------------------------------------------------------
# Section 5.1 — Tool
# ---------------------------------------------------------------------------


@dataclass
class Tool:
    """Tool definition with optional execute handler (Spec §5.1)."""

    name: str
    description: str
    parameters: dict[str, Any]
    execute: Callable[..., Any] | None = None


# ---------------------------------------------------------------------------
# Section 5.3 — ToolChoice
# ---------------------------------------------------------------------------


@dataclass
class ToolChoice:
    """Controls how the model uses tools (Spec §5.3)."""

    mode: str  # "auto", "none", "required", "named"
    tool_name: str | None = None


# ---------------------------------------------------------------------------
# Section 5.4 — ToolCall and ToolResult
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    """A tool invocation extracted from a response."""

    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str | None = None


@dataclass
class ToolResult:
    """The output of executing a tool call."""

    tool_call_id: str
    content: str | dict[str, Any] | list[Any]
    is_error: bool = False
```

Now update the `Request` dataclass to use proper types instead of `Any`. Replace the forward-ref annotations:

In `Request.__init__`, change:
- `tools: list[Any] | None = None` → `tools: list[Tool] | None = None`
- `tool_choice: Any | None = None` → `tool_choice: ToolChoice | None = None`

(This requires reordering the dataclass definitions in types.py so Tool and ToolChoice are defined before Request.)

#### Step 4: Run tests — verify all pass

```bash
uv run pytest tests/unit/test_types.py -v
```

Expected: all PASS.

#### Step 5: Commit

```bash
git add -A && git commit -m "feat: add Tool, ToolChoice, ToolCall, ToolResult types"
```

---

### Task 11: Streaming Types

**Files:**
- Modify: `unified_llm/types.py`
- Modify: `tests/unit/test_types.py`

**Depends on:** Task 9, 10
**Effort:** ~4 min

#### Step 1: Write failing tests

Append to `tests/unit/test_types.py`:
```python
from unified_llm.types import StreamAccumulator, StreamEvent, StreamEventType


class TestStreamEventType:
    """Spec §3.14 — StreamEventType enum with 13 types."""

    def test_all_thirteen_types_exist(self) -> None:
        expected = {
            "STREAM_START", "TEXT_START", "TEXT_DELTA", "TEXT_END",
            "REASONING_START", "REASONING_DELTA", "REASONING_END",
            "TOOL_CALL_START", "TOOL_CALL_DELTA", "TOOL_CALL_END",
            "FINISH", "ERROR", "PROVIDER_EVENT",
        }
        actual = {t.name for t in StreamEventType}
        assert actual == expected


class TestStreamEvent:
    """Spec §3.13 — StreamEvent record."""

    def test_text_delta_event(self) -> None:
        evt = StreamEvent(
            type=StreamEventType.TEXT_DELTA, delta="Hello", text_id="t1",
        )
        assert evt.type == StreamEventType.TEXT_DELTA
        assert evt.delta == "Hello"
        assert evt.text_id == "t1"

    def test_finish_event(self) -> None:
        evt = StreamEvent(
            type=StreamEventType.FINISH,
            finish_reason=FinishReason(reason="stop"),
            usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
        )
        assert evt.finish_reason is not None
        assert evt.usage is not None

    def test_error_event(self) -> None:
        evt = StreamEvent(type=StreamEventType.ERROR)
        assert evt.error is None  # error field exists but defaults to None

    def test_type_accepts_string(self) -> None:
        """Spec: type accepts String for provider-specific events."""
        evt = StreamEvent(type="custom_event")
        assert evt.type == "custom_event"


class TestStreamAccumulator:
    """Spec §4.4 — StreamAccumulator assembles events into Response."""

    def test_accumulate_text_deltas(self) -> None:
        acc = StreamAccumulator()
        acc.process(StreamEvent(type=StreamEventType.TEXT_START, text_id="t1"))
        acc.process(StreamEvent(type=StreamEventType.TEXT_DELTA, delta="Hello ", text_id="t1"))
        acc.process(StreamEvent(type=StreamEventType.TEXT_DELTA, delta="world", text_id="t1"))
        acc.process(StreamEvent(type=StreamEventType.TEXT_END, text_id="t1"))
        acc.process(StreamEvent(
            type=StreamEventType.FINISH,
            finish_reason=FinishReason(reason="stop"),
            usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
        ))
        resp = acc.response()
        assert resp.text == "Hello world"
        assert resp.finish_reason.reason == "stop"
        assert resp.usage.total_tokens == 15

    def test_accumulate_tool_call(self) -> None:
        acc = StreamAccumulator()
        acc.process(StreamEvent(
            type=StreamEventType.TOOL_CALL_START,
            tool_call=ToolCall(id="c1", name="search", arguments={}),
        ))
        acc.process(StreamEvent(
            type=StreamEventType.TOOL_CALL_DELTA,
            tool_call=ToolCall(id="c1", name="search", arguments={}, raw_arguments='{"q":'),
        ))
        acc.process(StreamEvent(
            type=StreamEventType.TOOL_CALL_END,
            tool_call=ToolCall(id="c1", name="search", arguments={"q": "test"}),
        ))
        acc.process(StreamEvent(
            type=StreamEventType.FINISH,
            finish_reason=FinishReason(reason="tool_calls"),
            usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
        ))
        resp = acc.response()
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "search"
```

#### Step 2: Run test — verify it fails

```bash
uv run pytest tests/unit/test_types.py::TestStreamEventType -v
```

Expected: FAIL — `ImportError`

#### Step 3: Implement streaming types

Append to `unified_llm/types.py`:
```python
# ---------------------------------------------------------------------------
# Section 3.14 — StreamEventType
# ---------------------------------------------------------------------------


class StreamEventType(str, Enum):
    """Thirteen stream event types following the start/delta/end pattern."""

    STREAM_START = "stream_start"
    TEXT_START = "text_start"
    TEXT_DELTA = "text_delta"
    TEXT_END = "text_end"
    REASONING_START = "reasoning_start"
    REASONING_DELTA = "reasoning_delta"
    REASONING_END = "reasoning_end"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_DELTA = "tool_call_delta"
    TOOL_CALL_END = "tool_call_end"
    FINISH = "finish"
    ERROR = "error"
    PROVIDER_EVENT = "provider_event"


# ---------------------------------------------------------------------------
# Section 3.13 — StreamEvent
# ---------------------------------------------------------------------------


@dataclass
class StreamEvent:
    """Unified stream event (Spec §3.13)."""

    type: StreamEventType | str

    # Text events
    delta: str | None = None
    text_id: str | None = None

    # Reasoning events
    reasoning_delta: str | None = None

    # Tool call events
    tool_call: ToolCall | None = None

    # Finish event
    finish_reason: FinishReason | None = None
    usage: Usage | None = None
    response: Response | None = None

    # Error event
    error: Any | None = None  # SDKError — typed in errors.py

    # Passthrough
    raw: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Section 4.4 — StreamAccumulator
# ---------------------------------------------------------------------------


class StreamAccumulator:
    """Collects stream events into a complete Response (Spec §4.4)."""

    def __init__(self) -> None:
        self._text_parts: dict[str | None, list[str]] = {}
        self._reasoning_parts: list[str] = []
        self._tool_calls: list[ToolCall] = []
        self._finish_reason: FinishReason | None = None
        self._usage: Usage | None = None
        self._response_id: str = ""
        self._model: str = ""
        self._provider: str = ""

    def process(self, event: StreamEvent) -> None:
        """Process a single stream event."""
        if event.type == StreamEventType.TEXT_DELTA and event.delta:
            key = event.text_id
            self._text_parts.setdefault(key, []).append(event.delta)
        elif event.type == StreamEventType.REASONING_DELTA and event.reasoning_delta:
            self._reasoning_parts.append(event.reasoning_delta)
        elif event.type == StreamEventType.TOOL_CALL_END and event.tool_call:
            self._tool_calls.append(event.tool_call)
        elif event.type == StreamEventType.FINISH:
            self._finish_reason = event.finish_reason
            self._usage = event.usage
            if event.response:
                self._response_id = event.response.id
                self._model = event.response.model
                self._provider = event.response.provider

    def response(self) -> Response:
        """Build the accumulated Response. Call after stream ends."""
        content: list[ContentPart] = []

        # Assemble text
        full_text = "".join(
            "".join(parts) for parts in self._text_parts.values()
        )
        if full_text:
            content.append(ContentPart(kind=ContentKind.TEXT, text=full_text))

        # Assemble reasoning
        if self._reasoning_parts:
            reasoning_text = "".join(self._reasoning_parts)
            content.append(ContentPart(
                kind=ContentKind.THINKING,
                thinking=ThinkingData(text=reasoning_text),
            ))

        # Assemble tool calls
        for tc in self._tool_calls:
            content.append(ContentPart(
                kind=ContentKind.TOOL_CALL,
                tool_call=ToolCallData(
                    id=tc.id, name=tc.name, arguments=tc.arguments,
                ),
            ))

        return Response(
            id=self._response_id,
            model=self._model,
            provider=self._provider,
            message=Message(role=Role.ASSISTANT, content=content),
            finish_reason=self._finish_reason or FinishReason(reason="other"),
            usage=self._usage or Usage(input_tokens=0, output_tokens=0, total_tokens=0),
        )
```

#### Step 4: Run tests — verify all pass

```bash
uv run pytest tests/unit/test_types.py -v
```

Expected: all PASS.

#### Step 5: Commit

```bash
git add -A && git commit -m "feat: add StreamEventType, StreamEvent, StreamAccumulator"
```

---

### Task 12: Generation Result Types

**Files:**
- Modify: `unified_llm/types.py`
- Modify: `tests/unit/test_types.py`

**Depends on:** Task 11
**Effort:** ~3 min

#### Step 1: Write failing tests

Append to `tests/unit/test_types.py`:
```python
from unified_llm.types import GenerateResult, StepResult


class TestStepResult:
    """Spec §4.3 — StepResult for each tool loop iteration."""

    def test_construction(self) -> None:
        resp = Response(
            id="r1", model="m", provider="p",
            message=Message.assistant("Hi"),
            finish_reason=FinishReason(reason="stop"),
            usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
        )
        step = StepResult(
            text="Hi", tool_calls=[], tool_results=[],
            finish_reason=FinishReason(reason="stop"),
            usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
            response=resp, warnings=[],
        )
        assert step.text == "Hi"
        assert step.reasoning is None


class TestGenerateResult:
    """Spec §4.3 — GenerateResult aggregating steps."""

    def test_construction(self) -> None:
        resp = Response(
            id="r1", model="m", provider="p",
            message=Message.assistant("Final answer"),
            finish_reason=FinishReason(reason="stop"),
            usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
        )
        result = GenerateResult(
            text="Final answer",
            finish_reason=FinishReason(reason="stop"),
            usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
            total_usage=Usage(input_tokens=30, output_tokens=15, total_tokens=45),
            steps=[],
            response=resp,
        )
        assert result.text == "Final answer"
        assert result.total_usage.total_tokens == 45
        assert result.output is None
```

#### Step 2: Run test — verify it fails

```bash
uv run pytest tests/unit/test_types.py::TestStepResult -v
```

Expected: FAIL — `ImportError`

#### Step 3: Implement generation result types

Append to `unified_llm/types.py`:
```python
# ---------------------------------------------------------------------------
# Section 4.3 — StepResult and GenerateResult
# ---------------------------------------------------------------------------


@dataclass
class StepResult:
    """Result of a single step in the tool loop."""

    text: str
    tool_calls: list[ToolCall]
    tool_results: list[ToolResult]
    finish_reason: FinishReason
    usage: Usage
    response: Response
    warnings: list[Warning]
    reasoning: str | None = None


@dataclass
class GenerateResult:
    """Aggregated result from generate() across all steps."""

    text: str
    finish_reason: FinishReason
    usage: Usage
    total_usage: Usage
    steps: list[StepResult]
    response: Response
    reasoning: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    output: Any | None = None  # Parsed structured output (generate_object)
```

#### Step 4: Run tests — verify all pass

```bash
uv run pytest tests/unit/test_types.py -v
```

Expected: all PASS.

#### Step 5: Commit

```bash
git add -A && git commit -m "feat: add StepResult and GenerateResult types"
```

---

### Task 13: Configuration Types

**Files:**
- Modify: `unified_llm/types.py`
- Modify: `tests/unit/test_types.py`

**Depends on:** Task 2
**Effort:** ~2 min

#### Step 1: Write failing tests

Append to `tests/unit/test_types.py`:
```python
from unified_llm.types import AdapterTimeout, ModelInfo, TimeoutConfig


class TestTimeoutConfig:
    """Spec §4.7 — Timeout configuration."""

    def test_defaults(self) -> None:
        tc = TimeoutConfig()
        assert tc.total is None
        assert tc.per_step is None


class TestAdapterTimeout:
    """Spec §4.7 — Adapter-level timeout scopes."""

    def test_defaults(self) -> None:
        at = AdapterTimeout()
        assert at.connect == 10.0
        assert at.request == 120.0
        assert at.stream_read == 30.0


class TestModelInfo:
    """Spec §2.9 — Model catalog entry."""

    def test_construction(self) -> None:
        mi = ModelInfo(
            id="claude-sonnet-4-20250514",
            provider="anthropic",
            display_name="Claude Sonnet 4",
            context_window=200000,
            supports_tools=True,
            supports_vision=True,
            supports_reasoning=True,
        )
        assert mi.id == "claude-sonnet-4-20250514"
        assert mi.max_output is None
        assert mi.input_cost_per_million is None
        assert mi.aliases == []
```

#### Step 2: Run test — verify it fails

```bash
uv run pytest tests/unit/test_types.py::TestTimeoutConfig -v
```

Expected: FAIL — `ImportError`

#### Step 3: Implement config types

Append to `unified_llm/types.py`:
```python
# ---------------------------------------------------------------------------
# Section 4.7 — Timeout Configuration
# ---------------------------------------------------------------------------


@dataclass
class TimeoutConfig:
    """Multi-step timeout configuration."""

    total: float | None = None
    per_step: float | None = None


@dataclass
class AdapterTimeout:
    """Adapter-level timeout scopes with sensible defaults."""

    connect: float = 10.0
    request: float = 120.0
    stream_read: float = 30.0


# ---------------------------------------------------------------------------
# Section 2.9 — ModelInfo (catalog entry)
# ---------------------------------------------------------------------------


@dataclass
class ModelInfo:
    """A model catalog entry."""

    id: str
    provider: str
    display_name: str
    context_window: int
    supports_tools: bool
    supports_vision: bool
    supports_reasoning: bool
    max_output: int | None = None
    input_cost_per_million: float | None = None
    output_cost_per_million: float | None = None
    aliases: list[str] = field(default_factory=list)
```

#### Step 4: Run tests — verify all pass

```bash
uv run pytest tests/unit/test_types.py -v
```

Expected: all PASS.

#### Step 5: Commit

```bash
git add -A && git commit -m "feat: add TimeoutConfig, AdapterTimeout, ModelInfo types"
```

---

### Task 14: Error Hierarchy

**Files:**
- Create: `../unified-llm-client/unified_llm/errors.py`
- Create: `../unified-llm-client/tests/unit/test_errors.py`

**Depends on:** Task 1
**Effort:** ~5 min

#### Step 1: Write failing tests

`tests/unit/test_errors.py`:
```python
"""Tests for unified_llm.errors — full 13-type error hierarchy."""

import unified_llm.errors as E


class TestErrorHierarchy:
    """Spec §6.1 — All errors inherit from SDKError."""

    def test_sdk_error_is_base(self) -> None:
        assert issubclass(E.ProviderError, E.SDKError)
        assert issubclass(E.NetworkError, E.SDKError)
        assert issubclass(E.StreamError, E.SDKError)
        assert issubclass(E.ConfigurationError, E.SDKError)

    def test_provider_error_subtypes(self) -> None:
        subtypes = [
            E.AuthenticationError, E.AccessDeniedError, E.NotFoundError,
            E.InvalidRequestError, E.RateLimitError, E.ServerError,
            E.ContentFilterError, E.ContextLengthError, E.QuotaExceededError,
        ]
        for cls in subtypes:
            assert issubclass(cls, E.ProviderError), f"{cls.__name__} not subclass of ProviderError"

    def test_non_provider_errors(self) -> None:
        non_provider = [
            E.RequestTimeoutError, E.AbortError, E.NetworkError,
            E.StreamError, E.InvalidToolCallError, E.NoObjectGeneratedError,
            E.ConfigurationError,
        ]
        for cls in non_provider:
            assert issubclass(cls, E.SDKError)
            assert not issubclass(cls, E.ProviderError), f"{cls.__name__} should NOT be ProviderError"


class TestSDKError:
    """SDKError base has message and cause."""

    def test_message(self) -> None:
        err = E.SDKError("something broke")
        assert str(err) == "something broke"
        assert err.message == "something broke"

    def test_cause(self) -> None:
        original = ValueError("bad value")
        err = E.SDKError("wrapped", cause=original)
        assert err.cause is original


class TestProviderError:
    """Spec §6.2 — ProviderError has extra fields."""

    def test_fields(self) -> None:
        err = E.RateLimitError(
            message="Rate limited",
            provider="anthropic",
            status_code=429,
            error_code="rate_limit_exceeded",
            retryable=True,
            retry_after=30.0,
            raw={"type": "error", "message": "Rate limited"},
        )
        assert err.provider == "anthropic"
        assert err.status_code == 429
        assert err.error_code == "rate_limit_exceeded"
        assert err.retryable is True
        assert err.retry_after == 30.0
        assert err.raw is not None


class TestRetryability:
    """Spec §6.3 — Retryability classification."""

    def test_non_retryable_errors(self) -> None:
        non_retryable = [
            E.AuthenticationError(message="bad key", provider="openai"),
            E.AccessDeniedError(message="forbidden", provider="openai"),
            E.NotFoundError(message="no model", provider="openai"),
            E.InvalidRequestError(message="bad params", provider="openai"),
            E.ContextLengthError(message="too long", provider="openai"),
            E.QuotaExceededError(message="over quota", provider="openai"),
            E.ContentFilterError(message="blocked", provider="openai"),
            E.ConfigurationError("no provider"),
        ]
        for err in non_retryable:
            assert not err.retryable, f"{type(err).__name__} should not be retryable"

    def test_retryable_errors(self) -> None:
        retryable = [
            E.RateLimitError(message="429", provider="openai", status_code=429),
            E.ServerError(message="500", provider="openai", status_code=500),
            E.RequestTimeoutError("timed out"),
            E.NetworkError("connection refused"),
            E.StreamError("stream broke"),
        ]
        for err in retryable:
            assert err.retryable, f"{type(err).__name__} should be retryable"


class TestHTTPStatusMapping:
    """Spec §6.4 — HTTP status code to error type mapping."""

    def test_status_code_mapping(self) -> None:
        mapping = {
            400: E.InvalidRequestError,
            401: E.AuthenticationError,
            403: E.AccessDeniedError,
            404: E.NotFoundError,
            408: E.RequestTimeoutError,
            413: E.ContextLengthError,
            422: E.InvalidRequestError,
            429: E.RateLimitError,
            500: E.ServerError,
            502: E.ServerError,
            503: E.ServerError,
            504: E.ServerError,
        }
        for status, expected_cls in mapping.items():
            err = E.error_from_status_code(
                status_code=status, message="test", provider="test",
            )
            assert isinstance(err, expected_cls), (
                f"Status {status} should produce {expected_cls.__name__}, "
                f"got {type(err).__name__}"
            )

    def test_unknown_status_defaults_retryable(self) -> None:
        """Spec §6.3: Unknown errors default to retryable."""
        err = E.error_from_status_code(
            status_code=999, message="unknown", provider="test",
        )
        assert isinstance(err, E.ProviderError)
        assert err.retryable is True
```

#### Step 2: Run test — verify it fails

```bash
uv run pytest tests/unit/test_errors.py -v
```

Expected: FAIL — `ModuleNotFoundError`

#### Step 3: Implement error hierarchy

`unified_llm/errors.py`:
```python
"""Error hierarchy for the unified LLM client (Spec §6.1-6.6).

13 error types: SDKError base, ProviderError with 9 subtypes,
plus RequestTimeoutError, AbortError, NetworkError, StreamError,
InvalidToolCallError, NoObjectGeneratedError, ConfigurationError.

Names deliberately avoid shadowing Python built-ins.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class SDKError(Exception):
    """Base exception for all unified-llm-client errors."""

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.cause = cause
        if cause:
            self.__cause__ = cause

    @property
    def retryable(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# Provider errors (Spec §6.2)
# ---------------------------------------------------------------------------


class ProviderError(SDKError):
    """Error from an LLM provider."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        status_code: int | None = None,
        error_code: str | None = None,
        retryable: bool = False,
        retry_after: float | None = None,
        raw: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, cause=cause)
        self.provider = provider
        self.status_code = status_code
        self.error_code = error_code
        self._retryable = retryable
        self.retry_after = retry_after
        self.raw = raw

    @property
    def retryable(self) -> bool:
        return self._retryable


# -- Non-retryable provider errors --


class AuthenticationError(ProviderError):
    """401 — Invalid API key or expired token."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("retryable", False)
        super().__init__(**kwargs)


class AccessDeniedError(ProviderError):
    """403 — Insufficient permissions."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("retryable", False)
        super().__init__(**kwargs)


class NotFoundError(ProviderError):
    """404 — Model or endpoint not found."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("retryable", False)
        super().__init__(**kwargs)


class InvalidRequestError(ProviderError):
    """400/422 — Malformed request or invalid parameters."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("retryable", False)
        super().__init__(**kwargs)


class ContentFilterError(ProviderError):
    """Response blocked by safety/content filter."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("retryable", False)
        super().__init__(**kwargs)


class ContextLengthError(ProviderError):
    """413 — Input + output exceeds context window."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("retryable", False)
        super().__init__(**kwargs)


class QuotaExceededError(ProviderError):
    """Billing/usage quota exhausted."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("retryable", False)
        super().__init__(**kwargs)


# -- Retryable provider errors --


class RateLimitError(ProviderError):
    """429 — Rate limit exceeded."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("retryable", True)
        super().__init__(**kwargs)


class ServerError(ProviderError):
    """500-504 — Provider internal error."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("retryable", True)
        super().__init__(**kwargs)


# ---------------------------------------------------------------------------
# Non-provider errors
# ---------------------------------------------------------------------------


class RequestTimeoutError(SDKError):
    """Request or stream timed out. Retryable."""

    @property
    def retryable(self) -> bool:
        return True


class AbortError(SDKError):
    """Request cancelled via abort signal. Not retryable."""

    @property
    def retryable(self) -> bool:
        return False


class NetworkError(SDKError):
    """Network-level failure. Retryable."""

    @property
    def retryable(self) -> bool:
        return True


class StreamError(SDKError):
    """Error during stream consumption. Retryable."""

    @property
    def retryable(self) -> bool:
        return True


class InvalidToolCallError(SDKError):
    """Tool call arguments failed validation. Not retryable."""

    @property
    def retryable(self) -> bool:
        return False


class NoObjectGeneratedError(SDKError):
    """Structured output parsing/validation failed. Not retryable."""

    @property
    def retryable(self) -> bool:
        return False


class ConfigurationError(SDKError):
    """SDK misconfiguration (missing provider, etc.). Not retryable."""

    @property
    def retryable(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# HTTP status → error type factory (Spec §6.4)
# ---------------------------------------------------------------------------

_STATUS_MAP: dict[int, type[ProviderError]] = {
    400: InvalidRequestError,
    401: AuthenticationError,
    403: AccessDeniedError,
    404: NotFoundError,
    408: RequestTimeoutError,  # type: ignore[dict-item]  # handled specially below
    413: ContextLengthError,
    422: InvalidRequestError,
    429: RateLimitError,
    500: ServerError,
    502: ServerError,
    503: ServerError,
    504: ServerError,
}


def error_from_status_code(
    *,
    status_code: int,
    message: str,
    provider: str,
    error_code: str | None = None,
    raw: dict[str, Any] | None = None,
    retry_after: float | None = None,
    cause: Exception | None = None,
) -> SDKError:
    """Map an HTTP status code to the appropriate error type (Spec §6.4)."""
    if status_code == 408:
        return RequestTimeoutError(message, cause=cause)

    cls = _STATUS_MAP.get(status_code)
    if cls is None:
        # Unknown status codes default to retryable (Spec §6.3)
        return ProviderError(
            message=message, provider=provider, status_code=status_code,
            error_code=error_code, retryable=True, raw=raw,
            retry_after=retry_after, cause=cause,
        )
    return cls(
        message=message, provider=provider, status_code=status_code,
        error_code=error_code, raw=raw, retry_after=retry_after, cause=cause,
    )
```

#### Step 4: Run tests — verify all pass

```bash
uv run pytest tests/unit/test_errors.py -v
```

Expected: all PASS.

#### Step 5: Commit

```bash
git add -A && git commit -m "feat: add full 13-type error hierarchy with status code mapping"
```

---

## Phase 2: Utilities — Retry, Middleware, Catalog

### Task 15: Retry System

**Files:**
- Create: `../unified-llm-client/unified_llm/retry.py`
- Create: `../unified-llm-client/tests/unit/test_retry.py`

**Depends on:** Task 14, 13
**Effort:** ~5 min

#### Step 1: Write failing tests

`tests/unit/test_retry.py`:
```python
"""Tests for unified_llm.retry — exponential backoff with jitter."""

import asyncio
from unittest.mock import AsyncMock, patch

from unified_llm.errors import (
    AuthenticationError,
    RateLimitError,
    ServerError,
)
from unified_llm.retry import RetryPolicy, retry


class TestRetryPolicy:
    """Spec §6.6 — RetryPolicy record with defaults."""

    def test_defaults(self) -> None:
        policy = RetryPolicy()
        assert policy.max_retries == 2
        assert policy.base_delay == 1.0
        assert policy.max_delay == 60.0
        assert policy.backoff_multiplier == 2.0
        assert policy.jitter is True
        assert policy.on_retry is None

    def test_delay_calculation_no_jitter(self) -> None:
        policy = RetryPolicy(base_delay=1.0, backoff_multiplier=2.0, jitter=False)
        assert policy.calculate_delay(0) == 1.0
        assert policy.calculate_delay(1) == 2.0
        assert policy.calculate_delay(2) == 4.0
        assert policy.calculate_delay(3) == 8.0

    def test_delay_capped_at_max(self) -> None:
        policy = RetryPolicy(
            base_delay=1.0, backoff_multiplier=2.0, max_delay=5.0, jitter=False,
        )
        assert policy.calculate_delay(10) == 5.0

    def test_delay_with_jitter_in_range(self) -> None:
        policy = RetryPolicy(base_delay=1.0, jitter=True)
        delays = [policy.calculate_delay(0) for _ in range(100)]
        assert all(0.5 <= d <= 1.5 for d in delays), f"Delays out of range: {min(delays)}-{max(delays)}"


class TestRetryFunction:
    """Spec §6.6 — retry() utility wrapping async callables."""

    def test_success_no_retry(self) -> None:
        mock_fn = AsyncMock(return_value="ok")
        result = asyncio.run(retry(mock_fn, RetryPolicy()))
        assert result == "ok"
        assert mock_fn.call_count == 1

    def test_retries_on_retryable_error(self) -> None:
        mock_fn = AsyncMock(side_effect=[
            ServerError(message="500", provider="test", status_code=500),
            "ok",
        ])
        with patch("unified_llm.retry.asyncio.sleep", new_callable=AsyncMock):
            result = asyncio.run(retry(mock_fn, RetryPolicy(max_retries=2)))
        assert result == "ok"
        assert mock_fn.call_count == 2

    def test_no_retry_on_non_retryable(self) -> None:
        mock_fn = AsyncMock(side_effect=AuthenticationError(
            message="bad key", provider="test", status_code=401,
        ))
        try:
            asyncio.run(retry(mock_fn, RetryPolicy(max_retries=3)))
            assert False, "Should have raised"
        except AuthenticationError:
            pass
        assert mock_fn.call_count == 1

    def test_max_retries_exhausted(self) -> None:
        mock_fn = AsyncMock(side_effect=ServerError(
            message="500", provider="test", status_code=500,
        ))
        with patch("unified_llm.retry.asyncio.sleep", new_callable=AsyncMock):
            try:
                asyncio.run(retry(mock_fn, RetryPolicy(max_retries=2)))
                assert False, "Should have raised"
            except ServerError:
                pass
        assert mock_fn.call_count == 3  # 1 initial + 2 retries

    def test_max_retries_zero_disables(self) -> None:
        mock_fn = AsyncMock(side_effect=ServerError(
            message="500", provider="test", status_code=500,
        ))
        try:
            asyncio.run(retry(mock_fn, RetryPolicy(max_retries=0)))
            assert False, "Should have raised"
        except ServerError:
            pass
        assert mock_fn.call_count == 1

    def test_retry_after_within_max_delay(self) -> None:
        """Spec: If Retry-After < max_delay, use provider's delay."""
        err = RateLimitError(
            message="429", provider="test", status_code=429, retry_after=5.0,
        )
        mock_fn = AsyncMock(side_effect=[err, "ok"])
        sleep_mock = AsyncMock()
        with patch("unified_llm.retry.asyncio.sleep", sleep_mock):
            asyncio.run(retry(mock_fn, RetryPolicy(max_delay=60.0)))
        sleep_mock.assert_called_once()
        actual_delay = sleep_mock.call_args[0][0]
        assert actual_delay == 5.0

    def test_retry_after_exceeds_max_delay_raises(self) -> None:
        """Spec: If Retry-After > max_delay, raise immediately."""
        err = RateLimitError(
            message="429", provider="test", status_code=429, retry_after=120.0,
        )
        mock_fn = AsyncMock(side_effect=err)
        try:
            asyncio.run(retry(mock_fn, RetryPolicy(max_delay=60.0)))
            assert False, "Should have raised"
        except RateLimitError:
            pass
        assert mock_fn.call_count == 1

    def test_on_retry_callback(self) -> None:
        callback = AsyncMock()
        mock_fn = AsyncMock(side_effect=[
            ServerError(message="500", provider="test", status_code=500),
            "ok",
        ])
        with patch("unified_llm.retry.asyncio.sleep", new_callable=AsyncMock):
            asyncio.run(retry(mock_fn, RetryPolicy(on_retry=callback)))
        callback.assert_called_once()
```

#### Step 2: Run test — verify it fails

```bash
uv run pytest tests/unit/test_retry.py -v
```

Expected: FAIL — `ModuleNotFoundError`

#### Step 3: Implement retry system

`unified_llm/retry.py`:
```python
"""Retry system with exponential backoff and jitter (Spec §6.6)."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from unified_llm.errors import SDKError

T = TypeVar("T")


@dataclass
class RetryPolicy:
    """Retry configuration (Spec §6.6)."""

    max_retries: int = 2
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_multiplier: float = 2.0
    jitter: bool = True
    on_retry: Callable[..., Any] | None = None

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for attempt n (0-indexed). Spec §6.6 formula."""
        delay = min(self.base_delay * (self.backoff_multiplier ** attempt), self.max_delay)
        if self.jitter:
            delay *= random.uniform(0.5, 1.5)
        return delay


async def retry(
    fn: Callable[..., Awaitable[T]],
    policy: RetryPolicy,
    *args: Any,
    **kwargs: Any,
) -> T:
    """Execute fn with automatic retry on retryable errors.

    Spec §6.6: Retries apply to individual calls. Only retryable errors trigger retry.
    Retry-After header is respected: if within max_delay, use it; if exceeds, raise.
    """
    last_error: SDKError | None = None

    for attempt in range(policy.max_retries + 1):
        try:
            return await fn(*args, **kwargs)
        except SDKError as err:
            last_error = err

            # Non-retryable: raise immediately
            if not err.retryable:
                raise

            # Last attempt: raise
            if attempt >= policy.max_retries:
                raise

            # Check Retry-After (on ProviderError)
            retry_after = getattr(err, "retry_after", None)
            if retry_after is not None and retry_after > policy.max_delay:
                raise

            # Calculate delay
            if retry_after is not None:
                delay = retry_after
            else:
                delay = policy.calculate_delay(attempt)

            # on_retry callback
            if policy.on_retry is not None:
                callback_result = policy.on_retry(err, attempt, delay)
                if asyncio.iscoroutine(callback_result):
                    await callback_result

            await asyncio.sleep(delay)

    # Should not reach here, but satisfy type checker
    assert last_error is not None
    raise last_error
```

#### Step 4: Run tests — verify all pass

```bash
uv run pytest tests/unit/test_retry.py -v
```

Expected: all PASS.

#### Step 5: Commit

```bash
git add -A && git commit -m "feat: add retry system with exponential backoff, jitter, Retry-After"
```

---

### Task 16: Middleware Chain

**Files:**
- Create: `../unified-llm-client/unified_llm/middleware.py`
- Create: `../unified-llm-client/tests/unit/test_middleware.py`

**Depends on:** Task 8, 9
**Effort:** ~5 min

#### Step 1: Write failing tests

`tests/unit/test_middleware.py`:
```python
"""Tests for unified_llm.middleware — onion pattern middleware chain."""

import asyncio
from collections.abc import AsyncIterator

from unified_llm.middleware import apply_middleware, apply_streaming_middleware
from unified_llm.types import (
    FinishReason,
    Message,
    Request,
    Response,
    StreamEvent,
    StreamEventType,
    Usage,
)


def _make_request() -> Request:
    return Request(model="test", messages=[Message.user("hi")])


def _make_response() -> Response:
    return Response(
        id="r1", model="test", provider="test",
        message=Message.assistant("hello"),
        finish_reason=FinishReason(reason="stop"),
        usage=Usage(input_tokens=1, output_tokens=1, total_tokens=2),
    )


class TestApplyMiddleware:
    """Spec §2.3 — Onion/chain-of-responsibility middleware."""

    def test_no_middleware(self) -> None:
        """Base handler called directly when no middleware."""
        async def handler(req: Request) -> Response:
            return _make_response()

        result = asyncio.run(apply_middleware([], handler, _make_request()))
        assert result.text == "hello"

    def test_single_middleware(self) -> None:
        order: list[str] = []

        async def mw(request: Request, next_fn):
            order.append("mw_request")
            response = await next_fn(request)
            order.append("mw_response")
            return response

        async def handler(req: Request) -> Response:
            order.append("handler")
            return _make_response()

        asyncio.run(apply_middleware([mw], handler, _make_request()))
        assert order == ["mw_request", "handler", "mw_response"]

    def test_execution_order(self) -> None:
        """Spec: Registration order for request, reverse for response."""
        order: list[str] = []

        async def mw_a(request, next_fn):
            order.append("A_req")
            response = await next_fn(request)
            order.append("A_resp")
            return response

        async def mw_b(request, next_fn):
            order.append("B_req")
            response = await next_fn(request)
            order.append("B_resp")
            return response

        async def handler(req):
            order.append("handler")
            return _make_response()

        asyncio.run(apply_middleware([mw_a, mw_b], handler, _make_request()))
        assert order == ["A_req", "B_req", "handler", "B_resp", "A_resp"]

    def test_middleware_can_modify_request(self) -> None:
        async def add_temp(request, next_fn):
            request.temperature = 0.5
            return await next_fn(request)

        captured_temp = None

        async def handler(req):
            nonlocal captured_temp
            captured_temp = req.temperature
            return _make_response()

        asyncio.run(apply_middleware([add_temp], handler, _make_request()))
        assert captured_temp == 0.5


class TestApplyStreamingMiddleware:
    """Spec §2.3 — Streaming middleware wraps the event iterator."""

    def test_streaming_passthrough(self) -> None:
        events = [
            StreamEvent(type=StreamEventType.TEXT_DELTA, delta="hi"),
            StreamEvent(type=StreamEventType.FINISH),
        ]

        async def handler(req: Request) -> AsyncIterator[StreamEvent]:
            for e in events:
                yield e

        async def run() -> list[StreamEvent]:
            result = []
            async for evt in apply_streaming_middleware([], handler, _make_request()):
                result.append(evt)
            return result

        result = asyncio.run(run())
        assert len(result) == 2

    def test_streaming_middleware_observes_events(self) -> None:
        seen: list[str] = []

        async def logger_mw(request, next_fn):
            async for event in next_fn(request):
                if event.delta:
                    seen.append(event.delta)
                yield event

        async def handler(req):
            yield StreamEvent(type=StreamEventType.TEXT_DELTA, delta="hello")
            yield StreamEvent(type=StreamEventType.FINISH)

        async def run() -> list[StreamEvent]:
            result = []
            async for evt in apply_streaming_middleware([logger_mw], handler, _make_request()):
                result.append(evt)
            return result

        asyncio.run(run())
        assert seen == ["hello"]
```

#### Step 2: Run test — verify it fails

```bash
uv run pytest tests/unit/test_middleware.py -v
```

Expected: FAIL — `ModuleNotFoundError`

#### Step 3: Implement middleware

`unified_llm/middleware.py`:
```python
"""Middleware chain with onion/chain-of-responsibility pattern (Spec §2.3).

Request phase: registration order (first registered = first to execute).
Response phase: reverse order.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from unified_llm.types import Request, Response, StreamEvent

# Middleware type: async (request, next) -> response
Middleware = Callable[..., Awaitable[Any]]


async def apply_middleware(
    middleware: list[Middleware],
    handler: Callable[[Request], Awaitable[Response]],
    request: Request,
) -> Response:
    """Apply middleware chain to a blocking complete() call."""
    if not middleware:
        return await handler(request)

    async def build_chain(index: int, req: Request) -> Response:
        if index >= len(middleware):
            return await handler(req)
        return await middleware[index](req, lambda r: build_chain(index + 1, r))

    return await build_chain(0, request)


async def apply_streaming_middleware(
    middleware: list[Middleware],
    handler: Callable[[Request], AsyncIterator[StreamEvent]],
    request: Request,
) -> AsyncIterator[StreamEvent]:
    """Apply middleware chain to a streaming call."""
    if not middleware:
        async for event in handler(request):
            yield event
        return

    async def build_chain(
        index: int, req: Request,
    ) -> AsyncIterator[StreamEvent]:
        if index >= len(middleware):
            async for event in handler(req):
                yield event
        else:
            async for event in middleware[index](req, lambda r: build_chain(index + 1, r)):
                yield event

    async for event in build_chain(0, request):
        yield event
```

#### Step 4: Run tests — verify all pass

```bash
uv run pytest tests/unit/test_middleware.py -v
```

Expected: all PASS.

#### Step 5: Commit

```bash
git add -A && git commit -m "feat: add middleware chain (onion pattern, blocking + streaming)"
```

---

### Task 17: Model Catalog

**Files:**
- Create: `../unified-llm-client/unified_llm/catalog.py`
- Create: `../unified-llm-client/unified_llm/data/models.json`
- Create: `../unified-llm-client/tests/unit/test_catalog.py`

**Depends on:** Task 13
**Effort:** ~5 min

#### Step 1: Write failing tests

`tests/unit/test_catalog.py`:
```python
"""Tests for unified_llm.catalog — model catalog and lookup functions."""

from unified_llm.catalog import get_latest_model, get_model_info, list_models


class TestGetModelInfo:
    """Spec §2.9 — get_model_info() lookup."""

    def test_known_model(self) -> None:
        info = get_model_info("claude-sonnet-4-20250514")
        assert info is not None
        assert info.provider == "anthropic"
        assert info.supports_tools is True

    def test_unknown_model_returns_none(self) -> None:
        """Spec: Unknown model strings pass through — catalog is advisory."""
        assert get_model_info("nonexistent-model-xyz") is None

    def test_alias_lookup(self) -> None:
        """Spec: Models have aliases for shorthand."""
        # The catalog should have at least one alias defined
        all_models = list_models()
        models_with_aliases = [m for m in all_models if m.aliases]
        if models_with_aliases:
            model = models_with_aliases[0]
            alias = model.aliases[0]
            result = get_model_info(alias)
            assert result is not None
            assert result.id == model.id


class TestListModels:
    """Spec §2.9 — list_models() with optional provider filter."""

    def test_list_all(self) -> None:
        models = list_models()
        assert len(models) > 0

    def test_filter_by_provider(self) -> None:
        anthropic_models = list_models(provider="anthropic")
        assert len(anthropic_models) > 0
        assert all(m.provider == "anthropic" for m in anthropic_models)

    def test_filter_unknown_provider(self) -> None:
        assert list_models(provider="nonexistent") == []


class TestGetLatestModel:
    """Spec §2.9 — get_latest_model() for each provider."""

    def test_latest_anthropic(self) -> None:
        model = get_latest_model("anthropic")
        assert model is not None
        assert model.provider == "anthropic"

    def test_latest_openai(self) -> None:
        model = get_latest_model("openai")
        assert model is not None
        assert model.provider == "openai"

    def test_latest_gemini(self) -> None:
        model = get_latest_model("gemini")
        assert model is not None
        assert model.provider == "gemini"

    def test_latest_unknown_provider(self) -> None:
        assert get_latest_model("nonexistent") is None

    def test_latest_with_capability_filter(self) -> None:
        model = get_latest_model("anthropic", capability="reasoning")
        assert model is not None
        assert model.supports_reasoning is True
```

#### Step 2: Run test — verify it fails

```bash
uv run pytest tests/unit/test_catalog.py -v
```

Expected: FAIL — `ModuleNotFoundError`

#### Step 3: Create models.json data file

`unified_llm/data/models.json`:
```json
[
  {
    "id": "claude-sonnet-4-20250514",
    "provider": "anthropic",
    "display_name": "Claude Sonnet 4",
    "context_window": 200000,
    "max_output": 16384,
    "supports_tools": true,
    "supports_vision": true,
    "supports_reasoning": true,
    "input_cost_per_million": 3.0,
    "output_cost_per_million": 15.0,
    "aliases": ["claude-sonnet", "sonnet"]
  },
  {
    "id": "claude-3-5-haiku-20241022",
    "provider": "anthropic",
    "display_name": "Claude 3.5 Haiku",
    "context_window": 200000,
    "max_output": 8192,
    "supports_tools": true,
    "supports_vision": true,
    "supports_reasoning": false,
    "input_cost_per_million": 0.80,
    "output_cost_per_million": 4.0,
    "aliases": ["claude-haiku", "haiku"]
  },
  {
    "id": "gpt-4.1",
    "provider": "openai",
    "display_name": "GPT-4.1",
    "context_window": 1047576,
    "max_output": 32768,
    "supports_tools": true,
    "supports_vision": true,
    "supports_reasoning": false,
    "input_cost_per_million": 2.0,
    "output_cost_per_million": 8.0,
    "aliases": ["gpt4.1"]
  },
  {
    "id": "o4-mini",
    "provider": "openai",
    "display_name": "o4-mini",
    "context_window": 200000,
    "max_output": 100000,
    "supports_tools": true,
    "supports_vision": true,
    "supports_reasoning": true,
    "input_cost_per_million": 1.10,
    "output_cost_per_million": 4.40,
    "aliases": ["o4mini"]
  },
  {
    "id": "gemini-2.5-flash",
    "provider": "gemini",
    "display_name": "Gemini 2.5 Flash",
    "context_window": 1048576,
    "max_output": 65536,
    "supports_tools": true,
    "supports_vision": true,
    "supports_reasoning": true,
    "input_cost_per_million": 0.15,
    "output_cost_per_million": 0.60,
    "aliases": ["gemini-flash"]
  },
  {
    "id": "gemini-2.5-pro",
    "provider": "gemini",
    "display_name": "Gemini 2.5 Pro",
    "context_window": 1048576,
    "max_output": 65536,
    "supports_tools": true,
    "supports_vision": true,
    "supports_reasoning": true,
    "input_cost_per_million": 1.25,
    "output_cost_per_million": 10.0,
    "aliases": ["gemini-pro"]
  }
]
```

Note to implementer: Update model IDs and pricing to match actual current API models at implementation time. The spec mentions future models — use whatever is current. The catalog is advisory and updateable.

#### Step 4: Implement catalog.py

`unified_llm/catalog.py`:
```python
"""Model catalog — advisory model lookup (Spec §2.9).

Unknown model strings pass through. The catalog is not restrictive.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from unified_llm.types import ModelInfo

_CATALOG: list[ModelInfo] | None = None
_ALIAS_MAP: dict[str, str] | None = None


def _load_catalog() -> tuple[list[ModelInfo], dict[str, str]]:
    """Load the catalog from the shipped JSON data file."""
    global _CATALOG, _ALIAS_MAP
    if _CATALOG is not None and _ALIAS_MAP is not None:
        return _CATALOG, _ALIAS_MAP

    data_path = Path(__file__).parent / "data" / "models.json"
    raw: list[dict[str, Any]] = json.loads(data_path.read_text())

    models: list[ModelInfo] = []
    aliases: dict[str, str] = {}

    for entry in raw:
        model = ModelInfo(
            id=entry["id"],
            provider=entry["provider"],
            display_name=entry["display_name"],
            context_window=entry["context_window"],
            max_output=entry.get("max_output"),
            supports_tools=entry["supports_tools"],
            supports_vision=entry["supports_vision"],
            supports_reasoning=entry["supports_reasoning"],
            input_cost_per_million=entry.get("input_cost_per_million"),
            output_cost_per_million=entry.get("output_cost_per_million"),
            aliases=entry.get("aliases", []),
        )
        models.append(model)
        for alias in model.aliases:
            aliases[alias] = model.id

    _CATALOG = models
    _ALIAS_MAP = aliases
    return models, aliases


def get_model_info(model_id: str) -> ModelInfo | None:
    """Look up a model by ID or alias. Returns None if unknown."""
    models, aliases = _load_catalog()
    # Direct ID match
    for model in models:
        if model.id == model_id:
            return model
    # Alias match
    canonical = aliases.get(model_id)
    if canonical:
        for model in models:
            if model.id == canonical:
                return model
    return None


def list_models(provider: str | None = None) -> list[ModelInfo]:
    """List all known models, optionally filtered by provider."""
    models, _ = _load_catalog()
    if provider is None:
        return list(models)
    return [m for m in models if m.provider == provider]


def get_latest_model(
    provider: str, capability: str | None = None,
) -> ModelInfo | None:
    """Get the newest/best model for a provider, optionally filtered by capability."""
    candidates = list_models(provider)
    if capability:
        cap_map = {
            "reasoning": lambda m: m.supports_reasoning,
            "vision": lambda m: m.supports_vision,
            "tools": lambda m: m.supports_tools,
        }
        filter_fn = cap_map.get(capability)
        if filter_fn:
            candidates = [m for m in candidates if filter_fn(m)]
    return candidates[0] if candidates else None
```

#### Step 5: Run tests — verify all pass

```bash
uv run pytest tests/unit/test_catalog.py -v
```

Expected: all PASS.

#### Step 6: Commit

```bash
git add -A && git commit -m "feat: add model catalog with JSON data and lookup functions"
```

---

## Phase 3: Core Client

### Task 18: ProviderAdapter Interface

**Files:**
- Create: `../unified-llm-client/unified_llm/adapters/__init__.py`

**Depends on:** Task 8, 9, 11
**Effort:** ~2 min

#### Step 1: Implement ProviderAdapter protocol

`unified_llm/adapters/__init__.py`:
```python
"""Provider adapter interface (Spec §2.4, §7.1).

Every provider adapter must implement complete() and stream().
Optional: close(), initialize(), supports_tool_choice().
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from unified_llm.types import Request, Response, StreamEvent


@runtime_checkable
class ProviderAdapter(Protocol):
    """Interface that every provider adapter must implement."""

    @property
    def name(self) -> str:
        """Provider name, e.g. 'openai', 'anthropic', 'gemini'."""
        ...

    async def complete(self, request: Request) -> Response:
        """Send a request, block until done, return full Response. No retry."""
        ...

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        """Send a request, return async iterator of StreamEvent. No retry."""
        ...

    async def close(self) -> None:
        """Release resources. Called by Client.close()."""
        ...

    async def initialize(self) -> None:
        """Validate configuration on startup. Called on registration."""
        ...

    def supports_tool_choice(self, mode: str) -> bool:
        """Check if a particular tool choice mode is supported."""
        ...
```

No test needed — this is a Protocol definition. It will be validated when adapters implement it.

#### Step 2: Commit

```bash
git add -A && git commit -m "feat: add ProviderAdapter protocol interface"
```

---

### Task 19: Client Class with Provider Routing

**Files:**
- Create: `../unified-llm-client/unified_llm/client.py`
- Create: `../unified-llm-client/tests/unit/test_client.py`

**Depends on:** Task 18, 14
**Effort:** ~5 min

#### Step 1: Write failing tests

`tests/unit/test_client.py`:
```python
"""Tests for unified_llm.client — Client class with provider routing."""

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

from unified_llm.client import Client
from unified_llm.errors import ConfigurationError
from unified_llm.types import (
    FinishReason,
    Message,
    Request,
    Response,
    StreamEvent,
    StreamEventType,
    Usage,
)


def _make_response(provider: str = "mock") -> Response:
    return Response(
        id="r1", model="test-model", provider=provider,
        message=Message.assistant("hello"),
        finish_reason=FinishReason(reason="stop"),
        usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
    )


class _MockAdapter:
    """Minimal ProviderAdapter for testing."""

    def __init__(self, name: str = "mock") -> None:
        self._name = name
        self.complete_mock = AsyncMock(return_value=_make_response(name))
        self.stream_events: list[StreamEvent] = [
            StreamEvent(type=StreamEventType.TEXT_DELTA, delta="hi"),
            StreamEvent(type=StreamEventType.FINISH),
        ]

    @property
    def name(self) -> str:
        return self._name

    async def complete(self, request: Request) -> Response:
        return await self.complete_mock(request)

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        for e in self.stream_events:
            yield e

    async def close(self) -> None:
        pass

    async def initialize(self) -> None:
        pass

    def supports_tool_choice(self, mode: str) -> bool:
        return True


def _make_request(provider: str | None = None) -> Request:
    return Request(model="test-model", messages=[Message.user("hi")], provider=provider)


class TestClientConstruction:
    """Client construction and provider registration."""

    def test_explicit_providers(self) -> None:
        adapter = _MockAdapter()
        client = Client(providers={"mock": adapter}, default_provider="mock")
        assert "mock" in client.providers

    def test_no_providers_raises_on_request(self) -> None:
        client = Client(providers={})
        try:
            asyncio.run(client.complete(_make_request()))
            assert False, "Should raise"
        except ConfigurationError as e:
            assert "no provider" in e.message.lower() or "no default" in e.message.lower()


class TestProviderRouting:
    """Spec §2.2 — Provider resolution."""

    def test_explicit_provider_field(self) -> None:
        mock_a = _MockAdapter("alpha")
        mock_b = _MockAdapter("beta")
        client = Client(providers={"alpha": mock_a, "beta": mock_b})
        asyncio.run(client.complete(_make_request(provider="beta")))
        mock_b.complete_mock.assert_called_once()
        mock_a.complete_mock.assert_not_called()

    def test_default_provider_when_omitted(self) -> None:
        adapter = _MockAdapter()
        client = Client(providers={"mock": adapter}, default_provider="mock")
        asyncio.run(client.complete(_make_request()))
        adapter.complete_mock.assert_called_once()

    def test_missing_provider_raises(self) -> None:
        adapter = _MockAdapter()
        client = Client(providers={"mock": adapter})
        try:
            asyncio.run(client.complete(_make_request(provider="nonexistent")))
            assert False, "Should raise"
        except ConfigurationError:
            pass

    def test_no_default_no_explicit_raises(self) -> None:
        adapter = _MockAdapter()
        client = Client(providers={"mock": adapter})
        try:
            asyncio.run(client.complete(_make_request()))
            assert False, "Should raise"
        except ConfigurationError:
            pass


class TestClientStream:
    """Client.stream() returns async iterator."""

    def test_stream_yields_events(self) -> None:
        adapter = _MockAdapter()
        client = Client(providers={"mock": adapter}, default_provider="mock")

        async def run() -> list[StreamEvent]:
            result = []
            async for evt in client.stream(_make_request()):
                result.append(evt)
            return result

        events = asyncio.run(run())
        assert len(events) == 2
        assert events[0].type == StreamEventType.TEXT_DELTA


class TestClientClose:
    """Client.close() calls close() on all adapters."""

    def test_close(self) -> None:
        adapter = _MockAdapter()
        client = Client(providers={"mock": adapter}, default_provider="mock")
        asyncio.run(client.close())
        # Should not raise
```

#### Step 2: Run test — verify it fails

```bash
uv run pytest tests/unit/test_client.py -v
```

Expected: FAIL — `ModuleNotFoundError`

#### Step 3: Implement Client

`unified_llm/client.py`:
```python
"""Core Client class with provider routing (Spec §2.2, §3, §4.1-4.2)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from unified_llm.adapters import ProviderAdapter
from unified_llm.errors import ConfigurationError
from unified_llm.middleware import Middleware, apply_middleware, apply_streaming_middleware
from unified_llm.types import Request, Response, StreamEvent

# Module-level default client (Spec §2.5)
_default_client: Client | None = None


class Client:
    """Provider-agnostic LLM client (Spec §3).

    Routes requests to registered provider adapters. Applies middleware.
    Does NOT retry — that's Layer 4's responsibility.
    """

    def __init__(
        self,
        providers: dict[str, ProviderAdapter],
        default_provider: str | None = None,
        middleware: list[Middleware] | None = None,
    ) -> None:
        self.providers = dict(providers)
        self.default_provider = default_provider
        self._middleware = middleware or []

    def _resolve_adapter(self, request: Request) -> ProviderAdapter:
        """Resolve which adapter handles this request."""
        provider_name = request.provider or self.default_provider
        if provider_name is None:
            raise ConfigurationError(
                "No provider specified and no default provider configured. "
                "Set provider on the request or configure a default_provider."
            )
        adapter = self.providers.get(provider_name)
        if adapter is None:
            raise ConfigurationError(
                f"Provider '{provider_name}' not found. "
                f"Available providers: {list(self.providers.keys())}"
            )
        return adapter

    async def complete(self, request: Request) -> Response:
        """Low-level blocking call. No retry. (Spec §4.1)."""
        adapter = self._resolve_adapter(request)

        async def handler(req: Request) -> Response:
            return await adapter.complete(req)

        return await apply_middleware(self._middleware, handler, request)

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        """Low-level streaming call. No retry. (Spec §4.2)."""
        adapter = self._resolve_adapter(request)

        async def handler(req: Request) -> AsyncIterator[StreamEvent]:
            async for event in adapter.stream(req):
                yield event

        async for event in apply_streaming_middleware(self._middleware, handler, request):
            yield event

    async def close(self) -> None:
        """Release resources on all adapters (Spec §2.4)."""
        for adapter in self.providers.values():
            if hasattr(adapter, "close"):
                await adapter.close()

    @classmethod
    def from_env(cls) -> Client:
        """Create a Client by detecting API keys from environment (Spec §2.2).

        Registers adapters for providers whose keys are present.
        First registered becomes default.
        """
        import os

        providers: dict[str, ProviderAdapter] = {}
        default: str | None = None

        # Anthropic
        if os.environ.get("ANTHROPIC_API_KEY"):
            from unified_llm.adapters.anthropic import AnthropicAdapter
            providers["anthropic"] = AnthropicAdapter()
            if default is None:
                default = "anthropic"

        # OpenAI
        if os.environ.get("OPENAI_API_KEY"):
            from unified_llm.adapters.openai import OpenAIAdapter
            providers["openai"] = OpenAIAdapter()
            if default is None:
                default = "openai"

        # Gemini
        if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            from unified_llm.adapters.gemini import GeminiAdapter
            providers["gemini"] = GeminiAdapter()
            if default is None:
                default = "gemini"

        if not providers:
            raise ConfigurationError(
                "No API keys found in environment. Set at least one of: "
                "ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY"
            )

        return cls(providers=providers, default_provider=default)


def set_default_client(client: Client) -> None:
    """Set the module-level default client (Spec §2.5)."""
    global _default_client
    _default_client = client


def get_default_client() -> Client:
    """Get or lazily initialize the default client."""
    global _default_client
    if _default_client is None:
        _default_client = Client.from_env()
    return _default_client
```

#### Step 4: Run tests — verify all pass

```bash
uv run pytest tests/unit/test_client.py -v
```

Expected: all PASS.

#### Step 5: Commit

```bash
git add -A && git commit -m "feat: add Client class with provider routing and from_env()"
```

---

### Task 20-21: Client.from_env and Middleware Integration

These are already implemented in Task 19's Client class. The `from_env()` constructor and middleware integration are part of the Client implementation. Add integration tests for these in Phase 9 (DoD tests).

---

## Phases 4-6: Provider Adapters

> **Note to implementer:** Each adapter is substantial (200-400 lines). The tasks below specify the structure, key translation logic, and test patterns. Complete SDK-specific implementation details (exact API field names, headers, etc.) should be derived from the spec sections §7.3-7.8 and from each SDK's documentation.

### Task 22-27: Anthropic Adapter (Phase 4)

**Files:**
- Create: `../unified-llm-client/unified_llm/adapters/anthropic.py`
- Create: `../unified-llm-client/tests/adapter/test_anthropic.py`

**Depends on:** Task 18, 14
**Effort:** ~25 min total (5 sub-tasks)

#### Task 22: Anthropic Request Translation

Write test: Mock the Anthropic SDK client. Verify that a unified `Request` with messages, tools, tool_choice, and provider_options translates correctly to Anthropic's Messages API format:
- System messages extracted to `system` parameter
- DEVELOPER role merged with system
- `max_tokens` defaults to 4096 when not set
- Strict user/assistant alternation enforced (consecutive same-role merged)
- Tool definitions translated to Anthropic's `{name, description, input_schema}` format
- ToolChoice modes mapped per spec §5.3
- `cache_control` breakpoints injected on system prompt (Task 27)
- `anthropic-beta` headers passed from `provider_options`

#### Task 23: Anthropic Response Translation

Write test: Given mocked Anthropic SDK response objects, verify translation to unified `Response`:
- Text content blocks → TEXT ContentParts
- `tool_use` blocks → TOOL_CALL ContentParts
- `thinking` blocks → THINKING ContentParts with signature preserved
- `redacted_thinking` blocks → REDACTED_THINKING ContentParts
- `end_turn` → FinishReason(reason="stop")
- `tool_use` → FinishReason(reason="tool_calls")
- Usage fields mapped: `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`

#### Task 24: Anthropic Error Translation

Write test: Given mocked Anthropic SDK exceptions, verify mapping to error hierarchy:
- `anthropic.AuthenticationError` → `errors.AuthenticationError`
- `anthropic.RateLimitError` → `errors.RateLimitError` with `retry_after`
- `anthropic.APIStatusError` with status 400 → `errors.InvalidRequestError`
- `anthropic.APIConnectionError` → `errors.NetworkError`

#### Task 25: Anthropic complete() Integration

Write test: Wire up the adapter, mock the SDK client, call `complete()`, verify the full round-trip (Request → SDK call → Response).

#### Task 26: Anthropic Streaming Translation

Write test: Given mocked Anthropic SSE events, verify translation to unified StreamEvent sequence:
- `message_start` → STREAM_START
- `content_block_start(type=text)` → TEXT_START
- `content_block_delta(type=text_delta)` → TEXT_DELTA
- `content_block_stop` → TEXT_END
- `content_block_start(type=tool_use)` → TOOL_CALL_START
- `content_block_start(type=thinking)` → REASONING_START
- `message_stop` → FINISH with accumulated response

#### Task 27: Anthropic Prompt Caching

Write test: Verify that `cache_control` breakpoints are injected automatically:
- On the last system message content block
- On tool definitions (when present)
- Verify `prompt-caching-2024-07-31` beta header is included
- Verify auto-caching can be disabled via `provider_options.anthropic.auto_cache = false`

**Commit after each sub-task:**
```bash
git add -A && git commit -m "feat(anthropic): <sub-task description>"
```

---

### Task 28-33: OpenAI Adapter (Phase 5)

**Files:**
- Create: `../unified-llm-client/unified_llm/adapters/openai.py`
- Create: `../unified-llm-client/tests/adapter/test_openai.py`

**Depends on:** Task 18, 14
**Effort:** ~25 min total

#### Task 28: OpenAI Request Translation (Responses API)

Write test: Verify Request → Responses API format:
- System messages → `instructions` parameter
- User messages → `input` items with `type: "message"`, `role: "user"`
- TEXT parts → `input_text` (user) or `output_text` (assistant)
- IMAGE parts → `input_image` with data URI format
- TOOL_CALL → `function_call` input items
- TOOL_RESULT → `function_call_output` input items
- Tool definitions → `{type: "function", function: {name, description, parameters}}`
- `reasoning_effort` → `reasoning.effort` parameter

#### Task 29: OpenAI Response Translation

Write test: Verify Responses API response → unified Response:
- `output` items parsed into ContentParts
- Usage mapped including `reasoning_tokens` from `output_tokens_details`
- `cached_tokens` from `prompt_tokens_details` → `cache_read_tokens`

#### Task 30: OpenAI Error Translation

Write test: Map OpenAI SDK exceptions to error hierarchy.

#### Task 31: OpenAI complete() Integration

Wire up and test the full round-trip.

#### Task 32: OpenAI Streaming Translation

Write test: Responses API streaming events → unified StreamEvent:
- `response.output_text.delta` → TEXT_DELTA
- `response.function_call_arguments.delta` → TOOL_CALL_DELTA
- `response.completed` → FINISH with reasoning token usage

#### Task 33: OpenAI Reasoning Tokens

Write test: Verify `reasoning_tokens` populated from Responses API, `reasoning_effort` param passed through.

**Commit after each sub-task.**

---

### Task 34-38: Gemini Adapter (Phase 6)

**Files:**
- Create: `../unified-llm-client/unified_llm/adapters/gemini.py`
- Create: `../unified-llm-client/tests/adapter/test_gemini.py`

**Depends on:** Task 18, 14
**Effort:** ~25 min total

#### Task 34: Gemini Request Translation

Write test: Verify Request → Gemini API format:
- System messages → `systemInstruction`
- User → `user` role, Assistant → `model` role
- TEXT → `{text: "..."}` parts
- IMAGE → `inlineData` / `fileData` parts
- TOOL_CALL → `functionCall` parts
- TOOL_RESULT → `functionResponse` parts with function NAME (not ID)
- Synthetic tool call IDs generated (`call_<uuid>`)
- Tool definitions → `functionDeclarations` format
- `thoughtsTokenCount` → `reasoning_tokens`

#### Task 35: Gemini Response Translation

Write test: Verify Gemini response → unified Response, including:
- `candidates[0].content.parts` → ContentParts
- `STOP`/`MAX_TOKENS`/`SAFETY` finish reason mapping
- Infer `tool_calls` finish reason from presence of `functionCall` parts
- `usageMetadata` → Usage (including `cachedContentTokenCount`)

#### Task 36: Gemini Error Translation (including gRPC)

Write test: Map gRPC status codes per spec §6.4:
- `NOT_FOUND` → `NotFoundError`
- `RESOURCE_EXHAUSTED` → `RateLimitError`
- `UNAUTHENTICATED` → `AuthenticationError`
- etc.

#### Task 37: Gemini complete() Integration

Wire up and test.

#### Task 38: Gemini Streaming Translation

Write test: Gemini SSE/JSON chunks → unified StreamEvent:
- Text parts → TEXT_DELTA (emit TEXT_START on first)
- functionCall parts → TOOL_CALL_START + TOOL_CALL_END (complete in one chunk)
- Final chunk → FINISH

**Commit after each sub-task.**

---

## Phase 7: High-Level API

### Task 39: generate() — Basic

**Files:**
- Create: `../unified-llm-client/unified_llm/generate.py`
- Create: `../unified-llm-client/tests/unit/test_generate.py`

**Depends on:** Task 19, 15
**Effort:** ~5 min

#### Step 1: Write failing tests

`tests/unit/test_generate.py`:
```python
"""Tests for unified_llm.generate — high-level API functions."""

import asyncio
from unittest.mock import AsyncMock

from unified_llm.client import Client, set_default_client
from unified_llm.errors import ConfigurationError
from unified_llm.generate import generate
from unified_llm.types import (
    FinishReason,
    Message,
    Response,
    Usage,
)


def _make_response() -> Response:
    return Response(
        id="r1", model="test", provider="mock",
        message=Message.assistant("Hello world"),
        finish_reason=FinishReason(reason="stop"),
        usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
    )


class _MockAdapter:
    def __init__(self) -> None:
        self.complete_mock = AsyncMock(return_value=_make_response())

    @property
    def name(self) -> str:
        return "mock"

    async def complete(self, request):
        return await self.complete_mock(request)

    async def stream(self, request):
        raise NotImplementedError

    async def close(self):
        pass


class TestGenerateBasic:
    """Spec §4.3 — generate() with simple prompt."""

    def test_simple_prompt(self) -> None:
        adapter = _MockAdapter()
        client = Client(providers={"mock": adapter}, default_provider="mock")
        result = asyncio.run(generate(
            model="test", prompt="Hello", provider="mock", client=client,
        ))
        assert result.text == "Hello world"
        assert result.finish_reason.reason == "stop"
        assert result.usage.total_tokens == 15
        assert result.total_usage.total_tokens == 15
        assert len(result.steps) == 1

    def test_messages_input(self) -> None:
        adapter = _MockAdapter()
        client = Client(providers={"mock": adapter}, default_provider="mock")
        result = asyncio.run(generate(
            model="test",
            messages=[Message.user("Hello")],
            provider="mock",
            client=client,
        ))
        assert result.text == "Hello world"

    def test_prompt_and_messages_raises(self) -> None:
        """Spec: Using both prompt and messages is an error."""
        adapter = _MockAdapter()
        client = Client(providers={"mock": adapter}, default_provider="mock")
        try:
            asyncio.run(generate(
                model="test", prompt="Hello",
                messages=[Message.user("Hello")],
                provider="mock", client=client,
            ))
            assert False, "Should raise"
        except ConfigurationError:
            pass

    def test_system_param_prepended(self) -> None:
        adapter = _MockAdapter()
        client = Client(providers={"mock": adapter}, default_provider="mock")
        asyncio.run(generate(
            model="test", prompt="Hi", system="Be helpful",
            provider="mock", client=client,
        ))
        call_args = adapter.complete_mock.call_args[0][0]
        assert call_args.messages[0].role.value == "system"
        assert call_args.messages[0].text == "Be helpful"

    def test_uses_default_client(self) -> None:
        adapter = _MockAdapter()
        client = Client(providers={"mock": adapter}, default_provider="mock")
        set_default_client(client)
        result = asyncio.run(generate(model="test", prompt="Hello", provider="mock"))
        assert result.text == "Hello world"
```

#### Step 2: Run test — verify it fails

```bash
uv run pytest tests/unit/test_generate.py -v
```

Expected: FAIL — `ModuleNotFoundError`

#### Step 3: Implement generate() basic

`unified_llm/generate.py`:
```python
"""High-level API functions (Spec §4.3-4.6).

generate(), stream(), generate_object(), stream_object().
"""

from __future__ import annotations

from typing import Any

from unified_llm.client import Client, get_default_client
from unified_llm.errors import ConfigurationError
from unified_llm.retry import RetryPolicy, retry
from unified_llm.types import (
    FinishReason,
    GenerateResult,
    Message,
    Request,
    Response,
    StepResult,
    Tool,
    ToolCall,
    ToolChoice,
    ToolResult,
    Usage,
)


async def generate(
    model: str,
    *,
    prompt: str | None = None,
    messages: list[Message] | None = None,
    system: str | None = None,
    tools: list[Tool] | None = None,
    tool_choice: ToolChoice | None = None,
    max_tool_rounds: int = 1,
    stop_when: Any | None = None,
    response_format: Any | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    stop_sequences: list[str] | None = None,
    reasoning_effort: str | None = None,
    provider: str | None = None,
    provider_options: dict[str, Any] | None = None,
    max_retries: int = 2,
    timeout: float | Any | None = None,
    abort_signal: Any | None = None,
    client: Client | None = None,
) -> GenerateResult:
    """Primary blocking generation function (Spec §4.3).

    Wraps Client.complete() with tool execution loops, retry, timeout.
    """
    # Validate prompt/messages
    if prompt is not None and messages is not None:
        raise ConfigurationError("Cannot specify both 'prompt' and 'messages'. Use one or the other.")

    # Resolve client
    resolved_client = client or get_default_client()

    # Build message list
    msg_list: list[Message] = []
    if system:
        msg_list.append(Message.system(system))
    if prompt is not None:
        msg_list.append(Message.user(prompt))
    elif messages is not None:
        msg_list.extend(messages)
    else:
        raise ConfigurationError("Either 'prompt' or 'messages' must be provided.")

    # Build request
    request = Request(
        model=model,
        messages=msg_list,
        provider=provider,
        tools=tools,
        tool_choice=tool_choice,
        response_format=response_format,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        stop_sequences=stop_sequences,
        reasoning_effort=reasoning_effort,
        provider_options=provider_options,
    )

    # Retry policy
    policy = RetryPolicy(max_retries=max_retries)

    # Tool loop
    steps: list[StepResult] = []
    conversation = list(request.messages)

    for round_num in range(max_tool_rounds + 1):
        # Each step's LLM call is retried independently
        step_request = Request(
            model=request.model,
            messages=conversation,
            provider=request.provider,
            tools=request.tools,
            tool_choice=request.tool_choice,
            response_format=request.response_format,
            temperature=request.temperature,
            top_p=request.top_p,
            max_tokens=request.max_tokens,
            stop_sequences=request.stop_sequences,
            reasoning_effort=request.reasoning_effort,
            provider_options=request.provider_options,
        )

        response = await retry(
            resolved_client.complete, policy, step_request,
        )

        # Extract tool calls
        tool_calls = [
            ToolCall(
                id=tc.id, name=tc.name,
                arguments=tc.arguments if isinstance(tc.arguments, dict) else {},
            )
            for tc in response.tool_calls
        ]

        # Execute tools if active and model wants to call them
        tool_results: list[ToolResult] = []
        if (
            tool_calls
            and response.finish_reason.reason == "tool_calls"
            and tools
        ):
            tool_results = await _execute_tools(tools, tool_calls)

        step = StepResult(
            text=response.text,
            reasoning=response.reasoning,
            tool_calls=tool_calls,
            tool_results=tool_results,
            finish_reason=response.finish_reason,
            usage=response.usage,
            response=response,
            warnings=response.warnings,
        )
        steps.append(step)

        # Check stop conditions
        if not tool_calls or response.finish_reason.reason != "tool_calls":
            break
        if round_num >= max_tool_rounds:
            break
        if stop_when is not None and stop_when(steps):
            break

        # Continue conversation with tool results
        conversation.append(response.message)
        for tr in tool_results:
            conversation.append(Message.tool_result(
                tool_call_id=tr.tool_call_id,
                content=tr.content,
                is_error=tr.is_error,
            ))

    # Aggregate results
    final = steps[-1]
    total_usage = steps[0].usage
    for s in steps[1:]:
        total_usage = total_usage + s.usage

    return GenerateResult(
        text=final.text,
        reasoning=final.reasoning,
        tool_calls=final.tool_calls,
        tool_results=final.tool_results,
        finish_reason=final.finish_reason,
        usage=final.usage,
        total_usage=total_usage,
        steps=steps,
        response=final.response,
    )


async def _execute_tools(
    tools: list[Tool], tool_calls: list[ToolCall],
) -> list[ToolResult]:
    """Execute tool calls concurrently (Spec §5.7).

    All calls are launched concurrently. All results returned, even on partial failure.
    """
    import asyncio

    tool_map = {t.name: t for t in tools if t.execute is not None}
    results: list[ToolResult] = []

    async def execute_one(call: ToolCall) -> ToolResult:
        tool = tool_map.get(call.name)
        if tool is None or tool.execute is None:
            return ToolResult(
                tool_call_id=call.id,
                content=f"Unknown tool: {call.name}",
                is_error=True,
            )
        try:
            result = tool.execute(**call.arguments)
            if asyncio.iscoroutine(result):
                result = await result
            content = result if isinstance(result, (str, dict, list)) else str(result)
            return ToolResult(tool_call_id=call.id, content=content, is_error=False)
        except Exception as exc:
            return ToolResult(
                tool_call_id=call.id, content=str(exc), is_error=True,
            )

    tasks = [execute_one(call) for call in tool_calls]
    results = await asyncio.gather(*tasks)
    return list(results)
```

#### Step 4: Run tests — verify all pass

```bash
uv run pytest tests/unit/test_generate.py -v
```

Expected: all PASS.

#### Step 5: Commit

```bash
git add -A && git commit -m "feat: add generate() with tool loop, retry, prompt standardization"
```

---

### Task 40: generate() — Tool Loop

**Depends on:** Task 39, 10
**Effort:** ~5 min

Add tool loop tests to `tests/unit/test_generate.py`. Test scenarios:
- Active tools trigger execution loop
- `max_tool_rounds` limits iterations
- `max_tool_rounds=0` disables auto-execution
- Parallel tool calls executed concurrently
- Tool execution errors produce error results (not exceptions)
- Unknown tool calls produce error results
- `StepResult` tracks each step's data
- `total_usage` aggregates across all steps

These tests follow the same pattern as Task 39 using `_MockAdapter` with a `complete_mock` that returns tool call responses followed by final responses.

---

### Task 41-42: stream() and stream() with Tools

**Files:**
- Modify: `unified_llm/generate.py` (add `stream()` function)
- Modify: `tests/unit/test_generate.py` (add stream tests)

**Depends on:** Task 39, 11
**Effort:** ~8 min total

Implement the `stream()` high-level function that returns a `StreamResult` — an async iterator over `StreamEvent` objects with `.response()` and `.text_stream` accessors. Test:
- Yields TEXT_DELTA events
- `.response()` available after iteration
- `.text_stream` yields only text deltas
- Tool loop: stream pauses during tool execution, then resumes
- Retry on initial connection only (not after partial data)

---

### Task 43: generate_object()

**Depends on:** Task 39
**Effort:** ~5 min

Add `generate_object()` to `unified_llm/generate.py`. It:
- Sets `response_format` to `json_schema` with the provided schema
- Parses JSON from response text
- Validates against schema (basic JSON parse, optionally jsonschema validation)
- Sets `result.output` to the parsed object
- Raises `NoObjectGeneratedError` on parse/validation failure
- Schema validation failures are NOT retried (spec requirement)

---

### Task 44: stream_object()

**Depends on:** Task 41, 43
**Effort:** ~5 min

Add `stream_object()` — streaming structured output with incremental JSON parsing. Returns an async iterator of partial objects.

---

### Task 45: Abort and Timeout

**Depends on:** Task 39, 41
**Effort:** ~5 min

Add abort signal and timeout support to `generate()` and `stream()`:
- `abort_signal` cancels the operation (raises `AbortError`)
- `timeout` as float or `TimeoutConfig`
- `total` timeout for entire multi-step operation
- `per_step` timeout per individual LLM call

---

## Phase 8: OpenAI-Compatible Adapter

### Task 46: OpenAI-Compatible Adapter

**Files:**
- Create: `../unified-llm-client/unified_llm/adapters/openai_compat.py`
- Create: `../unified-llm-client/tests/adapter/test_openai_compat.py`

**Depends on:** Task 18, 30
**Effort:** ~10 min

Implement `OpenAICompatAdapter` that uses Chat Completions API (`/v1/chat/completions`) for third-party services (vLLM, Ollama, Together AI, Groq). This adapter:
- Accepts `base_url` for custom endpoints
- Uses standard Chat Completions message format (not Responses API)
- Does NOT support reasoning tokens (Chat Completions limitation)
- Does NOT support built-in tools (Responses API feature)
- Translates standard Chat Completions streaming format

---

## Phase 9: Public API + DoD Tests

### Task 47: __init__.py Public Exports

**Files:**
- Modify: `../unified-llm-client/unified_llm/__init__.py`

**Depends on:** All above
**Effort:** ~2 min

Update `unified_llm/__init__.py` to export the public API:

```python
"""unified-llm-client: Provider-agnostic LLM client library.

Usage:
    from unified_llm import Client, generate, stream, generate_object
    client = Client.from_env()
    result = await generate(model="claude-sonnet-4-20250514", prompt="Hello")
"""

# Core client
from unified_llm.client import Client, get_default_client, set_default_client

# High-level API
from unified_llm.generate import generate, generate_object, stream, stream_object

# Types
from unified_llm.types import (
    AdapterTimeout,
    AudioData,
    ContentKind,
    ContentPart,
    DocumentData,
    FinishReason,
    GenerateResult,
    ImageData,
    Message,
    ModelInfo,
    RateLimitInfo,
    Request,
    Response,
    ResponseFormat,
    Role,
    StepResult,
    StreamAccumulator,
    StreamEvent,
    StreamEventType,
    ThinkingData,
    TimeoutConfig,
    Tool,
    ToolCall,
    ToolCallData,
    ToolChoice,
    ToolResult,
    ToolResultData,
    Usage,
    Warning,
)

# Errors
from unified_llm.errors import (
    AbortError,
    AccessDeniedError,
    AuthenticationError,
    ConfigurationError,
    ContentFilterError,
    ContextLengthError,
    InvalidRequestError,
    InvalidToolCallError,
    NetworkError,
    NoObjectGeneratedError,
    NotFoundError,
    ProviderError,
    QuotaExceededError,
    RateLimitError,
    RequestTimeoutError,
    SDKError,
    ServerError,
    StreamError,
)

# Retry
from unified_llm.retry import RetryPolicy

# Catalog
from unified_llm.catalog import get_latest_model, get_model_info, list_models

# Adapters
from unified_llm.adapters import ProviderAdapter

__all__ = [
    # Client
    "Client", "set_default_client", "get_default_client",
    # High-level API
    "generate", "stream", "generate_object", "stream_object",
    # Types - core
    "Role", "ContentKind", "ContentPart", "Message",
    "ImageData", "AudioData", "DocumentData",
    "ToolCallData", "ToolResultData", "ThinkingData",
    # Types - request/response
    "Request", "Response", "ResponseFormat",
    "FinishReason", "Usage", "Warning", "RateLimitInfo",
    # Types - generation
    "GenerateResult", "StepResult",
    "StreamEvent", "StreamEventType", "StreamAccumulator",
    # Types - tools
    "Tool", "ToolChoice", "ToolCall", "ToolResult",
    # Types - config
    "TimeoutConfig", "AdapterTimeout", "ModelInfo", "RetryPolicy",
    # Errors
    "SDKError", "ProviderError",
    "AuthenticationError", "AccessDeniedError", "NotFoundError",
    "InvalidRequestError", "RateLimitError", "ServerError",
    "ContentFilterError", "ContextLengthError", "QuotaExceededError",
    "RequestTimeoutError", "AbortError", "NetworkError", "StreamError",
    "InvalidToolCallError", "NoObjectGeneratedError", "ConfigurationError",
    # Catalog
    "get_model_info", "list_models", "get_latest_model",
    # Adapter interface
    "ProviderAdapter",
]
```

---

### Task 48: DoD Tests (Sections 8.1-8.8)

**Files:**
- Create: `tests/dod/test_8_1_core_infra.py`
- Create: `tests/dod/test_8_2_provider_adapters.py`
- Create: `tests/dod/test_8_3_content_model.py`
- Create: `tests/dod/test_8_4_generation.py`
- Create: `tests/dod/test_8_5_reasoning.py`
- Create: `tests/dod/test_8_6_caching.py`
- Create: `tests/dod/test_8_7_tool_calling.py`
- Create: `tests/dod/test_8_8_error_handling.py`

**Depends on:** Task 47
**Effort:** ~20 min total

Each file maps 1:1 to a DoD section from the spec (§8.1-8.8). Each checklist item becomes a test function. These tests use mocked SDK responses (no real API keys needed). The test names should match the spec checklist items verbatim.

Example for `test_8_1_core_infra.py`:
```python
"""DoD §8.1 — Core Infrastructure."""

# [ ] Client can be constructed from environment variables
def test_client_from_env() -> None: ...

# [ ] Client can be constructed programmatically
def test_client_programmatic() -> None: ...

# [ ] Provider routing dispatches correctly
def test_provider_routing() -> None: ...

# [ ] Default provider used when omitted
def test_default_provider() -> None: ...

# [ ] ConfigurationError when no provider configured
def test_no_provider_raises() -> None: ...

# [ ] Middleware chain order correct
def test_middleware_order() -> None: ...

# [ ] Module-level default client works
def test_default_client() -> None: ...

# [ ] Model catalog populated and working
def test_model_catalog() -> None: ...
```

---

### Task 49: DoD Test 8.9 — Cross-Provider Parity

**Files:**
- Create: `tests/dod/test_8_9_cross_provider_parity.py`

**Depends on:** Task 48
**Effort:** ~10 min

Parameterized test matrix: 15 test cases × 3 providers = 45 cells. Uses mocked SDK responses for each provider to verify behavior consistency without API keys.

```python
"""DoD §8.9 — Cross-Provider Parity Matrix.

15 test cases × 3 providers = 45 matrix cells.
Uses mocked SDK responses — no API keys needed.
"""

import pytest

PROVIDERS = ["openai", "anthropic", "gemini"]
TEST_CASES = [
    "simple_text_generation",
    "streaming_text_generation",
    "image_input_base64",
    "image_input_url",
    "single_tool_call",
    "parallel_tool_calls",
    "multi_step_tool_loop",
    "streaming_with_tool_calls",
    "structured_output",
    "reasoning_token_reporting",
    "error_handling_401",
    "error_handling_429",
    "usage_accuracy",
    "prompt_caching",
    "provider_options_passthrough",
]


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("test_case", TEST_CASES)
def test_cross_provider_parity(provider: str, test_case: str) -> None:
    """Each (provider, test_case) cell in the parity matrix."""
    # Implementation dispatches to per-test-case logic with provider-specific mocks
    ...
```

---

### Task 50: DoD Test 8.10 — Integration Smoke Tests

**Files:**
- Create: `tests/dod/test_8_10_integration_smoke.py`

**Depends on:** Task 49
**Effort:** ~5 min

6 end-to-end tests that require real API keys. These are marked with `@pytest.mark.integration` so they only run when keys are available:

```python
"""DoD §8.10 — Integration Smoke Tests.

Run with: pytest tests/dod/test_8_10_integration_smoke.py -m integration
Requires: OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY
"""

import os

import pytest

pytestmark = pytest.mark.integration

SKIP_REASON = "API keys not set"
HAS_KEYS = all(os.environ.get(k) for k in [
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
])


@pytest.mark.skipif(not HAS_KEYS, reason=SKIP_REASON)
class TestIntegrationSmoke:
    """6 end-to-end tests per spec §8.10."""

    def test_basic_generation_all_providers(self) -> None:
        """Spec: generate() across all providers returns non-empty text."""
        ...

    def test_streaming(self) -> None:
        """Spec: concatenated deltas == response.text."""
        ...

    def test_tool_calling_parallel(self) -> None:
        """Spec: tool loop with parallel execution, steps >= 2."""
        ...

    def test_image_input(self) -> None:
        """Spec: image input produces non-empty response."""
        ...

    def test_structured_output(self) -> None:
        """Spec: generate_object returns parsed, validated object."""
        ...

    def test_error_handling(self) -> None:
        """Spec: nonexistent model raises NotFoundError."""
        ...
```

---

## Summary

| Phase | Tasks | Description | Est. Effort |
|-------|-------|-------------|-------------|
| 1 | 1-14 | Scaffolding + all 30+ types + error hierarchy | ~45 min |
| 2 | 15-17 | Retry, middleware, catalog | ~15 min |
| 3 | 18-21 | Client class, routing, from_env | ~10 min |
| 4 | 22-27 | Anthropic adapter | ~25 min |
| 5 | 28-33 | OpenAI adapter | ~25 min |
| 6 | 34-38 | Gemini adapter | ~25 min |
| 7 | 39-45 | High-level API (generate, stream, etc.) | ~35 min |
| 8 | 46 | OpenAI-compatible adapter | ~10 min |
| 9 | 47-50 | Public exports + DoD tests | ~35 min |
| **Total** | **50 tasks** | | **~225 min (~4 hours)** |

**Key principles maintained throughout:**
- TDD: Every task writes tests first, then implementation
- Faithful to spec: Every type, function, behavior matches the NLSpec exactly
- Bite-sized: Each task is 2-5 minutes of focused work
- Dependency-ordered: Foundation first, then utilities, then client, then adapters, then high-level API
- Testable at each step: `pytest` should pass after every task
