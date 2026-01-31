"""Durable Agent Workflows - Comprehensive Examples

This module demonstrates various patterns for using create_durable_agent()
to build crash-proof AI agents with Temporal.

Examples include:
1. WeatherAssistant - Simple single-tool agent
2. ResearchAssistant - Multi-tool agent for research tasks
3. NotificationAgent - Agent with custom retry policies
4. FinanceAssistant - Agent with multiple financial tools
5. GeneralAssistant - Agent with all tools combined

Each workflow showcases different configurations and use cases.
"""

import logging
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import with sandbox passthrough for workflow context
with workflow.unsafe.imports_passed_through():
    from strands_temporal_plugin import BedrockProviderConfig, create_durable_agent
    from tools import (
        calculate,
        get_stock_price,
        get_user_info,
        get_weather,
        search_web,
        send_notification,
    )

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


# =============================================================================
# Example 1: Simple Weather Assistant
# =============================================================================


@workflow.defn
class WeatherAssistant:
    """Simple weather assistant using create_durable_agent.

    This is the most basic example - a single tool agent that answers
    weather-related questions.

    The create_durable_agent() factory:
    - Creates a TemporalModelStub for durable model calls
    - Creates a TemporalToolExecutor for durable tool execution
    - Auto-discovers tool modules from @tool decorated functions
    - Returns a standard Strands Agent

    Example:
        result = await client.execute_workflow(
            WeatherAssistant.run,
            "What's the weather in Seattle and Tokyo?",
            id="weather-1",
            task_queue="durable-agents",
        )
    """

    @workflow.run
    async def run(self, prompt: str) -> str:
        # Create a durable agent with minimal configuration
        agent = create_durable_agent(
            provider_config=BedrockProviderConfig(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            ),
            tools=[get_weather],
            system_prompt="You are a helpful weather assistant. Use the get_weather tool to answer questions about weather conditions.",
        )

        result = await agent.invoke_async(prompt)
        return str(result)


# =============================================================================
# Example 2: Research Assistant with Multiple Tools
# =============================================================================


@workflow.defn
class ResearchAssistant:
    """Research assistant with web search and calculation tools.

    Demonstrates using multiple tools together for research tasks.
    The agent can:
    - Search the web for information
    - Perform calculations
    - Combine results into coherent answers

    Example:
        result = await client.execute_workflow(
            ResearchAssistant.run,
            "Search for the current population of Tokyo and calculate what percentage it is of Japan's population (125 million)",
            id="research-1",
            task_queue="durable-agents",
        )
    """

    @workflow.run
    async def run(self, prompt: str) -> str:
        agent = create_durable_agent(
            provider_config=BedrockProviderConfig(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                max_tokens=4096,
            ),
            tools=[search_web, calculate],
            system_prompt=(
                "You are a research assistant. You can search the web for information "
                "and perform calculations. When asked questions:\n"
                "1. Search for relevant information if needed\n"
                "2. Use calculations to derive numerical answers\n"
                "3. Provide clear, well-sourced responses"
            ),
            # Custom timeout for potentially slow search operations
            tool_timeout=120.0,
        )

        result = await agent.invoke_async(prompt)
        return str(result)


# =============================================================================
# Example 3: Notification Agent with Custom Retry Policy
# =============================================================================


@workflow.defn
class NotificationAgent:
    """Agent that handles user lookups and notifications.

    Demonstrates custom timeout and retry configurations for
    tools that interact with external services.

    The send_notification tool has a small chance of failing,
    but the retry policy ensures reliable delivery.

    Example:
        result = await client.execute_workflow(
            NotificationAgent.run,
            "Look up user123 and send them an email saying their report is ready",
            id="notify-1",
            task_queue="durable-agents",
        )
    """

    @workflow.run
    async def run(self, prompt: str) -> str:
        agent = create_durable_agent(
            provider_config=BedrockProviderConfig(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            ),
            tools=[get_user_info, send_notification],
            system_prompt=(
                "You are a notification assistant. You can:\n"
                "1. Look up user information using their user ID\n"
                "2. Send notifications via email, sms, or slack\n\n"
                "When asked to notify someone, first look up their info if needed, "
                "then send the appropriate notification."
            ),
            # Longer timeout for notification delivery
            tool_timeout=60.0,
            # Model calls also get adequate timeout
            model_timeout=300.0,
        )

        result = await agent.invoke_async(prompt)
        return str(result)


