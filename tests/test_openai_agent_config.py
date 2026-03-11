"""
TDD test for task-8: OpenAI host agent uses native apply_patch from filesystem bundle.
"""

import pytest
import yaml
from pathlib import Path

AGENT_YAML = Path(__file__).parent.parent / "agents" / "attractor-agent-openai.yaml"


@pytest.fixture(scope="module")
def raw_text():
    """Lazily read the YAML file once per test module run."""
    return AGENT_YAML.read_text()


@pytest.fixture(scope="module")
def config_data(raw_text):
    """Parse the YAML file once per test module run."""
    return yaml.safe_load(raw_text)


@pytest.fixture(scope="module")
def ap_tool(config_data):
    """Return the tool-apply-patch dict, asserting it exists."""
    tools = config_data.get("tools", [])
    ap = next((t for t in tools if t.get("module") == "tool-apply-patch"), None)
    assert ap is not None, "tool-apply-patch not found in tools"
    return ap


def test_yaml_is_valid(config_data):
    """YAML file must parse without errors."""
    assert config_data is not None


def test_apply_patch_source_is_filesystem_bundle(ap_tool):
    """tool-apply-patch must come from amplifier-bundle-filesystem, not attractor."""
    source = ap_tool.get("source", "")
    assert "amplifier-bundle-filesystem" in source, (
        f"Expected source from amplifier-bundle-filesystem, got: {source}"
    )
    assert "amplifier-bundle-attractor" not in source, (
        f"Source must NOT be from attractor bundle, got: {source}"
    )


def test_apply_patch_engine_native_config(ap_tool):
    """tool-apply-patch must have config with engine: native."""
    config = ap_tool.get("config", {})
    assert config.get("engine") == "native", (
        f"Expected engine: native in config, got: {config}"
    )


def test_apply_patch_allowed_write_paths(ap_tool):
    """tool-apply-patch config must have allowed_write_paths: ['.']."""
    config = ap_tool.get("config", {})
    assert config.get("allowed_write_paths") == ["."], (
        f"Expected allowed_write_paths: ['.'], got: {config.get('allowed_write_paths')}"
    )


def test_apply_patch_denied_write_paths(ap_tool):
    """tool-apply-patch config must have denied_write_paths: []."""
    config = ap_tool.get("config", {})
    assert config.get("denied_write_paths") == [], (
        f"Expected denied_write_paths: [], got: {config.get('denied_write_paths')}"
    )


def test_comment_mentions_native_apply_patch(raw_text):
    """Top comment must say 'native apply_patch (Responses API built-in)'."""
    assert "native apply_patch (Responses API built-in)" in raw_text, (
        "Top comment must be updated to say 'native apply_patch (Responses API built-in)'"
    )


def test_description_mentions_native_apply_patch(config_data):
    """Bundle description field must mention native apply_patch."""
    description = config_data.get("bundle", {}).get("description", "")
    assert "native apply_patch" in description, (
        f"Description must mention 'native apply_patch', got: {description!r}"
    )
