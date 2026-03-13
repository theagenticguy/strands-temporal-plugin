"""MCP Activities for Temporal

Activities for interacting with MCP (Model Context Protocol) servers.
These activities handle:
- Listing available tools from MCP servers
- Executing MCP tool calls

MCP connections are created within activity context where I/O is allowed.
Each activity creates a fresh connection to ensure durability.
"""

from __future__ import annotations

import atexit
import fnmatch
import logging
import threading
from typing import Any

from temporalio import activity
from temporalio.exceptions import ApplicationError

from .types import (
    BaseMCPServerConfig,
    MCPListToolsInput,
    MCPListToolsResult,
    MCPToolExecutionInput,
    MCPToolExecutionResult,
    MCPToolSpec,
    StdioMCPServerConfig,
    StreamableHTTPMCPServerConfig,
)


logger = logging.getLogger(__name__)


# =============================================================================
# Worker-level MCP Client Cache
# =============================================================================
# MCP clients are cached per server_id to avoid restarting server processes
# for every tool call. The cache is thread-safe and cleaned up at exit.

_mcp_client_lock = threading.Lock()
_mcp_clients: dict[str, Any] = {}


def _get_cached_mcp_client(server_config: BaseMCPServerConfig) -> Any:
    """Get or create a cached MCP client for the given server config.

    Clients are cached by server_id and reused across activity executions
    on the same worker. This avoids the overhead of starting a new MCP
    server process for each tool call.

    Args:
        server_config: MCP server configuration

    Returns:
        MCPClient instance (already entered context manager)
    """
    cache_key = server_config.server_id

    with _mcp_client_lock:
        if cache_key in _mcp_clients:
            client = _mcp_clients[cache_key]
            # Verify the client is still usable
            try:
                # If client has a way to check liveness, use it
                if hasattr(client, "_transport") and client._transport is not None:
                    return client
            except Exception:
                pass
            # Client is stale — remove and recreate
            try:
                client.__exit__(None, None, None)
            except Exception:
                pass
            del _mcp_clients[cache_key]

        # Create new client
        client = _create_mcp_client(server_config)
        client.__enter__()
        _mcp_clients[cache_key] = client
        return client


def close_mcp_clients() -> None:
    """Close all cached MCP clients. Call during worker shutdown."""
    with _mcp_client_lock:
        for server_id, client in list(_mcp_clients.items()):
            try:
                client.__exit__(None, None, None)
                logger.info(f"Closed cached MCP client: {server_id}")
            except Exception as e:
                logger.warning(f"Error closing MCP client {server_id}: {e}")
        _mcp_clients.clear()


# Register cleanup for worker shutdown
atexit.register(close_mcp_clients)


def _safe_heartbeat(detail: str) -> None:
    """Send a heartbeat if running in activity context, otherwise no-op."""
    try:
        activity.heartbeat(detail)
    except RuntimeError:
        pass


# =============================================================================
# MCP Client Factory
# =============================================================================


def _create_mcp_client(server_config: BaseMCPServerConfig) -> Any:
    """Create an MCPClient from server configuration.

    Args:
        server_config: MCP server configuration

    Returns:
        Configured MCPClient instance

    Raises:
        ApplicationError: If MCP is not installed or configuration is invalid
    """
    try:
        from strands.tools.mcp import MCPClient
    except ImportError as e:
        raise ApplicationError(
            "MCPClient not available. Ensure strands-agents is installed with MCP support.",
            type="MCPNotAvailable",
            non_retryable=True,
        ) from e

    # Create transport callable based on config type
    transport_callable = _create_transport(server_config)

    # Create and return MCPClient
    # Note: Tool filtering and prefixing are handled separately after listing tools
    return MCPClient(
        transport_callable,
        startup_timeout=int(server_config.startup_timeout),
    )


def _create_transport(server_config: BaseMCPServerConfig) -> Any:
    """Create an MCP transport callable from server configuration.

    Args:
        server_config: MCP server configuration

    Returns:
        Callable that creates the MCP transport

    Raises:
        ApplicationError: If transport type is not supported
    """
    if isinstance(server_config, StdioMCPServerConfig):
        try:
            from mcp import StdioServerParameters, stdio_client
        except ImportError as e:
            raise ApplicationError(
                "MCP stdio client not available. Install the mcp package.",
                type="MCPNotAvailable",
                non_retryable=True,
            ) from e

        def create_stdio_transport():
            params = StdioServerParameters(
                command=server_config.command,
                args=server_config.args,
                env=server_config.env,
            )
            return stdio_client(params)

        return create_stdio_transport

    elif isinstance(server_config, StreamableHTTPMCPServerConfig):
        try:
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError as e:
            raise ApplicationError(
                "MCP streamable HTTP client not available. Install the mcp package.",
                type="MCPNotAvailable",
                non_retryable=True,
            ) from e

        def create_http_transport():
            return streamablehttp_client(
                url=server_config.url,
                headers=server_config.headers if server_config.headers else None,
            )

        return create_http_transport

    else:
        raise ApplicationError(
            f"Unsupported MCP transport type: {server_config.transport}",
            type="UnsupportedTransport",
            non_retryable=True,
        )