# =============================================================================
# Example 4: Finance Assistant
# =============================================================================


@workflow.defn
class FinanceAssistant:
    """Financial assistant for stock lookups and calculations.

    Combines stock price lookups with calculation capabilities
    for financial analysis.

    Example:
        result = await client.execute_workflow(
            FinanceAssistant.run,
            "Get the prices of AAPL, GOOGL, and MSFT, then calculate the total value if I own 10 shares of each",
            id="finance-1",
            task_queue="durable-agents",
        )
    """

    @workflow.run
    async def run(self, prompt: str) -> str:
        agent = create_durable_agent(
            provider_config=BedrockProviderConfig(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                max_tokens=2048,
            ),
            tools=[get_stock_price, calculate],
            system_prompt=(
                "You are a financial assistant. You can:\n"
                "1. Look up current stock prices\n"
                "2. Perform financial calculations\n\n"
                "Provide clear analysis and calculations when asked about stocks or investments. "
                "Always show your work when doing calculations."
            ),
        )

        result = await agent.invoke_async(prompt)
        return str(result)


# =============================================================================
# Example 5: General Purpose Assistant (All Tools)
# =============================================================================


@workflow.defn
class GeneralAssistant:
    """General-purpose assistant with all available tools.

    This agent has access to all tools and can handle a wide variety
    of tasks including:
    - Weather queries
    - Web searches
    - Calculations
    - Stock lookups
    - User management
    - Notifications

    Demonstrates how create_durable_agent handles many tools gracefully.

    Example:
        result = await client.execute_workflow(
            GeneralAssistant.run,
            "Check the weather in Seattle, look up AAPL stock, and calculate 15% of $500",
            id="general-1",
            task_queue="durable-agents",
        )
    """

    @workflow.run
    async def run(self, prompt: str) -> str:
        # Create agent with all tools
        agent = create_durable_agent(
            provider_config=BedrockProviderConfig(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                max_tokens=4096,
            ),
            tools=[
                get_weather,
                search_web,
                calculate,
                get_stock_price,
                get_user_info,
                send_notification,
            ],
            system_prompt=(
                "You are a versatile assistant with many capabilities:\n\n"
                "**Weather**: Get weather for any city\n"
                "**Search**: Search the web for information\n"
                "**Calculate**: Perform mathematical calculations\n"
                "**Stocks**: Look up current stock prices\n"
                "**Users**: Look up user information\n"
                "**Notify**: Send notifications via email, sms, or slack\n\n"
                "Choose the appropriate tool(s) based on the user's request. "
                "You can use multiple tools in sequence to complete complex tasks."
            ),
            # Generous timeouts for complex multi-tool operations
            model_timeout=300.0,
            tool_timeout=120.0,
        )

        result = await agent.invoke_async(prompt)
        return str(result)


# =============================================================================
# Example 6: Conversational Agent with History (Advanced)
# =============================================================================


@workflow.defn
class ConversationalAssistant:
    """Conversational assistant demonstrating multi-turn interactions.

    While workflows typically handle single requests, this example
    shows how to pass conversation history for context-aware responses.

    Note: For true multi-turn conversations, consider using Temporal
    signals or queries to interact with a long-running workflow.

    Example:
        # Single turn with context
        result = await client.execute_workflow(
            ConversationalAssistant.run,
            {
                "prompt": "What about Tokyo?",
                "context": "User previously asked about Seattle weather"
            },
            id="convo-1",
            task_queue="durable-agents",
        )
    """

    @workflow.run
    async def run(self, input_data: dict) -> str:
        prompt = input_data.get("prompt", "")
        context = input_data.get("context", "")

        # Build system prompt with context
        system_prompt = (
            "You are a helpful conversational assistant with access to weather and search tools.\n\n"
        )
        if context:
            system_prompt += f"Previous context: {context}\n\n"
        system_prompt += "Continue the conversation naturally, using tools when helpful."

        agent = create_durable_agent(
            provider_config=BedrockProviderConfig(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            ),
            tools=[get_weather, search_web, calculate],
            system_prompt=system_prompt,
        )

        result = await agent.invoke_async(prompt)
        return str(result)
