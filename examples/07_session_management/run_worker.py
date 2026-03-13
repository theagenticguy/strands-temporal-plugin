#!/usr/bin/env python3
"""Session Management Worker

Starts a Temporal worker for the session management example.

Usage:
    # Start Temporal server first:
    temporal server start-dev

    # Then run this worker:
    cd examples/07_session_management
    uv run python run_worker.py

    # With LocalStack for local S3:
    AWS_ENDPOINT_URL=http://localhost:4566 uv run python run_worker.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client
from temporalio.worker import Worker
from workflow import SessionWorkflow


async def main():
    """Set up and run the session management worker."""
    print()
    print("=" * 50)
    print("  Strands Temporal - Session Management Worker")
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
        task_queue="strands-session",
        workflows=[SessionWorkflow],
        # Activities are auto-registered by StrandsTemporalPlugin
    )

    print("[OK] Worker configured")
    print()
    print("Task Queue: strands-session")
    print("Workflow: SessionWorkflow")
    print()
    print("Tools available:")
    print("  - remember_fact: Store a fact for later recall")
    print("  - recall_facts: Retrieve all remembered facts")
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
