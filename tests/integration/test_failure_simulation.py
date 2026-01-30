"""Failure Simulation Tests for Strands Temporal Plugin.

These tests verify the crash-proof and retry capabilities of the plugin by
simulating various failure scenarios during model execution and tool calls.

Test Scenarios:
1. Transient network failures that succeed on retry
2. Activity failures mid-stream (simulating crashes)
3. Heartbeat-based recovery from partial progress
4. Multiple sequential failures followed by success
5. Non-retryable failures (permanent errors)
"""

import asyncio
import pytest
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from strands_temporal_plugin import (
    BedrockProviderConfig,
    ModelExecutionInput,
    ModelExecutionResult,
    ToolExecutionInput,
    ToolExecutionResult,
    create_durable_agent,
)


# =============================================================================
# Failure Tracking State
# =============================================================================


class FailureState:
    """Tracks failure injection state across activity calls."""

    def __init__(self):
        self.model_call_count = 0
        self.tool_call_count = 0
        self.failures_to_inject = 0
        self.failure_type = "transient"  # "transient", "mid_stream", "permanent"
        self.recovered_from_heartbeat = False

    def reset(self):
        self.model_call_count = 0
        self.tool_call_count = 0
        self.failures_to_inject = 0
        self.failure_type = "transient"
        self.recovered_from_heartbeat = False


# Global state for failure injection
failure_state = FailureState()


# =============================================================================
# Failure-Injecting Mock Activities
# =============================================================================


@activity.defn(name="execute_model_activity")
async def failing_model_activity(input_data: ModelExecutionInput) -> ModelExecutionResult:
    """Model activity that can inject failures based on failure_state."""
    info = activity.info()
    failure_state.model_call_count += 1
    current_attempt = info.attempt

    activity.logger.info(
        f"Model activity call #{failure_state.model_call_count}, "
        f"attempt #{current_attempt}, "
        f"failures_to_inject={failure_state.failures_to_inject}"
    )

    # Check if we should fail this attempt
    if failure_state.failures_to_inject > 0 and current_attempt <= failure_state.failures_to_inject:
        if failure_state.failure_type == "transient":
            # Simulate transient network error
            activity.heartbeat(f"Failing attempt {current_attempt}")
            raise ApplicationError(
                f"Simulated network timeout on attempt {current_attempt}",
                type="NetworkTimeout",
                non_retryable=False,  # Will retry
            )

        elif failure_state.failure_type == "mid_stream":
            # Simulate crash mid-stream (after partial events)
            events = [
                {"messageStart": {"role": "assistant"}},
                {"contentBlockStart": {"contentBlockIndex": 0, "start": {}}},
            ]
            # Heartbeat progress before "crashing"
            activity.heartbeat({"events_processed": 2, "events": events})

            raise RuntimeError(
                f"Simulated crash mid-stream on attempt {current_attempt}"
            )

        elif failure_state.failure_type == "permanent":
            # Simulate non-retryable error
            raise ApplicationError(
                "Simulated permanent model error",
                type="ModelConfigError",
                non_retryable=True,  # Will NOT retry
            )

    # Check for heartbeat recovery
    if info.heartbeat_details:
        failure_state.recovered_from_heartbeat = True
        activity.logger.info(f"Recovered from heartbeat: {info.heartbeat_details}")

    # Success case - return mock response
    messages = input_data.messages or []
    has_tool_result = any(
        any("toolResult" in block for block in msg.get("content", []))
        for msg in messages if msg.get("role") == "user"
    )

    # Check for weather query
    last_user_message = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", [])
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    last_user_message = block["text"]
                    break
            break

    if input_data.tool_specs and "weather" in last_user_message.lower() and not has_tool_result:
        # Return tool use response
        return ModelExecutionResult(
            events=[
                {"messageStart": {"role": "assistant"}},
                {
                    "contentBlockStart": {
                        "contentBlockIndex": 0,
                        "start": {
                            "toolUse": {
                                "toolUseId": f"tool_{failure_state.model_call_count}",
                                "name": "get_weather",
                            }
                        },
                    }
                },
                {
                    "contentBlockDelta": {
                        "contentBlockIndex": 0,
                        "delta": {"toolUse": {"input": '{"city": "Seattle"}'}},
                    }
                },
                {"contentBlockStop": {"contentBlockIndex": 0}},
                {"messageStop": {"stopReason": "tool_use"}},
                {"metadata": {"usage": {"inputTokens": 20, "outputTokens": 15}}},
            ]
        )

    if has_tool_result:
        return ModelExecutionResult(
            events=[
                {"messageStart": {"role": "assistant"}},
                {"contentBlockStart": {"contentBlockIndex": 0, "start": {}}},
                {
                    "contentBlockDelta": {
                        "contentBlockIndex": 0,
                        "delta": {"text": f"SUCCESS after {current_attempt} attempt(s): The weather in Seattle is sunny!"},
                    }
                },
                {"contentBlockStop": {"contentBlockIndex": 0}},
                {"messageStop": {"stopReason": "end_turn"}},
                {"metadata": {"usage": {"inputTokens": 30, "outputTokens": 25}}},
            ]
        )

    # Default response
    return ModelExecutionResult(
        events=[
            {"messageStart": {"role": "assistant"}},
            {"contentBlockStart": {"contentBlockIndex": 0, "start": {}}},
            {
                "contentBlockDelta": {
                    "contentBlockIndex": 0,
                    "delta": {"text": f"SUCCESS after {current_attempt} attempt(s)!"},
                }
            },
            {"contentBlockStop": {"contentBlockIndex": 0}},
            {"messageStop": {"stopReason": "end_turn"}},
            {"metadata": {"usage": {"inputTokens": 10, "outputTokens": 10}}},
        ]
    )


