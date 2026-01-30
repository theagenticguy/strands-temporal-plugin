#!/usr/bin/env python3
"""MCP Stdio Worker

Starts a Temporal worker for MCP stdio examples.

Usage:
    # Start Temporal server first:
    temporal server start-dev

    # Then run this worker:
    cd examples/04_mcp_stdio
    uv run python run_worker.py
"""

import asyncio

from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client
from temporalio.worker import Worker
from workflow import MCPDiscoveryWorkflow, SimpleMCPWorkflow


async def main():
    """Set up and run the MCP stdio worker."""
    print()
    print("=" * 50)
    print("  MCP Stdio Worker")
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
        task_queue="strands-mcp-stdio",
        workflows=[
            MCPDiscoveryWorkflow,
            SimpleMCPWorkflow,
        ],
        # Activities are auto-registered by StrandsTemporalPlugin
    )

    print("[OK] Worker configured")
    print()
    print("Task Queue: strands-mcp-stdio")
    print("Workflows:")
    print("  - MCPDiscoveryWorkflow : Dynamic MCP server configuration")
    print("  - SimpleMCPWorkflow    : Pre-configured MCP server")
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
