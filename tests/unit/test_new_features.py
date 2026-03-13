"""Unit tests for P1+P2 new features.

Tests cover: TemporalToolConfig, per-tool config in TemporalToolExecutor,
CustomProviderConfig, structured output types, session types, and MCP client cache.
"""

import json
import pytest
from datetime import timedelta
from strands_temporal_plugin.mcp_activities import close_mcp_clients
from strands_temporal_plugin.tool_executor import TemporalToolExecutor
from strands_temporal_plugin.types import (
    BedrockProviderConfig,
    CustomProviderConfig,
    SessionConfig,
    SessionData,
    StructuredOutputInput,
    StructuredOutputResult,
    TemporalToolConfig,
)
from temporalio.common import RetryPolicy
from unittest.mock import AsyncMock, MagicMock, patch


# =============================================================================
# TemporalToolConfig
# =============================================================================


class TestTemporalToolConfig:
    """Test TemporalToolConfig per-tool configuration."""

    def test_default_values(self):
        """Test TemporalToolConfig all fields default to None."""
        config = TemporalToolConfig()

        assert config.start_to_close_timeout is None
        assert config.heartbeat_timeout is None
        assert config.retry_max_attempts is None
        assert config.retry_initial_interval is None
        assert config.retry_max_interval is None
        assert config.retry_backoff_coefficient is None

    def test_custom_values(self):
        """Test TemporalToolConfig with custom values."""
        config = TemporalToolConfig(
            start_to_close_timeout=300.0,
            heartbeat_timeout=30.0,
            retry_max_attempts=5,
            retry_initial_interval=2.0,
            retry_max_interval=120.0,
            retry_backoff_coefficient=3.0,
        )

        assert config.start_to_close_timeout == 300.0
        assert config.heartbeat_timeout == 30.0
        assert config.retry_max_attempts == 5
        assert config.retry_initial_interval == 2.0
        assert config.retry_max_interval == 120.0
        assert config.retry_backoff_coefficient == 3.0

    def test_get_retry_policy_with_overrides(self):
        """Test get_retry_policy overrides fallback fields selectively."""
        config = TemporalToolConfig(
            retry_max_attempts=10,
            retry_initial_interval=5.0,
        )

        fallback = RetryPolicy(
            maximum_attempts=3,
            initial_interval=timedelta(seconds=1),
            maximum_interval=timedelta(seconds=30),
            backoff_coefficient=2.0,
        )

        policy = config.get_retry_policy(fallback)

        # Overridden fields
        assert policy.maximum_attempts == 10
        assert policy.initial_interval == timedelta(seconds=5)
        # Fallback fields
        assert policy.maximum_interval == timedelta(seconds=30)
        assert policy.backoff_coefficient == 2.0

    def test_get_retry_policy_no_overrides(self):
        """Test get_retry_policy returns fallback when no fields are set."""
        config = TemporalToolConfig()

        fallback = RetryPolicy(
            maximum_attempts=3,
            initial_interval=timedelta(seconds=1),
            maximum_interval=timedelta(seconds=30),
            backoff_coefficient=2.0,
        )

        policy = config.get_retry_policy(fallback)

        assert policy.maximum_attempts == 3
        assert policy.initial_interval == timedelta(seconds=1)
        assert policy.maximum_interval == timedelta(seconds=30)
        assert policy.backoff_coefficient == 2.0

    def test_get_retry_policy_full_overrides(self):
        """Test get_retry_policy with all fields overridden."""
        config = TemporalToolConfig(
            retry_max_attempts=7,
            retry_initial_interval=3.0,
            retry_max_interval=60.0,
            retry_backoff_coefficient=4.0,
        )

        fallback = RetryPolicy(
            maximum_attempts=1,
            initial_interval=timedelta(seconds=0.5),
            maximum_interval=timedelta(seconds=10),
            backoff_coefficient=1.5,
        )

        policy = config.get_retry_policy(fallback)

        assert policy.maximum_attempts == 7
        assert policy.initial_interval == timedelta(seconds=3)
        assert policy.maximum_interval == timedelta(seconds=60)
        assert policy.backoff_coefficient == 4.0

    def test_serialization_round_trip(self):
        """Test TemporalToolConfig JSON serialization round-trip."""
        config = TemporalToolConfig(
            start_to_close_timeout=300.0,
            heartbeat_timeout=30.0,
            retry_max_attempts=5,
            retry_initial_interval=2.0,
            retry_max_interval=120.0,
            retry_backoff_coefficient=3.0,
        )

        json_str = config.model_dump_json()
        data = json.loads(json_str)

        assert data["start_to_close_timeout"] == 300.0
        assert data["heartbeat_timeout"] == 30.0
        assert data["retry_max_attempts"] == 5

        restored = TemporalToolConfig.model_validate_json(json_str)
        assert restored == config

    def test_serialization_round_trip_defaults(self):
        """Test TemporalToolConfig serialization with all defaults (None values)."""
        config = TemporalToolConfig()

        json_str = config.model_dump_json()
        restored = TemporalToolConfig.model_validate_json(json_str)
        assert restored == config


