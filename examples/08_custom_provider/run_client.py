#!/usr/bin/env python3
"""Custom Provider Client

Connects to Temporal and executes the custom provider workflow.

Usage:
    # Make sure the worker is running first, then:
    cd examples/08_custom_provider

    # Default prompt
    uv run python run_client.py

    # Custom prompt
    uv run python run_client.py "Explain quantum computing in one paragraph."
"""

import asyncio
import sys
import uuid

from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client
from workflow import CustomProviderWorkflow


async def main():
    """Execute the custom provider workflow."""
    print()
    print("=" * 50)
    print("  Strands Temporal - Custom Provider Client")
    print("=" * 50)
    print()

    # Get prompt from command line or use default
    prompt = sys.argv[1] if len(sys.argv) > 1 else "What is the meaning of life?"

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
        CustomProviderWorkflow.run,
        prompt,
        id=f"custom-provider-{uuid.uuid4().hex[:8]}",
        task_queue="strands-custom-provider",
    )

    print("-" * 50)
    print("Response:")
    print("-" * 50)
    print(result)
    print("-" * 50)
    print()
    print("View workflow in Temporal UI: http://localhost:8233")
    print("Check worker logs for [CustomProvider] log messages.")


if __name__ == "__main__":
    asyncio.run(main())