def _filter_tools(tools: list[Any], server_config: BaseMCPServerConfig) -> list[Any]:
    """Apply tool filtering based on allowed/rejected patterns.

    Note: MCPClient should already handle this, but we add an extra layer
    for safety and to support additional filtering logic.

    Args:
        tools: List of MCP tools
        server_config: Server configuration with filter patterns

    Returns:
        Filtered list of tools
    """
    filtered = tools

    # Apply allowed filter (whitelist)
    if server_config.allowed_tools:
        filtered = [
            t for t in filtered if any(fnmatch.fnmatch(t.tool_name, pattern) for pattern in server_config.allowed_tools)
        ]

    # Apply rejected filter (blacklist)
    if server_config.rejected_tools:
        filtered = [
            t
            for t in filtered
            if not any(fnmatch.fnmatch(t.tool_name, pattern) for pattern in server_config.rejected_tools)
        ]

    return filtered


def _convert_mcp_tool_to_spec(tool: Any, server_id: str, tool_prefix: str | None = None) -> MCPToolSpec:
    """Convert an MCPAgentTool to a serializable MCPToolSpec.

    Args:
        tool: MCPAgentTool from Strands
        server_id: Server ID for routing
        tool_prefix: Optional prefix to add to tool names

    Returns:
        Serializable MCPToolSpec
    """
    # Get the tool spec from the MCPAgentTool
    spec = tool.tool_spec
    raw_name = spec.get("name", tool.tool_name)

    # Apply tool prefix if specified
    if tool_prefix:
        name = f"{tool_prefix}_{raw_name}"
    else:
        name = raw_name

    return MCPToolSpec(
        name=name,
        description=spec.get("description"),
        input_schema=spec.get("inputSchema", {}).get("json", {}),
        output_schema=spec.get("outputSchema", {}).get("json") if spec.get("outputSchema") else None,
        server_id=server_id,
    )


def _convert_mcp_tool_spec_to_strands(mcp_spec: MCPToolSpec) -> dict[str, Any]:
    """Convert MCPToolSpec to Strands ToolSpec format for model calls.

    Args:
        mcp_spec: MCPToolSpec from list_mcp_tools_activity

    Returns:
        Dict in Strands ToolSpec format (compatible with Bedrock Converse API)
    """
    result: dict[str, Any] = {
        "name": mcp_spec.name,
        "description": mcp_spec.description or "",
        "inputSchema": {
            "json": mcp_spec.input_schema,
        },
    }

    if mcp_spec.output_schema:
        result["outputSchema"] = {
            "json": mcp_spec.output_schema,
        }

    return result


# =============================================================================
# MCP List Tools Activity
# =============================================================================


@activity.defn
async def list_mcp_tools_activity(input_data: MCPListToolsInput) -> MCPListToolsResult:
    """List available tools from an MCP server.

    This activity:
    1. Creates an MCPClient with the specified configuration
    2. Connects to the MCP server
    3. Lists available tools
    4. Converts tools to serializable format
    5. Returns the tool specifications

    Args:
        input_data: MCP list tools input with server configuration

    Returns:
        MCPListToolsResult with available tools

    Raises:
        ApplicationError: For non-retryable errors (connection failed, etc.)
    """
    server_config = input_data.server_config
    logger.info(f"Listing MCP tools: server={server_config.server_id}, transport={server_config.transport}")

    try:
        # Create MCP client
        mcp_client = _create_mcp_client(server_config)

        # Connect and list tools
        with mcp_client:
            tools = mcp_client.list_tools_sync()

            # Apply filtering based on allowed/rejected patterns
            filtered_tools = _filter_tools(tools, server_config)

            # Convert to serializable format (with optional prefix)
            tool_specs = [
                _convert_mcp_tool_to_spec(tool, server_config.server_id, server_config.tool_prefix)
                for tool in filtered_tools
            ]

            logger.info(f"MCP tools listed: server={server_config.server_id}, count={len(tool_specs)}")

            # Heartbeat progress
            _safe_heartbeat(f"Listed {len(tool_specs)} tools from {server_config.server_id}")

            return MCPListToolsResult(tools=tool_specs)

    except ApplicationError:
        raise

    except Exception as e:
        error_type = type(e).__name__

        # Connection errors - may be retryable
        if "Connection" in error_type or "timeout" in str(e).lower():
            raise ApplicationError(
                f"MCP connection failed for server {server_config.server_id}: {e}",
                type="MCPConnectionError",
                non_retryable=False,  # Allow retry
            ) from e

        # Default: non-retryable
        logger.exception(f"Unexpected error listing MCP tools: {e}")
        raise ApplicationError(
            f"Failed to list MCP tools from {server_config.server_id}: {e}",
            type="MCPError",
            non_retryable=True,
        ) from e


# =============================================================================
# MCP Tool Execution Activity
# =============================================================================