# =============================================================================
# TemporalToolExecutor with tool_configs
# =============================================================================


class TestTemporalToolExecutorWithToolConfigs:
    """Test TemporalToolExecutor per-tool configuration integration."""

    def test_init_with_tool_configs(self):
        """Test TemporalToolExecutor accepts tool_configs parameter."""
        tool_configs = {
            "slow_search": TemporalToolConfig(
                start_to_close_timeout=300.0,
                heartbeat_timeout=30.0,
            ),
            "flaky_api": TemporalToolConfig(
                retry_max_attempts=5,
                retry_initial_interval=2.0,
            ),
        }
        executor = TemporalToolExecutor(
            tool_modules={"slow_search": "myapp.tools", "flaky_api": "myapp.tools"},
            tool_configs=tool_configs,
        )

        assert "slow_search" in executor._tool_configs
        assert "flaky_api" in executor._tool_configs
        assert executor._tool_configs["slow_search"].start_to_close_timeout == 300.0
        assert executor._tool_configs["flaky_api"].retry_max_attempts == 5

    def test_init_without_tool_configs(self):
        """Test TemporalToolExecutor defaults to empty tool_configs."""
        executor = TemporalToolExecutor()

        assert executor._tool_configs == {}

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.tool_executor.workflow")
    async def test_execute_static_tool_uses_per_tool_timeout(self, mock_workflow):
        """Test _execute_static_tool uses per-tool timeout when configured."""
        from strands_temporal_plugin.types import ToolExecutionResult

        tool_configs = {
            "slow_tool": TemporalToolConfig(
                start_to_close_timeout=300.0,
                heartbeat_timeout=60.0,
            ),
        }
        executor = TemporalToolExecutor(
            tool_modules={"slow_tool": "myapp.tools"},
            tool_configs=tool_configs,
        )

        mock_result = ToolExecutionResult(
            tool_use_id="tool_123",
            status="success",
            content=[{"text": "done"}],
        )
        mock_workflow.execute_activity = AsyncMock(return_value=mock_result)

        result = await executor._execute_static_tool(
            tool_name="slow_tool",
            tool_input={"query": "test"},
            tool_use_id="tool_123",
        )

        assert result.status == "success"

        # Verify the activity was called with per-tool timeout
        call_kwargs = mock_workflow.execute_activity.call_args[1]
        assert call_kwargs["start_to_close_timeout"] == timedelta(seconds=300.0)
        assert call_kwargs["heartbeat_timeout"] == timedelta(seconds=60.0)

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.tool_executor.workflow")
    async def test_execute_static_tool_falls_back_to_default(self, mock_workflow):
        """Test _execute_static_tool uses default timeout when no per-tool config."""
        from strands_temporal_plugin.types import ToolExecutionResult

        executor = TemporalToolExecutor(
            tool_modules={"normal_tool": "myapp.tools"},
            activity_timeout=90.0,
        )

        mock_result = ToolExecutionResult(
            tool_use_id="tool_456",
            status="success",
            content=[{"text": "done"}],
        )
        mock_workflow.execute_activity = AsyncMock(return_value=mock_result)

        result = await executor._execute_static_tool(
            tool_name="normal_tool",
            tool_input={"arg": "val"},
            tool_use_id="tool_456",
        )

        assert result.status == "success"

        # Verify the activity was called with default timeout
        call_kwargs = mock_workflow.execute_activity.call_args[1]
        assert call_kwargs["start_to_close_timeout"] == timedelta(seconds=90.0)
        # Default heartbeat_timeout of 25s when not configured per-tool
        assert call_kwargs["heartbeat_timeout"] == timedelta(seconds=25)

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.tool_executor.workflow")
    async def test_execute_static_tool_per_tool_retry_policy(self, mock_workflow):
        """Test _execute_static_tool applies per-tool retry policy overrides."""
        from strands_temporal_plugin.types import ToolExecutionResult

        tool_configs = {
            "flaky_tool": TemporalToolConfig(
                retry_max_attempts=10,
                retry_initial_interval=5.0,
            ),
        }
        executor = TemporalToolExecutor(
            tool_modules={"flaky_tool": "myapp.tools"},
            tool_configs=tool_configs,
        )

        mock_result = ToolExecutionResult(
            tool_use_id="tool_789",
            status="success",
            content=[{"text": "ok"}],
        )
        mock_workflow.execute_activity = AsyncMock(return_value=mock_result)

        await executor._execute_static_tool(
            tool_name="flaky_tool",
            tool_input={},
            tool_use_id="tool_789",
        )

        call_kwargs = mock_workflow.execute_activity.call_args[1]
        retry_policy = call_kwargs["retry_policy"]
        assert retry_policy.maximum_attempts == 10
        assert retry_policy.initial_interval == timedelta(seconds=5)
        # Fallback values from default
        assert retry_policy.maximum_interval == timedelta(seconds=30)
        assert retry_policy.backoff_coefficient == 2.0


