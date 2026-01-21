"""MCP Agent Workflow using DurableAgent Pattern

This example demonstrates how to create a Temporal workflow that uses
MCP (Model Context Protocol) servers for tool access.

Key concepts:
1. MCP servers are configured via MCPServerConfig types
2. Tools are discovered dynamically from MCP servers at runtime
3. Tool calls are routed to MCP activities for execution
4. All state is serializable through Pydantic models

MCP Transport Types:
- StdioMCPServerConfig: For local MCP servers via stdin/stdout
- StreamableHTTPMCPServerConfig: For remote MCP servers via HTTP

Example with AWS Documentation MCP Server:
    The AWS Documentation MCP Server provides tools for searching
    AWS documentation. Install it with:
        uvx awslabs.aws-documentation-mcp-server@latest

    Then run this workflow to ask questions about AWS services.
"""

import logging
from strands_temporal_plugin import BedrockProviderConfig, DurableAgent, DurableAgentConfig, StdioMCPServerConfig
from temporalio import workflow


# Configure logging
logging.getLogger("strands").setLevel(logging.DEBUG)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()],
)


@workflow.defn
class MCPAgentWorkflow:
    """MCP-powered agent workflow using the DurableAgent pattern.

    This workflow demonstrates the proper way to run AI agents with MCP tools
    within Temporal for full durability guarantees.

    The DurableAgent:
    - Discovers tools from MCP servers at runtime (via activity)
    - Routes tool calls to MCP servers (via activity)
    - Keeps all state serializable in the workflow
    - Orchestrates the agent loop deterministically

    Example usage:
        # Start the workflow
        result = await client.execute_workflow(
            MCPAgentWorkflow.run,
            "What is Amazon Bedrock?",
            id="mcp-agent-1",
            task_queue="strands-agents",
        )
    """

    @workflow.run
    async def run(self, prompt: str) -> str:
        """Run the MCP agent with durable execution.

        Args:
            prompt: User's question

        Returns:
            Agent's response
        """
        # Create the agent configuration with MCP servers
        config = DurableAgentConfig(
            # Model provider configuration
            provider_config=BedrockProviderConfig(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                max_tokens=4096,
            ),
            # System prompt for the agent
            system_prompt=(
                "You are a helpful AWS documentation assistant. "
                "You can search AWS documentation to answer questions about AWS services. "
                "Always use your tools to find accurate information before responding. "
                "Cite the documentation when providing answers."
            ),
            # MCP server configurations
            # Tools will be discovered from these servers at runtime
            mcp_servers=[
                StdioMCPServerConfig(
                    server_id="aws-docs",
                    command="uvx",
                    args=["awslabs.aws-documentation-mcp-server@latest"],
                    tool_prefix="docs",  # Tools will be prefixed: docs_search, etc.
                    startup_timeout=60.0,  # MCP servers can take time to start
                ),
            ],
            # Activity timeout configuration
            model_activity_timeout=300.0,  # 5 minutes for model calls
            mcp_activity_timeout=120.0,  # 2 minutes for MCP operations
            # Retry configuration
            max_retries=3,
            initial_retry_interval_seconds=1.0,
            backoff_coefficient=2.0,
        )

        # Create the DurableAgent
        agent = DurableAgent(config)

        # Invoke the agent - this orchestrates the full agent loop
        # 1. Discovers tools from MCP servers (via activity)
        # 2. Sends prompt to model (via activity)
        # 3. If model requests tool use, executes tools via MCP (via activity)
        # 4. Sends tool results back to model (via activity)
        # 5. Repeats until model returns final response
        result = await agent.invoke(prompt)

        # Return the final text response
        return result.text


@workflow.defn
class MultiMCPAgentWorkflow:
    """Agent workflow with multiple MCP servers.

    This demonstrates how to configure an agent with multiple
    MCP servers, each providing different tools.
    """

    @workflow.run
    async def run(self, prompt: str) -> str:
        """Run agent with multiple MCP servers.

        Args:
            prompt: User's question

        Returns:
            Agent's response
        """
        config = DurableAgentConfig(
            provider_config=BedrockProviderConfig(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            ),
            system_prompt=(
                "You are a helpful assistant with access to multiple tools. "
                "Use the appropriate tools to answer questions accurately."
            ),
            mcp_servers=[
                # AWS Documentation MCP Server
                StdioMCPServerConfig(
                    server_id="aws-docs",
                    command="uvx",
                    args=["awslabs.aws-documentation-mcp-server@latest"],
                    tool_prefix="docs",
                ),
                # You can add more MCP servers here:
                # StdioMCPServerConfig(
                #     server_id="code-analyzer",
                #     command="uvx",
                #     args=["some-code-analyzer-mcp@latest"],
                #     tool_prefix="code",
                # ),
            ],
        )

        agent = DurableAgent(config)
        result = await agent.invoke(prompt)
        return result.text
