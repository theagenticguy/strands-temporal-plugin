#!/usr/bin/env python3
"""Weather Agent Client

Connects to Temporal and executes the weather agent workflow.

Usage:
    # Make sure the worker is running first, then:
    cd examples/02_weather_agent

    # Default prompt
    uv run python run_client.py

    # Custom prompt
    uv run python run_client.py "How's the weather in Tokyo?"
"""

import asyncio
import sys
import uuid

from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client
from workflow import WeatherAgentWorkflow


async def main():
    """Execute the weather agent workflow."""
    print()
    print("=" * 50)
    print("  Strands Temporal - Weather Agent Client")
    print("=" * 50)
    print()

    # Get prompt from command line or use default
    prompt = sys.argv[1] if len(sys.argv) > 1 else "What's the weather in Seattle and Tokyo?"

    # Connect to Temporal
    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )
    print("[OK] Connected to Temporal")
    print()

    print(f"Prompt: {prompt}")
    print("Processing...")
    print()

    # Execute the workflow
    result = await client.execute_workflow(
        WeatherAgentWorkflow.run,
        prompt,
        id=f"weather-{uuid.uuid4().hex[:8]}",
        task_queue="strands-weather",
    )

    print("-" * 50)
    print("Response:")
    print("-" * 50)
    print(result)
    print("-" * 50)
    print()
    print("View workflow in Temporal UI: http://localhost:8233")


if __name__ == "__main__":
    asyncio.run(main())
