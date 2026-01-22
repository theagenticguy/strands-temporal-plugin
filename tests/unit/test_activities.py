"""Unit tests for strands_temporal_plugin.activities module."""

import pytest
from strands_temporal_plugin.activities import (
    _create_model_from_config,
    _load_tool_function,
    execute_model_activity,
    execute_tool_activity,
)
from strands_temporal_plugin.types import (
    AnthropicProviderConfig,
    BedrockProviderConfig,
    ModelExecutionInput,
    OllamaProviderConfig,
    OpenAIProviderConfig,
    ToolExecutionInput,
)
from temporalio.exceptions import ApplicationError
from unittest.mock import MagicMock, patch


class TestCreateModelFromConfig:
    """Tests for _create_model_from_config function."""

    def test_create_bedrock_model_minimal(self):
        """Test creating BedrockModel with minimal config."""
        config = BedrockProviderConfig(model_id="anthropic.claude-3-sonnet")

        mock_model_class = MagicMock()
        mock_model_class.return_value = MagicMock()

        with patch.dict("sys.modules", {"strands.models": MagicMock(BedrockModel=mock_model_class)}):
            result = _create_model_from_config(config)

            # max_tokens defaults to 4096 in BedrockProviderConfig
            mock_model_class.assert_called_once_with(model_id="anthropic.claude-3-sonnet", max_tokens=4096)
            assert result is mock_model_class.return_value

    def test_create_bedrock_model_full(self):
        """Test creating BedrockModel with all options."""
        config = BedrockProviderConfig(
            model_id="anthropic.claude-3-sonnet",
            region_name="us-west-2",
            max_tokens=4096,
            temperature=0.7,
            top_p=0.9,
            stop_sequences=["STOP"],
        )

        mock_model_class = MagicMock()
        mock_model_class.return_value = MagicMock()

        with patch.dict("sys.modules", {"strands.models": MagicMock(BedrockModel=mock_model_class)}):
            result = _create_model_from_config(config)

            mock_model_class.assert_called_once_with(
                model_id="anthropic.claude-3-sonnet",
                region_name="us-west-2",
                max_tokens=4096,
                temperature=0.7,
                top_p=0.9,
                stop_sequences=["STOP"],
            )
            assert result is mock_model_class.return_value

    def test_create_anthropic_model(self):
        """Test creating AnthropicModel."""
        config = AnthropicProviderConfig(model_id="claude-3-opus", max_tokens=2048, temperature=0.5)

        mock_model_class = MagicMock()
        mock_model_class.return_value = MagicMock()

        with patch.dict("sys.modules", {"strands.models": MagicMock(AnthropicModel=mock_model_class)}):
            result = _create_model_from_config(config)

            mock_model_class.assert_called_once_with(
                model_id="claude-3-opus",
                max_tokens=2048,
                temperature=0.5,
            )
            assert result is mock_model_class.return_value

    def test_create_openai_model(self):
        """Test creating OpenAIModel."""
        config = OpenAIProviderConfig(model_id="gpt-4", max_tokens=4096, temperature=0.8)

        mock_model_class = MagicMock()
        mock_model_class.return_value = MagicMock()

        with patch.dict("sys.modules", {"strands.models": MagicMock(OpenAIModel=mock_model_class)}):
            result = _create_model_from_config(config)

            mock_model_class.assert_called_once_with(
                model_id="gpt-4",
                max_tokens=4096,
                temperature=0.8,
            )
            assert result is mock_model_class.return_value

    def test_create_ollama_model(self):
        """Test creating OllamaModel."""
        config = OllamaProviderConfig(model_id="llama2", host="http://localhost:11434", temperature=0.6, top_p=0.95)

        mock_model_class = MagicMock()
        mock_model_class.return_value = MagicMock()

        with patch.dict("sys.modules", {"strands.models": MagicMock(OllamaModel=mock_model_class)}):
            result = _create_model_from_config(config)

            mock_model_class.assert_called_once_with(
                model_id="llama2",
                host="http://localhost:11434",
                temperature=0.6,
                top_p=0.95,
            )
            assert result is mock_model_class.return_value

    def test_create_model_unsupported_provider(self):
        """Test error handling for unsupported provider."""
        # Create a mock config with an unsupported provider
        mock_config = MagicMock()
        mock_config.provider = "unsupported_provider"

        with pytest.raises(ApplicationError) as exc_info:
            _create_model_from_config(mock_config)

        assert exc_info.value.type == "UnsupportedProvider"
        assert exc_info.value.non_retryable is True
        assert "unsupported_provider" in str(exc_info.value)


