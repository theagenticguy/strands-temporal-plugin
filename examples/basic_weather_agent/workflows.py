"""Weather Agent Workflows

This example demonstrates two patterns for running Strands agents with Temporal:

1. **FullyDurableWeatherAgent** (RECOMMENDED): Uses the real Strands Agent loop
   with both TemporalModelStub AND TemporalToolExecutor for full durability.
   Both model calls and tool calls are routed to Temporal activities.

2. **StrandsWeatherAgent**: Uses just TemporalModelStub (model durability only).
   Tools execute in workflow context - use only for pure functions without I/O.

All patterns provide durable AI agent execution through Temporal.
"""

import logging
from temporalio import workflow


# Import strands with sandbox passthrough to avoid I/O library restrictions
# This allows using the Agent class in workflow context while the actual
# model/tool I/O happens in activities
with workflow.unsafe.imports_passed_through():
    from strands import Agent
    from strands_temporal_plugin import BedrockProviderConfig, TemporalModelStub, create_durable_agent
    from tools import get_weather


# Configure logging
logging.getLogger("strands").setLevel(logging.DEBUG)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()],
)


# =============================================================================
# RECOMMENDED: Full Durability with create_durable_agent()
# =============================================================================


@workflow.defn
class FullyDurableWeatherAgent:
    """Weather agent with FULL durability for both model AND tools (RECOMMENDED).

    This workflow uses create_durable_agent() which configures:
    - TemporalModelStub: Routes model.stream() calls to activities
    - TemporalToolExecutor: Routes tool execution to activities

    This provides complete durability while preserving all Strands features
    (callbacks, hooks, conversation history, etc.).

    Use this pattern when:
    - Your tools do I/O (API calls, file access, etc.)
    - You need retry and timeout handling for tool calls
    - You want workflow replay to work correctly

    Example usage:
        result = await client.execute_workflow(
            FullyDurableWeatherAgent.run,
            "What's the weather in Seattle and Tokyo?",
            id="fully-durable-weather-1",
            task_queue="strands-agents",
        )
    """

    @workflow.run
    async def run(self, prompt: str) -> str:
        """Run the weather agent with full durability.

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

        # Use the real Strands Agent loop with full durability!
        result = await agent.invoke_async(prompt)

        return str(result)


# =============================================================================
# Alternative: Model-Only Durability (for pure function tools)
# =============================================================================


@workflow.defn
class StrandsWeatherAgent:
    """Weather agent with MODEL-ONLY durability.

    This workflow uses Strands Agent with just TemporalModelStub, which:
    - Preserves the full Strands Agent event loop
    - Routes model.stream() calls to Temporal activities for durability
    - Tools execute in WORKFLOW context (no activity durability)

    Use this pattern when:
    - Your tools are pure functions (no I/O)
    - You don't need retry handling for tool calls
    - You want simpler configuration

    WARNING: If your tools do I/O (API calls, file access, etc.), use
    FullyDurableWeatherAgent instead!

    Example usage:
        result = await client.execute_workflow(
            StrandsWeatherAgent.run,
            "What's the weather in Seattle and Tokyo?",
            id="strands-weather-1",
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
        # Create a real Strands Agent with TemporalModelStub
        # The stub routes model calls to Temporal activities
        agent = Agent(
            model=TemporalModelStub(
                BedrockProviderConfig(
                    model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                    max_tokens=4096,
                )
            ),
            tools=[get_weather],  # Use @tool decorated function directly!
            system_prompt=(
                "You are a helpful weather assistant. "
                "You can get current weather information for cities using your weather tool. "
                "Always use the get_weather tool when users ask about weather conditions. "
                "Provide friendly, informative responses about the weather."
            ),
        )

        # Use the real Strands Agent loop!
        # This preserves all agent features while getting Temporal durability
        result = await agent.invoke_async(prompt)

        return str(result)


@workflow.defn
class SimpleAgentWorkflow:
    """Simple agent without tools.

    Demonstrates the simplest possible agent usage - just a model
    with a system prompt, no tools.
    """

    @workflow.run
    async def run(self, prompt: str) -> str:
        """Run a simple agent without tools.

        Args:
            prompt: User's question

        Returns:
            Agent's response
        """
        agent = Agent(
            model=TemporalModelStub(
                BedrockProviderConfig(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0")
            ),
            system_prompt="You are a helpful assistant. Answer questions clearly and concisely.",
        )

        result = await agent.invoke_async(prompt)
        return str(result)
