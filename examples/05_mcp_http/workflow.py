"""MCP HTTP Workflows - Remote MCP Server Integration

This example demonstrates using remote HTTP-based MCP servers instead of
local stdio-based servers.

HTTP MCP servers are ideal for:
- Cloud-hosted MCP services
- Enterprise MCP gateways
- Shared MCP infrastructure
- Production deployments

Key Differences from stdio MCP:
- stdio: Spawns local process (uvx mcp-server-time)
- HTTP: Makes HTTP requests to remote server (https://knowledge-mcp.global.api.aws)
"""

import logging
from temporalio import workflow

# Import strands with sandbox passthrough
with workflow.unsafe.imports_passed_through():
    from strands import Agent
    from strands_temporal_plugin import (
        BedrockProviderConfig,
        StreamableHTTPMCPServerConfig,
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
    - No need to install MCP server locally
    - Centralized MCP infrastructure
    - Easier authentication and rate limiting
    - Better for production deployments

    Example usage:
        result = await client.execute_workflow(
            HTTPMCPWorkflow.run,
            args=[
                "Tell me about AWS Lambda",                    # prompt
                "https://knowledge-mcp.global.api.aws",        # mcp_url
                {},                                            # mcp_headers
            ],
            id="mcp-http-1",
            task_queue="strands-mcp-http",
        )
    """

    @workflow.run
    async def run(
        self,
        prompt: str,
        mcp_url: str,
        mcp_headers: dict[str, str] | None = None,
    ) -> str:
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

    The AWS Knowledge MCP server provides tools for searching AWS documentation,
    best practices, and service information.

    This is a convenience workflow with the server pre-configured.
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
