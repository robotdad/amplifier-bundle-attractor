# Isolated Environment Agent Profiles Design

## Goal

Ensure that when attractor pipeline nodes execute in isolated environments (Docker, SSH), the LLM agent can ONLY use environment tools (`env_exec`, `env_read_file`, etc.) and cannot accidentally use host-local tools (`bash`, `read_file`, `write_file`) that would break isolation.

This is achieved through two mechanisms:

1. Isolated agent profile variants that exclude standard file/bash/search tools
2. Documentation guidance for bundle authors on correct composition

## Background

The execution-environments project provides `env_*` namespaced tools (`env_exec`, `env_read_file`, `env_write_file`, etc.) that route operations through an EnvironmentBackend (Docker, SSH, Local). The attractor pipeline orchestrator can create a Docker container at pipeline start and have child sessions attach to it.

The problem: when both `env_*` tools and standard tools (`tool-filesystem`, `tool-bash`, `tool-search`) are available in the same session, the LLM may use the standard tools instead of the environment tools, breaking container isolation. Files get written to the host instead of the container.

A "Phase 2 transparent routing" approach was considered (where standard tool names automatically route through the environment) but rejected because it creates cross-module dependencies that violate `REPOSITORY_RULES.md`. Modules should not have awareness of or dependencies on other modules.

Instead, the solution is compositional: provide agent profiles that include ONLY the environment tools, and document guidance for bundle authors to not mix both tool sets.

## Key Design Decisions

1. **No cross-module coupling** -- The attractor bundle does not import, depend on, or have awareness of the execution-environments bundle. The isolation is achieved purely through bundle YAML composition.
2. **Isolated profiles are separate YAML files** -- Not runtime logic that conditionally excludes tools. This follows Amplifier's declarative composition model.
3. **Guidance over enforcement** -- We tell developers what to do, we don't build validation logic to prevent mixing. This is consistent with Amplifier's philosophy (mechanism, not policy).

## Architecture

### Component Overview

```
amplifier-bundle-attractor/
  agents/
    attractor-agent-anthropic.yaml              # existing -- standard tools (local)
    attractor-agent-anthropic-isolated.yaml     # NEW -- env_* tools only (Docker/SSH)
    attractor-agent-openai.yaml                 # existing -- standard tools (local)
    attractor-agent-openai-isolated.yaml        # NEW -- env_* tools only (Docker/SSH)
    attractor-agent-gemini.yaml                 # existing -- standard tools (local)
    attractor-agent-gemini-isolated.yaml        # NEW -- env_* tools only (Docker/SSH)
  context/
    isolated-environment-guidance.md            # NEW -- LLM instructions for env_* tools
  docs/
    APP-INTEGRATION-GUIDE.md                    # updated -- isolation guidance added
    GETTING-STARTED.md                          # updated -- isolation guidance added
```

### How It Works

The pipeline orchestrator does not change. The user's bundle config simply references the isolated profiles instead of the standard ones:

```yaml
profiles:
  anthropic: attractor-anthropic-isolated
```

When `execution_environment` is configured with isolated profiles, the LLM has no choice -- there is only one set of file/exec tools available, and they all route through the environment.

## Components

### Isolated Agent Profiles

Three new YAML files, one per provider:

- `agents/attractor-agent-anthropic-isolated.yaml`
- `agents/attractor-agent-openai-isolated.yaml`
- `agents/attractor-agent-gemini-isolated.yaml`

Each isolated profile:

- **Includes** `env-all` behavior instead of `tool-filesystem` + `tool-bash` + `tool-search`
- **Includes** a system prompt context that instructs the LLM to use only environment tools
- **Includes** `tool-report-outcome` (pipeline outcome reporting is not environment-specific)
- **Includes** `hooks-tool-truncation` (truncation is environment-agnostic)
- **Excludes** `tool-filesystem`, `tool-bash`, `tool-search`

### Isolated Environment Guidance Context

A new context file (`context/isolated-environment-guidance.md`) loaded into sessions using isolated profiles. This gives the LLM explicit instructions:

> Use `env_exec`, `env_read_file`, `env_write_file`, `env_edit_file`, `env_grep`, `env_glob` for all file and command operations. Do NOT use `bash`, `read_file`, `write_file`, or any tools that operate on the host filesystem directly.

### Documentation Updates

Guidance added to `docs/APP-INTEGRATION-GUIDE.md` and `docs/GETTING-STARTED.md` covering three rules:

1. **When composing `env-all` for isolated execution, do NOT also compose `tool-filesystem`, `tool-bash`, or `tool-search`.** Having both sets of tools creates ambiguity -- the LLM may use the host-local tools instead of the environment tools, breaking isolation.

2. **Use the isolated agent profiles** (`attractor-agent-anthropic-isolated`, etc.) when running pipelines with `execution_environment` configured.

3. **If building custom profiles**, the rule is: include `env-all` behavior OR standard file/bash/search tools, never both. The `tool-report-outcome` and `hooks-tool-truncation` modules are environment-agnostic and safe to include alongside either set.

## Data Flow

Standard (local) execution:

```
Pipeline Orchestrator
  -> Child Session (standard profile)
    -> tool-filesystem (read_file, write_file, etc.)
    -> tool-bash (bash)
    -> tool-search (grep, glob)
    -> Operates on host filesystem directly
```

Isolated (Docker/SSH) execution:

```
Pipeline Orchestrator
  -> Child Session (isolated profile)
    -> env-all (env_read_file, env_write_file, env_exec, etc.)
    -> EnvironmentBackend routes to Docker/SSH
    -> Operates inside container/remote host
```

## Error Handling

No new error handling is required. If a user accidentally mixes both tool sets (ignoring guidance), the standard tools would operate on the host and env tools on the container. The result would be incorrect behavior, but not crashes or errors. The guidance documentation exists to prevent this configuration mistake.

## Scope Boundaries

- This design covers isolated profiles for the three existing providers (Anthropic, OpenAI, Gemini)
- No changes to the execution-environments project
- No changes to the pipeline orchestrator or engine
- No runtime validation or enforcement -- purely compositional and documentation-based
- Phase 2 transparent routing is NOT in scope -- it requires foundation-level changes and creates coupling

## Testing Strategy

1. Verify the isolated profile YAML files are well-formed and reference correct sources
2. Verify the standard tools (`bash`, `read_file`) are NOT present in the isolated profiles
3. Verify the `env_*` tools ARE present in the isolated profiles
4. Integration: run the Docker E2E test with an isolated profile and verify operations happen in the container

## Open Questions

None -- the design is straightforward.
