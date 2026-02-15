# Attractor

Multi-stage AI pipelines for code. Plan, implement, test, review — orchestrated as
directed graphs.

## Quick Start (30 seconds)

1. Add Attractor to your Amplifier config:
   ```yaml
   includes:
     - bundle: git+https://github.com/microsoft/amplifier-bundle-attractor@main#subdirectory=profiles/attractor-profile-anthropic
   ```

2. Ask the agent to run a pipeline:
   > "Run the plan-implement-test pipeline to add input validation to the login endpoint"

3. Or run directly from the CLI:
   ```bash
   amp run --agent attractor-anthropic --goal "Add input validation" \
       --dot-file examples/pipelines/02-plan-implement-test.dot
   ```

4. Or generate a pipeline on-the-fly:
   > "Build a test suite for the auth module using a parallel pipeline"

## What Can It Do?

**Fix a bug systematically** — Reproduce, diagnose, fix, regression test, verify:
```
amp run --dot-file examples/pipelines/practical/bug-fix.dot \
    --goal "Fix the NullPointerError in UserService.getProfile()"
```

**Review a PR in parallel** — Analyze diff, then simultaneously check for bugs, security,
performance, and style — then prioritize and generate review comments:
```
amp run --dot-file examples/pipelines/practical/pr-review.dot \
    --goal "Review PR #142"
```

**Build a feature safely** — Parse spec, parallel implement (core, API, tests),
integration test, human review gate:
```
amp run --dot-file examples/pipelines/practical/feature-build.dot \
    --goal "Add user avatar upload with S3 storage"
```

## Pipeline Gallery

| Pipeline | Pattern | Use Case |
|----------|---------|----------|
| [Simple Linear](examples/pipelines/01-simple-linear.dot) | `A -> B -> C` | Quick single-task |
| [Plan-Implement-Test](examples/pipelines/02-plan-implement-test.dot) | `plan -> impl -> test` | Standard dev workflow |
| [Conditional Routing](examples/pipelines/03-conditional-routing.dot) | `if/else` branches | Outcome-based flow |
| [Retry with Fallback](examples/pipelines/04-retry-with-fallback.dot) | Retry loop | Resilient execution |
| [Parallel Fan-Out](examples/pipelines/05-parallel-fan-out.dot) | Fork/join | Concurrent work |
| [Model Stylesheet](examples/pipelines/06-model-stylesheet.dot) | CSS-like config | Multi-provider |
| [Fidelity Modes](examples/pipelines/07-fidelity-modes.dot) | Context control | Execution fidelity |
| [Human Gate](examples/pipelines/08-human-gate.dot) | Approval gate | Human-in-the-loop |
| [Manager-Supervisor](examples/pipelines/09-manager-supervisor.dot) | Hierarchical | Agent supervision |
| [Full Attractor](examples/pipelines/10-full-attractor.dot) | All features | Complete pipeline |
| [PR Review](examples/pipelines/practical/pr-review.dot) | Parallel analysis | Code review |
| [Test Generation](examples/pipelines/practical/test-gen.dot) | Retry loop | Test authoring |
| [Bug Fix](examples/pipelines/practical/bug-fix.dot) | Diagnose + verify | Debugging |
| [Feature Build](examples/pipelines/practical/feature-build.dot) | Parallel + gate | Feature development |
| [Refactoring](examples/pipelines/practical/refactor.dot) | Snapshot safety | Code improvement |

## How It Works

The **loop-pipeline** orchestrator walks a Graphviz DOT digraph. Each node is an AI task
(or control node like fork/join/gate), and edges define the flow between them. The
orchestrator spawns a **loop-agent** session per node, which runs a mini agentic tool
loop — call LLM, execute tools, feed results back — until the node completes.

## Customization

- **Model stylesheets** — Override provider, model, and reasoning effort per-node via CSS-like selectors
- **Fidelity modes** — Control context carryover between nodes (full, compact, summary)
- **Human gates** — Pause pipelines for human approval at any stage
- **`$param` expansion** — Pass key-value parameters to pipelines for template reuse:
  ```json
  {
    "goal": "Build a REST API",
    "dot_file": "template.dot",
    "params": {"language": "Python", "framework": "FastAPI"}
  }
  ```

## DOT Syntax

See [docs/DOT-SYNTAX.md](docs/DOT-SYNTAX.md) for the complete reference.

Quick version — pipelines are Graphviz DOT digraphs where node shapes determine behavior:

| Shape | What it does |
|-------|-------------|
| `Mdiamond` | Start node (entry point) |
| `Msquare` | Exit node (pipeline end) |
| `box` | LLM agent node (default) |
| `component` | Parallel fan-out |
| `tripleoctagon` | Parallel fan-in (collect results) |
| `house` | Human approval gate |
| `diamond` | Decision/routing node |

## Available Profiles

| Profile | Provider | Best For |
|---------|----------|----------|
| `attractor-profile-anthropic` | Anthropic Claude | Tool-heavy coding tasks |
| `attractor-profile-openai` | OpenAI | Reasoning-heavy analysis |
| `attractor-profile-gemini` | Gemini | Large context tasks |

<details>
<summary>Architecture</summary>

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
├── examples/pipelines/          # 10 example + 5 practical DOT pipelines
├── modules/                     # Amplifier modules
│   ├── loop-agent/              # Agent loop orchestrator
│   ├── loop-pipeline/           # DOT graph-driven pipeline orchestrator
│   ├── tool-apply-patch/        # v4a unified diff tool (OpenAI only)
│   ├── tool-report-outcome/     # Structured outcome reporting tool
│   ├── tool-pipeline-run/       # Runtime pipeline invocation tool
│   ├── hooks-tool-truncation/   # Tool output truncation hook
│   └── hooks-pipeline-progress/ # Pipeline progress reporting hook
└── docs/                        # Documentation
    └── DOT-SYNTAX.md            # DOT syntax cheat sheet
```

### Module Responsibilities

| Module | Type | Description |
|--------|------|-------------|
| `loop-agent` | orchestrator | Single-turn coding agent loop with steering, loop detection, and context management |
| `loop-pipeline` | orchestrator | Multi-stage DOT graph-driven pipeline with checkpointing and retry |
| `tool-apply-patch` | tool | v4a unified diff patch application (OpenAI/codex-rs style) |
| `tool-report-outcome` | tool | Structured result reporting for pipeline integration |
| `tool-pipeline-run` | tool | Runtime pipeline invocation via session.spawn |
| `hooks-tool-truncation` | hook | Truncates large tool outputs to manage context window |
| `hooks-pipeline-progress` | hook | Reports pipeline stage progress |

</details>

## Development

Each module is independently testable:

```bash
cd modules/loop-agent && uv run pytest tests/ -q
cd modules/loop-pipeline && uv run pytest tests/ -q
cd modules/tool-apply-patch && uv run pytest tests/ -q
cd modules/tool-report-outcome && uv run pytest tests/ -q
cd modules/tool-pipeline-run && uv run pytest tests/ -q
cd modules/hooks-tool-truncation && uv run pytest tests/ -q
```

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
