"""Weather Agent Workflow using DurableAgent Pattern

This example demonstrates how to create a Temporal workflow that uses
the DurableAgent class for durable AI agent execution.

Key concepts:
1. DurableAgent runs entirely within workflow context
2. Model calls are routed to activities (where credentials exist)
3. Tool calls are routed to activities (with proper retries)
4. All state is serializable through Pydantic models
"""

import logging
from strands_temporal_plugin import BedrockProviderConfig, DurableAgent, DurableAgentConfig
from temporalio import workflow


# Configure logging
logging.getLogger("strands").setLevel(logging.DEBUG)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()],
)


# Tool specification for the weather tool
# This defines what the model knows about the tool
# Note: Bedrock Converse API requires inputSchema to be wrapped in {"json": ...}
WEATHER_TOOL_SPEC = {
    "name": "get_weather",
    "description": "Get the current weather for a city. Use this when the user asks about weather conditions.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "The name of the city to get weather for",
                }
            },
            "required": ["city"],
        }
    },
}


@workflow.defn
class WeatherAgentWorkflow:
    """Weather agent workflow using the DurableAgent pattern.

    This workflow demonstrates the proper way to run AI agents
    within Temporal for full durability guarantees.

    The DurableAgent:
    - Keeps all state serializable in the workflow
    - Routes model calls to activities (where AWS credentials exist)
    - Routes tool calls to activities (with proper retries)
    - Orchestrates the agent loop deterministically

    Example usage:
        # Start the workflow
        result = await client.execute_workflow(
            WeatherAgentWorkflow.run,
            "What's the weather in Seattle?",
            id="weather-agent-1",
            task_queue="strands-agents",
        )
    """

    @workflow.run
    async def run(self, prompt: str) -> str:
        """Run the weather agent with durable execution.

        Args:
            prompt: User's weather question

        Returns:
            Weather information response
        """
        # Create the agent configuration
        # This is fully serializable and defines how the agent should behave
        config = DurableAgentConfig(
            # Model provider configuration
            provider_config=BedrockProviderConfig(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                max_tokens=4096,
            ),
            # System prompt for the agent
            system_prompt=(
                "You are a helpful weather assistant. "
                "You can get current weather information for cities using your weather tool. "
                "Always use the get_weather tool when users ask about weather conditions. "
                "Provide friendly, informative responses about the weather."
            ),
            # Tool specifications - what tools the model knows about
            tool_specs=[WEATHER_TOOL_SPEC],
            # Tool module mapping - where to find the actual tool implementations
            # The activity will dynamically import these when executing tools
            # Use just "tools" since we run from the examples/basic_weather_agent directory
            tool_modules={
                "get_weather": "tools",
            },
            # Activity timeout configuration
            model_activity_timeout=300.0,  # 5 minutes for model calls
            tool_activity_timeout=30.0,  # 30 seconds for tool calls
            # Retry configuration
            max_retries=3,
            initial_retry_interval_seconds=1.0,
            backoff_coefficient=2.0,
        )

        # Create the DurableAgent
        agent = DurableAgent(config)

        # Invoke the agent - this orchestrates the full agent loop
        # 1. Sends prompt to model (via activity)
        # 2. If model requests tool use, executes tools (via activity)
        # 3. Sends tool results back to model (via activity)
        # 4. Repeats until model returns final response
        result = await agent.invoke(prompt)

        # Return the final text response
        return result.text


@workflow.defn
class SimpleAgentWorkflow:
    """Simple agent workflow without tools.

    This demonstrates the simplest possible DurableAgent usage -
    just a model with a system prompt, no tools.
    """

    @workflow.run
    async def run(self, prompt: str) -> str:
        """Run a simple agent without tools.

        Args:
            prompt: User's question

        Returns:
            Agent's response
        """
        config = DurableAgentConfig(
            provider_config=BedrockProviderConfig(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            ),
            system_prompt="You are a helpful assistant. Answer questions clearly and concisely.",
        )

        agent = DurableAgent(config)
        result = await agent.invoke(prompt)
        return result.text
