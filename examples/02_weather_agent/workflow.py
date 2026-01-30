"""Weather Agent Workflow - First Tool Example

This example demonstrates adding tools to your Strands + Temporal agent.
It uses `create_durable_agent()` which provides full durability for both
model calls AND tool calls.

This is the recommended pattern for production agents.
"""

import logging
from temporalio import workflow

# Import strands with sandbox passthrough to avoid I/O library restrictions
with workflow.unsafe.imports_passed_through():
    from strands_temporal_plugin import BedrockProviderConfig, create_durable_agent
    from tools import get_weather


# Configure logging
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()],
)


@workflow.defn
class WeatherAgentWorkflow:
    """Weather agent with full durability for model AND tool calls.

    This workflow uses `create_durable_agent()` which configures:
    - TemporalModelStub: Routes model.stream() calls to activities
    - TemporalToolExecutor: Routes tool execution to activities

    This provides complete durability:
    - Model calls survive worker restarts
    - Tool calls survive worker restarts
    - Automatic retries for transient failures
    - Full visibility in Temporal UI

    Example usage:
        result = await client.execute_workflow(
            WeatherAgentWorkflow.run,
            "What's the weather in Seattle?",
            id="weather-1",
            task_queue="strands-weather",
        )
    """

    @workflow.run
    async def run(self, prompt: str) -> str:
        """Run the weather agent.

        Args:
            prompt: User's weather question

        Returns:
            Weather information response
        """
        # Create a fully durable agent using the factory function
        # Both model calls AND tool calls are routed to Temporal activities
        agent = create_durable_agent(
            provider_config=BedrockProviderConfig(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                max_tokens=4096,
            ),
            tools=[get_weather],
            system_prompt=(
                "You are a helpful weather assistant. "
                "You can get current weather information for cities using your weather tool. "
                "Always use the get_weather tool when users ask about weather conditions. "
                "Provide friendly, informative responses about the weather."
            ),
        )

        # Use the Strands Agent loop with full durability
        result = await agent.invoke_async(prompt)
        return str(result)
