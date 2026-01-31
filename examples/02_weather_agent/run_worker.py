#!/usr/bin/env python3
"""Weather Agent Worker

Starts a Temporal worker for the weather agent example.

Usage:
    # Start Temporal server first:
    temporal server start-dev

    # Then run this worker:
    cd examples/02_weather_agent
    uv run python run_worker.py
"""

import asyncio

from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client
from temporalio.worker import Worker
from workflow import WeatherAgentWorkflow


async def main():
    """Set up and run the weather agent worker."""
    print()
    print("=" * 50)
    print("  Strands Temporal - Weather Agent Worker")
    print("=" * 50)
    print()

    # Connect to Temporal with the plugin
    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )
    print("[OK] Connected to Temporal server at localhost:7233")

    # Create the worker
    worker = Worker(
        client,
        task_queue="strands-weather",
        workflows=[WeatherAgentWorkflow],
        # Activities are auto-registered by StrandsTemporalPlugin
    )

    print("[OK] Worker configured")
    print()
    print("Task Queue: strands-weather")
    print("Workflow: WeatherAgentWorkflow")
    print()
    print("Tools available:")
    print("  - get_weather: Get weather for any city")
    print()
    print("-" * 50)
    print("Worker starting... Press Ctrl+C to stop")
    print("-" * 50)
    print()

    try:
        await worker.run()
    except KeyboardInterrupt:
        print("\nShutting down worker...")
    finally:
        print("Worker stopped.")


if __name__ == "__main__":
    asyncio.run(main())
