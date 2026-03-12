"""Strands Agent Runtime - Temporal Model Stub and Durable Agent Factory

This module provides:
1. TemporalModelStub - A Model implementation that routes model inference to activities
2. create_durable_agent() - Factory function for fully durable Strands agents

The key insight is that Strands Agent's event loop calls model.stream() for
inference and tool_executor._execute() for tool calls. By replacing both with
Temporal-aware implementations, we get full durability while preserving the
complete Strands Agent event loop.

Usage (Model-only durability):
    from strands import Agent
    from strands_temporal_plugin import TemporalModelStub, BedrockProviderConfig

    @workflow.defn
    class MyWorkflow:
        @workflow.run
        async def run(self, prompt: str) -> str:
            agent = Agent(
                model=TemporalModelStub(
                    BedrockProviderConfig(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0")
                ),
                tools=[my_pure_tool],  # Pure functions only (no I/O)
                system_prompt="You are helpful.",
            )
            result = await agent.invoke_async(prompt)
            return str(result)

Usage (Full durability - RECOMMENDED):
    from strands import tool
    from strands_temporal_plugin import create_durable_agent, BedrockProviderConfig

    @tool
    def get_weather(city: str) -> str:
        '''Get weather for a city.'''
        return fetch_weather_api(city)  # I/O is safe - runs in activity

    @workflow.defn
    class MyWorkflow:
        @workflow.run
        async def run(self, prompt: str) -> str:
            agent = create_durable_agent(
                provider_config=BedrockProviderConfig(model_id="..."),
                tools=[get_weather],
                system_prompt="You are helpful.",
            )
            result = await agent.invoke_async(prompt)
            return str(result)

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                        WORKFLOW CONTEXT                          │
    │                                                                  │
    │   Agent.invoke_async(prompt)                                     │
    │        │                                                         │
    │        ▼                                                         │
    │   ┌──────────────────────────────────────────────────────────┐  │
    │   │              Strands Agent Event Loop                     │  │
    │   │                                                           │  │
    │   │   1. Format messages                                      │  │
    │   │   2. Call model.stream() ──────┐                          │  │
    │   │   3. Parse response            │                          │  │
    │   │   4. Execute tools (if any)    │                          │  │
    │   │   5. Loop until done           │                          │  │
    │   └───────────────────────────────│───────────────────────────┘  │
    │                                    │                             │
    │                                    ▼                             │
    │   ┌──────────────────────────────────────────────────────────┐  │
    │   │              TemporalModelStub.stream()                   │  │
    │   │                                                           │  │
    │   │   Routes to activity ──────────────────┐                  │  │
    │   └───────────────────────────────────────│──────────────────┘  │
    │                                            │                     │
    └────────────────────────────────────────────│─────────────────────┘
                                                 │
                                                 ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                       ACTIVITY CONTEXT                           │
    │                                                                  │
    │   execute_model_activity()                                       │
    │        │                                                         │
    │        ▼                                                         │
    │   ┌──────────────────────────────────────────────────────────┐  │
    │   │   1. Create real Model (BedrockModel, etc.)               │  │
    │   │   2. Call model.stream() with AWS credentials             │  │
    │   │   3. Collect stream events                                │  │
    │   │   4. Return serialized events                             │  │
    │   └──────────────────────────────────────────────────────────┘  │
    └─────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from .activities import execute_model_activity
from .types import BedrockProviderConfig, ModelExecutionInput, ModelExecutionResult, ProviderConfig
from collections.abc import AsyncIterator
from datetime import timedelta
from strands.types.content import Messages
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolSpec
from temporalio import workflow
from temporalio.common import RetryPolicy
from typing import Any


def _extract_tool_modules(tools: list[Any]) -> dict[str, str]:
    """Extract module paths from @tool decorated functions.

    Args:
        tools: List of @tool decorated functions

    Returns:
        Dictionary mapping tool names to module paths

    Raises:
        ValueError: If a tool is defined in __main__ module or lacks attributes
    """
    tool_modules = {}

    for tool in tools:
        # Get tool name
        tool_name = getattr(tool, "tool_name", None) or getattr(tool, "__name__", None)
        if not tool_name:
            raise ValueError(f"Cannot determine tool name for {tool}. Ensure it's a @tool decorated function.")

        # Get module path
        module = getattr(tool, "__module__", None)
        if not module:
            raise ValueError(f"Cannot determine module for tool '{tool_name}'. Provide explicit tool_modules mapping.")

        # Handle __main__ edge case
        if module == "__main__":
            raise ValueError(
                f"Tool '{tool_name}' is defined in __main__ module which cannot be "
                f"re-imported in activity workers. Move the tool to a separate "
                f"importable module (e.g., myapp/tools.py) or provide an explicit "
                f"tool_modules mapping."
            )

        tool_modules[tool_name] = module

    return tool_modules


class TemporalModelStub:
    """Model stub that routes inference calls to Temporal activities.

    This class implements the Strands Model interface but instead of calling
    a model directly, it routes the call to a Temporal activity. This provides:

    1. Durability: Model calls survive workflow restarts
    2. Retries: Failed model calls are automatically retried
    3. Timeouts: Long-running calls are properly handled
    4. Credentials: Real model creation happens in activity where credentials exist

    The stub preserves the full Strands Agent event loop - tool execution,
    conversation history management, and all other agent logic remains intact.

    Args:
        provider_config: Configuration for the model provider (Bedrock, Anthropic, etc.)
                        Can also pass a model_id string for convenience (defaults to Bedrock)
        activity_timeout: Timeout for model activity execution (default 5 minutes)
        retry_policy: Custom retry policy for model activities (optional)

    Example:
        # With provider config
        model = TemporalModelStub(
            BedrockProviderConfig(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0")
        )

        # Simple string convenience (uses Bedrock)
        model = TemporalModelStub("us.anthropic.claude-sonnet-4-20250514-v1:0")
    """

    def __init__(
        self,
        provider_config: ProviderConfig | str,
        activity_timeout: float = 300.0,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        """Initialize the TemporalModelStub.

        Args:
            provider_config: Provider configuration or model ID string
            activity_timeout: Timeout in seconds for model activity (default 5 minutes)
            retry_policy: Optional custom retry policy
        """
        # Allow string convenience for simple cases (defaults to Bedrock)
        if isinstance(provider_config, str):
            self._provider_config: ProviderConfig = BedrockProviderConfig(model_id=provider_config)
        else:
            self._provider_config = provider_config

        self._activity_timeout = activity_timeout
        self._retry_policy = retry_policy or RetryPolicy(
            maximum_attempts=3,
            initial_interval=timedelta(seconds=1),
            maximum_interval=timedelta(seconds=60),
            backoff_coefficient=2.0,
        )

    @property
    def provider_config(self) -> ProviderConfig:
        """Get the provider configuration."""
        return self._provider_config

    def update_config(self, **kwargs: Any) -> None:
        """Update model configuration.

        Note: This updates the provider config which will be used
        in subsequent activity calls.
        """
        # Update provider config fields if they exist
        for key, value in kwargs.items():
            if hasattr(self._provider_config, key):
                setattr(self._provider_config, key, value)

    def get_config(self) -> dict[str, Any]:
        """Get current model configuration."""
        return self._provider_config.model_dump()

    async def stream(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        """Route model inference to Temporal activity.

        This method is called by the Strands Agent event loop when it needs
        model inference. Instead of calling a model directly, we route to
        a Temporal activity for durability.

        Args:
            messages: Conversation history in Strands format
            tool_specs: Tool specifications for the model
            system_prompt: System prompt for the model
            **kwargs: Additional arguments (passed through)

        Yields:
            StreamEvent: Events from the model inference
        """
        # Versioning gate for future streaming changes (e.g., S3-backed session loading)
        # Currently both paths are identical — this establishes the patch point so future
        # changes to model invocation logic can branch safely without breaking replay.
        if workflow.patched("model-stream-v1"):
            activity_input = ModelExecutionInput(
                provider_config=self._provider_config,
                messages=list(messages) if messages else None,
                tool_specs=list(tool_specs) if tool_specs else None,
                system_prompt=system_prompt,
            )

            result: ModelExecutionResult = await workflow.execute_activity(
                execute_model_activity,
                activity_input,
                start_to_close_timeout=timedelta(seconds=self._activity_timeout),
                retry_policy=self._retry_policy,
            )

            for event in result.events:
                yield event
        else:
            # Original behavior for replay compatibility
            activity_input = ModelExecutionInput(
                provider_config=self._provider_config,
                messages=list(messages) if messages else None,
                tool_specs=list(tool_specs) if tool_specs else None,
                system_prompt=system_prompt,
            )

            result: ModelExecutionResult = await workflow.execute_activity(
                execute_model_activity,
                activity_input,
                start_to_close_timeout=timedelta(seconds=self._activity_timeout),
                retry_policy=self._retry_policy,
            )

            for event in result.events:
                yield event

    async def structured_output(
        self,
        output_model: Any,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Structured output is not yet supported in Temporal context.

        This would require additional activity support for schema validation.

        Raises:
            NotImplementedError: Always raises as this is not yet supported
        """
        raise NotImplementedError(
            "Structured output is not yet implemented in Temporal context. "
            "Use regular model calls and parse the response manually."
        )


# =============================================================================
# Durable Agent Factory
# =============================================================================


def create_durable_agent(
    provider_config: ProviderConfig,
    tools: list[Any] | None = None,
    tool_modules: dict[str, str] | None = None,
    system_prompt: str | None = None,
    mcp_servers: list[Any] | None = None,
    model_timeout: float = 300.0,
    tool_timeout: float = 60.0,
    **agent_kwargs: Any,
) -> Any:
    """Create a Strands Agent with full Temporal durability.

    This factory function creates a real Strands Agent configured with:
    - TemporalModelStub: Routes model.stream() calls to activities
    - TemporalToolExecutor: Routes tool execution to activities

    This provides complete durability for both model inference AND tool
    execution while preserving the full Strands Agent event loop and all
    its features (hooks, callbacks, conversation history, etc.).

    Args:
        provider_config: Configuration for the model provider (Bedrock, Anthropic, etc.)
        tools: List of @tool decorated functions to use with the agent
        tool_modules: (Optional) Tool name to module path mapping.
                     If not provided, automatically extracted from tools.
                     Provide this to override auto-discovery for specific tools.
                     Example: {"get_weather": "myapp.tools"}
        system_prompt: System prompt for the agent
        mcp_servers: Optional list of MCP server configurations for tool discovery
        model_timeout: Timeout for model activities in seconds (default 5 minutes)
        tool_timeout: Timeout for tool activities in seconds (default 1 minute)
        **agent_kwargs: Additional arguments passed to Strands Agent constructor

    Returns:
        Configured Strands Agent with durable model and tool execution

    Example with static tools:
        from strands import tool
        from strands_temporal_plugin import create_durable_agent, BedrockProviderConfig

        @tool
        def get_weather(city: str) -> str:
            '''Get weather for a city.'''
            return fetch_weather_api(city)  # I/O is safe - runs in activity

        @workflow.defn
        class WeatherWorkflow:
            @workflow.run
            async def run(self, prompt: str) -> str:
                agent = create_durable_agent(
                    provider_config=BedrockProviderConfig(
                        model_id="us.anthropic.claude-sonnet-4-20250514-v1:0"
                    ),
                    tools=[get_weather],
                    system_prompt="You are a helpful weather assistant.",
                )

                result = await agent.invoke_async(prompt)
                return str(result)

    Example with MCP tools:
        from strands_temporal_plugin import (
            create_durable_agent,
            BedrockProviderConfig,
            StdioMCPServerConfig,
            TemporalToolExecutor,
        )

        @workflow.defn
        class MCPWorkflow:
            @workflow.run
            async def run(self, prompt: str) -> str:
                # For MCP tools, create executor first to discover tools
                executor = TemporalToolExecutor(
                    mcp_servers=[
                        StdioMCPServerConfig(
                            server_id="aws-docs",
                            command="uvx",
                            args=["awslabs.aws-documentation-mcp-server@latest"],
                        ),
                    ],
                )

                # Discover MCP tools via activity
                await executor.discover_mcp_tools()

                # Create agent with discovered tools
                from strands import Agent
                agent = Agent(
                    model=TemporalModelStub(BedrockProviderConfig(...)),
                    tool_executor=executor,
                    tools=executor.get_mcp_tool_specs(),
                    system_prompt="You are a documentation assistant.",
                )

                result = await agent.invoke_async(prompt)
                return str(result)

    Note:
        For MCP tools, it's recommended to use TemporalToolExecutor directly
        since MCP tool discovery must happen in workflow context before
        creating the agent.
    """
    # Import here to avoid circular dependencies and sandbox issues
    from .tool_executor import TemporalToolExecutor
    from strands import Agent

    # Auto-discover tool modules if tools provided
    auto_modules = {}
    if tools:
        try:
            auto_modules = _extract_tool_modules(tools)
        except ValueError:
            # If auto-discovery fails and no explicit mapping provided, re-raise
            if not tool_modules:
                raise
            # Otherwise, continue with explicit mapping

    # Merge: explicit tool_modules takes precedence over auto-discovered
    merged_modules = {**auto_modules, **(tool_modules or {})}

    # Create model stub
    model_stub = TemporalModelStub(
        provider_config=provider_config,
        activity_timeout=model_timeout,
    )

    # Create tool executor
    tool_executor = TemporalToolExecutor(
        tool_modules=merged_modules,
        mcp_servers=mcp_servers,
        activity_timeout=tool_timeout,
    )

    # Create agent with durable model and tool execution
    return Agent(
        model=model_stub,
        tool_executor=tool_executor,
        tools=tools or [],
        system_prompt=system_prompt,
        **agent_kwargs,
    )
