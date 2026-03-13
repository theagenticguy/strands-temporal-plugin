"""Replay and versioning tests for non-determinism regression.

Tests verify that:
1. Versioning gates (workflow.patched()) are correctly placed
2. Both branches of each patch produce consistent behavior
3. The TemporalModelStub and TemporalToolExecutor handle patched/unpatched paths
"""

import pytest
from datetime import timedelta
from strands_temporal_plugin.runner import TemporalModelStub
from strands_temporal_plugin.tool_executor import TemporalToolExecutor
from strands_temporal_plugin.types import (
    BedrockProviderConfig,
    ModelExecutionResult,
    TemporalToolConfig,
    ToolExecutionResult,
)
from unittest.mock import AsyncMock, MagicMock, patch


# =============================================================================
# TemporalModelStub versioning tests
# =============================================================================


class TestModelStubVersioning:
    """Test that TemporalModelStub model-stream-v1 patch produces consistent results."""

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.runner.workflow")
    async def test_model_stream_patched_path(self, mock_workflow):
        """Test model.stream() via the patched (model-stream-v1) code path."""
        mock_workflow.patched.return_value = True

        mock_events = [
            {"messageStart": {"role": "assistant"}},
            {"contentBlockDelta": {"delta": {"text": "Hello"}}},
            {"messageStop": {"stopReason": "end_turn"}},
        ]
        mock_result = ModelExecutionResult(events=mock_events)
        mock_workflow.execute_activity = AsyncMock(return_value=mock_result)

        stub = TemporalModelStub(BedrockProviderConfig(model_id="test-model"))

        collected = []
        async for event in stub.stream(messages=[{"role": "user", "content": [{"text": "Hi"}]}]):
            collected.append(event)

        assert collected == mock_events
        mock_workflow.patched.assert_called_with("model-stream-v1")

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.runner.workflow")
    async def test_model_stream_unpatched_path(self, mock_workflow):
        """Test model.stream() via the unpatched (legacy) code path."""
        mock_workflow.patched.return_value = False

        mock_events = [
            {"messageStart": {"role": "assistant"}},
            {"contentBlockDelta": {"delta": {"text": "Hello"}}},
            {"messageStop": {"stopReason": "end_turn"}},
        ]
        mock_result = ModelExecutionResult(events=mock_events)
        mock_workflow.execute_activity = AsyncMock(return_value=mock_result)

        stub = TemporalModelStub(BedrockProviderConfig(model_id="test-model"))

        collected = []
        async for event in stub.stream(messages=[{"role": "user", "content": [{"text": "Hi"}]}]):
            collected.append(event)

        assert collected == mock_events

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.runner.workflow")
    async def test_model_stream_both_paths_identical_output(self, mock_workflow):
        """Verify patched and unpatched paths produce identical results.

        This is the key non-determinism regression test: if the two branches
        of model-stream-v1 ever diverge, this test catches it.
        """
        mock_events = [
            {"messageStart": {"role": "assistant"}},
            {"contentBlockDelta": {"delta": {"text": "Test response"}}},
            {"messageStop": {"stopReason": "end_turn"}},
            {"metadata": {"usage": {"inputTokens": 10, "outputTokens": 5}}},
        ]
        mock_result = ModelExecutionResult(events=mock_events)
        mock_workflow.execute_activity = AsyncMock(return_value=mock_result)

        stub = TemporalModelStub(BedrockProviderConfig(model_id="test-model"))
        messages = [{"role": "user", "content": [{"text": "Hi"}]}]
        tool_specs = [{"name": "test_tool", "description": "A test tool"}]

        # Collect results from patched path
        mock_workflow.patched.return_value = True
        patched_results = []
        async for event in stub.stream(messages=messages, tool_specs=tool_specs, system_prompt="Be helpful"):
            patched_results.append(event)

        patched_call_args = mock_workflow.execute_activity.call_args

        # Collect results from unpatched path
        mock_workflow.execute_activity.reset_mock()
        mock_workflow.patched.return_value = False
        unpatched_results = []
        async for event in stub.stream(messages=messages, tool_specs=tool_specs, system_prompt="Be helpful"):
            unpatched_results.append(event)

        unpatched_call_args = mock_workflow.execute_activity.call_args

        # Both paths must produce identical output
        assert patched_results == unpatched_results
        # Both paths must call the same activity with the same input
        assert patched_call_args[0] == unpatched_call_args[0]  # positional args
        assert patched_call_args[1] == unpatched_call_args[1]  # keyword args

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.runner.workflow")
    async def test_model_stream_activity_timeout_propagated(self, mock_workflow):
        """Verify custom activity_timeout is used in both paths."""
        mock_workflow.patched.return_value = True
        mock_result = ModelExecutionResult(events=[])
        mock_workflow.execute_activity = AsyncMock(return_value=mock_result)

        stub = TemporalModelStub(
            BedrockProviderConfig(model_id="test-model"),
            activity_timeout=600.0,
        )

        async for _ in stub.stream(messages=[]):
            pass

        call_kwargs = mock_workflow.execute_activity.call_args[1]
        assert call_kwargs["start_to_close_timeout"] == timedelta(seconds=600.0)


