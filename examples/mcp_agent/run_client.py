"""Run the MCP Agent Workflow Client.

This script starts a workflow execution that uses MCP tools
to answer questions. It connects to the Temporal server and
executes the MCPAgentWorkflow with a user prompt.

Prerequisites:
    1. Temporal server running: temporal server start-dev
    2. Worker running: uv run python run_worker.py
    3. AWS credentials configured (for Bedrock)

Usage:
    uv run python run_client.py
    uv run python run_client.py "What is Amazon S3?"
"""

import asyncio
import sys
import uuid
from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client
from workflows import MCPAgentWorkflow


async def main():
    """Execute the MCP agent workflow."""
    # Get prompt from command line or use default
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    else:
        prompt = "What is Amazon Bedrock and how does it work?"

    print("Executing MCP Agent Workflow")
    print(f"Query: {prompt}")
    print("-" * 60)

    # Connect to Temporal with the plugin
    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )

    # Generate a unique workflow ID
    workflow_id = f"mcp-agent-{uuid.uuid4().hex[:8]}"

    try:
        # Execute the workflow
        result = await client.execute_workflow(
            MCPAgentWorkflow.run,
            prompt,
            id=workflow_id,
            task_queue="strands-agents",
        )

        print("Response:")
        print(result)
        print("-" * 60)
        print("Workflow completed successfully!")
        print(f"View in Temporal UI: http://localhost:8233/namespaces/default/workflows/{workflow_id}")

    except Exception as e:
        print(f"Workflow failed: {e}")
        print(f"Check Temporal UI for details: http://localhost:8233/namespaces/default/workflows/{workflow_id}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
