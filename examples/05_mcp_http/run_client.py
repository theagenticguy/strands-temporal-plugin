#!/usr/bin/env python3
"""MCP HTTP Client

Demonstrates using remote HTTP-based MCP servers.

Prerequisites:
    1. Temporal server running: temporal server start-dev
    2. Worker running: python run_worker.py

Usage:
    cd examples/05_mcp_http

    # Use AWS Knowledge MCP (pre-configured)
    uv run python run_client.py

    # Use custom HTTP MCP server
    uv run python run_client.py --url "https://your-mcp-server.com"
"""

import argparse
import asyncio
import uuid

from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client
from workflow import AWSKnowledgeMCPWorkflow, HTTPMCPWorkflow


async def run_aws_example(client: Client, prompt: str):
    """Run example with AWS Knowledge MCP server."""
    print("Running AWSKnowledgeMCPWorkflow...")
    print(f"Prompt: {prompt}")
    print()

    result = await client.execute_workflow(
        AWSKnowledgeMCPWorkflow.run,
        prompt,
        id=f"mcp-http-aws-{uuid.uuid4().hex[:8]}",
        task_queue="strands-mcp-http",
    )

    return result


async def run_generic_example(client: Client, prompt: str, mcp_url: str):
    """Run example with generic HTTP MCP server."""
    print("Running HTTPMCPWorkflow...")
    print(f"URL: {mcp_url}")
    print(f"Prompt: {prompt}")
    print()

    result = await client.execute_workflow(
        HTTPMCPWorkflow.run,
        args=[
            prompt,
            mcp_url,
            {},  # headers
        ],
        id=f"mcp-http-generic-{uuid.uuid4().hex[:8]}",
        task_queue="strands-mcp-http",
    )

    return result


async def main():
    """Execute the MCP HTTP examples."""
    parser = argparse.ArgumentParser(
        description="Run MCP HTTP workflow examples",
    )
    parser.add_argument(
        "--url",
        type=str,
        help="Custom MCP server URL (uses generic HTTPMCPWorkflow)",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="What is Amazon S3 and what are its key features?",
        help="Custom prompt",
    )

    args = parser.parse_args()

    print()
    print("=" * 50)
    print("  MCP HTTP Client")
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
        if args.url:
            result = await run_generic_example(client, args.prompt, args.url)
        else:
            result = await run_aws_example(client, args.prompt)

        print("-" * 50)
        print("Response:")
        print("-" * 50)
        print(result)
        print("-" * 50)

    except Exception as e:
        print(f"Error: {e}")
        print()
        print("Troubleshooting:")
        print("1. Check network connectivity to the MCP server")
        print("2. Make sure the worker is running:")
        print("   uv run python run_worker.py")
        print("3. Check Temporal server is running")

    print()
    print("View workflow in Temporal UI: http://localhost:8233")


if __name__ == "__main__":
    asyncio.run(main())
