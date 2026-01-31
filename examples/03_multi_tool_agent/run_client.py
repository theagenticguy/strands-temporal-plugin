#!/usr/bin/env python3
"""Multi-Tool Agent Client

Run various multi-tool agent workflows demonstrating different patterns.

Prerequisites:
    1. Temporal server running: temporal server start-dev
    2. Worker running: python run_worker.py

Usage:
    cd examples/03_multi_tool_agent

    # Run specific example
    uv run python run_client.py weather
    uv run python run_client.py research
    uv run python run_client.py notify
    uv run python run_client.py finance
    uv run python run_client.py general

    # Run all examples
    uv run python run_client.py all

    # Custom prompt
    uv run python run_client.py weather --prompt "What's the weather in Paris?"
"""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

# Add the example directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client

from workflows import (
    ConversationalAssistant,
    FinanceAssistant,
    GeneralAssistant,
    NotificationAgent,
    ResearchAssistant,
    WeatherAssistant,
)


# Default prompts for each example
DEFAULT_PROMPTS = {
    "weather": "What's the weather in Seattle and Tokyo?",
    "research": "Search for information about renewable energy and calculate what percentage 30 is of 100.",
    "notify": "Look up user123 and send them an email notification saying their weekly report is ready.",
    "finance": "Get the current prices for AAPL, GOOGL, and NVDA. Then calculate the total value if I own 5 shares of each.",
    "general": "Check the weather in Miami, search for today's top tech news, and calculate 18% tip on a $85 bill.",
    "convo": "Tell me about the weather in London and what activities you'd recommend.",
}


async def run_weather(client: Client, prompt: str) -> str:
    """Run the WeatherAssistant workflow."""
    print(f"Running WeatherAssistant...")
    print(f"  Prompt: {prompt}")
    print()

    result = await client.execute_workflow(
        WeatherAssistant.run,
        prompt,
        id=f"weather-{uuid.uuid4().hex[:8]}",
        task_queue="durable-agents",
    )
    return result


async def run_research(client: Client, prompt: str) -> str:
    """Run the ResearchAssistant workflow."""
    print(f"Running ResearchAssistant...")
    print(f"  Prompt: {prompt}")
    print()

    result = await client.execute_workflow(
        ResearchAssistant.run,
        prompt,
        id=f"research-{uuid.uuid4().hex[:8]}",
        task_queue="durable-agents",
    )
    return result


async def run_notify(client: Client, prompt: str) -> str:
    """Run the NotificationAgent workflow."""
    print(f"Running NotificationAgent...")
    print(f"  Prompt: {prompt}")
    print()

    result = await client.execute_workflow(
        NotificationAgent.run,
        prompt,
        id=f"notify-{uuid.uuid4().hex[:8]}",
        task_queue="durable-agents",
    )
    return result


async def run_finance(client: Client, prompt: str) -> str:
    """Run the FinanceAssistant workflow."""
    print(f"Running FinanceAssistant...")
    print(f"  Prompt: {prompt}")
    print()

    result = await client.execute_workflow(
        FinanceAssistant.run,
        prompt,
        id=f"finance-{uuid.uuid4().hex[:8]}",
        task_queue="durable-agents",
    )
    return result


async def run_general(client: Client, prompt: str) -> str:
    """Run the GeneralAssistant workflow."""
    print(f"Running GeneralAssistant...")
    print(f"  Prompt: {prompt}")
    print()

    result = await client.execute_workflow(
        GeneralAssistant.run,
        prompt,
        id=f"general-{uuid.uuid4().hex[:8]}",
        task_queue="durable-agents",
    )
    return result


async def run_convo(client: Client, prompt: str) -> str:
    """Run the ConversationalAssistant workflow."""
    print(f"Running ConversationalAssistant...")
    print(f"  Prompt: {prompt}")
    print()

    result = await client.execute_workflow(
        ConversationalAssistant.run,
        {"prompt": prompt, "context": "This is a new conversation."},
        id=f"convo-{uuid.uuid4().hex[:8]}",
        task_queue="durable-agents",
    )
    return result


RUNNERS = {
    "weather": run_weather,
    "research": run_research,
    "notify": run_notify,
    "finance": run_finance,
    "general": run_general,
    "convo": run_convo,
}


async def main():
    parser = argparse.ArgumentParser(
        description="Run durable agent workflow examples",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_client.py weather
  python run_client.py finance --prompt "What's the price of TSLA?"
  python run_client.py all
        """,
    )
    parser.add_argument(
        "example",
        choices=["weather", "research", "notify", "finance", "general", "convo", "all"],
        help="Which example to run",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        help="Custom prompt (overrides default)",
    )
    parser.add_argument(
        "--temporal-address",
        type=str,
        default="localhost:7233",
        help="Temporal server address (default: localhost:7233)",
    )

    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  Multi-Tool Agent Client")
    print("=" * 60)
    print()

    # Connect to Temporal
    client = await Client.connect(
        args.temporal_address,
        plugins=[StrandsTemporalPlugin()],
    )
    print(f"[OK] Connected to Temporal at {args.temporal_address}")
    print()

    if args.example == "all":
        # Run all examples sequentially
        examples_to_run = ["weather", "research", "notify", "finance", "general"]
    else:
        examples_to_run = [args.example]

    for example in examples_to_run:
        print("-" * 60)
        prompt = args.prompt if args.prompt else DEFAULT_PROMPTS[example]
        runner = RUNNERS[example]

        try:
            result = await runner(client, prompt)
            print("Result:")
            print("-" * 40)
            print(result)
            print("-" * 40)
            print()
        except Exception as e:
            print(f"Error running {example}: {e}")
            print()

    print("=" * 60)
    print("Done!")
    print()
    print("View workflow history in Temporal UI: http://localhost:8233")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