@activity.defn
async def execute_mcp_tool_activity(input_data: MCPToolExecutionInput) -> MCPToolExecutionResult:
    """Execute a tool on an MCP server.

    This activity:
    1. Creates an MCPClient with the specified configuration
    2. Connects to the MCP server
    3. Calls the specified tool with arguments
    4. Converts the result to serializable format
    5. Returns the tool result

    Args:
        input_data: MCP tool execution input with server config, tool name, and arguments

    Returns:
        MCPToolExecutionResult with tool output

    Raises:
        ApplicationError: For non-retryable errors (tool not found, etc.)
    """
    server_config = input_data.server_config
    tool_name = input_data.tool_name

    # Strip prefix from tool name if present (MCP server doesn't know about prefixes)
    actual_tool_name = tool_name
    if server_config.tool_prefix and tool_name.startswith(f"{server_config.tool_prefix}_"):
        actual_tool_name = tool_name[len(server_config.tool_prefix) + 1 :]

    logger.info(f"Executing MCP tool: server={server_config.server_id}, tool={tool_name} (actual={actual_tool_name})")

    try:
        # Get or create cached MCP client (avoids restarting server process per call)
        _safe_heartbeat("connecting")
        mcp_client = _get_cached_mcp_client(server_config)

        # Call the tool (using actual name without prefix)
        # Signature: call_tool_sync(tool_use_id, name, arguments)
        _safe_heartbeat("executing")
        result = mcp_client.call_tool_sync(input_data.tool_use_id, actual_tool_name, input_data.tool_input)

        # Convert result to serializable format
        content = _convert_mcp_result_to_content(result)

        logger.info(f"MCP tool executed: server={server_config.server_id}, tool={tool_name}")

        return MCPToolExecutionResult(
            tool_use_id=input_data.tool_use_id,
            status="success",
            content=content,
            structured_content=getattr(result, "structuredContent", None),
            metadata=getattr(result, "metadata", None),
        )

    except ApplicationError:
        raise

    except Exception as e:
        error_type = type(e).__name__

        # Tool not found - non-retryable
        if "not found" in str(e).lower() or "unknown tool" in str(e).lower():
            return MCPToolExecutionResult(
                tool_use_id=input_data.tool_use_id,
                status="error",
                content=[{"text": f"Tool '{tool_name}' not found on MCP server: {e}"}],
            )

        # Connection errors - may be retryable
        if "Connection" in error_type or "timeout" in str(e).lower():
            raise ApplicationError(
                f"MCP connection failed during tool execution: {e}",
                type="MCPConnectionError",
                non_retryable=False,  # Allow retry
            ) from e

        # Tool execution error - return as error result
        logger.exception(f"MCP tool execution failed: {e}")
        return MCPToolExecutionResult(
            tool_use_id=input_data.tool_use_id,
            status="error",
            content=[{"text": f"MCP tool execution failed: {e}"}],
        )


def _convert_mcp_result_to_content(result: Any) -> list[dict[str, Any]]:
    """Convert MCP tool result to Strands content format.

    Args:
        result: MCPToolResult from Strands MCP client

    Returns:
        List of content blocks in Strands format
    """
    content: list[dict[str, Any]] = []

    # Handle MCPToolResult content
    if hasattr(result, "content"):
        for item in result.content:
            if hasattr(item, "text"):
                content.append({"text": item.text})
            elif hasattr(item, "source"):
                # Image content
                content.append(
                    {
                        "image": {
                            "format": item.source.get("media_type", "image/png").split("/")[-1],
                            "source": {
                                "bytes": item.source.get("data", ""),
                            },
                        }
                    }
                )
            else:
                # Unknown content type - serialize as text
                content.append({"text": str(item)})

    # If no content, try to serialize the whole result
    if not content:
        import json

        try:
            if hasattr(result, "model_dump"):
                content = [{"text": json.dumps(result.model_dump())}]
            elif hasattr(result, "__dict__"):
                content = [{"text": json.dumps(result.__dict__)}]
            else:
                content = [{"text": str(result)}]
        except Exception:
            content = [{"text": str(result)}]

    return content


# =============================================================================
# Helper Functions for Tool Conversion
# =============================================================================


def mcp_tool_specs_to_strands(mcp_specs: list[MCPToolSpec]) -> list[dict[str, Any]]:
    """Convert a list of MCPToolSpec to Strands ToolSpec format.

    This is used to merge MCP tools with static tools for model calls.

    Args:
        mcp_specs: List of MCPToolSpec from list_mcp_tools_activity

    Returns:
        List of dicts in Strands ToolSpec format
    """
    return [_convert_mcp_tool_spec_to_strands(spec) for spec in mcp_specs]


def get_mcp_server_for_tool(tool_name: str, mcp_tools: list[MCPToolSpec]) -> tuple[str, MCPToolSpec] | None:
    """Find which MCP server owns a tool.

    Args:
        tool_name: Name of the tool to find
        mcp_tools: List of MCP tool specs

    Returns:
        Tuple of (server_id, MCPToolSpec) if found, None otherwise
    """
    for spec in mcp_tools:
        if spec.name == tool_name:
            return (spec.server_id, spec)
    return None
