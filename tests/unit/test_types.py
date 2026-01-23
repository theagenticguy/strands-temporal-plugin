"""Unit tests for strands_temporal_plugin.types module."""

import json
from strands_temporal_plugin.types import (
    AnthropicProviderConfig,
    BedrockProviderConfig,
    ModelExecutionInput,
    ModelExecutionResult,
    OllamaProviderConfig,
    OpenAIProviderConfig,
    ToolExecutionInput,
    ToolExecutionResult,
    messages_to_serializable,
    tool_specs_to_serializable,
)


class TestProviderConfigs:
    """Test provider configuration classes."""

    def test_bedrock_config_defaults(self):
        """Test BedrockProviderConfig with minimal required fields."""
        config = BedrockProviderConfig(model_id="anthropic.claude-3-sonnet")

        assert config.provider == "bedrock"
        assert config.model_id == "anthropic.claude-3-sonnet"
        assert config.max_tokens == 4096
        assert config.region_name is None
        assert config.temperature is None

    def test_bedrock_config_full(self):
        """Test BedrockProviderConfig with all fields."""
        config = BedrockProviderConfig(
            model_id="anthropic.claude-3-sonnet",
            region_name="us-west-2",
            max_tokens=8192,
            temperature=0.7,
            top_p=0.9,
            stop_sequences=["END"],
        )

        assert config.provider == "bedrock"
        assert config.model_id == "anthropic.claude-3-sonnet"
        assert config.region_name == "us-west-2"
        assert config.max_tokens == 8192
        assert config.temperature == 0.7
        assert config.top_p == 0.9
        assert config.stop_sequences == ["END"]

    def test_bedrock_config_serialization(self):
        """Test BedrockProviderConfig JSON serialization round-trip."""
        config = BedrockProviderConfig(
            model_id="anthropic.claude-3-sonnet",
            region_name="us-east-1",
            max_tokens=2048,
        )

        # Serialize to JSON
        json_str = config.model_dump_json()
        data = json.loads(json_str)

        # Verify discriminator field is present
        assert data["provider"] == "bedrock"

        # Deserialize back
        restored = BedrockProviderConfig.model_validate_json(json_str)
        assert restored == config

    def test_anthropic_config(self):
        """Test AnthropicProviderConfig."""
        config = AnthropicProviderConfig(
            model_id="claude-sonnet-4-20250514",
            max_tokens=4096,
        )

        assert config.provider == "anthropic"
        assert config.model_id == "claude-sonnet-4-20250514"

    def test_openai_config(self):
        """Test OpenAIProviderConfig."""
        config = OpenAIProviderConfig(
            model_id="gpt-4o",
            temperature=0.5,
        )

        assert config.provider == "openai"
        assert config.model_id == "gpt-4o"
        assert config.temperature == 0.5

    def test_ollama_config(self):
        """Test OllamaProviderConfig."""
        config = OllamaProviderConfig(
            model_id="llama3.2",
            host="http://localhost:11434",
        )

        assert config.provider == "ollama"
        assert config.model_id == "llama3.2"
        assert config.host == "http://localhost:11434"


class TestModelExecutionTypes:
    """Test model execution input/output types."""

    def test_model_execution_input_minimal(self):
        """Test ModelExecutionInput with minimal fields."""
        config = BedrockProviderConfig(model_id="anthropic.claude-3-sonnet")
        input_data = ModelExecutionInput(provider_config=config)

        assert input_data.provider_config == config
        assert input_data.messages is None
        assert input_data.tool_specs is None
        assert input_data.system_prompt is None

    def test_model_execution_input_full(self, sample_messages, sample_tool_spec):
        """Test ModelExecutionInput with all fields."""
        config = BedrockProviderConfig(model_id="anthropic.claude-3-sonnet")
        input_data = ModelExecutionInput(
            provider_config=config,
            messages=sample_messages,
            tool_specs=[sample_tool_spec],
            system_prompt="You are a helpful assistant.",
        )

        assert input_data.messages == sample_messages
        assert input_data.tool_specs == [sample_tool_spec]
        assert input_data.system_prompt == "You are a helpful assistant."

    def test_model_execution_input_serialization(self, sample_messages):
        """Test ModelExecutionInput JSON serialization."""
        config = BedrockProviderConfig(model_id="anthropic.claude-3-sonnet")
        input_data = ModelExecutionInput(
            provider_config=config,
            messages=sample_messages,
            system_prompt="Test prompt",
        )

        # Serialize
        json_str = input_data.model_dump_json()
        data = json.loads(json_str)

        # Verify structure
        assert "provider_config" in data
        assert data["provider_config"]["provider"] == "bedrock"
        assert data["messages"] == sample_messages

        # Deserialize
        restored = ModelExecutionInput.model_validate_json(json_str)
        assert restored.provider_config.model_id == config.model_id
        assert restored.messages == sample_messages

    def test_model_execution_result(self, sample_stream_events):
        """Test ModelExecutionResult."""
        result = ModelExecutionResult(events=sample_stream_events)

        assert result.events == sample_stream_events

        # Verify serialization
        json_str = result.model_dump_json()
        restored = ModelExecutionResult.model_validate_json(json_str)
        assert restored.events == sample_stream_events


class TestToolExecutionTypes:
    """Test tool execution input/output types."""

    def test_tool_execution_input(self):
        """Test ToolExecutionInput."""
        input_data = ToolExecutionInput(
            tool_name="get_weather",
            tool_module="my_app.tools",
            tool_input={"city": "Seattle"},
            tool_use_id="tool_123",
        )

        assert input_data.tool_name == "get_weather"
        assert input_data.tool_module == "my_app.tools"
        assert input_data.tool_input == {"city": "Seattle"}
        assert input_data.tool_use_id == "tool_123"

    def test_tool_execution_input_serialization(self):
        """Test ToolExecutionInput JSON serialization."""
        input_data = ToolExecutionInput(
            tool_name="get_weather",
            tool_module="my_app.tools",
            tool_input={"city": "Seattle", "units": "celsius"},
            tool_use_id="tool_456",
        )

        json_str = input_data.model_dump_json()
        restored = ToolExecutionInput.model_validate_json(json_str)

        assert restored == input_data

    def test_tool_execution_result_success(self):
        """Test ToolExecutionResult for success case."""
        result = ToolExecutionResult(
            tool_use_id="tool_123",
            status="success",
            content=[{"text": "The weather in Seattle is sunny, 72°F"}],
        )

        assert result.status == "success"
        assert result.tool_use_id == "tool_123"
        assert len(result.content) == 1

    def test_tool_execution_result_error(self):
        """Test ToolExecutionResult for error case."""
        result = ToolExecutionResult(
            tool_use_id="tool_123",
            status="error",
            content=[{"text": "Failed to fetch weather data"}],
        )

        assert result.status == "error"


class TestSerializationHelpers:
    """Test serialization helper functions."""

    def test_messages_to_serializable_none(self):
        """Test messages_to_serializable with None."""
        result = messages_to_serializable(None)
        assert result == []

    def test_messages_to_serializable_list(self, sample_messages):
        """Test messages_to_serializable with messages."""
        result = messages_to_serializable(sample_messages)
        assert result == sample_messages

    def test_tool_specs_to_serializable_none(self):
        """Test tool_specs_to_serializable with None."""
        result = tool_specs_to_serializable(None)
        assert result == []

    def test_tool_specs_to_serializable_list(self, sample_tool_spec):
        """Test tool_specs_to_serializable with specs."""
        result = tool_specs_to_serializable([sample_tool_spec])
        assert result == [sample_tool_spec]
