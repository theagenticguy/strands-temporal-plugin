"""Run the MCP Agent Temporal Worker.

This script starts a Temporal worker that can execute MCP agent workflows.
The worker uses the StrandsTemporalPlugin which automatically registers
the necessary activities for model and MCP tool execution.

Prerequisites:
    1. Temporal server running: temporal server start-dev
    2. AWS credentials configured (for Bedrock)
    3. uvx available for running MCP servers

Usage:
    uv run python run_worker.py
"""

import asyncio
import logging
from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client
from temporalio.worker import Worker
from workflows import MCPAgentWorkflow, MultiMCPAgentWorkflow


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(name)s | %(message)s",
)

# Debug logging for Strands and MCP
logging.getLogger("strands").setLevel(logging.DEBUG)


async def main():
    """Run the MCP agent worker."""
    print("Starting MCP Agent Worker...")

    # Connect to Temporal with the plugin
    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )

    print("Connected to Temporal server")
    print("Registering workflows: MCPAgentWorkflow, MultiMCPAgentWorkflow")
    print("Activities registered automatically by StrandsTemporalPlugin:")
    print("  - execute_model_activity")
    print("  - execute_tool_activity")
    print("  - list_mcp_tools_activity")
    print("  - execute_mcp_tool_activity")

    # Create and run the worker
    worker = Worker(
        client,
        task_queue="strands-agents",
        workflows=[MCPAgentWorkflow, MultiMCPAgentWorkflow],
        # Note: Activities are auto-registered by the plugin
    )

    print("Worker listening on task queue: strands-agents")
    print("Ready to process MCP agent workflows!")
    print("Press Ctrl+C to stop...")

    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
