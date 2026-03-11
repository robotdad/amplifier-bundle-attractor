"""
TDD test for task-8: OpenAI host agent uses native apply_patch from filesystem bundle.
"""

import yaml
from pathlib import Path

AGENT_YAML = Path(__file__).parent.parent / "agents" / "attractor-agent-openai.yaml"
RAW_TEXT = AGENT_YAML.read_text()


def _load_yaml():
    return yaml.safe_load(RAW_TEXT)


def test_yaml_is_valid():
    """YAML file must parse without errors."""
    data = _load_yaml()
    assert data is not None


def test_apply_patch_source_is_filesystem_bundle():
    """tool-apply-patch must come from amplifier-bundle-filesystem, not attractor."""
    data = _load_yaml()
    tools = data.get("tools", [])
    ap = next((t for t in tools if t.get("module") == "tool-apply-patch"), None)
    assert ap is not None, "tool-apply-patch not found in tools"
    source = ap.get("source", "")
    assert "amplifier-bundle-filesystem" in source, (
        f"Expected source from amplifier-bundle-filesystem, got: {source}"
    )
    assert "amplifier-bundle-attractor" not in source, (
        f"Source must NOT be from attractor bundle, got: {source}"
    )


def test_apply_patch_engine_native_config():
    """tool-apply-patch must have config with engine: native."""
    data = _load_yaml()
    tools = data.get("tools", [])
    ap = next((t for t in tools if t.get("module") == "tool-apply-patch"), None)
    assert ap is not None, "tool-apply-patch not found in tools"
    config = ap.get("config", {})
    assert config.get("engine") == "native", (
        f"Expected engine: native in config, got: {config}"
    )


def test_apply_patch_allowed_write_paths():
    """tool-apply-patch config must have allowed_write_paths: ['.']."""
    data = _load_yaml()
    tools = data.get("tools", [])
    ap = next((t for t in tools if t.get("module") == "tool-apply-patch"), None)
    assert ap is not None, "tool-apply-patch not found in tools"
    config = ap.get("config", {})
    assert config.get("allowed_write_paths") == ["."], (
        f"Expected allowed_write_paths: ['.'], got: {config.get('allowed_write_paths')}"
    )


def test_apply_patch_denied_write_paths():
    """tool-apply-patch config must have denied_write_paths: []."""
    data = _load_yaml()
    tools = data.get("tools", [])
    ap = next((t for t in tools if t.get("module") == "tool-apply-patch"), None)
    assert ap is not None, "tool-apply-patch not found in tools"
    config = ap.get("config", {})
    assert config.get("denied_write_paths") == [], (
        f"Expected denied_write_paths: [], got: {config.get('denied_write_paths')}"
    )


def test_comment_mentions_native_apply_patch():
    """Top comment must say 'native apply_patch (Responses API built-in)'."""
    assert "native apply_patch (Responses API built-in)" in RAW_TEXT, (
        "Top comment must be updated to say 'native apply_patch (Responses API built-in)'"
    )


def test_description_mentions_native_apply_patch():
    """Bundle description field must mention native apply_patch."""
    data = _load_yaml()
    description = data.get("bundle", {}).get("description", "")
    assert "native apply_patch" in description, (
        f"Description must mention 'native apply_patch', got: {description!r}"
    )