class TestLoadToolFunction:
    """Tests for _load_tool_function function."""

    def test_load_tool_function_success(self):
        """Test successfully loading a tool function."""
        mock_func = MagicMock()
        mock_module = MagicMock()
        mock_module.my_tool = mock_func

        with patch("strands_temporal_plugin.activities.importlib.import_module", return_value=mock_module):
            result = _load_tool_function("my_tool", "my_app.tools")

        assert result is mock_func

    def test_load_tool_function_no_module(self):
        """Test error when no module specified."""
        with pytest.raises(ApplicationError) as exc_info:
            _load_tool_function("my_tool", "")

        assert exc_info.value.type == "ToolNotFound"
        assert exc_info.value.non_retryable is True

    def test_load_tool_function_tool_not_found_in_module(self):
        """Test error when tool not found in module."""
        mock_module = MagicMock(spec=[])  # Empty module

        with patch("strands_temporal_plugin.activities.importlib.import_module", return_value=mock_module):
            with pytest.raises(ApplicationError) as exc_info:
                _load_tool_function("nonexistent_tool", "my_app.tools")

        assert exc_info.value.type == "ToolNotFound"
        assert exc_info.value.non_retryable is True
        assert "nonexistent_tool" in str(exc_info.value)

    def test_load_tool_function_import_error(self):
        """Test error when module import fails."""
        with patch(
            "strands_temporal_plugin.activities.importlib.import_module", side_effect=ImportError("Module not found")
        ):
            with pytest.raises(ApplicationError) as exc_info:
                _load_tool_function("my_tool", "nonexistent.module")

        assert exc_info.value.type == "ToolModuleNotFound"
        assert exc_info.value.non_retryable is True


