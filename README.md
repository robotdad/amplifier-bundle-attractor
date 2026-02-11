# Attractor Bundle

A non-interactive coding agent and pipeline framework built on [Amplifier](https://github.com/microsoft/amplifier-core).

Attractor implements the StrongDM Attractor nlspec — a coding agent structured as a graph of phases, sufficient for use in a Software Factory.

## Quick Start

Use a provider-specific profile for a complete configuration:

```yaml
# In your bundle.md or amplifier config:
includes:
  - bundle: git+https://github.com/bkrabach/amplifier-bundle-attractor@main#subdirectory=profiles/attractor-profile-anthropic
```

## Available Profiles

| Profile | Provider | Edit Style | Shell Timeout |
|---------|----------|-----------|---------------|
| `attractor-profile-openai` | OpenAI | `apply_patch` (codex-rs aligned) | 10s |
| `attractor-profile-anthropic` | Anthropic | `edit_file` (Claude Code aligned) | 120s |
| `attractor-profile-gemini` | Gemini | `edit_file` (gemini-cli aligned) | 10s |

## Structure

```
amplifier-bundle-attractor/
├── bundle.md                    # Entry point (thin bundle)
├── behaviors/
│   └── attractor-core.yaml     # Shared tools + hooks (provider-agnostic)
├── profiles/                    # Provider-specific complete configs
│   ├── attractor-profile-openai.yaml
│   ├── attractor-profile-anthropic.yaml
│   └── attractor-profile-gemini.yaml
├── context/                     # System prompts per provider
│   ├── system-openai.md
│   ├── system-anthropic.md
│   └── system-gemini.md
├── specs/                       # Attractor nlspec documents
│   ├── attractor-spec.md
│   ├── coding-agent-loop-spec.md
│   └── unified-llm-spec.md
├── docs/plans/                  # Implementation planning docs
└── modules/                     # Amplifier modules
    ├── loop-agent/              # Agent loop orchestrator
    ├── loop-pipeline/           # DOT graph-driven pipeline orchestrator
    ├── tool-apply-patch/        # v4a unified diff tool (OpenAI only)
    ├── tool-report-outcome/     # Structured outcome reporting tool
    └── hooks-tool-truncation/   # Tool output truncation hook
```

## Architecture

### Layers

- **attractor-core** (behavior): Provider-agnostic tools and hooks shared by all profiles. Includes `tool-report-outcome` and `hooks-tool-truncation`.
- **Profiles**: Each profile includes `attractor-core` and adds a provider, orchestrator, provider-specific tools, and a system prompt.
- **Modules**: Self-contained Amplifier modules, each independently testable.

### Module Responsibilities

| Module | Type | Description |
|--------|------|-------------|
| `loop-agent` | orchestrator | Single-turn coding agent loop with steering, loop detection, and context management |
| `loop-pipeline` | orchestrator | Multi-stage DOT graph-driven pipeline with checkpointing and retry |
| `tool-apply-patch` | tool | v4a unified diff patch application (OpenAI/codex-rs style) |
| `tool-report-outcome` | tool | Structured result reporting for pipeline integration |
| `hooks-tool-truncation` | hook | Truncates large tool outputs to manage context window |

## Development

### Running Tests

Each module is independently testable:

```bash
cd modules/loop-agent && uv run pytest tests/ -q
cd modules/loop-pipeline && uv run pytest tests/ -q
cd modules/tool-apply-patch && uv run pytest tests/ -q
cd modules/tool-report-outcome && uv run pytest tests/ -q
cd modules/hooks-tool-truncation && uv run pytest tests/ -q
```

### Local Development

The `pyproject.toml` in each module points to `amplifier-core` via relative path for local development:

```toml
[tool.uv.sources]
amplifier-core = { path = "../../../amplifier-core", editable = true }
```

## Module Source of Truth

The canonical source for all Attractor modules is this bundle repository under `modules/`.
Standalone module repositories (e.g., `amplifier-module-loop-agent`,
`amplifier-module-loop-pipeline`, `amplifier-module-hooks-tool-truncation`) may exist
in the `attractor-next` workspace or on GitHub but **may be stale or diverged**.

Always develop against and submit changes to the copies in this bundle:

- `modules/loop-agent/`
- `modules/loop-pipeline/`
- `modules/tool-apply-patch/`
- `modules/tool-report-outcome/`
- `modules/hooks-tool-truncation/`

## License

MIT
