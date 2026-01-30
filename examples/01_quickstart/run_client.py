#!/usr/bin/env python3
"""Quickstart Client

Connects to Temporal and executes the quickstart workflow.

Usage:
    # Make sure the worker is running first, then:
    cd examples/01_quickstart

    # Default prompt
    uv run python run_client.py

    # Custom prompt
    uv run python run_client.py "What is 2 + 2?"
"""

import asyncio
import sys
import uuid

from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client
from workflow import QuickstartWorkflow


async def main():
    """Execute the quickstart workflow."""
    print()
    print("=" * 50)
    print("  Strands Temporal - Quickstart Client")
    print("=" * 50)
    print()

    # Get prompt from command line or use default
    prompt = sys.argv[1] if len(sys.argv) > 1 else "What is the capital of France?"

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
        QuickstartWorkflow.run,
        prompt,
        id=f"quickstart-{uuid.uuid4().hex[:8]}",
        task_queue="strands-quickstart",
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
