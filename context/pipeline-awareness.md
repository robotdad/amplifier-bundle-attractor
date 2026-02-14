# Pipeline Capabilities

You have access to the `run_pipeline` tool which can execute DOT graph pipelines.

## When to Use Pipelines

Use `run_pipeline` when the user asks you to:
- Run a pipeline or workflow defined in a `.dot` file
- Execute a multi-step coding pipeline
- Run an Attractor pipeline

## How to Use

Call `run_pipeline` with:
- **`goal`** (required): The task description. This replaces `$goal` in node prompts.
- **`dot_file`** (optional): Path to a `.dot` file. Supports `@attractor:` mentions.
- **`dot_source`** (optional): Inline DOT digraph string.

You must provide either `dot_file` or `dot_source`.

## Examples

Run a pipeline from a file:
```json
{
  "goal": "Refactor the authentication module to use async patterns",
  "dot_file": "@attractor:examples/pipelines/02-plan-implement-test.dot"
}
```

Run a simple inline pipeline:
```json
{
  "goal": "Add input validation to the user registration endpoint",
  "dot_source": "digraph { start [shape=Mdiamond]; implement [prompt=\"$goal\"]; test [prompt=\"Write tests for the changes\"]; done [shape=Msquare]; start -> implement -> test -> done }"
}
```

## Available Example Pipelines

- `@attractor:examples/pipelines/01-simple-linear.dot` — Minimal start -> implement -> done
- `@attractor:examples/pipelines/02-plan-implement-test.dot` — Plan, implement, test cycle
- `@attractor:examples/pipelines/03-conditional-routing.dot` — Conditional branching based on outcomes
- `@attractor:examples/pipelines/04-retry-with-fallback.dot` — Retry logic with fallback paths
- `@attractor:examples/pipelines/06-model-stylesheet.dot` — Multi-provider model selection
