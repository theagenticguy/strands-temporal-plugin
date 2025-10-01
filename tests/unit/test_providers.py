"""Unit tests for provider factory functionality."""

import pytest
from strands.models import BedrockModel
from strands_temporal_plugin.providers import EchoModel, create_model_from_config, validate_provider_config
from strands_temporal_plugin.types import BedrockProviderConfig, EchoProviderConfig


class TestProviderFactory:
    """Test the provider factory system."""

    def test_create_bedrock_model(self):
        """Test creating a Bedrock model from configuration."""
        config = BedrockProviderConfig(model_id="anthropic.claude-3-sonnet-20240229-v1:0", region="us-west-2")

        model = create_model_from_config(config)
        assert isinstance(model, BedrockModel)

    def test_create_echo_model(self):
        """Test creating an Echo model from configuration."""
        config = EchoProviderConfig(sleep_s=0.1, chunk_chars=10)

        model = create_model_from_config(config)
        assert isinstance(model, EchoModel)
        assert model.sleep_s == 0.1
        assert model.chunk_chars == 10

    def test_invalid_provider_type(self):
        """Test handling of invalid provider types."""
        # Create a valid config but modify the type field directly
        config = EchoProviderConfig()
        # Bypass type validation by modifying the underlying data
        config.type = "invalid"  # type: ignore

        with pytest.raises(ValueError, match="Unsupported provider type"):
            create_model_from_config(config)


class TestProviderValidation:
    """Test provider configuration validation."""

    def test_valid_bedrock_config(self):
        """Test validation of valid Bedrock configuration."""
        config = BedrockProviderConfig(model_id="anthropic.claude-3-sonnet-20240229-v1:0")

        assert validate_provider_config(config) is True

    def test_invalid_bedrock_config_missing_model_id(self):
        """Test validation fails for missing model_id."""
        config = BedrockProviderConfig(model_id="")

        with pytest.raises(ValueError, match="model_id is required"):
            validate_provider_config(config)

    def test_valid_echo_config(self):
        """Test validation of valid Echo configuration."""
        config = EchoProviderConfig(sleep_s=0.1, chunk_chars=20)

        assert validate_provider_config(config) is True

    def test_invalid_echo_config_negative_sleep(self):
        """Test validation fails for negative sleep."""
        config = EchoProviderConfig(sleep_s=-1.0)

        with pytest.raises(ValueError, match="sleep_s must be non-negative"):
            validate_provider_config(config)


class TestEchoModel:
    """Test the EchoModel implementation."""

    def test_echo_model_config(self):
        """Test EchoModel configuration."""
        model = EchoModel(sleep_s=0.2, chunk_chars=15)

        config = model.get_config()
        assert config["sleep_s"] == 0.2
        assert config["chunk_chars"] == 15

    def test_echo_model_update_config(self):
        """Test EchoModel configuration updates."""
        model = EchoModel(sleep_s=0.1, chunk_chars=10)

        model.update_config(sleep_s=0.3, chunk_chars=25)

        config = model.get_config()
        assert config["sleep_s"] == 0.3
        assert config["chunk_chars"] == 25

    @pytest.mark.asyncio
    async def test_echo_model_stream(self):
        """Test EchoModel streaming functionality."""
        model = EchoModel(sleep_s=0.0, chunk_chars=5)  # Fast execution for testing

        from strands.types.content import Message
        from typing import cast

        message_dict = {"role": "user", "content": [{"text": "Hello"}]}
        messages = [cast(Message, message_dict)]

        events = []
        async for event in model.stream(messages):
            events.append(event)

        # Should have message start, content delta(s), and message stop
        assert len(events) >= 3
        assert events[0].get("messageStart") is not None
        assert events[-1].get("messageStop") is not None

        # Should have at least one content delta
        content_deltas = [e for e in events if "contentBlockDelta" in e]
        assert len(content_deltas) > 0
