#!/usr/bin/env python3
"""Structured Output Worker

Starts a Temporal worker for the structured output example.

Usage:
    # Start Temporal server first:
    temporal server start-dev

    # Then run this worker:
    cd examples/06_structured_output
    uv run python run_worker.py
"""

import asyncio
import sys
from pathlib import Path

# Ensure models.py is importable by the activity (structured_output resolves
# the Pydantic class via its module path, e.g. "models.WeatherAnalysis")
sys.path.insert(0, str(Path(__file__).parent))

from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client
from temporalio.worker import Worker
from workflow import MovieReviewWorkflow, WeatherAnalysisWorkflow


async def main():
    """Set up and run the structured output worker."""
    print()
    print("=" * 50)
    print("  Strands Temporal - Structured Output Worker")
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
        task_queue="strands-structured-output",
        workflows=[WeatherAnalysisWorkflow, MovieReviewWorkflow],
        # Activities are auto-registered by StrandsTemporalPlugin
    )

    print("[OK] Worker configured")
    print()
    print("Task Queue: strands-structured-output")
    print("Workflows:")
    print("  - WeatherAnalysisWorkflow")
    print("  - MovieReviewWorkflow")
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
