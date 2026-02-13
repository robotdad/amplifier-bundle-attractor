---
bundle:
  name: attractor
  version: 0.1.0
  description: >
    Attractor coding agent and pipeline framework for Amplifier.
    Implements the StrongDM Attractor nlspec — a non-interactive coding agent
    structured as a graph of phases, sufficient for use in a Software Factory.

includes:
  - bundle: git+https://github.com/microsoft/amplifier-foundation@main
  - bundle: attractor:behaviors/attractor-core

agents:
  attractor-profile-anthropic:
    bundle: attractor:profiles/attractor-profile-anthropic
    description: Attractor coding agent with Anthropic provider
  attractor-profile-openai:
    bundle: attractor:profiles/attractor-profile-openai
    description: Attractor coding agent with OpenAI provider
  attractor-profile-gemini:
    bundle: attractor:profiles/attractor-profile-gemini
    description: Attractor coding agent with Gemini provider
---

# Attractor

A non-interactive coding agent and pipeline framework built on Amplifier.

## Quick Start

Use a provider-specific profile for a complete configuration:

```yaml
includes:
  - bundle: git+https://github.com/microsoft/amplifier-bundle-attractor@main#subdirectory=profiles/attractor-profile-anthropic
```

## Available Profiles

- `attractor:profiles/attractor-profile-openai` — OpenAI (codex-rs aligned, apply_patch)
- `attractor:profiles/attractor-profile-anthropic` — Anthropic (Claude Code aligned, edit_file)
- `attractor:profiles/attractor-profile-gemini` — Gemini (gemini-cli aligned)