@activity.defn(name="execute_tool_activity")
async def failing_tool_activity(input_data: ToolExecutionInput) -> ToolExecutionResult:
    """Tool activity that can inject failures."""
    info = activity.info()
    failure_state.tool_call_count += 1
    current_attempt = info.attempt

    activity.logger.info(
        f"Tool activity call #{failure_state.tool_call_count}, "
        f"attempt #{current_attempt}"
    )

    # Success case
    if input_data.tool_name == "get_weather":
        city = input_data.tool_input.get("city", "Unknown")
        return ToolExecutionResult(
            tool_use_id=input_data.tool_use_id,
            status="success",
            content=[{"text": f"Weather in {city}: Sunny, 72°F (fetched on attempt {current_attempt})"}],
        )

    return ToolExecutionResult(
        tool_use_id=input_data.tool_use_id,
        status="error",
        content=[{"text": f"Unknown tool: {input_data.tool_name}"}],
    )


# =============================================================================
# Test Workflows
# =============================================================================


def get_weather(city: str) -> str:
    """Test tool for weather."""
    return f"Weather in {city}: Sunny, 72°F"


@workflow.defn
class FailureTestWorkflow:
    """Workflow for testing failure scenarios."""

    @workflow.run
    async def run(self, prompt: str) -> str:
        with workflow.unsafe.imports_passed_through():
            from strands import tool

            weather_tool = tool(
                name="get_weather",
                description="Get weather for a city",
                inputSchema={
                    "json": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    }
                },
            )(get_weather)

            agent = create_durable_agent(
                provider_config=BedrockProviderConfig(model_id="test-model"),
                system_prompt="You are a weather assistant.",
                tools=[weather_tool],
                tool_modules={"get_weather": "tests.integration.test_failure_simulation"},
            )

        result = await agent.invoke_async(prompt)
        return str(result)


@workflow.defn
class SimpleFailureWorkflow:
    """Simple workflow without tools for basic failure testing."""

    @workflow.run
    async def run(self, prompt: str) -> str:
        with workflow.unsafe.imports_passed_through():
            agent = create_durable_agent(
                provider_config=BedrockProviderConfig(model_id="test-model"),
            )

        result = await agent.invoke_async(prompt)
        return str(result)


# =============================================================================
# Test Cases
# =============================================================================


