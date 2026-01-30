#!/usr/bin/env python3
"""Quickstart Worker

Starts a Temporal worker for the quickstart example.

Usage:
    # Start Temporal server first:
    temporal server start-dev

    # Then run this worker:
    cd examples/01_quickstart
    uv run python run_worker.py
"""

import asyncio

from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client
from temporalio.worker import Worker
from workflow import QuickstartWorkflow


async def main():
    """Set up and run the quickstart worker."""
    print()
    print("=" * 50)
    print("  Strands Temporal - Quickstart Worker")
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
        task_queue="strands-quickstart",
        workflows=[QuickstartWorkflow],
        # Activities are auto-registered by StrandsTemporalPlugin
    )

    print("[OK] Worker configured")
    print()
    print("Task Queue: strands-quickstart")
    print("Workflow: QuickstartWorkflow")
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
