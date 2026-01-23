"""MCP Tool Discovery Workflow Example

This example demonstrates how to use MCP (Model Context Protocol) servers
with the TemporalToolExecutor for durable tool discovery and execution.

The workflow:
1. Discovers tools from MCP servers via Temporal activity
2. Creates a Strands Agent with the discovered tools
3. Executes the agent with full durability

Usage:
    # Start Temporal server first:
    temporal server start-dev

    # Run the worker (from examples/basic_weather_agent):
    uv run python run_worker.py

    # Run this example:
    uv run python mcp_workflow.py
"""

import asyncio
import logging
import uuid
from temporalio import workflow
from temporalio.client import Client
from temporalio.worker import Worker


# Import strands with sandbox passthrough to avoid I/O library restrictions
with workflow.unsafe.imports_passed_through():
    from strands import Agent
    from strands_temporal_plugin import (
        BedrockProviderConfig,
        StdioMCPServerConfig,
        StrandsTemporalPlugin,
        TemporalModelStub,
        TemporalToolExecutor,
    )


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@workflow.defn
class MCPDiscoveryWorkflow:
    """Workflow demonstrating MCP tool discovery and execution.

    This workflow shows the full pattern for using MCP tools:
    1. Configure MCP servers
    2. Discover tools via activity (durable)
    3. Create agent with discovered tools
    4. Execute with full durability

    Note: This example uses a hypothetical MCP server. Replace with
    your actual MCP server configuration.
    """

    @workflow.run
    async def run(self, prompt: str, server_command: str, server_args: list[str]) -> str:
        """Run the MCP discovery workflow.

        Args:
            prompt: User's question
            server_command: MCP server command (e.g., "uvx", "npx")
            server_args: MCP server arguments

        Returns:
            Agent's response
        """
        logger.info(f"Starting MCP workflow with server: {server_command} {server_args}")

        # Create tool executor with MCP server configuration
        tool_executor = TemporalToolExecutor(
            mcp_servers=[
                StdioMCPServerConfig(
                    server_id="mcp-server",
                    command=server_command,
                    args=server_args,
                    startup_timeout=30.0,
                ),
            ],
            activity_timeout=120.0,  # MCP calls may take longer
        )

        # Discover tools from MCP servers via Temporal activity
        # This is durable - if the workflow restarts, discovery results are replayed
        logger.info("Discovering MCP tools...")
        mcp_tools = await tool_executor.discover_mcp_tools()
        logger.info(f"Discovered {len(mcp_tools)} tools from MCP server")

        for tool in mcp_tools:
            logger.info(f"  - {tool.name}: {tool.description}")

        # Create agent with discovered MCP tools
        agent = Agent(
            model=TemporalModelStub(
                BedrockProviderConfig(
                    model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                    max_tokens=4096,
                ),
                activity_timeout=300.0,
            ),
            tool_executor=tool_executor,
            tools=tool_executor.get_mcp_tools(),  # Use discovered MCP tools as proxy AgentTools
            system_prompt=(
                "You are a helpful assistant with access to MCP tools. "
                "Use the available tools to help answer the user's questions."
            ),
        )

        # Execute with full durability
        # Both model calls and MCP tool calls are routed to activities
        logger.info("Executing agent...")
        result = await agent.invoke_async(prompt)

        return str(result)


@workflow.defn
class SimpleMCPWorkflow:
    """Simpler MCP workflow without dynamic server configuration.

    Use this pattern when you have a fixed MCP server configuration.
    """

    @workflow.run
    async def run(self, prompt: str) -> str:
        """Run with pre-configured MCP server.

        Args:
            prompt: User's question

        Returns:
            Agent's response
        """
        # Example: Using a filesystem MCP server
        # Replace with your actual MCP server
        tool_executor = TemporalToolExecutor(
            mcp_servers=[
                StdioMCPServerConfig(
                    server_id="filesystem",
                    command="uvx",
                    args=["mcp-server-filesystem", "/tmp"],  # Example filesystem server
                    startup_timeout=30.0,
                ),
            ],
        )

        # Discover tools
        await tool_executor.discover_mcp_tools()

        # Create and run agent
        agent = Agent(
            model=TemporalModelStub(
                BedrockProviderConfig(
                    model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                )
            ),
            tool_executor=tool_executor,
            tools=tool_executor.get_mcp_tools(),  # Proxy tools for Agent
            system_prompt="You are a helpful assistant.",
        )

        result = await agent.invoke_async(prompt)
        return str(result)


async def run_mcp_example():
    """Run the MCP workflow example."""
    print("MCP Tool Discovery Workflow Example")
    print("====================================")
    print()
    print("This example demonstrates MCP tool discovery with Temporal durability.")
    print()

    # Connect to Temporal
    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )

    # For this demo, we use mcp-server-time which provides time/timezone tools
    # Other MCP servers you could use:
    # - uvx mcp-server-filesystem /path
    # - uvx awslabs.aws-documentation-mcp-server@latest

    print("NOTE: This demo uses the mcp-server-time MCP server.")
    print()

    # Try with time MCP server
    try:
        print("Attempting to run with time MCP server...")
        print()

        result = await client.execute_workflow(
            MCPDiscoveryWorkflow.run,
            args=[
                "What time is it in Tokyo, Japan?",  # prompt
                "uvx",  # server_command
                ["mcp-server-time"],  # server_args
            ],
            id=f"mcp-discovery-{uuid.uuid4().hex[:8]}",
            task_queue="strands-agents",
        )

        print(f"Result: {result}")

    except Exception as e:
        print(f"Error: {e}")
        print()
        print("The MCP server might not be available. To run this example:")
        print("1. Make sure the MCP server works: uvx mcp-server-time --help")
        print("2. Start the worker: uv run python run_worker.py")
        print("3. Run this script again")


async def run_worker_with_mcp():
    """Run a worker that includes MCP workflows."""
    print("Starting worker with MCP workflows...")

    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )

    # Import other workflows
    from workflows import DurableWeatherAgent, FullyDurableWeatherAgent, SimpleAgentWorkflow, StrandsWeatherAgent

    worker = Worker(
        client,
        task_queue="strands-agents",
        workflows=[
            FullyDurableWeatherAgent,
            StrandsWeatherAgent,
            DurableWeatherAgent,
            SimpleAgentWorkflow,
            MCPDiscoveryWorkflow,  # Add MCP workflow
            SimpleMCPWorkflow,
        ],
    )

    print("Worker started with MCP workflows")
    print("Press Ctrl+C to stop")

    await worker.run()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        asyncio.run(run_worker_with_mcp())
    else:
        asyncio.run(run_mcp_example())