# =============================================================================
# CustomProviderConfig
# =============================================================================


class TestCustomProviderConfig:
    """Test CustomProviderConfig type."""

    def test_construction(self):
        """Test CustomProviderConfig construction."""
        config = CustomProviderConfig(
            model_id="my-custom-model",
            provider_class_path="myapp.models.MyCustomModel",
            provider_kwargs={"api_key": "sk-test", "base_url": "https://api.example.com"},
        )

        assert config.provider == "custom"
        assert config.model_id == "my-custom-model"
        assert config.provider_class_path == "myapp.models.MyCustomModel"
        assert config.provider_kwargs == {"api_key": "sk-test", "base_url": "https://api.example.com"}

    def test_construction_defaults(self):
        """Test CustomProviderConfig with default provider_kwargs."""
        config = CustomProviderConfig(
            model_id="my-model",
            provider_class_path="myapp.models.Custom",
        )

        assert config.provider_kwargs == {}

    def test_serialization_round_trip(self):
        """Test CustomProviderConfig JSON serialization round-trip."""
        config = CustomProviderConfig(
            model_id="my-custom-model",
            provider_class_path="myapp.models.MyCustomModel",
            provider_kwargs={"api_key": "sk-test", "timeout": 30},
        )

        json_str = config.model_dump_json()
        data = json.loads(json_str)

        assert data["provider"] == "custom"
        assert data["model_id"] == "my-custom-model"
        assert data["provider_class_path"] == "myapp.models.MyCustomModel"
        assert data["provider_kwargs"] == {"api_key": "sk-test", "timeout": 30}

        restored = CustomProviderConfig.model_validate_json(json_str)
        assert restored == config

    def test_discriminator_in_provider_config_union(self):
        """Test CustomProviderConfig works in ProviderConfig discriminated union."""
        from strands_temporal_plugin.types import ModelExecutionInput

        config = CustomProviderConfig(
            model_id="my-model",
            provider_class_path="myapp.models.Custom",
        )

        # Use it in ModelExecutionInput which expects ProviderConfig union
        input_data = ModelExecutionInput(
            provider_config=config,
            system_prompt="Hello",
        )

        assert input_data.provider_config.provider == "custom"
        assert isinstance(input_data.provider_config, CustomProviderConfig)

        # Verify serialization round-trip through the union
        json_str = input_data.model_dump_json()
        restored = ModelExecutionInput.model_validate_json(json_str)
        assert isinstance(restored.provider_config, CustomProviderConfig)
        assert restored.provider_config.provider_class_path == "myapp.models.Custom"


