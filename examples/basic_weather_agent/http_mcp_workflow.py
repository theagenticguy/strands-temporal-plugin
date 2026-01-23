"""HTTP MCP Server Workflow Example

This example demonstrates using remote HTTP-based MCP servers instead of
local stdio-based servers. HTTP MCP servers are ideal for:
- Cloud-hosted MCP services
- Enterprise MCP gateways
- Shared MCP infrastructure

Key Differences from stdio MCP:
- stdio: Spawns local process (uvx mcp-server-time)
- HTTP: Makes HTTP requests to remote server (https://knowledge-mcp.global.api.aws)

Usage:
    # Start Temporal server first:
    temporal server start-dev

    # Run the worker (from examples/basic_weather_agent):
    uv run python run_worker.py

    # Run this example:
    uv run python http_mcp_workflow.py
"""

import asyncio
import logging
import uuid
from temporalio import workflow
from temporalio.client import Client


# Import strands with sandbox passthrough
with workflow.unsafe.imports_passed_through():
    from strands import Agent
    from strands_temporal_plugin import (
        BedrockProviderConfig,
        StreamableHTTPMCPServerConfig,
        StrandsTemporalPlugin,
        TemporalModelStub,
        TemporalToolExecutor,
    )


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@workflow.defn
class HTTPMCPWorkflow:
    """Workflow demonstrating HTTP-based MCP server integration.

    This workflow shows how to use remote MCP servers accessed via HTTP
    instead of spawning local processes via stdio.

    Benefits of HTTP MCP:
    - No need to install MCP server locally (no uvx/npx)
    - Centralized MCP infrastructure
    - Easier authentication and rate limiting
    - Better for production deployments
    """

    @workflow.run
    async def run(self, prompt: str, mcp_url: str, mcp_headers: dict[str, str] | None = None) -> str:
        """Run with HTTP-based MCP server.

        Args:
            prompt: User's question
            mcp_url: URL of the HTTP MCP server
            mcp_headers: Optional HTTP headers (e.g., for authentication)

        Returns:
            Agent's response
        """
        logger.info(f"Starting HTTP MCP workflow with URL: {mcp_url}")

        # Create tool executor with HTTP MCP server configuration
        tool_executor = TemporalToolExecutor(
            mcp_servers=[
                StreamableHTTPMCPServerConfig(
                    server_id="http-mcp-server",
                    url=mcp_url,
                    headers=mcp_headers or {},
                ),
            ],
            activity_timeout=120.0,
        )

        # Discover tools from HTTP MCP server via Temporal activity
        logger.info("Discovering tools from HTTP MCP server...")
        mcp_tools = await tool_executor.discover_mcp_tools()
        logger.info(f"Discovered {len(mcp_tools)} tools from HTTP MCP server")

        for tool in mcp_tools:
            logger.info(f"  - {tool.name}: {tool.description}")

        # Create agent with discovered HTTP MCP tools
        agent = Agent(
            model=TemporalModelStub(
                BedrockProviderConfig(
                    model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                    max_tokens=4096,
                ),
                activity_timeout=300.0,
            ),
            tool_executor=tool_executor,
            tools=tool_executor.get_mcp_tools(),
            system_prompt=(
                "You are a helpful assistant with access to MCP tools. "
                "Use the available tools to help answer the user's questions."
            ),
        )

        # Execute with full durability
        logger.info("Executing agent...")
        result = await agent.invoke_async(prompt)

        return str(result)


@workflow.defn
class AWSKnowledgeMCPWorkflow:
    """Pre-configured workflow for AWS Knowledge MCP server.

    This is a convenience workflow with AWS Knowledge MCP server pre-configured.
    The AWS Knowledge MCP server provides tools for searching AWS documentation,
    best practices, and service information.
    """

    @workflow.run
    async def run(self, prompt: str) -> str:
        """Run with AWS Knowledge MCP server.

        Args:
            prompt: User's AWS-related question

        Returns:
            Agent's response with AWS documentation context
        """
        # Pre-configured AWS Knowledge MCP server
        tool_executor = TemporalToolExecutor(
            mcp_servers=[
                StreamableHTTPMCPServerConfig(
                    server_id="aws-knowledge-mcp",
                    url="https://knowledge-mcp.global.api.aws",
                    headers={},  # Public endpoint, no auth needed
                ),
            ],
            activity_timeout=120.0,
        )

        # Discover tools
        logger.info("Discovering AWS Knowledge MCP tools...")
        await tool_executor.discover_mcp_tools()

        # Create agent
        agent = Agent(
            model=TemporalModelStub(
                BedrockProviderConfig(
                    model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                    max_tokens=4096,
                )
            ),
            tool_executor=tool_executor,
            tools=tool_executor.get_mcp_tools(),
            system_prompt=(
                "You are an AWS expert assistant with access to AWS documentation and knowledge. "
                "Use the AWS Knowledge tools to provide accurate, up-to-date information about "
                "AWS services, best practices, and troubleshooting guidance."
            ),
        )

        result = await agent.invoke_async(prompt)
        return str(result)


async def run_http_mcp_example():
    """Run the HTTP MCP workflow example."""
    print("HTTP MCP Server Workflow Example")
    print("=================================")
    print()
    print("This example demonstrates using remote HTTP-based MCP servers.")
    print()

    # Connect to Temporal
    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )

    print("NOTE: This demo uses the AWS Knowledge HTTP MCP server.")
    print("URL: https://knowledge-mcp.global.api.aws")
    print()

    # Try with AWS Knowledge MCP server
    try:
        print("Attempting to run with AWS Knowledge HTTP MCP server...")
        print()

        result = await client.execute_workflow(
            AWSKnowledgeMCPWorkflow.run,
            "What is Amazon S3 and what are its key features?",
            id=f"http-mcp-aws-{uuid.uuid4().hex[:8]}",
            task_queue="strands-agents",
        )

        print(f"Result: {result}")

    except Exception as e:
        print(f"Error: {e}")
        print()
        print("Troubleshooting:")
        print("1. Check if the AWS Knowledge MCP server is accessible")
        print("2. Verify network connectivity to https://knowledge-mcp.global.api.aws")
        print("3. Make sure the worker is running: uv run python run_worker.py")


async def run_generic_http_mcp():
    """Run with a generic HTTP MCP server (with custom configuration)."""
    print("Generic HTTP MCP Server Example")
    print("================================")
    print()

    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )

    # Example with custom HTTP MCP server
    # Replace with your actual MCP server URL
    mcp_url = "https://knowledge-mcp.global.api.aws"
    mcp_headers = {}  # Add authentication headers if needed

    print(f"Using HTTP MCP server: {mcp_url}")
    print()

    try:
        result = await client.execute_workflow(
            HTTPMCPWorkflow.run,
            args=[
                "Tell me about AWS Lambda",  # prompt
                mcp_url,  # mcp_url
                mcp_headers,  # mcp_headers
            ],
            id=f"http-mcp-generic-{uuid.uuid4().hex[:8]}",
            task_queue="strands-agents",
        )

        print(f"Result: {result}")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--generic":
        asyncio.run(run_generic_http_mcp())
    else:
        asyncio.run(run_http_mcp_example())