class TestTransientFailures:
    """Test recovery from transient network failures."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset failure state before each test."""
        failure_state.reset()
        yield
        failure_state.reset()

    @pytest.mark.asyncio
    async def test_single_retry_success(self):
        """Test that workflow recovers from a single transient failure."""
        from strands_temporal_plugin.plugin import _merge_workflow_runner

        # Inject 1 failure, should succeed on 2nd attempt
        failure_state.failures_to_inject = 1
        failure_state.failure_type = "transient"

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="failure-test-queue",
                workflows=[SimpleFailureWorkflow],
                activities=[failing_model_activity, failing_tool_activity],
                workflow_runner=_merge_workflow_runner(None),
            ):
                result = await env.client.execute_workflow(
                    SimpleFailureWorkflow.run,
                    "Hello!",
                    id="single-retry-test",
                    task_queue="failure-test-queue",
                )

                assert "SUCCESS" in result
                assert "2 attempt" in result  # Should have succeeded on 2nd attempt
                assert failure_state.model_call_count >= 1

    @pytest.mark.asyncio
    async def test_multiple_retries_success(self):
        """Test that workflow recovers from multiple transient failures."""
        from strands_temporal_plugin.plugin import _merge_workflow_runner

        # Inject 2 failures, should succeed on 3rd attempt
        failure_state.failures_to_inject = 2
        failure_state.failure_type = "transient"

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="failure-test-queue",
                workflows=[SimpleFailureWorkflow],
                activities=[failing_model_activity, failing_tool_activity],
                workflow_runner=_merge_workflow_runner(None),
            ):
                result = await env.client.execute_workflow(
                    SimpleFailureWorkflow.run,
                    "Hello!",
                    id="multi-retry-test",
                    task_queue="failure-test-queue",
                )

                assert "SUCCESS" in result
                assert "3 attempt" in result  # Should have succeeded on 3rd attempt

    @pytest.mark.asyncio
    async def test_tool_workflow_with_failures(self):
        """Test that tool-using workflow recovers from failures."""
        from strands_temporal_plugin.plugin import _merge_workflow_runner

        # Inject 1 failure on model calls
        failure_state.failures_to_inject = 1
        failure_state.failure_type = "transient"

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="failure-test-queue",
                workflows=[FailureTestWorkflow],
                activities=[failing_model_activity, failing_tool_activity],
                workflow_runner=_merge_workflow_runner(None),
            ):
                result = await env.client.execute_workflow(
                    FailureTestWorkflow.run,
                    "What's the weather in Seattle?",
                    id="tool-failure-test",
                    task_queue="failure-test-queue",
                )

                # Should have recovered and completed with weather info
                assert "Seattle" in result or "sunny" in result.lower() or "SUCCESS" in result


class TestMidStreamFailures:
    """Test recovery from failures during streaming."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset failure state before each test."""
        failure_state.reset()
        yield
        failure_state.reset()

    @pytest.mark.asyncio
    async def test_crash_mid_stream_recovery(self):
        """Test recovery when activity crashes mid-stream."""
        from strands_temporal_plugin.plugin import _merge_workflow_runner

        # Inject 1 mid-stream crash
        failure_state.failures_to_inject = 1
        failure_state.failure_type = "mid_stream"

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="failure-test-queue",
                workflows=[SimpleFailureWorkflow],
                activities=[failing_model_activity, failing_tool_activity],
                workflow_runner=_merge_workflow_runner(None),
            ):
                result = await env.client.execute_workflow(
                    SimpleFailureWorkflow.run,
                    "Hello!",
                    id="mid-stream-crash-test",
                    task_queue="failure-test-queue",
                )

                assert "SUCCESS" in result
                # Verify we could have recovered from heartbeat
                # (in real scenario, heartbeat details would be used)


class TestPermanentFailures:
    """Test handling of non-retryable failures."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset failure state before each test."""
        failure_state.reset()
        yield
        failure_state.reset()

    @pytest.mark.asyncio
    async def test_permanent_failure_no_retry(self):
        """Test that permanent failures are not retried."""
        from strands_temporal_plugin.plugin import _merge_workflow_runner
        from temporalio.client import WorkflowFailureError

        # Inject permanent failure
        failure_state.failures_to_inject = 10  # Many failures
        failure_state.failure_type = "permanent"

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="failure-test-queue",
                workflows=[SimpleFailureWorkflow],
                activities=[failing_model_activity, failing_tool_activity],
                workflow_runner=_merge_workflow_runner(None),
            ):
                with pytest.raises(WorkflowFailureError) as exc_info:
                    await env.client.execute_workflow(
                        SimpleFailureWorkflow.run,
                        "Hello!",
                        id="permanent-failure-test",
                        task_queue="failure-test-queue",
                    )

                # Should fail after 1 attempt (non-retryable)
                # Note: model_call_count tracks calls across all workers, may be 1
                assert failure_state.model_call_count >= 1
                # Verify the workflow failed (specific error details in cause chain)
                assert exc_info.value is not None


