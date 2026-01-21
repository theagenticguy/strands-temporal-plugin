"""Strands Temporal Plugin

Seamless integration between Strands Agents SDK and Temporal workflows.

This plugin provides the DurableAgent pattern for running Strands agents
with full Temporal durability guarantees.

Quick Start:
    from temporalio import workflow
    from temporalio.client import Client
    from temporalio.worker import Worker
    from strands_temporal_plugin import (
        StrandsTemporalPlugin,
        DurableAgent,
        DurableAgentConfig,
        BedrockProviderConfig,
    )

    # 1. Connect with plugin
    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()]
    )

    # 2. Define your workflow using DurableAgent
    @workflow.defn
    class WeatherWorkflow:
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

    # 3. Create and run worker
    worker = Worker(
        client,
        task_queue="strands-agents",
        workflows=[WeatherWorkflow],
    )
    await worker.run()

Architecture:
    The DurableAgent pattern properly separates:
    - Deterministic orchestration (workflow context)
    - Side effects with retries (activity context)
    - Serializable state (Pydantic models)

    Model creation happens in activities where credentials exist.
    Tool execution happens in activities with proper retries.
    The workflow only orchestrates and manages serializable state.
"""

from .activities import (
    execute_model_activity,
    execute_tool_activity,
)
from .durable_agent import DurableAgent, DurableAgentResult
from .mcp_activities import (
    execute_mcp_tool_activity,
    get_mcp_server_for_tool,
    list_mcp_tools_activity,
    mcp_tool_specs_to_strands,
)
from .plugin import StrandsTemporalPlugin
from .types import (
    AnthropicProviderConfig,
    BaseMCPServerConfig,
    BaseProviderConfig,
    BedrockProviderConfig,
    DurableAgentConfig,
    MCPListToolsInput,
    MCPListToolsResult,
    MCPServerConfig,
    MCPToolExecutionInput,
    MCPToolExecutionResult,
    MCPToolSpec,
    ModelExecutionInput,
    ModelExecutionResult,
    OllamaProviderConfig,
    OpenAIProviderConfig,
    ProviderConfig,
    StdioMCPServerConfig,
    StreamableHTTPMCPServerConfig,
    ToolExecutionInput,
    ToolExecutionResult,
    messages_to_serializable,
    tool_specs_to_serializable,
)


__version__ = "0.1.0"

__all__ = [
    # Main plugin
    "StrandsTemporalPlugin",
    # DurableAgent pattern
    "DurableAgent",
    "DurableAgentResult",
    "DurableAgentConfig",
    # Provider configurations
    "BaseProviderConfig",
    "BedrockProviderConfig",
    "AnthropicProviderConfig",
    "OpenAIProviderConfig",
    "OllamaProviderConfig",
    "ProviderConfig",
    # MCP server configurations
    "BaseMCPServerConfig",
    "StdioMCPServerConfig",
    "StreamableHTTPMCPServerConfig",
    "MCPServerConfig",
    # Activity types - Model and Tool
    "ModelExecutionInput",
    "ModelExecutionResult",
    "ToolExecutionInput",
    "ToolExecutionResult",
    # Activity types - MCP
    "MCPToolSpec",
    "MCPListToolsInput",
    "MCPListToolsResult",
    "MCPToolExecutionInput",
    "MCPToolExecutionResult",
    # Activities (for custom registration)
    "execute_model_activity",
    "execute_tool_activity",
    "list_mcp_tools_activity",
    "execute_mcp_tool_activity",
    # MCP Helpers
    "mcp_tool_specs_to_strands",
    "get_mcp_server_for_tool",
    # Serialization Helpers
    "messages_to_serializable",
    "tool_specs_to_serializable",
]
