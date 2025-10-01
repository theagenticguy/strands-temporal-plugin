"""Clean Strands Weather Client

Following the OpenAI Agents pattern for simple client execution.
"""

import asyncio
from temporalio.client import Client
from strands_temporal_plugin import StrandsTemporalPlugin
from weather_workflow import StrandsWeatherAgent


async def main():
    """Run the clean weather agent client."""
    print("Clean Strands Weather Agent Client")
    print("==================================")

    # Setup client with plugin (same as OpenAI pattern)
    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )

    # Test single query
    query = "What's the weather like in Miami?"
    print(f"Query: {query}")
    print("Processing...")

    # Execute the workflow - it will create Agent() inside and route to activities
    result = await client.execute_workflow(
        StrandsWeatherAgent.run,
        query,
        id="weather-clean-test",
        task_queue="strands-agents",
    )

    print(f"\nResponse: {result}")


async def interactive_mode():
    """Interactive mode for testing."""
    print("Clean Strands Weather Agent - Interactive Mode")
    print("===========================================")

    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )

    print("Connected! Type weather questions or 'exit' to quit.")
    print("Example: 'What's the weather in Seattle?'")

    while True:
        try:
            user_input = input("\n> ").strip()

            if user_input.lower() in ["exit", "quit"]:
                break

            if not user_input:
                continue

            print("Processing...")

            # Execute workflow
            result = await client.execute_workflow(
                StrandsWeatherAgent.run,
                user_input,
                id=f"weather-interactive-{hash(user_input)}",
                task_queue="strands-agents",
            )

            print(f"Weather Agent: {result}")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")

    print("Goodbye!")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        asyncio.run(interactive_mode())
    else:
        asyncio.run(main())
