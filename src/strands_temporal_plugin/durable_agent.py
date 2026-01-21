"""Durable Agent for Temporal Workflows

The DurableAgent class provides a Temporal-native way to run Strands agents
with full durability. It properly separates:

1. Deterministic orchestration (workflow context)
2. Side effects with retries (activity context)
3. Serializable state (Pydantic models)

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                        WORKFLOW CONTEXT                          │
    │  ┌────────────────────────────────────────────────────────────┐ │
    │  │                     DurableAgent                            │ │
    │  │                                                             │ │
    │  │  config: DurableAgentConfig  ─┐                             │ │
    │  │  messages: list[dict]         │  Serializable only          │ │
    │  │  tool_specs: list[dict]      ─┘                             │ │
    │  │  mcp_tools: list[MCPToolSpec] │                             │ │
    │  │                                                             │ │
    │  │  invoke() ──────────────────────────────────┐              │ │
    │  │     │                                        │              │ │
    │  │     ▼                                        ▼              │ │
    │  │  ┌────────────────────┐     ┌───────────────────────────┐  │ │
    │  │  │ execute_model_call │     │ execute_tool_activity     │  │ │
    │  │  │     (Activity)     │     │  OR execute_mcp_tool      │  │ │
    │  │  │                    │     │      (Activity)           │  │ │
    │  │  │ - Creates Model    │     │ - Loads tool function     │  │ │
    │  │  │ - Uses AWS creds   │     │ - OR calls MCP server     │  │ │
    │  │  │ - Streams response │     │ - Returns ToolResult      │  │ │
    │  │  └────────────────────┘     └───────────────────────────┘  │ │
    │  │                                                             │ │
    │  └────────────────────────────────────────────────────────────┘ │
    └─────────────────────────────────────────────────────────────────┘

Usage with Static Tools:
    @workflow.defn
    class MyWorkflow:
        @workflow.run
        async def run(self, prompt: str) -> str:
            agent = DurableAgent(
                config=DurableAgentConfig(
                    provider_config=BedrockProviderConfig(
                        model_id="us.anthropic.claude-sonnet-4-20250514-v1:0"
                    ),
                    system_prompt="You are a helpful assistant.",
                    tool_specs=[...],
                    tool_modules={"get_weather": "my_app.tools"},
                )
            )
            result = await agent.invoke(prompt)
            return result.text

Usage with MCP Tools:
    @workflow.defn
    class MCPWorkflow:
        @workflow.run
        async def run(self, prompt: str) -> str:
            agent = DurableAgent(
                config=DurableAgentConfig(
                    provider_config=BedrockProviderConfig(
                        model_id="us.anthropic.claude-sonnet-4-20250514-v1:0"
                    ),
                    system_prompt="You are a documentation assistant.",
                    mcp_servers=[
                        StdioMCPServerConfig(
                            server_id="aws-docs",
                            command="uvx",
                            args=["awslabs.aws-documentation-mcp-server@latest"],
                        ),
                    ],
                )
            )
            result = await agent.invoke(prompt)
            return result.text
"""

from __future__ import annotations

import logging
from .activities import execute_model_activity, execute_tool_activity
from .mcp_activities import (
    execute_mcp_tool_activity,
    get_mcp_server_for_tool,
    list_mcp_tools_activity,
    mcp_tool_specs_to_strands,
)
from .types import (
    DurableAgentConfig,
    MCPListToolsInput,
    MCPListToolsResult,
    MCPToolExecutionInput,
    MCPToolExecutionResult,
    MCPToolSpec,
    ModelExecutionInput,
    ModelExecutionResult,
    ToolExecutionInput,
    ToolExecutionResult,
    messages_to_serializable,
)
from dataclasses import dataclass, field
from datetime import timedelta
from temporalio import workflow
from typing import Any


logger = logging.getLogger(__name__)


@dataclass
class DurableAgentResult:
    """Result from a DurableAgent invocation.

    Attributes:
        text: The final text response from the agent
        messages: Complete conversation history including tool calls
        stop_reason: Why the agent stopped (e.g., "end_turn", "max_tokens")
        usage: Token usage statistics
    """

    text: str
    messages: list[dict[str, Any]]
    stop_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