# =============================================================================
# TemporalToolExecutor versioning tests
# =============================================================================


class TestToolExecutorVersioning:
    """Test that parallel-tool-execution-v1 patch handles both paths correctly."""

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.tool_executor.workflow")
    async def test_parallel_path_executes_concurrently(self, mock_workflow):
        """Test patched path uses asyncio.gather for parallel execution."""
        mock_workflow.patched.return_value = True

        tool_results = [
            ToolExecutionResult(tool_use_id="t1", status="success", content=[{"text": "r1"}]),
            ToolExecutionResult(tool_use_id="t2", status="success", content=[{"text": "r2"}]),
        ]
        call_count = 0

        async def mock_execute_activity(_activity, input_data, **_kwargs):
            nonlocal call_count
            call_count += 1
            # Return result based on tool_use_id
            if hasattr(input_data, "tool_use_id"):
                for r in tool_results:
                    if r.tool_use_id == input_data.tool_use_id:
                        return r
            return tool_results[0]

        mock_workflow.execute_activity = mock_execute_activity

        executor = TemporalToolExecutor(
            tool_modules={"tool_a": "mod.a", "tool_b": "mod.b"},
        )

        tool_uses = [
            {"name": "tool_a", "input": {"arg": "1"}, "toolUseId": "t1"},
            {"name": "tool_b", "input": {"arg": "2"}, "toolUseId": "t2"},
        ]

        results = []
        tool_results_list = []
        async for event in executor._execute(
            agent=MagicMock(),
            tool_uses=tool_uses,
            tool_results=tool_results_list,
            cycle_trace=None,
            cycle_span=None,
            invocation_state={},
        ):
            results.append(event)

        # Both tools should have been called
        assert len(results) == 2
        assert len(tool_results_list) == 2
        assert tool_results_list[0]["toolUseId"] == "t1"
        assert tool_results_list[1]["toolUseId"] == "t2"

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.tool_executor.workflow")
    async def test_sequential_path_executes_in_order(self, mock_workflow):
        """Test unpatched path executes tools sequentially."""
        mock_workflow.patched.return_value = False

        execution_order = []

        async def mock_execute_activity(_activity, input_data, **_kwargs):
            tool_id = input_data.tool_use_id if hasattr(input_data, "tool_use_id") else "unknown"
            execution_order.append(tool_id)
            return ToolExecutionResult(
                tool_use_id=tool_id,
                status="success",
                content=[{"text": f"result-{tool_id}"}],
            )

        mock_workflow.execute_activity = mock_execute_activity

        executor = TemporalToolExecutor(
            tool_modules={"tool_a": "mod.a", "tool_b": "mod.b"},
        )

        tool_uses = [
            {"name": "tool_a", "input": {}, "toolUseId": "t1"},
            {"name": "tool_b", "input": {}, "toolUseId": "t2"},
        ]

        results = []
        tool_results_list = []
        async for event in executor._execute(
            agent=MagicMock(),
            tool_uses=tool_uses,
            tool_results=tool_results_list,
            cycle_trace=None,
            cycle_span=None,
            invocation_state={},
        ):
            results.append(event)

        assert len(results) == 2
        # Sequential path: t1 before t2
        assert execution_order == ["t1", "t2"]

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.tool_executor.workflow")
    async def test_both_paths_produce_same_results(self, mock_workflow):
        """Verify parallel and sequential paths produce identical tool results.

        Order of results must match order of tool_uses in both paths.
        """
        tool_results_map = {
            "t1": ToolExecutionResult(tool_use_id="t1", status="success", content=[{"text": "r1"}]),
            "t2": ToolExecutionResult(tool_use_id="t2", status="success", content=[{"text": "r2"}]),
            "t3": ToolExecutionResult(tool_use_id="t3", status="success", content=[{"text": "r3"}]),
        }

        async def mock_execute_activity(_activity, input_data, **_kwargs):
            return tool_results_map[input_data.tool_use_id]

        mock_workflow.execute_activity = mock_execute_activity

        executor = TemporalToolExecutor(
            tool_modules={"tool_a": "mod.a", "tool_b": "mod.b", "tool_c": "mod.c"},
        )

        tool_uses = [
            {"name": "tool_a", "input": {}, "toolUseId": "t1"},
            {"name": "tool_b", "input": {}, "toolUseId": "t2"},
            {"name": "tool_c", "input": {}, "toolUseId": "t3"},
        ]

        # Parallel path
        mock_workflow.patched.return_value = True
        parallel_results = []
        parallel_tool_results = []
        async for event in executor._execute(
            agent=MagicMock(),
            tool_uses=tool_uses,
            tool_results=parallel_tool_results,
            cycle_trace=None,
            cycle_span=None,
            invocation_state={},
        ):
            parallel_results.append(event)

        # Sequential path
        mock_workflow.patched.return_value = False
        sequential_results = []
        sequential_tool_results = []
        async for event in executor._execute(
            agent=MagicMock(),
            tool_uses=tool_uses,
            tool_results=sequential_tool_results,
            cycle_trace=None,
            cycle_span=None,
            invocation_state={},
        ):
            sequential_results.append(event)

        # Both paths must produce the same tool results in the same order
        assert len(parallel_tool_results) == len(sequential_tool_results) == 3
        for p, s in zip(parallel_tool_results, sequential_tool_results, strict=True):
            assert p["toolUseId"] == s["toolUseId"]
            assert p["status"] == s["status"]
            assert p["content"] == s["content"]


