"""Temporal Tool Executor for Strands Agents

This module provides TemporalToolExecutor, a custom ToolExecutor that routes
tool execution to Temporal activities for durable execution.

The key insight is that Strands Agent's event loop calls tool_executor._execute()
for tool execution. By replacing the executor with TemporalToolExecutor, we get
automatic durability for all tool calls while preserving the full Strands Agent loop.

Usage:
    from strands import Agent
    from strands_temporal_plugin import (
        TemporalModelStub,
        TemporalToolExecutor,
        BedrockProviderConfig,
    )

    @workflow.defn
    class MyWorkflow:
        @workflow.run
        async def run(self, prompt: str) -> str:
            tool_executor = TemporalToolExecutor(
                tool_modules={"get_weather": "myapp.tools"},
            )

            agent = Agent(
                model=TemporalModelStub(BedrockProviderConfig(model_id="...")),
                tool_executor=tool_executor,
                tools=[get_weather],
                system_prompt="You are helpful.",
            )
            result = await agent.invoke_async(prompt)
            return str(result)

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                        WORKFLOW CONTEXT                          │
    │                                                                  │
    │   Strands Agent Event Loop                                       │
    │        │                                                         │
    │        ▼                                                         │
    │   ┌──────────────────────────────────────────────────────────┐  │
    │   │              TemporalToolExecutor._execute()              │  │
    │   │                                                           │  │
    │   │   for tool_use in tool_uses:                              │  │
    │   │       if is_mcp_tool(tool_use):                           │  │
    │   │           → execute_mcp_tool_activity()                   │  │
    │   │       else:                                               │  │
    │   │           → execute_tool_activity()                       │  │
    │   │       yield ToolResultEvent                               │  │
    │   └──────────────────────────────────────────────────────────┘  │
    │                                    │                             │
    └────────────────────────────────────│─────────────────────────────┘
                                         │
                                         ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                       ACTIVITY CONTEXT                           │
    │                                                                  │
    │   execute_tool_activity() / execute_mcp_tool_activity()         │
    │   - Loads tool function dynamically                              │
    │   - OR calls MCP server                                          │
    │   - Returns ToolResult                                           │
    └─────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import logging
from .activities import execute_tool_activity
from .mcp_activities import (
    execute_mcp_tool_activity,
    get_mcp_server_for_tool,
    list_mcp_tools_activity,
    mcp_tool_specs_to_strands,
)
from .types import (
    MCPListToolsInput,
    MCPListToolsResult,
    MCPServerConfig,
    MCPToolExecutionInput,
    MCPToolExecutionResult,
    MCPToolSpec,
    ToolExecutionInput,
    ToolExecutionResult,
)
from collections.abc import AsyncGenerator
from datetime import timedelta

# Import TypedEvent for proper event yielding
# This import is safe in workflow context due to sandbox passthrough
from strands.types._events import ToolResultEvent, TypedEvent
from temporalio import workflow
from temporalio.common import RetryPolicy
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from strands import Agent
    from strands.types.tools import ToolResult, ToolUse


logger = logging.getLogger(__name__)


def _create_mcp_proxy_tool(mcp_spec: MCPToolSpec) -> Any:
    """Create a proxy tool function for an MCP tool.

    The proxy function has the correct signature and tool_spec for the Agent
    to register, but its execution is handled by TemporalToolExecutor._execute().

    Args:
        mcp_spec: MCP tool specification

    Returns:
        A decorated tool function that acts as a proxy
    """
    from strands import tool

    # Create a proxy function that will never be called directly
    # (TemporalToolExecutor._execute handles the actual execution)
    async def proxy_impl(**kwargs: Any) -> str:  # noqa: ARG001
        # This should never be called - TemporalToolExecutor intercepts it
        raise RuntimeError(
            f"MCP tool '{mcp_spec.name}' should be executed via TemporalToolExecutor, "
            "not called directly. Ensure you're using TemporalToolExecutor as your tool_executor."
        )

    # Set the function name and docstring
    proxy_impl.__name__ = mcp_spec.name
    proxy_impl.__doc__ = mcp_spec.description or f"MCP tool: {mcp_spec.name}"

    # Apply the @tool decorator with explicit inputSchema from MCP
    # This ensures the correct input schema is used (not derived from the proxy function)
    decorated = tool(
        name=mcp_spec.name,
        description=mcp_spec.description or f"MCP tool: {mcp_spec.name}",
        inputSchema={"json": mcp_spec.input_schema},
    )(proxy_impl)

    return decorated


class TemporalToolExecutor:
    """Tool executor that routes tool calls to Temporal activities.

    This class implements the Strands ToolExecutor interface but instead of
    executing tools directly, it routes each tool call to a Temporal activity.
    This provides:

    1. Durability: Tool calls survive workflow restarts
    2. Retries: Failed tool calls are automatically retried
    3. Timeouts: Long-running tools are properly handled
    4. Isolation: Tool execution happens in activity context

    The executor supports both static tools (decorated with @tool) and
    MCP tools (discovered from MCP servers).

    Args:
        tool_modules: Mapping of tool names to module paths for dynamic import
                     Example: {"get_weather": "myapp.tools"}
        mcp_servers: Optional list of MCP server configurations for tool discovery
        activity_timeout: Timeout for tool activity execution (default 60 seconds)
        retry_policy: Custom retry policy for tool activities (optional)

    Example:
        # With static tools only
        executor = TemporalToolExecutor(
            tool_modules={"get_weather": "myapp.tools"},
        )

        # With MCP servers
        executor = TemporalToolExecutor(
            tool_modules={"local_tool": "myapp.tools"},
            mcp_servers=[
                StdioMCPServerConfig(
                    server_id="aws-docs",
                    command="uvx",
                    args=["awslabs.aws-documentation-mcp-server@latest"],
                ),
            ],
        )

        # Discover MCP tools (call from workflow)
        await executor.discover_mcp_tools()

        # Use with Agent
        agent = Agent(
            model=TemporalModelStub(...),
            tool_executor=executor,
            tools=[get_weather] + executor.get_mcp_tools(),
        )
    """

    def __init__(
        self,
        tool_modules: dict[str, str] | None = None,
        mcp_servers: list[MCPServerConfig] | None = None,
        activity_timeout: float = 60.0,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        """Initialize the TemporalToolExecutor.

        Args:
            tool_modules: Mapping of tool names to module paths
            mcp_servers: List of MCP server configurations
            activity_timeout: Timeout in seconds for tool activities
            retry_policy: Optional custom retry policy
        """
        self._tool_modules = tool_modules or {}
        self._mcp_servers = mcp_servers or []
        self._activity_timeout = activity_timeout
        self._retry_policy = retry_policy or RetryPolicy(
            maximum_attempts=3,
            initial_interval=timedelta(seconds=1),
            maximum_interval=timedelta(seconds=30),
            backoff_coefficient=2.0,
        )

        # MCP state (populated by discover_mcp_tools)
        self._mcp_tools: list[MCPToolSpec] = []
        self._mcp_server_configs: dict[str, MCPServerConfig] = {}

    @property
    def tool_modules(self) -> dict[str, str]:
        """Get the tool module mappings."""
        return self._tool_modules.copy()

    @property
    def mcp_tools(self) -> list[MCPToolSpec]:
        """Get the discovered MCP tools."""
        return self._mcp_tools.copy()

    async def discover_mcp_tools(self) -> list[MCPToolSpec]:
        """Discover tools from all configured MCP servers.

        This method must be called from workflow context. It executes
        activities to list tools from each configured MCP server.

        Returns:
            List of discovered MCP tool specifications

        Example:
            @workflow.defn
            class MyWorkflow:
                @workflow.run
                async def run(self, prompt: str) -> str:
                    executor = TemporalToolExecutor(
                        mcp_servers=[StdioMCPServerConfig(...)]
                    )

                    # Discover tools via activity
                    mcp_tools = await executor.discover_mcp_tools()

                    # Use discovered tools
                    agent = Agent(
                        model=TemporalModelStub(...),
                        tool_executor=executor,
                        tools=executor.get_mcp_tools(),
                    )
        """
        logger.info(f"Discovering tools from {len(self._mcp_servers)} MCP server(s)")

        self._mcp_tools = []
        self._mcp_server_configs = {}

        for server_config in self._mcp_servers:
            logger.info(f"Listing tools from MCP server: {server_config.server_id}")

            # Store config for later tool execution
            self._mcp_server_configs[server_config.server_id] = server_config

            activity_input = MCPListToolsInput(server_config=server_config)

            result: MCPListToolsResult = await workflow.execute_activity(
                list_mcp_tools_activity,
                activity_input,
                start_to_close_timeout=timedelta(seconds=self._activity_timeout),
                retry_policy=self._retry_policy,
            )

            logger.info(f"Discovered {len(result.tools)} tools from MCP server: {server_config.server_id}")
            self._mcp_tools.extend(result.tools)

        logger.info(f"Total MCP tools discovered: {len(self._mcp_tools)}")
        return self._mcp_tools

    def get_mcp_tool_specs(self) -> list[dict[str, Any]]:
        """Get MCP tools in Strands ToolSpec format (raw dicts).

        Note: These are raw tool specifications for passing to model calls.
        For use with the standard Strands Agent, use get_mcp_tools() instead
        which returns proxy AgentTool instances.

        Returns:
            List of tool specifications in Strands format
        """
        return mcp_tool_specs_to_strands(self._mcp_tools)

    def get_mcp_tools(self) -> list[Any]:
        """Get MCP tools as proxy AgentTool instances for use with Strands Agent.

        Creates proxy tool functions that can be registered with the Agent.
        The actual execution is handled by TemporalToolExecutor._execute().

        Returns:
            List of proxy tool functions decorated with @tool

        Example:
            executor = TemporalToolExecutor(mcp_servers=[...])
            await executor.discover_mcp_tools()

            agent = Agent(
                model=TemporalModelStub(...),
                tool_executor=executor,
                tools=executor.get_mcp_tools(),  # Proxy tools for Agent
            )
        """
        proxy_tools = []

        for mcp_spec in self._mcp_tools:
            # Create a proxy function for this MCP tool
            # The actual execution is handled by TemporalToolExecutor._execute()
            proxy_fn = _create_mcp_proxy_tool(mcp_spec)
            proxy_tools.append(proxy_fn)

        return proxy_tools

    async def _execute(
        self,
        agent: Agent,
        tool_uses: list[ToolUse],
        tool_results: list[ToolResult],
        cycle_trace: Any,
        cycle_span: Any,
        invocation_state: dict[str, Any],
        structured_output_context: Any | None = None,
    ) -> AsyncGenerator[TypedEvent]:
        """Execute tools via Temporal activities.

        This method is called by the Strands Agent event loop when tools
        need to be executed. It routes each tool call to an appropriate
        Temporal activity.

        For workflows started after the parallel-tool-execution-v1 patch,
        multiple tool calls from a single model response are executed
        concurrently via asyncio.gather(). Older workflows replay with
        sequential execution for compatibility.

        Args:
            agent: The Strands Agent instance
            tool_uses: List of tool use requests from the model
            tool_results: List to accumulate tool results
            cycle_trace: Tracing context (not used in Temporal context)
            cycle_span: OpenTelemetry span (not used in Temporal context)
            invocation_state: Shared state across the invocation
            structured_output_context: Context for structured output

        Yields:
            TypedEvent: Tool result events (ToolResultEvent instances)
        """
        if workflow.patched("parallel-tool-execution-v1"):
            # Parallel: launch all tool activities concurrently
            results = await asyncio.gather(*[self._execute_single_tool(tool_use) for tool_use in tool_uses])
            for result in results:
                tool_result: ToolResult = {
                    "toolUseId": result.tool_use_id,
                    "status": result.status,
                    "content": result.content,
                }
                tool_results.append(tool_result)
                yield ToolResultEvent(tool_result=tool_result)
        else:
            # Sequential: original behavior for replay compatibility with pre-v1 workflows
            for tool_use in tool_uses:
                result = await self._execute_single_tool(tool_use)
                tool_result: ToolResult = {
                    "toolUseId": result.tool_use_id,
                    "status": result.status,
                    "content": result.content,
                }
                tool_results.append(tool_result)
                yield ToolResultEvent(tool_result=tool_result)

    async def _execute_single_tool(self, tool_use: ToolUse) -> ToolExecutionResult:
        """Execute a single tool via the appropriate Temporal activity.

        Routes to either MCP or static tool execution based on tool registration.

        Args:
            tool_use: Tool use request from the model

        Returns:
            ToolExecutionResult with tool output
        """
        tool_name = tool_use["name"]
        tool_input = tool_use.get("input", {})
        tool_use_id = tool_use["toolUseId"]

        logger.info(f"Executing tool via activity: {tool_name}")

        mcp_info = get_mcp_server_for_tool(tool_name, self._mcp_tools)

        if mcp_info is not None:
            server_id, mcp_spec = mcp_info
            return await self._execute_mcp_tool(
                server_id=server_id,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_use_id=tool_use_id,
            )
        else:
            return await self._execute_static_tool(
                tool_name=tool_name,
                tool_input=tool_input,
                tool_use_id=tool_use_id,
            )

    async def _execute_static_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str,
    ) -> ToolExecutionResult:
        """Execute a static (function-based) tool via Temporal activity.

        Args:
            tool_name: Name of the tool to execute
            tool_input: Input parameters for the tool
            tool_use_id: ID for correlation

        Returns:
            ToolExecutionResult with tool output
        """
        tool_module = self._tool_modules.get(tool_name, "")

        if not tool_module:
            logger.warning(
                f"No module path found for tool '{tool_name}'. Registered modules: {list(self._tool_modules.keys())}"
            )
            return ToolExecutionResult(
                tool_use_id=tool_use_id,
                status="error",
                content=[{"text": f"Tool '{tool_name}' not found. Make sure it's registered in tool_modules."}],
            )

        activity_input = ToolExecutionInput(
            tool_name=tool_name,
            tool_module=tool_module,
            tool_input=tool_input,
            tool_use_id=tool_use_id,
        )

        result: ToolExecutionResult = await workflow.execute_activity(
            execute_tool_activity,
            activity_input,
            start_to_close_timeout=timedelta(seconds=self._activity_timeout),
            retry_policy=self._retry_policy,
        )

        return result

    async def _execute_mcp_tool(
        self,
        server_id: str,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str,
    ) -> ToolExecutionResult:
        """Execute an MCP tool via Temporal activity.

        Args:
            server_id: ID of the MCP server that owns the tool
            tool_name: Name of the tool to execute
            tool_input: Input parameters for the tool
            tool_use_id: ID for correlation

        Returns:
            ToolExecutionResult with tool output (converted from MCP format)
        """
        server_config = self._mcp_server_configs.get(server_id)

        if server_config is None:
            return ToolExecutionResult(
                tool_use_id=tool_use_id,
                status="error",
                content=[{"text": f"MCP server '{server_id}' not found"}],
            )

        activity_input = MCPToolExecutionInput(
            server_config=server_config,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_use_id=tool_use_id,
        )

        result: MCPToolExecutionResult = await workflow.execute_activity(
            execute_mcp_tool_activity,
            activity_input,
            start_to_close_timeout=timedelta(seconds=self._activity_timeout),
            retry_policy=self._retry_policy,
        )

        # Convert MCPToolExecutionResult to ToolExecutionResult
        return ToolExecutionResult(
            tool_use_id=result.tool_use_id,
            status=result.status,
            content=result.content,
        )
