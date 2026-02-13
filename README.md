# Attractor

A multi-stage AI pipeline engine and non-interactive coding agent built on [Amplifier](https://github.com/microsoft/amplifier-core).

Attractor implements the Attractor specification — a coding agent structured as a directed graph of phases, with support for conditional routing, parallel execution, human approval gates, and retry logic. It is designed for use in automated Software Factory workflows.

## Features

- **DOT graph pipelines** — Define multi-stage agent workflows as Graphviz DOT files
- **Coding agent loop** — Single-turn agent orchestrator with steering, loop detection, and context management
- **Parallel execution** — Fan-out to multiple nodes with configurable concurrency
- **Conditional routing** — Branch pipeline execution based on prior stage outcomes
- **Human approval gates** — Pause pipelines for human review before proceeding
- **Retry with fallback** — Automatic retry with configurable fallback routing on failure
- **Model stylesheets** — Override provider, model, and parameters per-node via CSS-like selectors
- **Fidelity modes** — Control execution fidelity (full LLM calls, direct pass-through, etc.)
- **Checkpointing** — Resume interrupted pipelines from the last completed stage
- **Multi-provider support** — Ready-made profiles for Anthropic, OpenAI, and Gemini

## Quick Start

Use a provider-specific profile for a complete configuration:

```yaml
# In your bundle.md or amplifier config:
includes:
  - bundle: git+https://github.com/microsoft/amplifier-bundle-attractor@main#subdirectory=profiles/attractor-profile-anthropic
```

## Available Profiles

| Profile | Provider | Edit Style | Shell Timeout |
|---------|----------|-----------|---------------|
| `attractor-profile-openai` | OpenAI | `apply_patch` (codex-rs aligned) | 10s |
| `attractor-profile-anthropic` | Anthropic | `edit_file` (Claude Code aligned) | 120s |
| `attractor-profile-gemini` | Gemini | `edit_file` (gemini-cli aligned) | 10s |

## Example Pipelines

The [`examples/pipelines/`](examples/pipelines/) directory contains 10 example pipelines demonstrating each capability:

| # | Example | Description |
|---|---------|-------------|
| 01 | [Simple Linear](examples/pipelines/01-simple-linear.md) | Basic sequential pipeline |
| 02 | [Plan-Implement-Test](examples/pipelines/02-plan-implement-test.md) | Three-phase development workflow |
| 03 | [Conditional Routing](examples/pipelines/03-conditional-routing.md) | Branch execution based on outcomes |
| 04 | [Retry with Fallback](examples/pipelines/04-retry-with-fallback.md) | Automatic retry and fallback paths |
| 05 | [Parallel Fan-Out](examples/pipelines/05-parallel-fan-out.md) | Concurrent node execution |
| 06 | [Model Stylesheet](examples/pipelines/06-model-stylesheet.md) | Per-node model and parameter overrides |
| 07 | [Fidelity Modes](examples/pipelines/07-fidelity-modes.md) | Execution fidelity control |
| 08 | [Human Gate](examples/pipelines/08-human-gate.md) | Human-in-the-loop approval gates |
| 09 | [Manager-Supervisor](examples/pipelines/09-manager-supervisor.md) | Hierarchical agent supervision |
| 10 | [Full Attractor](examples/pipelines/10-full-attractor.md) | Complete pipeline combining all features |

## Architecture

### Layers

- **attractor-core** (behavior): Provider-agnostic tools and hooks shared by all profiles. Includes `tool-report-outcome` and `hooks-tool-truncation`.
- **Profiles**: Each profile includes `attractor-core` and adds a provider, orchestrator, provider-specific tools, and a system prompt.
- **Modules**: Self-contained Amplifier modules, each independently testable.

### Repository Structure

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
├── specs/                       # Attractor specification documents
│   ├── attractor-spec.md
│   ├── coding-agent-loop-spec.md
│   └── unified-llm-spec.md
├── examples/pipelines/          # 10 example DOT pipelines
├── modules/                     # Amplifier modules
│   ├── loop-agent/              # Agent loop orchestrator
│   ├── loop-pipeline/           # DOT graph-driven pipeline orchestrator
│   ├── tool-apply-patch/        # v4a unified diff tool (OpenAI only)
│   ├── tool-report-outcome/     # Structured outcome reporting tool
│   ├── hooks-tool-truncation/   # Tool output truncation hook
│   └── hooks-pipeline-progress/ # Pipeline progress reporting hook
└── docs/plans/                  # Implementation planning docs
```

### Module Responsibilities

| Module | Type | Description |
|--------|------|-------------|
| `loop-agent` | orchestrator | Single-turn coding agent loop with steering, loop detection, and context management |
| `loop-pipeline` | orchestrator | Multi-stage DOT graph-driven pipeline with checkpointing and retry |
| `tool-apply-patch` | tool | v4a unified diff patch application (OpenAI/codex-rs style) |
| `tool-report-outcome` | tool | Structured result reporting for pipeline integration |
| `hooks-tool-truncation` | hook | Truncates large tool outputs to manage context window |
| `hooks-pipeline-progress` | hook | Reports pipeline stage progress |

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

## Contributing

This project welcomes contributions and suggestions. Please see our [Code of Conduct](CODE_OF_CONDUCT.md) for community guidelines.

For bugs and feature requests, please [open a GitHub issue](https://github.com/microsoft/amplifier-bundle-attractor/issues). See [SUPPORT.md](SUPPORT.md) for additional support information.

## License

This project is licensed under the [MIT License](LICENSE).

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft
trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.