class DurableAgent:
    """A Temporal-native agent that runs with full durability.

    This agent is designed to be used ONLY within Temporal workflows.
    It routes all non-deterministic operations (model calls, tool execution)
    to activities for proper durability guarantees.

    Key Design Principles:
    1. All state is serializable (no function references, no clients)
    2. Model creation happens in activities (where credentials exist)
    3. Tool execution happens in activities (with proper retries)
    4. MCP tool discovery happens via activities (dynamic tool lists)
    5. The workflow only orchestrates and manages state

    Example with Static Tools:
        @workflow.defn
        class WeatherWorkflow:
            @workflow.run
            async def run(self, prompt: str) -> str:
                config = DurableAgentConfig(
                    provider_config=BedrockProviderConfig(
                        model_id="us.anthropic.claude-sonnet-4-20250514-v1:0"
                    ),
                    system_prompt="You are a weather assistant.",
                    tool_specs=[{
                        "name": "get_weather",
                        "description": "Get weather for a city",
                        "inputSchema": {...},
                    }],
                    tool_modules={"get_weather": "my_app.tools"},
                )

                agent = DurableAgent(config)
                result = await agent.invoke(prompt)
                return result.text

    Example with MCP Tools:
        @workflow.defn
        class MCPWorkflow:
            @workflow.run
            async def run(self, prompt: str) -> str:
                config = DurableAgentConfig(
                    provider_config=BedrockProviderConfig(
                        model_id="us.anthropic.claude-sonnet-4-20250514-v1:0"
                    ),
                    system_prompt="You are a documentation assistant.",
                    mcp_servers=[
                        StdioMCPServerConfig(
                            server_id="aws-docs",
                            command="uvx",
                            args=["awslabs.aws-documentation-mcp-server@latest"],
                        ),
                    ],
                )

                agent = DurableAgent(config)
                result = await agent.invoke(prompt)
                return result.text
    """

    def __init__(self, config: DurableAgentConfig) -> None:
        """Initialize the DurableAgent.

        Args:
            config: Agent configuration (must be serializable)
        """
        self._config = config
        self._messages: list[dict[str, Any]] = []
        self._mcp_tools: list[MCPToolSpec] = []  # Discovered MCP tools
        self._mcp_server_configs: dict[str, Any] = {}  # server_id -> config mapping

    @property
    def config(self) -> DurableAgentConfig:
        """Get the agent configuration."""
        return self._config

    @property
    def messages(self) -> list[dict[str, Any]]:
        """Get the current conversation history."""
        return self._messages.copy()

    @property
    def mcp_tools(self) -> list[MCPToolSpec]:
        """Get the discovered MCP tools."""
        return self._mcp_tools.copy()

    async def invoke(self, prompt: str, max_iterations: int = 10) -> DurableAgentResult:
        """Invoke the agent with a prompt.

        This method orchestrates the agent event loop:
        1. Discover MCP tools (if any MCP servers configured)
        2. Add user message
        3. Call model (via activity) with all available tools
        4. If model requests tool use, execute tools (via activity)
        5. Repeat until model returns final response or max iterations

        Args:
            prompt: The user's prompt
            max_iterations: Maximum number of model calls (prevents infinite loops)

        Returns:
            DurableAgentResult with the final response

        Raises:
            RuntimeError: If max iterations exceeded
        """
        # Discover MCP tools if MCP servers are configured
        if self._config.mcp_servers:
            await self._discover_mcp_tools()

        # Add user message to history
        self._add_user_message(prompt)

        total_usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
        stop_reason: str | None = None

        for iteration in range(max_iterations):
            logger.info(f"DurableAgent iteration {iteration + 1}/{max_iterations}")

            # Execute model call via activity
            model_result = await self._execute_model_call()

            # Process the stream events to build assistant message
            assistant_content: list[dict[str, Any]] = []
            tool_calls: list[dict[str, Any]] = []

            for event in model_result.events:
                # Handle different event types from Strands streaming
                if "contentBlockStart" in event:
                    block_start = event["contentBlockStart"]
                    if "toolUse" in block_start.get("start", {}):
                        tool_use_start = block_start["start"]["toolUse"]
                        tool_calls.append(
                            {
                                "toolUseId": tool_use_start.get("toolUseId", ""),
                                "name": tool_use_start.get("name", ""),
                                "input": {},  # Will be filled by deltas
                            }
                        )

                elif "contentBlockDelta" in event:
                    delta = event["contentBlockDelta"]["delta"]
                    if "text" in delta:
                        # Text content
                        if not assistant_content or "text" not in assistant_content[-1]:
                            assistant_content.append({"text": ""})
                        assistant_content[-1]["text"] += delta["text"]
                    elif "toolUse" in delta:
                        # Tool use input delta (JSON string chunks)
                        if tool_calls:
                            # Accumulate tool input JSON
                            input_str = delta["toolUse"].get("input", "")
                            if isinstance(input_str, str):
                                if "_input_str" not in tool_calls[-1]:
                                    tool_calls[-1]["_input_str"] = ""
                                tool_calls[-1]["_input_str"] += input_str

                elif "messageStop" in event:
                    stop_reason = event["messageStop"].get("stopReason")

                elif "metadata" in event:
                    # Usage information
                    usage = event["metadata"].get("usage", {})
                    total_usage["input_tokens"] += usage.get("inputTokens", 0)
                    total_usage["output_tokens"] += usage.get("outputTokens", 0)

            # Parse accumulated tool input JSON strings
            import json

            for tool_call in tool_calls:
                if "_input_str" in tool_call:
                    try:
                        tool_call["input"] = json.loads(tool_call["_input_str"])
                    except json.JSONDecodeError:
                        tool_call["input"] = {}
                    del tool_call["_input_str"]

            # Add tool uses to assistant content
            for tool_call in tool_calls:
                assistant_content.append(
                    {
                        "toolUse": {
                            "toolUseId": tool_call["toolUseId"],
                            "name": tool_call["name"],
                            "input": tool_call["input"],
                        }
                    }
                )

            # Add assistant message to history
            self._messages.append({"role": "assistant", "content": assistant_content})

            # Check if we need to execute tools
            if tool_calls and stop_reason == "tool_use":
                # Execute each tool and collect results
                tool_results: list[dict[str, Any]] = []

                for tool_call in tool_calls:
                    tool_name = tool_call["name"]
                    tool_input = tool_call["input"]
                    tool_use_id = tool_call["toolUseId"]

                    # Check if this is an MCP tool or a static tool
                    mcp_tool_info = get_mcp_server_for_tool(tool_name, self._mcp_tools)

                    if mcp_tool_info is not None:
                        # MCP tool - execute via MCP activity
                        server_id, mcp_spec = mcp_tool_info
                        tool_result = await self._execute_mcp_tool_call(
                            server_id=server_id,
                            tool_name=tool_name,
                            tool_input=tool_input,
                            tool_use_id=tool_use_id,
                        )
                    else:
                        # Static tool - execute via regular tool activity
                        tool_result = await self._execute_static_tool_call(
                            tool_name=tool_name,
                            tool_input=tool_input,
                            tool_use_id=tool_use_id,
                        )

                    tool_results.append(
                        {
                            "toolResult": {
                                "toolUseId": tool_result.tool_use_id,
                                "status": tool_result.status,
                                "content": tool_result.content,
                            }
                        }
                    )

                # Add tool results as user message (Strands convention)
                self._messages.append({"role": "user", "content": tool_results})

            else:
                # No tool calls or end_turn - we're done
                break

        else:
            raise RuntimeError(f"DurableAgent exceeded maximum iterations ({max_iterations})")

        # Extract final text response
        final_text = self._extract_final_text()

        return DurableAgentResult(
            text=final_text,
            messages=self._messages.copy(),
            stop_reason=stop_reason,
            usage=total_usage,
        )

    def _add_user_message(self, prompt: str) -> None:
        """Add a user message to the conversation history."""
        self._messages.append({"role": "user", "content": [{"text": prompt}]})

    async def _execute_model_call(self) -> ModelExecutionResult:
        """Execute a model call via Temporal activity.

        Merges static tools and MCP tools for the model call.

        Returns:
            ModelExecutionResult with stream events
        """
        # Merge static tools and MCP tools
        all_tool_specs = self._get_merged_tool_specs()

        activity_input = ModelExecutionInput(
            provider_config=self._config.provider_config,
            messages=messages_to_serializable(self._messages),
            tool_specs=all_tool_specs if all_tool_specs else None,
            system_prompt=self._config.system_prompt,
        )

        result: ModelExecutionResult = await workflow.execute_activity(
            execute_model_activity,
            activity_input,
            start_to_close_timeout=timedelta(seconds=self._config.model_activity_timeout),
            retry_policy=self._config.get_model_retry_policy(),
        )

        return result

    def _get_merged_tool_specs(self) -> list[dict[str, Any]]:
        """Get merged tool specs from static tools and MCP tools.

        Returns:
            Combined list of tool specifications
        """
        merged: list[dict[str, Any]] = []

        # Add static tools
        if self._config.tool_specs:
            merged.extend(self._config.tool_specs)

        # Add MCP tools (converted to Strands format)
        if self._mcp_tools:
            mcp_specs = mcp_tool_specs_to_strands(self._mcp_tools)
            merged.extend(mcp_specs)

        return merged

    async def _execute_static_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str,
    ) -> ToolExecutionResult:
        """Execute a static (function-based) tool call via Temporal activity.

        Args:
            tool_name: Name of the tool to execute
            tool_input: Input parameters for the tool
            tool_use_id: ID for correlation

        Returns:
            ToolExecutionResult with tool output
        """
        tool_module = self._config.tool_modules.get(tool_name, "")

        activity_input = ToolExecutionInput(
            tool_name=tool_name,
            tool_module=tool_module,
            tool_input=tool_input,
            tool_use_id=tool_use_id,
        )

        result: ToolExecutionResult = await workflow.execute_activity(
            execute_tool_activity,
            activity_input,
            start_to_close_timeout=timedelta(seconds=self._config.tool_activity_timeout),
            retry_policy=self._config.get_tool_retry_policy(),
        )

        return result

    async def _execute_mcp_tool_call(
        self,
        server_id: str,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str,
    ) -> ToolExecutionResult:
        """Execute an MCP tool call via Temporal activity.

        Args:
            server_id: ID of the MCP server that owns the tool
            tool_name: Name of the tool to execute
            tool_input: Input parameters for the tool
            tool_use_id: ID for correlation

        Returns:
            ToolExecutionResult with tool output (converted from MCP format)
        """
        # Get the server config
        server_config = self._mcp_server_configs.get(server_id)
        if server_config is None:
            # This shouldn't happen if tool routing is correct
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
            start_to_close_timeout=timedelta(seconds=self._config.mcp_activity_timeout),
            retry_policy=self._config.get_mcp_retry_policy(),
        )

        # Convert MCPToolExecutionResult to ToolExecutionResult
        return ToolExecutionResult(
            tool_use_id=result.tool_use_id,
            status=result.status,
            content=result.content,
        )

    async def _discover_mcp_tools(self) -> None:
        """Discover tools from all configured MCP servers.

        This method is called at the start of invoke() if MCP servers are configured.
        It lists tools from each server and stores them for later use.
        """
        logger.info(f"Discovering tools from {len(self._config.mcp_servers)} MCP server(s)")

        self._mcp_tools = []
        self._mcp_server_configs = {}

        for server_config in self._config.mcp_servers:
            logger.info(f"Listing tools from MCP server: {server_config.server_id}")

            # Store server config for later tool execution
            self._mcp_server_configs[server_config.server_id] = server_config

            activity_input = MCPListToolsInput(server_config=server_config)

            result: MCPListToolsResult = await workflow.execute_activity(
                list_mcp_tools_activity,
                activity_input,
                start_to_close_timeout=timedelta(seconds=self._config.mcp_activity_timeout),
                retry_policy=self._config.get_mcp_retry_policy(),
            )

            logger.info(f"Discovered {len(result.tools)} tools from MCP server: {server_config.server_id}")
            self._mcp_tools.extend(result.tools)

        logger.info(f"Total MCP tools discovered: {len(self._mcp_tools)}")

    def _extract_final_text(self) -> str:
        """Extract the final text response from conversation history."""
        # Find the last assistant message
        for message in reversed(self._messages):
            if message.get("role") == "assistant":
                content = message.get("content", [])
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        text_parts.append(block["text"])
                if text_parts:
                    return "".join(text_parts)
        return ""
