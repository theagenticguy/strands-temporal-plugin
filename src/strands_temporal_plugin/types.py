"""Strands Temporal Plugin Types

Pydantic models for serialization between workflows and activities.
These models ensure proper serialization of Strands types through Temporal's
data converter using the Pydantic payload converter.
"""

from __future__ import annotations

from datetime import timedelta
from pydantic import BaseModel, ConfigDict, Field
from temporalio.common import RetryPolicy
from typing import Annotated, Any, Literal


# =============================================================================
# Provider Configuration Types
# =============================================================================


class BaseProviderConfig(BaseModel):
    """Base configuration for all model providers.

    All provider configs must include a discriminator field 'provider'
    to enable proper union deserialization.
    """

    model_config = ConfigDict(extra="forbid")

    provider: str
    model_id: str


class BedrockProviderConfig(BaseProviderConfig):
    """Configuration for AWS Bedrock models.

    Example:
        config = BedrockProviderConfig(
            model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            region_name="us-east-1",
            max_tokens=4096,
        )
    """

    provider: Literal["bedrock"] = "bedrock"
    region_name: str | None = None
    max_tokens: int = 4096
    temperature: float | None = None
    top_p: float | None = None
    stop_sequences: list[str] | None = None


class AnthropicProviderConfig(BaseProviderConfig):
    """Configuration for Anthropic API models (direct, not via Bedrock).

    Example:
        config = AnthropicProviderConfig(
            model_id="claude-sonnet-4-20250514",
            max_tokens=4096,
        )
    """

    provider: Literal["anthropic"] = "anthropic"
    max_tokens: int = 4096
    temperature: float | None = None
    top_p: float | None = None
    stop_sequences: list[str] | None = None


class OpenAIProviderConfig(BaseProviderConfig):
    """Configuration for OpenAI models.

    Example:
        config = OpenAIProviderConfig(
            model_id="gpt-4o",
            max_tokens=4096,
        )
    """

    provider: Literal["openai"] = "openai"
    max_tokens: int = 4096
    temperature: float | None = None
    top_p: float | None = None


class OllamaProviderConfig(BaseProviderConfig):
    """Configuration for Ollama local models.

    Example:
        config = OllamaProviderConfig(
            model_id="llama3.2",
            host="http://localhost:11434",
        )
    """

    provider: Literal["ollama"] = "ollama"
    host: str = "http://localhost:11434"
    temperature: float | None = None
    top_p: float | None = None


# ProviderConfig union is defined after CustomProviderConfig below


# =============================================================================
# MCP Server Configuration Types
# =============================================================================


class BaseMCPServerConfig(BaseModel):
    """Base configuration for MCP servers.

    All MCP server configs must include a discriminator field 'transport'
    to enable proper union deserialization.
    """

    model_config = ConfigDict(extra="forbid")

    # Unique identifier for this MCP server (used in tool namespacing)
    server_id: str

    # Transport type discriminator
    transport: str

    # Optional tool filtering
    allowed_tools: list[str] | None = None  # Glob patterns for allowed tools
    rejected_tools: list[str] | None = None  # Glob patterns for rejected tools

    # Optional prefix for tool names (e.g., "docs" -> "docs_search")
    tool_prefix: str | None = None

    # Connection timeout
    startup_timeout: float = 30.0


class StdioMCPServerConfig(BaseMCPServerConfig):
    """Configuration for STDIO-based MCP servers.

    Use this for local MCP servers that communicate via stdin/stdout.

    Example:
        config = StdioMCPServerConfig(
            server_id="aws-docs",
            command="uvx",
            args=["awslabs.aws-documentation-mcp-server@latest"],
        )
    """

    transport: Literal["stdio"] = "stdio"

    # Command to run the MCP server
    command: str

    # Arguments for the command
    args: list[str] = Field(default_factory=list)

    # Environment variables for the subprocess
    env: dict[str, str] | None = None

    # Working directory for the subprocess
    cwd: str | None = None