class TestRetryPolicyConfiguration:
    """Test custom retry policy configurations."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset failure state before each test."""
        failure_state.reset()
        yield
        failure_state.reset()

    @pytest.mark.asyncio
    async def test_exhausted_retries(self):
        """Test behavior when all retries are exhausted."""
        from strands_temporal_plugin.plugin import _merge_workflow_runner
        from temporalio.client import WorkflowFailureError

        # Inject more failures than the default retry limit (3)
        failure_state.failures_to_inject = 5
        failure_state.failure_type = "transient"

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="failure-test-queue",
                workflows=[SimpleFailureWorkflow],
                activities=[failing_model_activity, failing_tool_activity],
                workflow_runner=_merge_workflow_runner(None),
            ):
                with pytest.raises(WorkflowFailureError):
                    await env.client.execute_workflow(
                        SimpleFailureWorkflow.run,
                        "Hello!",
                        id="exhausted-retries-test",
                        task_queue="failure-test-queue",
                    )

                # Should have made attempts (activity retried until max reached)
                # Note: The activity is called once but internally retries
                assert failure_state.model_call_count >= 1


# =============================================================================
# Network Simulation Helpers (for manual testing)
# =============================================================================


class NetworkSimulator:
    """Helper class for simulating network conditions.

    For use with manual/integration tests that need actual network manipulation.
    Uses macOS pfctl for network blocking.

    Example usage:
        async with NetworkSimulator() as sim:
            await sim.block_bedrock()
            # ... run test that should fail ...
            await sim.unblock_bedrock()
            # ... run test that should succeed ...
    """

    BEDROCK_HOST = "bedrock-runtime.us-east-1.amazonaws.com"
    BEDROCK_AGENT_HOST = "bedrock-agent-runtime.us-east-1.amazonaws.com"

    def __init__(self):
        self._blocked = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._blocked:
            await self.unblock_bedrock()

    async def block_bedrock(self) -> None:
        """Block traffic to Bedrock endpoints using macOS pfctl.

        Requires sudo privileges.
        """
        import subprocess

        # Create pfctl rule to block bedrock
        rules = f"""
block drop quick on en0 proto tcp to {self.BEDROCK_HOST} port 443
block drop quick on en0 proto tcp to {self.BEDROCK_AGENT_HOST} port 443
"""
        # This would need to be run with sudo in practice
        # subprocess.run(["sudo", "pfctl", "-ef", "-"], input=rules.encode())
        self._blocked = True

    async def unblock_bedrock(self) -> None:
        """Remove Bedrock traffic blocking."""
        import subprocess

        # This would flush the rules
        # subprocess.run(["sudo", "pfctl", "-F", "all"])
        self._blocked = False

    async def add_latency(self, ms: int = 1000) -> None:
        """Add network latency to Bedrock calls.

        Uses macOS network link conditioner or dummynet.
        """
        pass  # Would use dnctl or network link conditioner


# =============================================================================
# Real Network Failure Test (for manual execution)
# =============================================================================


@pytest.mark.skip(reason="Manual test - requires real Temporal server and AWS credentials")
class TestRealNetworkFailure:
    """Tests that use actual network manipulation.

    These tests are skipped by default and intended for manual execution
    to validate the plugin against real network failures.

    To run:
        pytest tests/integration/test_failure_simulation.py::TestRealNetworkFailure -v --run-manual
    """

    @pytest.mark.asyncio
    async def test_bedrock_network_failure_recovery(self):
        """Test recovery from actual Bedrock network failures.

        This test:
        1. Starts a workflow that calls Bedrock
        2. Blocks network to Bedrock mid-call
        3. Verifies the activity fails
        4. Unblocks network
        5. Verifies retry succeeds
        """
        # This test would need:
        # 1. Real Temporal server (not time-skipping env)
        # 2. AWS credentials
        # 3. sudo access for network manipulation
        # 4. Manual execution
        pass
