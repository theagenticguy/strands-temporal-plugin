#!/usr/bin/env python3
"""Custom Provider Worker

Starts a Temporal worker for the custom provider example.

Usage:
    # Start Temporal server first:
    temporal server start-dev

    # Then run this worker:
    cd examples/08_custom_provider
    uv run python run_worker.py
"""

import asyncio
import sys
from pathlib import Path

# Ensure custom_model.py is importable by the activity (CustomProviderConfig
# resolves the class via importlib using provider_class_path)
sys.path.insert(0, str(Path(__file__).parent))

from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client
from temporalio.worker import Worker
from workflow import CustomProviderWorkflow


async def main():
    """Set up and run the custom provider worker."""
    print()
    print("=" * 50)
    print("  Strands Temporal - Custom Provider Worker")
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
        task_queue="strands-custom-provider",
        workflows=[CustomProviderWorkflow],
        # Activities are auto-registered by StrandsTemporalPlugin
    )

    print("[OK] Worker configured")
    print()
    print("Task Queue: strands-custom-provider")
    print("Workflow: CustomProviderWorkflow")
    print("Provider: custom_model.LoggingBedrockModel")
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