class TestExecuteModelActivity:
    """Tests for execute_model_activity function."""

    @pytest.mark.asyncio
    async def test_execute_model_activity_success(self):
        """Test successful model activity execution."""
        config = BedrockProviderConfig(model_id="anthropic.claude-3-sonnet")
        input_data = ModelExecutionInput(
            provider_config=config,
            messages=[{"role": "user", "content": [{"text": "Hello"}]}],
            tool_specs=None,
            system_prompt=None,
        )

        # Mock stream events
        mock_events = [
            {"messageStart": {"role": "assistant"}},
            {"contentBlockStart": {"contentBlockIndex": 0}},
            {"contentBlockDelta": {"delta": {"text": "Hi there!"}}},
            {"contentBlockStop": {"contentBlockIndex": 0}},
            {"messageStop": {"stopReason": "end_turn"}},
        ]

        async def mock_stream(*_args, **_kwargs):
            for event in mock_events:
                yield event

        mock_model = MagicMock()
        mock_model.stream = mock_stream

        with patch("strands_temporal_plugin.activities._create_model_from_config", return_value=mock_model):
            with patch("temporalio.activity.heartbeat"):
                result = await execute_model_activity(input_data)

        assert result.events == mock_events

    @pytest.mark.asyncio
    async def test_execute_model_activity_with_heartbeat(self):
        """Test that heartbeat is called during long operations."""
        config = BedrockProviderConfig(model_id="anthropic.claude-3-sonnet")
        input_data = ModelExecutionInput(
            provider_config=config, messages=[{"role": "user", "content": [{"text": "Hello"}]}]
        )

        # Create many events to trigger heartbeat
        mock_events = [{"event": i} for i in range(25)]

        async def mock_stream(*_args, **_kwargs):
            for event in mock_events:
                yield event

        mock_model = MagicMock()
        mock_model.stream = mock_stream

        with patch("strands_temporal_plugin.activities._create_model_from_config", return_value=mock_model):
            with patch("temporalio.activity.heartbeat") as mock_heartbeat:
                await execute_model_activity(input_data)

                # Should heartbeat every 10 events (at 10, 20)
                assert mock_heartbeat.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_model_activity_context_overflow(self):
        """Test handling of context window overflow error."""
        config = BedrockProviderConfig(model_id="anthropic.claude-3-sonnet")
        input_data = ModelExecutionInput(
            provider_config=config, messages=[{"role": "user", "content": [{"text": "Hello"}]}]
        )

        async def mock_stream(*_args, **_kwargs):
            raise Exception("ContextWindowOverflow: too many tokens")
            yield  # Make it a generator

        mock_model = MagicMock()
        mock_model.stream = mock_stream

        with patch("strands_temporal_plugin.activities._create_model_from_config", return_value=mock_model):
            with pytest.raises(ApplicationError) as exc_info:
                await execute_model_activity(input_data)

        assert exc_info.value.type == "ContextOverflow"
        assert exc_info.value.non_retryable is True

    @pytest.mark.asyncio
    async def test_execute_model_activity_model_not_found(self):
        """Test handling of model not found error."""
        config = BedrockProviderConfig(model_id="nonexistent-model")
        input_data = ModelExecutionInput(
            provider_config=config, messages=[{"role": "user", "content": [{"text": "Hello"}]}]
        )

        async def mock_stream(*_args, **_kwargs):
            raise Exception("ModelNotFound: model not found")
            yield

        mock_model = MagicMock()
        mock_model.stream = mock_stream

        with patch("strands_temporal_plugin.activities._create_model_from_config", return_value=mock_model):
            with pytest.raises(ApplicationError) as exc_info:
                await execute_model_activity(input_data)

        assert exc_info.value.type == "ModelNotFound"
        assert exc_info.value.non_retryable is True

    @pytest.mark.asyncio
    async def test_execute_model_activity_throttling(self):
        """Test handling of throttling error (retryable)."""
        config = BedrockProviderConfig(model_id="anthropic.claude-3-sonnet")
        input_data = ModelExecutionInput(
            provider_config=config, messages=[{"role": "user", "content": [{"text": "Hello"}]}]
        )

        async def mock_stream(*_args, **_kwargs):
            raise Exception("ThrottlingException: rate limit exceeded")
            yield

        mock_model = MagicMock()
        mock_model.stream = mock_stream

        with patch("strands_temporal_plugin.activities._create_model_from_config", return_value=mock_model):
            with pytest.raises(ApplicationError) as exc_info:
                await execute_model_activity(input_data)

        assert exc_info.value.type == "ModelThrottled"
        assert exc_info.value.non_retryable is False  # Should be retryable

    @pytest.mark.asyncio
    async def test_execute_model_activity_unknown_error(self):
        """Test handling of unknown errors (retryable by default)."""
        config = BedrockProviderConfig(model_id="anthropic.claude-3-sonnet")
        input_data = ModelExecutionInput(
            provider_config=config, messages=[{"role": "user", "content": [{"text": "Hello"}]}]
        )

        async def mock_stream(*_args, **_kwargs):
            raise Exception("Unknown error occurred")
            yield

        mock_model = MagicMock()
        mock_model.stream = mock_stream

        with patch("strands_temporal_plugin.activities._create_model_from_config", return_value=mock_model):
            with pytest.raises(ApplicationError) as exc_info:
                await execute_model_activity(input_data)

        assert exc_info.value.type == "ModelExecutionError"
        assert exc_info.value.non_retryable is False

    @pytest.mark.asyncio
    async def test_execute_model_activity_reraises_application_error(self):
        """Test that ApplicationError is re-raised as-is."""
        config = BedrockProviderConfig(model_id="anthropic.claude-3-sonnet")
        input_data = ModelExecutionInput(
            provider_config=config, messages=[{"role": "user", "content": [{"text": "Hello"}]}]
        )

        original_error = ApplicationError("Custom error", type="CustomType", non_retryable=True)

        async def mock_stream(*_args, **_kwargs):
            raise original_error
            yield

        mock_model = MagicMock()
        mock_model.stream = mock_stream

        with patch("strands_temporal_plugin.activities._create_model_from_config", return_value=mock_model):
            with pytest.raises(ApplicationError) as exc_info:
                await execute_model_activity(input_data)

        assert exc_info.value is original_error