class StreamableHTTPMCPServerConfig(BaseMCPServerConfig):
    """Configuration for Streamable HTTP MCP servers.

    Use this for remote MCP servers that communicate via HTTP.

    Example:
        config = StreamableHTTPMCPServerConfig(
            server_id="bedrock-mcp",
            url="https://gateway.bedrock-agentcore.amazonaws.com/mcp",
            headers={"Authorization": "Bearer token"},
        )
    """

    transport: Literal["streamable_http"] = "streamable_http"

    # URL of the MCP server
    url: str

    # HTTP headers (e.g., for authentication)
    headers: dict[str, str] = Field(default_factory=dict)

    # HTTP timeout in seconds
    timeout: float = 30.0


# Union type for MCP server configuration with discriminator
MCPServerConfig = Annotated[
    StdioMCPServerConfig | StreamableHTTPMCPServerConfig,
    Field(discriminator="transport"),
]


# =============================================================================
# Activity Input/Output Types
# =============================================================================


class ModelExecutionInput(BaseModel):
    """Input for the model execution activity.

    This is the payload sent from workflow to activity for model inference.
    All fields must be JSON-serializable.
    """

    model_config = ConfigDict(extra="forbid")

    # Provider configuration (determines which model to use)
    provider_config: ProviderConfig

    # Messages in Strands format (list of Message TypedDicts)
    # Using Any since Messages is a TypedDict that serializes to list[dict]
    messages: list[dict[str, Any]] | None = None

    # Tool specifications (list of ToolSpec TypedDicts)
    # Using Any since ToolSpec is a TypedDict that serializes to list[dict]
    tool_specs: list[dict[str, Any]] | None = None

    # System prompt
    system_prompt: str | None = None


class ModelExecutionResult(BaseModel):
    """Result from model execution activity.

    Contains the stream events from model inference.
    """

    model_config = ConfigDict(extra="forbid")

    # Stream events from model (list of StreamEvent TypedDicts)
    # Using Any since StreamEvent is a TypedDict that serializes to list[dict]
    events: list[dict[str, Any]]


class ToolExecutionInput(BaseModel):
    """Input for tool execution activity.

    This is the payload sent from workflow to activity for tool execution.
    """

    model_config = ConfigDict(extra="forbid")

    # Tool name to execute
    tool_name: str

    # Tool module path for dynamic import (e.g., "my_module.tools.get_weather")
    tool_module: str

    # Tool input parameters
    tool_input: dict[str, Any]

    # Tool use ID for correlation
    tool_use_id: str


class ToolExecutionResult(BaseModel):
    """Result from tool execution activity.

    Contains the tool result in Strands ToolResult format.
    """

    model_config = ConfigDict(extra="forbid")

    # Tool use ID for correlation
    tool_use_id: str

    # Execution status
    status: Literal["success", "error"]

    # Result content (list of content blocks)
    content: list[dict[str, Any]]


# =============================================================================
# MCP Activity Input/Output Types
# =============================================================================


class MCPToolSpec(BaseModel):
    """Serializable MCP tool specification.

    This represents a tool definition from an MCP server in a format
    that can be serialized through Temporal and used with Strands models.
    """

    model_config = ConfigDict(extra="forbid")

    # Tool name (may be prefixed with server prefix)
    name: str

    # Tool description
    description: str | None = None

    # JSON Schema for input parameters
    input_schema: dict[str, Any]

    # JSON Schema for output (optional)
    output_schema: dict[str, Any] | None = None

    # Server ID this tool belongs to (for routing tool calls)
    server_id: str


class MCPListToolsInput(BaseModel):
    """Input for the MCP list tools activity.

    This is the payload sent from workflow to activity to list available tools.
    """

    model_config = ConfigDict(extra="forbid")

    # MCP server configuration
    server_config: MCPServerConfig


class MCPListToolsResult(BaseModel):
    """Result from MCP list tools activity.

    Contains the list of available tools from the MCP server.
    """

    model_config = ConfigDict(extra="forbid")

    # List of available tools
    tools: list[MCPToolSpec]


