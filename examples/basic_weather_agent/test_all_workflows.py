"""Test all workflow examples.

This script runs all the workflow examples sequentially.
"""

import asyncio
import uuid
from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client
from workflows import FullyDurableWeatherAgent, SimpleAgentWorkflow, StrandsWeatherAgent


async def main():
    """Run all workflow examples."""
    print("Testing All Workflows")
    print("=" * 60)
    print()

    # Connect to Temporal
    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )

    # Test 1: FullyDurableWeatherAgent (RECOMMENDED)
    print("1. FullyDurableWeatherAgent (full model + tool durability)")
    print("-" * 60)
    try:
        result = await client.execute_workflow(
            FullyDurableWeatherAgent.run,
            "What's the weather in Seattle?",
            id=f"test-fully-durable-{uuid.uuid4().hex[:8]}",
            task_queue="strands-agents",
        )
        print(f"✓ SUCCESS: {result[:100]}...")
    except Exception as e:
        print(f"✗ FAILED: {e}")
    print()

    # Test 2: StrandsWeatherAgent (model-only durability)
    print("2. StrandsWeatherAgent (model-only durability)")
    print("-" * 60)
    try:
        result = await client.execute_workflow(
            StrandsWeatherAgent.run,
            "How's the weather in Tokyo?",
            id=f"test-strands-{uuid.uuid4().hex[:8]}",
            task_queue="strands-agents",
        )
        print(f"✓ SUCCESS: {result[:100]}...")
    except Exception as e:
        print(f"✗ FAILED: {e}")
    print()

    # Test 3: SimpleAgentWorkflow (no tools)
    print("3. SimpleAgentWorkflow (no tools)")
    print("-" * 60)
    try:
        result = await client.execute_workflow(
            SimpleAgentWorkflow.run,
            "What is the capital of France?",
            id=f"test-simple-{uuid.uuid4().hex[:8]}",
            task_queue="strands-agents",
        )
        print(f"✓ SUCCESS: {result[:100]}...")
    except Exception as e:
        print(f"✗ FAILED: {e}")
    print()

    print("=" * 60)
    print("Basic workflow tests complete!")


if __name__ == "__main__":
    asyncio.run(main())