class TestExecuteToolActivity:
    """Tests for execute_tool_activity function."""

    @pytest.mark.asyncio
    async def test_execute_tool_activity_sync_success(self):
        """Test successful synchronous tool execution."""
        input_data = ToolExecutionInput(
            tool_name="my_tool", tool_module="my_app.tools", tool_use_id="tool_123", tool_input={"arg1": "value1"}
        )

        def mock_tool(arg1):
            return f"Result: {arg1}"

        mock_module = MagicMock()
        mock_module.my_tool = mock_tool

        with patch("strands_temporal_plugin.activities.importlib.import_module", return_value=mock_module):
            result = await execute_tool_activity(input_data)

        assert result.tool_use_id == "tool_123"
        assert result.status == "success"
        assert result.content == [{"text": "Result: value1"}]

    @pytest.mark.asyncio
    async def test_execute_tool_activity_async_success(self):
        """Test successful asynchronous tool execution."""
        input_data = ToolExecutionInput(
            tool_name="my_async_tool",
            tool_module="my_app.tools",
            tool_use_id="tool_456",
            tool_input={"query": "test"},
        )

        async def mock_async_tool(query):
            return {"data": query}

        mock_module = MagicMock()
        mock_module.my_async_tool = mock_async_tool

        with patch("strands_temporal_plugin.activities.importlib.import_module", return_value=mock_module):
            result = await execute_tool_activity(input_data)

        assert result.tool_use_id == "tool_456"
        assert result.status == "success"
        assert '{"data": "test"}' in result.content[0]["text"]

    @pytest.mark.asyncio
    async def test_execute_tool_activity_wrapped_tool(self):
        """Test tool execution with @tool decorated function."""
        input_data = ToolExecutionInput(
            tool_name="decorated_tool",
            tool_module="my_app.tools",
            tool_use_id="tool_789",
            tool_input={"x": 5},
        )

        def actual_func(x):
            return x * 2

        # Simulate @tool decoration
        decorated = MagicMock()
        decorated.__wrapped__ = actual_func

        mock_module = MagicMock()
        mock_module.decorated_tool = decorated

        with patch("strands_temporal_plugin.activities.importlib.import_module", return_value=mock_module):
            result = await execute_tool_activity(input_data)

        assert result.status == "success"
        assert result.content == [{"text": "10"}]

    @pytest.mark.asyncio
    async def test_execute_tool_activity_dict_result(self):
        """Test tool that returns a dictionary."""
        input_data = ToolExecutionInput(
            tool_name="dict_tool", tool_module="my_app.tools", tool_use_id="tool_dict", tool_input={}
        )

        def mock_tool():
            return {"key": "value", "count": 42}

        mock_module = MagicMock()
        mock_module.dict_tool = mock_tool

        with patch("strands_temporal_plugin.activities.importlib.import_module", return_value=mock_module):
            result = await execute_tool_activity(input_data)

        assert result.status == "success"
        assert '{"key": "value", "count": 42}' in result.content[0]["text"]

    @pytest.mark.asyncio
    async def test_execute_tool_activity_list_result(self):
        """Test tool that returns a list (content blocks)."""
        input_data = ToolExecutionInput(
            tool_name="list_tool", tool_module="my_app.tools", tool_use_id="tool_list", tool_input={}
        )

        def mock_tool():
            return [{"text": "Part 1"}, {"text": "Part 2"}]

        mock_module = MagicMock()
        mock_module.list_tool = mock_tool

        with patch("strands_temporal_plugin.activities.importlib.import_module", return_value=mock_module):
            result = await execute_tool_activity(input_data)

        assert result.status == "success"
        assert result.content == [{"text": "Part 1"}, {"text": "Part 2"}]

    @pytest.mark.asyncio
    async def test_execute_tool_activity_error(self):
        """Test tool execution that raises an error."""
        input_data = ToolExecutionInput(
            tool_name="failing_tool", tool_module="my_app.tools", tool_use_id="tool_fail", tool_input={}
        )

        def mock_tool():
            raise ValueError("Something went wrong")

        mock_module = MagicMock()
        mock_module.failing_tool = mock_tool

        with patch("strands_temporal_plugin.activities.importlib.import_module", return_value=mock_module):
            result = await execute_tool_activity(input_data)

        assert result.tool_use_id == "tool_fail"
        assert result.status == "error"
        assert "Tool execution failed" in result.content[0]["text"]
        assert "Something went wrong" in result.content[0]["text"]

    @pytest.mark.asyncio
    async def test_execute_tool_activity_tool_not_found(self):
        """Test handling of tool not found error."""
        input_data = ToolExecutionInput(
            tool_name="nonexistent", tool_module="my_app.tools", tool_use_id="tool_nf", tool_input={}
        )

        with patch(
            "strands_temporal_plugin.activities._load_tool_function",
            side_effect=ApplicationError("Tool not found", type="ToolNotFound", non_retryable=True),
        ):
            with pytest.raises(ApplicationError) as exc_info:
                await execute_tool_activity(input_data)

        assert exc_info.value.type == "ToolNotFound"

    @pytest.mark.asyncio
    async def test_execute_tool_activity_arbitrary_result(self):
        """Test tool that returns arbitrary type (converted to string)."""
        input_data = ToolExecutionInput(
            tool_name="custom_tool", tool_module="my_app.tools", tool_use_id="tool_custom", tool_input={}
        )

        class CustomResult:
            def __str__(self):
                return "CustomResult(data=42)"

        def mock_tool():
            return CustomResult()

        mock_module = MagicMock()
        mock_module.custom_tool = mock_tool

        with patch("strands_temporal_plugin.activities.importlib.import_module", return_value=mock_module):
            result = await execute_tool_activity(input_data)

        assert result.status == "success"
        assert "CustomResult(data=42)" in result.content[0]["text"]
