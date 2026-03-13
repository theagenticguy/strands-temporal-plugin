#!/usr/bin/env python3
"""Multi-Tool Agent Worker

Starts a Temporal worker for comprehensive multi-tool agent examples.

The StrandsTemporalPlugin automatically:
- Registers model execution activities
- Registers tool execution activities
- Configures Pydantic serialization
- Sets up sandbox restrictions for Strands imports

Usage:
    # Start Temporal server first:
    temporal server start-dev

    # Then run this worker:
    cd examples/03_multi_tool_agent
    uv run python run_worker.py
"""

import asyncio
import sys
from pathlib import Path

# Add the example directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client
from temporalio.worker import Worker

from workflows import (
    ConversationalAssistant,
    FinanceAssistant,
    GeneralAssistant,
    NotificationAgent,
    PerToolConfigAssistant,
    ResearchAssistant,
    WeatherAssistant,
)


async def main():
    """Set up and run the durable agent worker."""
    print()
    print("=" * 60)
    print("  Multi-Tool Agent Worker")
    print("=" * 60)
    print()

    # Connect to Temporal with the plugin
    # The plugin configures Pydantic serialization for all types
    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )
    print("[OK] Connected to Temporal server at localhost:7233")

    # Create the worker with all example workflows
    worker = Worker(
        client,
        task_queue="durable-agents",
        workflows=[
            WeatherAssistant,
            ResearchAssistant,
            NotificationAgent,
            FinanceAssistant,
            GeneralAssistant,
            ConversationalAssistant,
            PerToolConfigAssistant,
        ],
        # Note: Activities are auto-registered by StrandsTemporalPlugin
    )

    print("[OK] Worker configured")
    print()
    print("Available Workflows:")
    print("  - WeatherAssistant       : Simple weather queries")
    print("  - ResearchAssistant      : Web search + calculations")
    print("  - NotificationAgent      : User lookup + notifications")
    print("  - FinanceAssistant       : Stock prices + calculations")
    print("  - GeneralAssistant       : All tools combined")
    print("  - ConversationalAssistant: Multi-turn with context")
    print("  - PerToolConfigAssistant : Per-tool timeout/retry config")
    print()
    print("Task Queue: durable-agents")
    print()
    print("The StrandsTemporalPlugin automatically registers:")
    print("  - execute_model_activity  : Handles LLM inference")
    print("  - execute_tool_activity   : Handles tool execution")
    print("  - discover_mcp_tools_activity")
    print("  - execute_mcp_tool_activity")
    print()
    print("-" * 60)
    print("Worker starting... Press Ctrl+C to stop")
    print("-" * 60)
    print()

    try:
        await worker.run()
    except KeyboardInterrupt:
        print()
        print("Shutting down worker...")
    finally:
        print("Worker stopped.")


if __name__ == "__main__":
    asyncio.run(main())
