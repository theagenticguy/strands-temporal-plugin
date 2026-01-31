#!/usr/bin/env python3
"""MCP HTTP Worker

Starts a Temporal worker for MCP HTTP examples.

Usage:
    # Start Temporal server first:
    temporal server start-dev

    # Then run this worker:
    cd examples/05_mcp_http
    uv run python run_worker.py
"""

import asyncio

from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client
from temporalio.worker import Worker
from workflow import AWSKnowledgeMCPWorkflow, HTTPMCPWorkflow


async def main():
    """Set up and run the MCP HTTP worker."""
    print()
    print("=" * 50)
    print("  MCP HTTP Worker")
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
        task_queue="strands-mcp-http",
        workflows=[
            HTTPMCPWorkflow,
            AWSKnowledgeMCPWorkflow,
        ],
        # Activities are auto-registered by StrandsTemporalPlugin
    )

    print("[OK] Worker configured")
    print()
    print("Task Queue: strands-mcp-http")
    print("Workflows:")
    print("  - HTTPMCPWorkflow        : Generic HTTP MCP server")
    print("  - AWSKnowledgeMCPWorkflow: AWS Knowledge MCP (pre-configured)")
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