class MCPToolExecutionInput(BaseModel):
    """Input for MCP tool execution activity.

    This is the payload sent from workflow to activity for MCP tool execution.
    """

    model_config = ConfigDict(extra="forbid")

    # MCP server configuration
    server_config: MCPServerConfig

    # Tool name to execute
    tool_name: str

    # Tool input parameters
    tool_input: dict[str, Any]

    # Tool use ID for correlation
    tool_use_id: str


class MCPToolExecutionResult(BaseModel):
    """Result from MCP tool execution activity.

    Contains the tool result from the MCP server.
    """

    model_config = ConfigDict(extra="forbid")

    # Tool use ID for correlation
    tool_use_id: str

    # Execution status
    status: Literal["success", "error"]

    # Result content (list of content blocks)
    content: list[dict[str, Any]]

    # Structured content from MCP (if any)
    structured_content: dict[str, Any] | None = None

    # Metadata from MCP server (if any)
    metadata: dict[str, Any] | None = None


# =============================================================================
# Tool Executor Configuration
# =============================================================================


class ToolExecutorConfig(BaseModel):
    """Configuration for TemporalToolExecutor.

    This configuration specifies how tools should be executed via Temporal
    activities, including module paths for static tools and MCP server
    configurations for dynamic tool discovery.

    Example:
        config = ToolExecutorConfig(
            tool_modules={"get_weather": "myapp.tools"},
            mcp_servers=[
                StdioMCPServerConfig(
                    server_id="aws-docs",
                    command="uvx",
                    args=["awslabs.aws-documentation-mcp-server@latest"],
                ),
            ],
        )
    """

    model_config = ConfigDict(extra="forbid")

    # Tool module paths for dynamic import in activity context
    # Maps tool name to module path (e.g., {"get_weather": "my_module.tools"})
    tool_modules: dict[str, str] = Field(default_factory=dict)

    # MCP server configurations for dynamic tool discovery
    mcp_servers: list[MCPServerConfig] = Field(default_factory=list)

    # Activity execution configuration
    activity_timeout: float = 60.0  # 1 minute default

    # Retry configuration
    max_retries: int = 3
    initial_retry_interval_seconds: float = 1.0
    max_retry_interval_seconds: float = 30.0
    backoff_coefficient: float = 2.0

    def get_retry_policy(self) -> RetryPolicy:
        """Get RetryPolicy for tool activities."""
        return RetryPolicy(
            maximum_attempts=self.max_retries,
            initial_interval=timedelta(seconds=self.initial_retry_interval_seconds),
            maximum_interval=timedelta(seconds=self.max_retry_interval_seconds),
            backoff_coefficient=self.backoff_coefficient,
        )


# =============================================================================
# Per-Tool Activity Configuration
# =============================================================================


class TemporalToolConfig(BaseModel):
    """Per-tool configuration for Temporal activity execution.

    Allows overriding timeout, heartbeat, and retry settings on a per-tool basis.
    When a field is None, the executor's default is used.

    Example:
        tool_configs = {
            "slow_search": TemporalToolConfig(
                start_to_close_timeout=300.0,
                heartbeat_timeout=30.0,
            ),
            "flaky_api": TemporalToolConfig(
                retry_max_attempts=5,
                retry_initial_interval=2.0,
            ),
        }
    """

    model_config = ConfigDict(extra="forbid")

    start_to_close_timeout: float | None = None
    heartbeat_timeout: float | None = None
    retry_max_attempts: int | None = None
    retry_initial_interval: float | None = None  # seconds
    retry_max_interval: float | None = None  # seconds
    retry_backoff_coefficient: float | None = None

    def get_retry_policy(self, fallback: RetryPolicy) -> RetryPolicy:
        """Build a RetryPolicy, falling back to the provided default for unset fields."""
        return RetryPolicy(
            maximum_attempts=self.retry_max_attempts if self.retry_max_attempts is not None else fallback.maximum_attempts,
            initial_interval=(
                timedelta(seconds=self.retry_initial_interval)
                if self.retry_initial_interval is not None
                else fallback.initial_interval
            ),
            maximum_interval=(
                timedelta(seconds=self.retry_max_interval)
                if self.retry_max_interval is not None
                else fallback.maximum_interval
            ),
            backoff_coefficient=(
                self.retry_backoff_coefficient if self.retry_backoff_coefficient is not None else fallback.backoff_coefficient
            ),
        )


