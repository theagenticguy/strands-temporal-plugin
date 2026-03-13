"""Unit tests for runner.py - Auto-discovery and durable agent creation."""

import pytest
from strands import tool
from strands.models.model import Model as StrandsModel
from strands_temporal_plugin import BedrockProviderConfig
from strands_temporal_plugin.runner import TemporalModelStub, _extract_tool_modules, create_durable_agent


@tool
def sample_tool(arg: str) -> str:
    """Sample tool for testing."""
    return arg


def test_extract_tool_modules_success():
    """Test auto-discovery from decorated tool functions."""
    result = _extract_tool_modules([sample_tool])

    assert "sample_tool" in result
    assert result["sample_tool"] == "tests.unit.test_runner"


def test_extract_tool_modules_main_module_raises():
    """Test that __main__ module tools raise clear error."""
    @tool
    def local_tool():
        pass

    # Simulate __main__ module
    local_tool.__module__ = "__main__"

    with pytest.raises(ValueError) as exc:
        _extract_tool_modules([local_tool])

    assert "__main__" in str(exc.value)
    assert "importable module" in str(exc.value)


def test_extract_tool_modules_missing_name():
    """Test error when tool lacks __name__ attribute."""
    class BadTool:
        pass

    bad_tool = BadTool()

    with pytest.raises(ValueError) as exc:
        _extract_tool_modules([bad_tool])

    assert "Cannot determine tool name" in str(exc.value)


def test_create_durable_agent_without_tool_modules():
    """Test that tool_modules can be omitted (auto-discovery)."""
    agent = create_durable_agent(
        provider_config=BedrockProviderConfig(model_id="test"),
        tools=[sample_tool],
        # No tool_modules provided - should auto-discover
    )

    # Verify tool executor has the mapping
    assert agent.tool_executor.tool_modules == {
        "sample_tool": "tests.unit.test_runner"
    }


def test_create_durable_agent_explicit_override():
    """Test that explicit tool_modules overrides auto-discovery."""
    agent = create_durable_agent(
        provider_config=BedrockProviderConfig(model_id="test"),
        tools=[sample_tool],
        tool_modules={"sample_tool": "custom.path"},  # Explicit override
    )

    # Verify explicit takes precedence
    assert agent.tool_executor.tool_modules["sample_tool"] == "custom.path"


def test_create_durable_agent_partial_override():
    """Test mixing auto-discovery with explicit overrides."""
    @tool
    def tool_a():
        pass

    @tool
    def tool_b():
        pass

    agent = create_durable_agent(
        provider_config=BedrockProviderConfig(model_id="test"),
        tools=[tool_a, tool_b],
        tool_modules={"tool_b": "custom.override"},  # Only override tool_b
    )

    modules = agent.tool_executor.tool_modules
    assert modules["tool_a"] == "tests.unit.test_runner"  # Auto-discovered
    assert modules["tool_b"] == "custom.override"  # Explicit


def test_create_durable_agent_no_tools():
    """Test creating agent without any tools."""
    agent = create_durable_agent(
        provider_config=BedrockProviderConfig(model_id="test"),
        tools=None,
    )

    # Should work fine with empty tool modules
    assert agent.tool_executor.tool_modules == {}


def test_create_durable_agent_main_module_without_explicit_fails():
    """Test that __main__ tools fail when no explicit mapping provided."""
    @tool
    def main_tool():
        pass

    main_tool.__module__ = "__main__"

    with pytest.raises(ValueError) as exc:
        create_durable_agent(
            provider_config=BedrockProviderConfig(model_id="test"),
            tools=[main_tool],
        )

    assert "__main__" in str(exc.value)


def test_create_durable_agent_main_module_with_explicit_works():
    """Test that __main__ tools work when explicit mapping provided."""
    @tool
    def main_tool():
        pass

    main_tool.__module__ = "__main__"

    # Should work with explicit mapping
    agent = create_durable_agent(
        provider_config=BedrockProviderConfig(model_id="test"),
        tools=[main_tool],
        tool_modules={"main_tool": "myapp.tools"},  # Explicit override
    )

    assert agent.tool_executor.tool_modules["main_tool"] == "myapp.tools"


def test_temporal_model_stub_is_strands_model():
    """Test that TemporalModelStub is a subclass of the Strands Model ABC."""
    stub = TemporalModelStub(BedrockProviderConfig(model_id="test"))
    assert isinstance(stub, StrandsModel)


@pytest.mark.asyncio
async def test_stream_accepts_keyword_only_params():
    """Test that stream() accepts the SDK's keyword-only params without error."""
    from strands_temporal_plugin.types import ModelExecutionResult
    from unittest.mock import AsyncMock, patch

    with patch("strands_temporal_plugin.runner.workflow") as mock_workflow:
        mock_workflow.patched.return_value = True
        mock_result = ModelExecutionResult(events=[{"messageStart": {"role": "assistant"}}])
        mock_workflow.execute_activity = AsyncMock(return_value=mock_result)

        stub = TemporalModelStub(BedrockProviderConfig(model_id="test"))
        events = []
        async for event in stub.stream(
            messages=[{"role": "user", "content": [{"text": "Hi"}]}],
            tool_specs=None,
            system_prompt=None,
            tool_choice=None,
            system_prompt_content=None,
            invocation_state={"key": "value"},
        ):
            events.append(event)

        assert len(events) == 1
