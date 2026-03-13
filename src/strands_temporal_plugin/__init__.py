"""Strands Temporal Plugin

Seamless integration between Strands Agents SDK and Temporal workflows.

This plugin provides full durability for Strands agents with two patterns:

1. **Full Durability (RECOMMENDED)**: Use `create_durable_agent()` or
   `TemporalModelStub` + `TemporalToolExecutor` for both model AND tool durability.

2. **Model-Only Durability**: Use just `TemporalModelStub` for pure function tools.

Quick Start (Full Durability - RECOMMENDED):
    from temporalio import workflow
    from strands import tool
    from strands_temporal_plugin import create_durable_agent, BedrockProviderConfig

    @tool
    def get_weather(city: str) -> str:
        '''Get weather for a city.'''
        return fetch_weather_api(city)  # I/O is safe - runs in activity!

    @workflow.defn
    class WeatherWorkflow:
        @workflow.run
        async def run(self, prompt: str) -> str:
            agent = create_durable_agent(
                provider_config=BedrockProviderConfig(
                    model_id="us.anthropic.claude-sonnet-4-20250514-v1:0"
                ),
                tools=[get_weather],
                tool_modules={"get_weather": "myapp.tools"},
                system_prompt="You are a weather assistant.",
            )
            result = await agent.invoke_async(prompt)
            return str(result)

Model-Only Durability (for pure function tools):
    from strands import Agent, tool
    from strands_temporal_plugin import TemporalModelStub, BedrockProviderConfig

    @tool
    def calculate(expr: str) -> str:
        '''Calculate a math expression (no I/O).'''
        return str(eval(expr))

    @workflow.defn
    class CalcWorkflow:
        @workflow.run
        async def run(self, prompt: str) -> str:
            agent = Agent(
                model=TemporalModelStub(
                    BedrockProviderConfig(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0")
                ),
                tools=[calculate],  # Pure function - OK in workflow context
                system_prompt="You are a calculator.",
            )
            result = await agent.invoke_async(prompt)
            return str(result)

Architecture:
    The plugin preserves the full Strands Agent event loop while routing
    model and tool calls to Temporal activities for durability:

    - Agent.invoke_async() runs the Strands event loop
    - TemporalModelStub routes model.stream() to activities
    - TemporalToolExecutor routes tool execution to activities
    - Full Strands features: callbacks, hooks, conversation history, etc.
"""

from .activities import (
    execute_model_activity,
    execute_structured_output_activity,
    execute_tool_activity,
)
from .mcp_activities import (
    close_mcp_clients,
    execute_mcp_tool_activity,
    get_mcp_server_for_tool,
    list_mcp_tools_activity,
    mcp_tool_specs_to_strands,
)
from .plugin import StrandsTemporalPlugin
from .runner import TemporalModelStub, create_durable_agent
from .session import (
    TemporalSessionManager,
    load_session_activity,
    save_session_activity,
)
from .tool_executor import TemporalToolExecutor
from .types import (
    AnthropicProviderConfig,
    BaseMCPServerConfig,
    BaseProviderConfig,
    BedrockProviderConfig,
    CustomProviderConfig,
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
    SessionConfig,
    SessionData,
    SessionLoadInput,
    SessionSaveInput,
    StdioMCPServerConfig,
    StreamableHTTPMCPServerConfig,
    StructuredOutputInput,
    StructuredOutputResult,
    TemporalToolConfig,
    ToolExecutionInput,
    ToolExecutionResult,
    ToolExecutorConfig,
    messages_to_serializable,
    tool_specs_to_serializable,
)


__version__ = "0.2.0"

__all__ = [
    # Main plugin
    "StrandsTemporalPlugin",
    # Full Durability Pattern (RECOMMENDED)
    "create_durable_agent",
    "TemporalModelStub",
    "TemporalToolExecutor",
    "ToolExecutorConfig",
    # Per-tool configuration
    "TemporalToolConfig",
    # Session management (S3-backed, activity-driven)
    "TemporalSessionManager",
    "SessionConfig",
    "SessionData",
    "SessionLoadInput",
    "SessionSaveInput",
    # Provider configurations
    "BaseProviderConfig",
    "BedrockProviderConfig",
    "AnthropicProviderConfig",
    "OpenAIProviderConfig",
    "OllamaProviderConfig",
    "CustomProviderConfig",
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
    # Activity types - Structured Output
    "StructuredOutputInput",
    "StructuredOutputResult",
    # Activity types - MCP
    "MCPToolSpec",
    "MCPListToolsInput",
    "MCPListToolsResult",
    "MCPToolExecutionInput",
    "MCPToolExecutionResult",
    # Activities (for custom registration)
    "execute_model_activity",
    "execute_tool_activity",
    "execute_structured_output_activity",
    "list_mcp_tools_activity",
    "execute_mcp_tool_activity",
    "load_session_activity",
    "save_session_activity",
    # MCP Helpers
    "mcp_tool_specs_to_strands",
    "get_mcp_server_for_tool",
    "close_mcp_clients",
    # Serialization Helpers
    "messages_to_serializable",
    "tool_specs_to_serializable",
]