# =============================================================================
# Session Management Types (S3-backed, activity-driven)
# =============================================================================


class SessionConfig(BaseModel):
    """Configuration for S3-backed session persistence.

    Used with TemporalSessionManager to load/save agent state through activities.
    The offset/stream model: S3 is the state store, Temporal is the orchestrator,
    session_id is the pointer.

    Example:
        config = SessionConfig(
            session_id="user-456",
            bucket="my-agent-sessions",
            prefix="production/",
            region_name="us-west-2",
        )
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str
    bucket: str
    prefix: str = ""
    region_name: str | None = None


class SessionData(BaseModel):
    """Session data loaded from / saved to S3.

    Contains everything needed to restore an agent's conversational state.
    """

    model_config = ConfigDict(extra="forbid")

    messages: list[dict[str, Any]] = Field(default_factory=list)
    agent_state: dict[str, Any] = Field(default_factory=dict)
    conversation_manager_state: dict[str, Any] = Field(default_factory=dict)


class SessionLoadInput(BaseModel):
    """Input for the session load activity."""

    model_config = ConfigDict(extra="forbid")

    config: SessionConfig


class SessionSaveInput(BaseModel):
    """Input for the session save activity."""

    model_config = ConfigDict(extra="forbid")

    config: SessionConfig
    data: SessionData


# =============================================================================
# Structured Output Types
# =============================================================================


class StructuredOutputInput(BaseModel):
    """Input for structured output model activity.

    The output_model_path is a dotted import path (e.g. 'myapp.models.WeatherOutput')
    that resolves to a Pydantic model class on the worker side.
    """

    model_config = ConfigDict(extra="forbid")

    provider_config: ProviderConfig
    output_model_path: str
    prompt: str
    system_prompt: str | None = None


class StructuredOutputResult(BaseModel):
    """Result from structured output activity."""

    model_config = ConfigDict(extra="forbid")

    output: dict[str, Any]
    output_model_path: str


# =============================================================================
# Custom Provider Configuration
# =============================================================================


class CustomProviderConfig(BaseProviderConfig):
    """Configuration for custom model providers via import path.

    Allows plugging in any Strands-compatible Model implementation without
    modifying the plugin source. The provider_class_path should resolve to
    a class that accepts **provider_kwargs in its constructor.

    Example:
        config = CustomProviderConfig(
            model_id="my-custom-model",
            provider_class_path="myapp.models.MyCustomModel",
            provider_kwargs={"api_key": "sk-...", "base_url": "https://..."},
        )
    """

    provider: Literal["custom"] = "custom"
    provider_class_path: str
    provider_kwargs: dict[str, Any] = Field(default_factory=dict)


# Update the ProviderConfig union to include CustomProviderConfig
ProviderConfig = Annotated[  # noqa: F811
    BedrockProviderConfig | AnthropicProviderConfig | OpenAIProviderConfig | OllamaProviderConfig | CustomProviderConfig,
    Field(discriminator="provider"),
]


# =============================================================================
# Serialization Helpers
# =============================================================================


def messages_to_serializable(messages: Any) -> list[dict[str, Any]]:
    """Convert Strands Messages to serializable format.

    Args:
        messages: Strands Messages (list of Message TypedDicts)

    Returns:
        List of dicts that can be JSON serialized
    """
    if messages is None:
        return []
    # Messages are already TypedDicts, which serialize as dicts
    return list(messages)


def tool_specs_to_serializable(tool_specs: Any) -> list[dict[str, Any]]:
    """Convert Strands ToolSpecs to serializable format.

    Args:
        tool_specs: List of ToolSpec TypedDicts

    Returns:
        List of dicts that can be JSON serialized
    """
    if tool_specs is None:
        return []
    # ToolSpecs are already TypedDicts, which serialize as dicts
    return list(tool_specs)
