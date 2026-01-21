"""Integration tests for strands-temporal-plugin workflows.

These tests use Temporal's WorkflowEnvironment to test the complete
workflow execution with mocked activities.
"""

import pytest
from strands_temporal_plugin import (
    BedrockProviderConfig,
    DurableAgent,
    DurableAgentConfig,
    ModelExecutionInput,
    ModelExecutionResult,
    StrandsTemporalPlugin,
    ToolExecutionInput,
    ToolExecutionResult,
)
from temporalio import activity, workflow
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker


# =============================================================================
# Mock Activities for Testing
# =============================================================================


@activity.defn(name="execute_model_activity")
async def mock_execute_model_activity(input_data: ModelExecutionInput) -> ModelExecutionResult:
    """Mock model activity that returns canned responses."""
    # Check if this is a request that should trigger tool use
    messages = input_data.messages or []
    last_user_message = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", [])
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    last_user_message = block["text"]
                    break
            break

    # Check for tool result in messages (means we already called a tool)
    has_tool_result = any(
        any("toolResult" in block for block in msg.get("content", [])) for msg in messages if msg.get("role") == "user"
    )

    # If we have tools and user asks about weather and no tool result yet
    if input_data.tool_specs and "weather" in last_user_message.lower() and not has_tool_result:
        return ModelExecutionResult(
            events=[
                {"messageStart": {"role": "assistant"}},
                {
                    "contentBlockStart": {
                        "contentBlockIndex": 0,
                        "start": {
                            "toolUse": {
                                "toolUseId": "mock_tool_123",
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

    # If we have a tool result, generate final response
    if has_tool_result:
        return ModelExecutionResult(
            events=[
                {"messageStart": {"role": "assistant"}},
                {"contentBlockStart": {"contentBlockIndex": 0, "start": {}}},
                {
                    "contentBlockDelta": {
                        "contentBlockIndex": 0,
                        "delta": {"text": "The weather in Seattle is sunny and 72°F."},
                    }
                },
                {"contentBlockStop": {"contentBlockIndex": 0}},
                {"messageStop": {"stopReason": "end_turn"}},
                {"metadata": {"usage": {"inputTokens": 30, "outputTokens": 20}}},
            ]
        )

    # Default: simple text response
    return ModelExecutionResult(
        events=[
            {"messageStart": {"role": "assistant"}},
            {"contentBlockStart": {"contentBlockIndex": 0, "start": {}}},
            {
                "contentBlockDelta": {
                    "contentBlockIndex": 0,
                    "delta": {"text": "Hello! "},
                }
            },
            {
                "contentBlockDelta": {
                    "contentBlockIndex": 0,
                    "delta": {"text": "How can I help you today?"},
                }
            },
            {"contentBlockStop": {"contentBlockIndex": 0}},
            {"messageStop": {"stopReason": "end_turn"}},
            {"metadata": {"usage": {"inputTokens": 10, "outputTokens": 15}}},
        ]
    )


@activity.defn(name="execute_tool_activity")
async def mock_execute_tool_activity(input_data: ToolExecutionInput) -> ToolExecutionResult:
    """Mock tool activity that returns canned responses."""
    if input_data.tool_name == "get_weather":
        city = input_data.tool_input.get("city", "Unknown")
        return ToolExecutionResult(
            tool_use_id=input_data.tool_use_id,
            status="success",
            content=[{"text": f"Weather in {city}: Sunny, 72°F"}],
        )

    return ToolExecutionResult(
        tool_use_id=input_data.tool_use_id,
        status="error",
        content=[{"text": f"Unknown tool: {input_data.tool_name}"}],
    )


# =============================================================================
# Test Workflows
# =============================================================================


@workflow.defn
class SimpleAgentWorkflow:
    """Simple workflow for testing basic agent execution."""

    @workflow.run
    async def run(self, prompt: str) -> str:
        config = DurableAgentConfig(provider_config=BedrockProviderConfig(model_id="anthropic.claude-3-sonnet"))
        agent = DurableAgent(config)
        result = await agent.invoke(prompt)
        return result.text


@workflow.defn
class ToolAgentWorkflow:
    """Workflow with tools for testing tool execution."""

    @workflow.run
    async def run(self, prompt: str) -> str:
        config = DurableAgentConfig(
            provider_config=BedrockProviderConfig(model_id="anthropic.claude-3-sonnet"),
            system_prompt="You are a weather assistant.",
            tool_specs=[
                {
                    "name": "get_weather",
                    "description": "Get weather for a city",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                            "required": ["city"],
                        }
                    },
                }
            ],
            tool_modules={"get_weather": "tests.integration.test_workflow"},
        )
        agent = DurableAgent(config)
        result = await agent.invoke(prompt)
        return result.text


# =============================================================================
# Integration Tests
# =============================================================================


class TestSimpleWorkflow:
    """Test simple workflow execution."""

    @pytest.mark.asyncio
    async def test_simple_agent_response(self):
        """Test that a simple agent workflow returns expected response."""
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-queue",
                workflows=[SimpleAgentWorkflow],
                activities=[mock_execute_model_activity, mock_execute_tool_activity],
            ):
                result = await env.client.execute_workflow(
                    SimpleAgentWorkflow.run,
                    "Hello!",
                    id="test-simple-1",
                    task_queue="test-queue",
                )

                assert "Hello!" in result
                assert "help" in result.lower()


class TestToolWorkflow:
    """Test workflow with tool execution."""

    @pytest.mark.asyncio
    async def test_tool_agent_with_weather(self):
        """Test that an agent workflow can use tools."""
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-queue",
                workflows=[ToolAgentWorkflow],
                activities=[mock_execute_model_activity, mock_execute_tool_activity],
            ):
                result = await env.client.execute_workflow(
                    ToolAgentWorkflow.run,
                    "What's the weather in Seattle?",
                    id="test-tool-1",
                    task_queue="test-queue",
                )

                # Should have called the tool and gotten weather info
                assert "Seattle" in result or "weather" in result.lower() or "72" in result


class TestPluginConfiguration:
    """Test plugin configuration."""

    @pytest.mark.asyncio
    async def test_plugin_registers_activities(self):
        """Test that the plugin properly configures the worker."""
        plugin = StrandsTemporalPlugin()

        # Create a mock config
        config = {"activities": []}

        # Configure the worker
        result_config = plugin.configure_worker(config)

        # Should have registered both activities
        assert len(result_config["activities"]) == 2

    @pytest.mark.asyncio
    async def test_plugin_configures_sandbox(self):
        """Test that the plugin configures sandbox restrictions."""
        plugin = StrandsTemporalPlugin()

        config = {"activities": []}
        result_config = plugin.configure_worker(config)

        # Should have a workflow runner configured
        assert "workflow_runner" in result_config
