"""Unit tests for strands_temporal_plugin.durable_agent module."""

from strands_temporal_plugin.durable_agent import DurableAgent, DurableAgentResult
from strands_temporal_plugin.types import BedrockProviderConfig, DurableAgentConfig


class TestDurableAgentResult:
    """Test DurableAgentResult dataclass."""

    def test_result_basic(self):
        """Test basic DurableAgentResult creation."""
        result = DurableAgentResult(
            text="Hello, world!",
            messages=[{"role": "assistant", "content": [{"text": "Hello, world!"}]}],
        )

        assert result.text == "Hello, world!"
        assert len(result.messages) == 1
        assert result.stop_reason is None
        assert result.usage == {}

    def test_result_full(self):
        """Test DurableAgentResult with all fields."""
        messages = [
            {"role": "user", "content": [{"text": "Hi"}]},
            {"role": "assistant", "content": [{"text": "Hello!"}]},
        ]
        result = DurableAgentResult(
            text="Hello!",
            messages=messages,
            stop_reason="end_turn",
            usage={"input_tokens": 5, "output_tokens": 10},
        )

        assert result.text == "Hello!"
        assert result.messages == messages
        assert result.stop_reason == "end_turn"
        assert result.usage["input_tokens"] == 5
        assert result.usage["output_tokens"] == 10


class TestDurableAgentInit:
    """Test DurableAgent initialization."""

    def test_init_minimal(self):
        """Test DurableAgent initialization with minimal config."""
        config = DurableAgentConfig(provider_config=BedrockProviderConfig(model_id="anthropic.claude-3-sonnet"))
        agent = DurableAgent(config)

        assert agent.config == config
        assert agent.messages == []

    def test_init_with_tools(self, sample_tool_spec):
        """Test DurableAgent initialization with tools."""
        config = DurableAgentConfig(
            provider_config=BedrockProviderConfig(model_id="anthropic.claude-3-sonnet"),
            system_prompt="You are a helpful assistant.",
            tool_specs=[sample_tool_spec],
            tool_modules={"get_weather": "my_app.tools"},
        )
        agent = DurableAgent(config)

        assert agent.config.system_prompt == "You are a helpful assistant."
        assert len(agent.config.tool_specs) == 1
        assert agent.config.tool_modules["get_weather"] == "my_app.tools"

    def test_messages_property_returns_copy(self):
        """Test that messages property returns a copy."""
        config = DurableAgentConfig(provider_config=BedrockProviderConfig(model_id="anthropic.claude-3-sonnet"))
        agent = DurableAgent(config)

        # Get messages and modify the returned list
        messages = agent.messages
        messages.append({"role": "test"})

        # Original should be unchanged
        assert agent.messages == []


class TestDurableAgentMessageHandling:
    """Test DurableAgent message handling."""

    def test_add_user_message(self):
        """Test adding user message internally."""
        config = DurableAgentConfig(provider_config=BedrockProviderConfig(model_id="anthropic.claude-3-sonnet"))
        agent = DurableAgent(config)

        # Access private method for testing
        agent._add_user_message("Hello, how are you?")

        assert len(agent._messages) == 1
        assert agent._messages[0]["role"] == "user"
        assert agent._messages[0]["content"][0]["text"] == "Hello, how are you?"

    def test_extract_final_text_simple(self):
        """Test extracting final text from simple response."""
        config = DurableAgentConfig(provider_config=BedrockProviderConfig(model_id="anthropic.claude-3-sonnet"))
        agent = DurableAgent(config)

        # Add messages directly
        agent._messages = [
            {"role": "user", "content": [{"text": "Hi"}]},
            {"role": "assistant", "content": [{"text": "Hello! How can I help?"}]},
        ]

        result = agent._extract_final_text()
        assert result == "Hello! How can I help?"

    def test_extract_final_text_multiple_blocks(self):
        """Test extracting final text with multiple content blocks."""
        config = DurableAgentConfig(provider_config=BedrockProviderConfig(model_id="anthropic.claude-3-sonnet"))
        agent = DurableAgent(config)

        agent._messages = [
            {"role": "user", "content": [{"text": "Hi"}]},
            {
                "role": "assistant",
                "content": [
                    {"text": "Part 1. "},
                    {"text": "Part 2."},
                ],
            },
        ]

        result = agent._extract_final_text()
        assert result == "Part 1. Part 2."

    def test_extract_final_text_with_tool_use(self):
        """Test extracting final text with tool use in content."""
        config = DurableAgentConfig(provider_config=BedrockProviderConfig(model_id="anthropic.claude-3-sonnet"))
        agent = DurableAgent(config)

        agent._messages = [
            {"role": "user", "content": [{"text": "What's the weather?"}]},
            {
                "role": "assistant",
                "content": [
                    {"text": "Let me check the weather for you."},
                    {
                        "toolUse": {
                            "toolUseId": "tool_123",
                            "name": "get_weather",
                            "input": {"city": "Seattle"},
                        }
                    },
                ],
            },
        ]

        result = agent._extract_final_text()
        assert result == "Let me check the weather for you."

    def test_extract_final_text_empty(self):
        """Test extracting final text when no assistant messages."""
        config = DurableAgentConfig(provider_config=BedrockProviderConfig(model_id="anthropic.claude-3-sonnet"))
        agent = DurableAgent(config)

        agent._messages = [{"role": "user", "content": [{"text": "Hi"}]}]

        result = agent._extract_final_text()
        assert result == ""


class TestDurableAgentConfig:
    """Additional tests for DurableAgentConfig specific to DurableAgent usage."""

    def test_config_immutability_via_agent(self):
        """Test that config is accessible but changes don't affect agent."""
        config = DurableAgentConfig(
            provider_config=BedrockProviderConfig(model_id="anthropic.claude-3-sonnet"),
            tool_specs=[{"name": "test"}],
        )
        agent = DurableAgent(config)

        # The config should be the same object
        assert agent.config is config
        assert agent.config.tool_specs == [{"name": "test"}]