# =============================================================================
# Structured Output Types
# =============================================================================


class TestStructuredOutputTypes:
    """Test structured output input/result types."""

    def test_structured_output_input_construction(self):
        """Test StructuredOutputInput construction."""
        config = BedrockProviderConfig(model_id="anthropic.claude-3-sonnet")
        input_data = StructuredOutputInput(
            provider_config=config,
            output_model_path="myapp.models.WeatherOutput",
            prompt="What's the weather in Seattle?",
            system_prompt="You are a weather assistant.",
        )

        assert input_data.provider_config == config
        assert input_data.output_model_path == "myapp.models.WeatherOutput"
        assert input_data.prompt == "What's the weather in Seattle?"
        assert input_data.system_prompt == "You are a weather assistant."

    def test_structured_output_input_no_system_prompt(self):
        """Test StructuredOutputInput with no system_prompt."""
        config = BedrockProviderConfig(model_id="anthropic.claude-3-sonnet")
        input_data = StructuredOutputInput(
            provider_config=config,
            output_model_path="myapp.models.Output",
            prompt="Do something.",
        )

        assert input_data.system_prompt is None

    def test_structured_output_result_construction(self):
        """Test StructuredOutputResult construction."""
        result = StructuredOutputResult(
            output={"city": "Seattle", "temperature": 72, "unit": "F"},
            output_model_path="myapp.models.WeatherOutput",
        )

        assert result.output == {"city": "Seattle", "temperature": 72, "unit": "F"}
        assert result.output_model_path == "myapp.models.WeatherOutput"

    def test_structured_output_input_serialization_round_trip(self):
        """Test StructuredOutputInput JSON serialization round-trip."""
        config = BedrockProviderConfig(model_id="anthropic.claude-3-sonnet")
        input_data = StructuredOutputInput(
            provider_config=config,
            output_model_path="myapp.models.WeatherOutput",
            prompt="What's the weather?",
            system_prompt="Be helpful.",
        )

        json_str = input_data.model_dump_json()
        data = json.loads(json_str)

        assert data["output_model_path"] == "myapp.models.WeatherOutput"
        assert data["prompt"] == "What's the weather?"
        assert data["provider_config"]["provider"] == "bedrock"

        restored = StructuredOutputInput.model_validate_json(json_str)
        assert restored == input_data

    def test_structured_output_result_serialization_round_trip(self):
        """Test StructuredOutputResult JSON serialization round-trip."""
        result = StructuredOutputResult(
            output={"city": "Seattle", "temperature": 72},
            output_model_path="myapp.models.WeatherOutput",
        )

        json_str = result.model_dump_json()
        restored = StructuredOutputResult.model_validate_json(json_str)
        assert restored == result


# =============================================================================
# Session Config / Session Data
# =============================================================================


