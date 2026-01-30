#!/usr/bin/env python3
"""MCP Stdio Client

Demonstrates using MCP servers that run as local processes.

Prerequisites:
    1. Temporal server running: temporal server start-dev
    2. Worker running: python run_worker.py
    3. MCP server installed (e.g., uvx mcp-server-time)

Usage:
    cd examples/04_mcp_stdio

    # Use time MCP server
    uv run python run_client.py

    # Use filesystem MCP server
    uv run python run_client.py --simple
"""

import argparse
import asyncio
import uuid

from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client
from workflow import MCPDiscoveryWorkflow, SimpleMCPWorkflow


async def run_time_example(client: Client):
    """Run example with mcp-server-time."""
    print("Running MCPDiscoveryWorkflow with mcp-server-time...")
    print()

    result = await client.execute_workflow(
        MCPDiscoveryWorkflow.run,
        args=[
            "What time is it in Tokyo, Japan?",  # prompt
            "uvx",  # server_command
            ["mcp-server-time"],  # server_args
        ],
        id=f"mcp-stdio-time-{uuid.uuid4().hex[:8]}",
        task_queue="strands-mcp-stdio",
    )

    return result


async def run_simple_example(client: Client):
    """Run example with pre-configured filesystem server."""
    print("Running SimpleMCPWorkflow with mcp-server-filesystem...")
    print()

    result = await client.execute_workflow(
        SimpleMCPWorkflow.run,
        "List the files in /tmp",
        id=f"mcp-stdio-simple-{uuid.uuid4().hex[:8]}",
        task_queue="strands-mcp-stdio",
    )

    return result


async def main():
    """Execute the MCP stdio examples."""
    parser = argparse.ArgumentParser(
        description="Run MCP stdio workflow examples",
    )
    parser.add_argument(
        "--simple",
        action="store_true",
        help="Use SimpleMCPWorkflow instead of MCPDiscoveryWorkflow",
    )

    args = parser.parse_args()

    print()
    print("=" * 50)
    print("  MCP Stdio Client")
    print("=" * 50)
    print()

    # Connect to Temporal
    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )
    print("[OK] Connected to Temporal")
    print()

    try:
        if args.simple:
            result = await run_simple_example(client)
        else:
            result = await run_time_example(client)

        print("-" * 50)
        print("Response:")
        print("-" * 50)
        print(result)
        print("-" * 50)

    except Exception as e:
        print(f"Error: {e}")
        print()
        print("Troubleshooting:")
        print("1. Make sure the MCP server is installed:")
        print("   uvx mcp-server-time --help")
        print("2. Make sure the worker is running:")
        print("   uv run python run_worker.py")
        print("3. Check Temporal server is running")

    print()
    print("View workflow in Temporal UI: http://localhost:8233")


if __name__ == "__main__":
    asyncio.run(main())
