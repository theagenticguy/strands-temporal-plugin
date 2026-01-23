"""Weather Agent Client

Connects to Temporal and executes weather agent workflows.

Usage:
    # Make sure the worker is running first, then:
    cd examples/basic_weather_agent
    uv run python run_client.py

    # Or for interactive mode:
    uv run python run_client.py --interactive
"""

import asyncio
import sys
import uuid
from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client
from workflows import FullyDurableWeatherAgent, SimpleAgentWorkflow, StrandsWeatherAgent


async def run_single_query():
    """Run a single weather query."""
    print("Strands Weather Agent Client")
    print("============================")
    print()

    # Connect to Temporal with the plugin
    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )

    # Example query
    query = "What's the weather like in Seattle?"
    print(f"Query: {query}")
    print("Processing with FullyDurableWeatherAgent (full model + tool durability)...")
    print()

    # Execute the workflow using the recommended FullyDurableWeatherAgent
    result = await client.execute_workflow(
        FullyDurableWeatherAgent.run,
        query,
        id=f"fully-durable-agent-{uuid.uuid4().hex[:8]}",
        task_queue="strands-agents",
    )

    print(f"Response: {result}")


async def run_interactive():
    """Run in interactive mode."""
    print("Strands Weather Agent - Interactive Mode")
    print("========================================")
    print()

    # Connect to Temporal
    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )

    print("Connected to Temporal!")
    print("Type weather questions or 'exit' to quit.")
    print()
    print("Prefixes:")
    print("  (default)  - Use FullyDurableWeatherAgent (RECOMMENDED: full durability)")
    print("  model:     - Use StrandsWeatherAgent (model-only durability)")
    print("  simple:    - Use SimpleAgentWorkflow (no tools)")
    print()
    print("Examples:")
    print("  What's the weather in Seattle?")
    print("  model: How's the weather in Tokyo?")
    print("  simple: What is the capital of France?")
    print()

    while True:
        try:
            user_input = input("> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "q"]:
                break

            # Check which workflow to use
            if user_input.lower().startswith("simple:"):
                prompt = user_input[7:].strip()
                workflow = SimpleAgentWorkflow
                workflow_name = "SimpleAgentWorkflow"
            elif user_input.lower().startswith("model:"):
                prompt = user_input[6:].strip()
                workflow = StrandsWeatherAgent
                workflow_name = "StrandsWeatherAgent (model-only)"
            else:
                prompt = user_input
                workflow = FullyDurableWeatherAgent
                workflow_name = "FullyDurableWeatherAgent"

            print(f"Running {workflow_name}...")

            # Execute the workflow
            result = await client.execute_workflow(
                workflow.run,
                prompt,
                id=f"agent-{uuid.uuid4().hex[:8]}",
                task_queue="strands-agents",
            )

            print(f"\nAgent: {result}\n")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}\n")

    print("Goodbye!")


async def main():
    """Entry point."""
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        await run_interactive()
    else:
        await run_single_query()


if __name__ == "__main__":
    asyncio.run(main())