class TestSessionConfigAndData:
    """Test SessionConfig and SessionData types."""

    def test_session_config_defaults(self):
        """Test SessionConfig with required fields and defaults."""
        config = SessionConfig(session_id="user-123", bucket="my-bucket")

        assert config.session_id == "user-123"
        assert config.bucket == "my-bucket"
        assert config.prefix == ""
        assert config.region_name is None

    def test_session_config_full(self):
        """Test SessionConfig with all fields."""
        config = SessionConfig(
            session_id="user-456",
            bucket="prod-bucket",
            prefix="sessions/",
            region_name="eu-west-1",
        )

        assert config.session_id == "user-456"
        assert config.bucket == "prod-bucket"
        assert config.prefix == "sessions/"
        assert config.region_name == "eu-west-1"

    def test_session_config_serialization_round_trip(self):
        """Test SessionConfig JSON serialization round-trip."""
        config = SessionConfig(
            session_id="user-789",
            bucket="test-bucket",
            prefix="dev/",
            region_name="us-east-1",
        )

        json_str = config.model_dump_json()
        data = json.loads(json_str)
        assert data["session_id"] == "user-789"
        assert data["bucket"] == "test-bucket"
        assert data["prefix"] == "dev/"
        assert data["region_name"] == "us-east-1"

        restored = SessionConfig.model_validate_json(json_str)
        assert restored == config

    def test_session_data_defaults(self):
        """Test SessionData defaults to empty lists/dicts."""
        data = SessionData()

        assert data.messages == []
        assert data.agent_state == {}
        assert data.conversation_manager_state == {}

    def test_session_data_with_content(self):
        """Test SessionData with messages and state."""
        data = SessionData(
            messages=[
                {"role": "user", "content": [{"text": "Hello"}]},
                {"role": "assistant", "content": [{"text": "Hi!"}]},
            ],
            agent_state={"turn_count": 1, "last_tool": "search"},
            conversation_manager_state={"summary": "User greeted the agent."},
        )

        assert len(data.messages) == 2
        assert data.agent_state["turn_count"] == 1
        assert data.conversation_manager_state["summary"] == "User greeted the agent."

    def test_session_data_serialization_round_trip(self):
        """Test SessionData JSON serialization round-trip."""
        data = SessionData(
            messages=[{"role": "user", "content": [{"text": "test"}]}],
            agent_state={"key": "value"},
            conversation_manager_state={"summary": "test"},
        )

        json_str = data.model_dump_json()
        restored = SessionData.model_validate_json(json_str)
        assert restored == data

    def test_session_data_empty_serialization_round_trip(self):
        """Test empty SessionData JSON serialization round-trip."""
        data = SessionData()

        json_str = data.model_dump_json()
        restored = SessionData.model_validate_json(json_str)
        assert restored == data
        assert restored.messages == []
        assert restored.agent_state == {}


# =============================================================================
# MCP Client Cache
# =============================================================================


class TestMCPClientCache:
    """Test MCP client cache management."""

    @patch("strands_temporal_plugin.mcp_activities._mcp_clients", new_callable=dict)
    @patch("strands_temporal_plugin.mcp_activities._mcp_client_lock")
    def test_close_mcp_clients_clears_cache(self, mock_lock, mock_clients):
        """Test close_mcp_clients closes all clients and clears the cache."""
        # Set up mock clients in the cache
        mock_client_1 = MagicMock()
        mock_client_2 = MagicMock()
        mock_clients["server-1"] = mock_client_1
        mock_clients["server-2"] = mock_client_2

        # Make lock context manager work
        mock_lock.__enter__ = MagicMock(return_value=None)
        mock_lock.__exit__ = MagicMock(return_value=False)

        close_mcp_clients()

        # Verify both clients were closed
        mock_client_1.__exit__.assert_called_once_with(None, None, None)
        mock_client_2.__exit__.assert_called_once_with(None, None, None)

        # Verify cache was cleared
        assert len(mock_clients) == 0

    @patch("strands_temporal_plugin.mcp_activities._mcp_clients", new_callable=dict)
    @patch("strands_temporal_plugin.mcp_activities._mcp_client_lock")
    def test_close_mcp_clients_handles_errors(self, mock_lock, mock_clients):
        """Test close_mcp_clients handles errors gracefully during cleanup."""
        mock_client = MagicMock()
        mock_client.__exit__.side_effect = RuntimeError("cleanup error")
        mock_clients["server-1"] = mock_client

        mock_lock.__enter__ = MagicMock(return_value=None)
        mock_lock.__exit__ = MagicMock(return_value=False)

        # Should not raise even if client cleanup fails
        close_mcp_clients()

        # Cache should still be cleared even after error
        assert len(mock_clients) == 0

    @patch("strands_temporal_plugin.mcp_activities._mcp_clients", new_callable=dict)
    @patch("strands_temporal_plugin.mcp_activities._mcp_client_lock")
    def test_close_mcp_clients_empty_cache(self, mock_lock, mock_clients):
        """Test close_mcp_clients is a no-op on empty cache."""
        mock_lock.__enter__ = MagicMock(return_value=None)
        mock_lock.__exit__ = MagicMock(return_value=False)

        # Should not raise
        close_mcp_clients()

        assert len(mock_clients) == 0