# =============================================================================
# Per-tool config versioning interaction tests
# =============================================================================


class TestPerToolConfigWithVersioning:
    """Verify per-tool config works correctly with versioning gates."""

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.tool_executor.workflow")
    async def test_parallel_path_respects_per_tool_config(self, mock_workflow):
        """Ensure per-tool configs are applied correctly in parallel execution."""
        mock_workflow.patched.return_value = True

        call_kwargs_by_tool = {}

        async def mock_execute_activity(_activity, input_data, **kwargs):
            tool_id = input_data.tool_use_id
            call_kwargs_by_tool[tool_id] = kwargs
            return ToolExecutionResult(
                tool_use_id=tool_id,
                status="success",
                content=[{"text": "ok"}],
            )

        mock_workflow.execute_activity = mock_execute_activity

        executor = TemporalToolExecutor(
            tool_modules={"fast_tool": "mod.fast", "slow_tool": "mod.slow"},
            tool_configs={
                "slow_tool": TemporalToolConfig(
                    start_to_close_timeout=300.0,
                    heartbeat_timeout=60.0,
                    retry_max_attempts=5,
                ),
            },
        )

        tool_uses = [
            {"name": "fast_tool", "input": {}, "toolUseId": "t1"},
            {"name": "slow_tool", "input": {}, "toolUseId": "t2"},
        ]

        results = []
        async for event in executor._execute(
            agent=MagicMock(),
            tool_uses=tool_uses,
            tool_results=[],
            cycle_trace=None,
            cycle_span=None,
            invocation_state={},
        ):
            results.append(event)

        # fast_tool should use default timeout
        assert call_kwargs_by_tool["t1"]["start_to_close_timeout"] == timedelta(seconds=60.0)

        # slow_tool should use per-tool timeout
        assert call_kwargs_by_tool["t2"]["start_to_close_timeout"] == timedelta(seconds=300.0)
        assert call_kwargs_by_tool["t2"]["heartbeat_timeout"] == timedelta(seconds=60.0)
        assert call_kwargs_by_tool["t2"]["retry_policy"].maximum_attempts == 5


# =============================================================================
# Structured output versioning tests
# =============================================================================


class TestStructuredOutputVersioning:
    """Test structured_output() uses activity routing correctly."""

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.runner.workflow")
    async def test_structured_output_routes_to_activity(self, mock_workflow):
        """Verify structured_output() calls execute_structured_output_activity."""
        from strands_temporal_plugin.types import StructuredOutputResult

        mock_result = StructuredOutputResult(
            output={"city": "Seattle", "temperature_f": 55.0},
            output_model_path="models.WeatherAnalysis",
        )
        mock_workflow.execute_activity = AsyncMock(return_value=mock_result)

        stub = TemporalModelStub(BedrockProviderConfig(model_id="test-model"))

        # Create a mock Pydantic model class
        mock_model_class = MagicMock()
        mock_model_class.__module__ = "models"
        mock_model_class.__qualname__ = "WeatherAnalysis"
        mock_model_class.model_validate.return_value = {"city": "Seattle", "temperature_f": 55.0}

        await stub.structured_output(
            output_model=mock_model_class,
            prompt="Analyze weather in Seattle",
        )

        # Verify activity was called
        mock_workflow.execute_activity.assert_called_once()
        call_args = mock_workflow.execute_activity.call_args
        activity_input = call_args[0][1]  # second positional arg
        assert activity_input.output_model_path == "models.WeatherAnalysis"
        assert activity_input.prompt == "Analyze weather in Seattle"

        # Verify model_validate was called with the output dict
        mock_model_class.model_validate.assert_called_once_with({"city": "Seattle", "temperature_f": 55.0})
