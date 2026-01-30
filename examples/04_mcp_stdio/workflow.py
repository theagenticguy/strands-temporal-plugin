"""MCP Stdio Workflows - Local MCP Server Integration

This example demonstrates using MCP (Model Context Protocol) servers
that run as local processes via stdio communication.

Stdio MCP servers are ideal for:
- Local development and testing
- Self-contained MCP tools (mcp-server-time, mcp-server-filesystem)
- When you have the MCP server installed locally

Key concepts:
- StdioMCPServerConfig: Configure local MCP servers
- TemporalToolExecutor: Discovers and executes MCP tools durably
- discover_mcp_tools(): Fetch available tools from MCP server
"""

import logging
from temporalio import workflow

# Import strands with sandbox passthrough
with workflow.unsafe.imports_passed_through():
    from strands import Agent
    from strands_temporal_plugin import (
        BedrockProviderConfig,
        StdioMCPServerConfig,
        TemporalModelStub,
        TemporalToolExecutor,
    )


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@workflow.defn
class MCPDiscoveryWorkflow:
    """Workflow demonstrating MCP tool discovery and execution.

    This workflow shows the full pattern for using stdio MCP tools:
    1. Configure MCP servers (command + args)
    2. Discover tools via activity (durable)
    3. Create agent with discovered tools
    4. Execute with full durability

    Example usage:
        result = await client.execute_workflow(
            MCPDiscoveryWorkflow.run,
            args=[
                "What time is it in Tokyo?",  # prompt
                "uvx",                         # server_command
                ["mcp-server-time"],           # server_args
            ],
            id="mcp-stdio-1",
            task_queue="strands-mcp-stdio",
        )
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
    """Simpler MCP workflow with pre-configured server.

    Use this pattern when you have a fixed MCP server configuration
    and don't need dynamic server selection.

    This example uses the filesystem MCP server to demonstrate
    file operations.
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
            system_prompt="You are a helpful assistant with filesystem access.",
        )

        result = await agent.invoke_async(prompt)
        return str(result)
