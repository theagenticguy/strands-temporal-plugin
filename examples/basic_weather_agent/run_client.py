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
from workflows import SimpleAgentWorkflow, WeatherAgentWorkflow


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
    print("Processing...")
    print()

    # Execute the workflow
    result = await client.execute_workflow(
        WeatherAgentWorkflow.run,
        query,
        id=f"weather-agent-{uuid.uuid4().hex[:8]}",
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
    print("Type 'simple' followed by a question to use SimpleAgentWorkflow.")
    print()
    print("Examples:")
    print("  What's the weather in Seattle?")
    print("  How's the weather in Tokyo?")
    print("  simple What is the capital of France?")
    print()

    while True:
        try:
            user_input = input("> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "q"]:
                break

            # Check if user wants simple workflow
            if user_input.lower().startswith("simple "):
                prompt = user_input[7:]  # Remove "simple " prefix
                workflow = SimpleAgentWorkflow
                workflow_name = "SimpleAgentWorkflow"
            else:
                prompt = user_input
                workflow = WeatherAgentWorkflow
                workflow_name = "WeatherAgentWorkflow"

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
