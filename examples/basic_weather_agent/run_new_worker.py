"""Clean Strands Weather Worker

Following the OpenAI Agents pattern for simple worker setup.
"""

import asyncio
from temporalio.client import Client
from temporalio.worker import Worker
from strands_temporal_plugin import StrandsTemporalPlugin
from weather_workflow import StrandsWeatherAgent


async def main():
    """Set up and run the clean Strands worker."""
    print("Clean Strands Weather Worker")
    print("===========================")

    # Setup client with plugin (identical to OpenAI pattern)
    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )

    # Create worker with workflows - plugin handles everything else
    worker = Worker(
        client,
        task_queue="strands-agents",
        workflows=[StrandsWeatherAgent],
    )

    print("Worker starting...")
    print("Task queue: strands-agents")
    print("Workflows: [StrandsWeatherAgent]")
    print("Plugin automatically handles:")
    print("  - Agent execution activity registration")
    print("  - Strands Agent runtime overrides")
    print("  - Pydantic serialization for Strands types")
    print("  - Sandbox restrictions for Strands imports")
    print("\nPress Ctrl+C to stop")

    try:
        # Run the worker - plugin automatically activates overrides
        await worker.run()
    except KeyboardInterrupt:
        print("\nShutting down worker...")
    finally:
        print("Worker stopped.")


if __name__ == "__main__":
    asyncio.run(main())
