#!/usr/bin/env python3
"""Failure Resilience Worker

Starts a Temporal worker for the failure resilience examples.

Usage:
    # Start Temporal server first:
    temporal server start-dev

    # Then run this worker:
    cd examples/09_failure_resilience
    uv run python run_worker.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client
from temporalio.worker import Worker
from workflow import (
    GracefulDegradationWorkflow,
    TimeoutRecoveryWorkflow,
    TransientFailureWorkflow,
)


async def main():
    """Set up and run the failure resilience worker."""
    print()
    print("=" * 60)
    print("  Strands Temporal - Failure Resilience Worker")
    print("=" * 60)
    print()

    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )
    print("[OK] Connected to Temporal server at localhost:7233")

    worker = Worker(
        client,
        task_queue="strands-resilience",
        workflows=[
            TransientFailureWorkflow,
            TimeoutRecoveryWorkflow,
            GracefulDegradationWorkflow,
        ],
    )

    print("[OK] Worker configured")
    print()
    print("Workflows:")
    print("  - TransientFailureWorkflow    : Retries flaky API calls")
    print("  - TimeoutRecoveryWorkflow     : Heartbeat timeout on slow queries")
    print("  - GracefulDegradationWorkflow : Handles permanent failures")
    print()
    print("Task Queue: strands-resilience")
    print()
    print("-" * 60)
    print("Worker starting... Press Ctrl+C to stop")
    print("-" * 60)
    print()

    try:
        await worker.run()
    except KeyboardInterrupt:
        print("\nShutting down worker...")
    finally:
        print("Worker stopped.")


if __name__ == "__main__":
    asyncio.run(main())
