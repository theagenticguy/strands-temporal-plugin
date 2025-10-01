This file is a merged representation of the entire codebase, combined into a single document by Repomix.

# File Summary

## Purpose
This file contains a packed representation of the entire repository's contents.
It is designed to be easily consumable by AI systems for analysis, code review,
or other automated processes.

## File Format
The content is organized as follows:
1. This summary section
2. Repository information
3. Directory structure
4. Repository files (if enabled)
5. Multiple file entries, each consisting of:
  a. A header with the file path (## File: path/to/file)
  b. The full contents of the file in a code block

## Usage Guidelines
- This file should be treated as read-only. Any changes should be made to the
  original repository files, not this packed version.
- When processing this file, use the file path to distinguish
  between different files in the repository.
- Be aware that this file may contain sensitive information. Handle it with
  the same level of security as you would the original repository.

## Notes
- Some files may have been excluded based on .gitignore rules and Repomix's configuration
- Binary files are not included in this packed representation. Please refer to the Repository Structure section for a complete list of file paths, including binary files
- Files matching patterns in .gitignore are excluded
- Files matching default ignore patterns are excluded
- Files are sorted by Git change count (files with more changes are at the bottom)

# Directory Structure
```
strands_temporal_plugin/
  activities/
    model.py
    tools.py
  adapters/
    model_adapter.py
  workflows/
    __init__.py
    agent.py
    strands_agent.py
  __init__.py
  helpers.py
  hooks.py
  logging.py
  plugin.py
  providers.py
  pydantic_converter.py
  registry.py
  types.py
```

# Files

## File: strands_temporal_plugin/activities/model.py
````python
"""Model inference activity for Temporal workflows."""

from ..providers import create_model_from_config
from ..types import ModelCallInput, ModelCallResult, StopReason, Usage
from strands.event_loop.streaming import process_stream
from temporalio import activity


@activity.defn(name="model_infer_activity")
async def model_infer_activity(input_data: ModelCallInput) -> ModelCallResult:
    """Temporal activity that performs model inference using Strands models.

    This activity creates the appropriate Strands model based on the provider
    configuration, calls the model's stream method, and aggregates the streaming
    response using Strands' process_stream utility.

    Args:
        input_data: Model call input containing messages, tool specs, and provider config

    Returns:
        Model call result with aggregated text, usage, and stop reason

    Raises:
        Exception: If model inference fails
    """
    try:
        # Create model instance from provider configuration
        model = create_model_from_config(input_data.provider)

        # Use Strands types directly (no conversion needed)
        strands_messages = input_data.messages
        tool_specs = input_data.tool_specs

        # Call model.stream() with the input parameters
        stream = model.stream(messages=strands_messages, tool_specs=tool_specs, system_prompt=input_data.system_prompt)

        # Use Strands' process_stream to aggregate the streaming response
        text_content = ""
        usage = Usage()
        stop_reason = StopReason.END_TURN

        async for event in process_stream(stream):
            if "callback" in event:
                # Handle streaming callbacks
                callback_data = event["callback"]
                if "data" in callback_data and not callback_data.get("reasoning", False):
                    # This is text content (not reasoning content)
                    text_content += callback_data["data"]

            elif "stop" in event:
                # Final event with aggregated results
                stop_reason_str, final_message, usage_data, metrics_data = event["stop"]

                # Extract text content from final message
                final_text = ""
                for content_block in final_message["content"]:
                    if "text" in content_block:
                        final_text += content_block["text"]

                # Use final text if we have it, otherwise use accumulated text
                if final_text:
                    text_content = final_text

                # Map stop reason
                if stop_reason_str == "tool_use":
                    stop_reason = StopReason.TOOL_USE
                elif stop_reason_str == "max_tokens":
                    stop_reason = StopReason.MAX_STEPS
                elif stop_reason_str == "error":
                    stop_reason = StopReason.ERROR
                else:
                    stop_reason = StopReason.END_TURN

                # Extract usage information - handle various formats
                try:
                    if hasattr(usage_data, "inputTokens"):
                        # Object form from Strands
                        usage = Usage(
                            input_tokens=usage_data.inputTokens,
                            output_tokens=usage_data.outputTokens,
                            total_tokens=usage_data.totalTokens,
                        )
                    elif isinstance(usage_data, dict):
                        # Try camelCase keys first (Strands format)
                        if "inputTokens" in usage_data:
                            usage = Usage(
                                input_tokens=usage_data.get("inputTokens", 0),
                                output_tokens=usage_data.get("outputTokens", 0),
                                total_tokens=usage_data.get("totalTokens", 0),
                            )
                        else:
                            # Try snake_case keys (fallback)
                            usage = Usage(
                                input_tokens=usage_data.get("input_tokens", 0),
                                output_tokens=usage_data.get("output_tokens", 0),
                                total_tokens=usage_data.get("total_tokens", 0),
                            )
                    else:
                        # Default empty usage
                        usage = Usage()
                except Exception:
                    # Fallback to empty usage
                    usage = Usage()

        return ModelCallResult(text=text_content, usage=usage, stop_reason=stop_reason)

    except Exception as e:
        # Return error result instead of raising exception to maintain workflow determinism
        return ModelCallResult(
            text=f"Error during model inference: {str(e)}", usage=Usage(), stop_reason=StopReason.ERROR
        )
````

## File: strands_temporal_plugin/activities/tools.py
````python
from __future__ import annotations

from ..registry import _resolve
from ..types import ToolCallInput, ToolCallResult
from temporalio import activity
from typing import Any


@activity.defn(name="call_registered_tool_activity")
async def call_registered_tool_activity(call: ToolCallInput) -> ToolCallResult:
    """Dispatch a registered tool by name.

    Tools are regular Python callables registered via `register_tool` at worker startup.
    Returns a Strands-like content list with a single text block, or structured JSON in `toolResult` form.
    """
    func = _resolve(call.name)
    try:
        result = func(**call.arguments)
    except TypeError as e:
        # Provide clearer error messages for bad tool inputs
        raise TypeError(f"Error invoking tool '{call.name}': {e}") from e

    # Normalize result into content blocks that Strands understands
    content: list[dict[str, Any]] = []
    if isinstance(result, str):
        content.append({"text": result})
    elif isinstance(result, (int, float, bool)):
        content.append({"text": str(result)})
    elif isinstance(result, dict):
        content.append({"toolResult": result})
    else:
        # Fallback to JSON dumping of arbitrary structures
        import json

        try:
            content.append({"toolResult": json.loads(json.dumps(result, default=str))})
        except Exception:
            content.append({"text": str(result)})

    # Cast to ToolResultContent for type compatibility
    from strands.types.tools import ToolResultContent
    from typing import cast

    return ToolCallResult(content=cast(list[ToolResultContent], content))
````

## File: strands_temporal_plugin/adapters/model_adapter.py
````python
from __future__ import annotations

from ..types import ModelCallInput, ModelCallResult, ProviderConfig
from collections.abc import AsyncIterable
from datetime import timedelta

# Strands imports (runtime dependency)
from strands.models import Model  # type: ignore[import-not-found]
from strands.types.content import Messages  # type: ignore[import-not-found]
from strands.types.streaming import StreamEvent  # type: ignore[import-not-found]
from strands.types.tools import ToolSpec  # type: ignore[import-not-found]
from temporalio import workflow
from typing import Any


class TemporalDelegatingModel(Model):
    """A Strands Model that delegates inference to a Temporal activity.

    This keeps workflows deterministic. The activity performs vendor I/O and streams
    tokens; we return a **valid** StreamEvent sequence from the workflow.
    """

    def __init__(self, provider: ProviderConfig, *, chunk_chars: int = 120) -> None:
        self._provider = provider
        self._chunk_chars = max(16, chunk_chars)

    async def stream(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[StreamEvent]:
        # Use Strands types directly (no conversion needed)
        input = ModelCallInput(
            messages=messages,
            tool_specs=tool_specs,
            system_prompt=system_prompt,
            provider=self._provider,
        )

        # Execute activity with sensible timeouts; retry policy is configured on worker or via start options.
        result: ModelCallResult = await workflow.execute_activity(
            "model_infer_activity",
            input,
            schedule_to_close_timeout=timedelta(minutes=5),
            start_to_close_timeout=timedelta(minutes=4, seconds=30),
        )

        # Emit a minimal-but-valid Strands stream from the full text returned by the activity.
        # This intentionally simulates streaming on the workflow side to keep determinism.

        # Start message event
        yield {"messageStart": {"role": "assistant"}}

        txt = result.text or ""
        if txt:
            # Start content block - use minimal valid structure
            yield {"contentBlockStart": {"contentBlockIndex": 0}}

            # Stream text in chunks
            for i in range(0, len(txt), self._chunk_chars):
                piece = txt[i : i + self._chunk_chars]
                if piece:
                    yield {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": piece}}}

            # End content block
            yield {"contentBlockStop": {"contentBlockIndex": 0}}

        # End message with stop reason - map to Strands StopReason values
        strands_stop_reason = "end_turn"  # Default
        if result.stop_reason == "tool_use":
            strands_stop_reason = "tool_use"
        elif result.stop_reason == "max_steps":
            strands_stop_reason = "max_tokens"
        elif result.stop_reason == "error":
            strands_stop_reason = "end_turn"

        yield {"messageStop": {"stopReason": strands_stop_reason}}

    def get_config(self) -> dict[str, Any]:
        """Get the current model configuration."""
        return {
            "provider": self._provider.model_dump(),
            "chunk_chars": self._chunk_chars,
        }

    def update_config(self, **kwargs: Any) -> None:
        """Update the model configuration."""
        if "provider" in kwargs:
            self._provider = kwargs["provider"]
        if "chunk_chars" in kwargs:
            self._chunk_chars = max(16, kwargs["chunk_chars"])

    def structured_output(self, *args: Any, **kwargs: Any) -> Any:
        """Structured output method (placeholder for Strands compatibility)."""
        raise NotImplementedError("Structured output not yet implemented for TemporalDelegatingModel")
````

## File: strands_temporal_plugin/workflows/__init__.py
````python
"""Strands Temporal Plugin Workflows.

This module contains Temporal workflows for orchestrating Strands agent operations.
"""

from .agent import AgentWorkflow
from .strands_agent import StrandsAgentWorkflow, execute_conversation_turn, get_or_create_agent_handle

__all__ = ["AgentWorkflow", "StrandsAgentWorkflow", "execute_conversation_turn", "get_or_create_agent_handle"]
````

## File: strands_temporal_plugin/workflows/agent.py
````python
"""Agent Event Loop Workflow.

This module implements the core Temporal workflow that orchestrates the Strands agent event loop,
coordinating model inference and tool execution through durable activities.
"""

from __future__ import annotations

import temporalio.workflow as workflow

# Import plugin types and Strands types (now safe with sandbox passthrough)
from ..types import (
    EchoProviderConfig,
    ModelCallInput,
    ProviderConfig,
    StopReason,
    ToolCallInput,
    ToolCallResult,
    TurnInput,
    TurnResult,
    Usage,
)
from datetime import timedelta
from strands.types.content import Message, Messages
from strands.types.tools import ToolResult
from temporalio.common import RetryPolicy
from typing import Any


@workflow.defn
class AgentWorkflow:
    """Temporal workflow that orchestrates the Strands agent event loop.

    This workflow coordinates model inference and tool execution through durable activities,
    maintaining conversation state and handling multi-turn interactions.
    """

    def __init__(self) -> None:
        """Initialize the agent workflow."""
        self.provider_config: ProviderConfig | None = None

    @workflow.run
    async def run(self, input_data: TurnInput) -> TurnResult:
        """Run the agent event loop workflow.

        Args:
            input_data: The turn input containing session ID and optional user message

        Returns:
            TurnResult containing the final response and usage metrics
        """
        # Initialize conversation state using Strands types
        messages: Messages = []
        total_usage = Usage()

        # Add user message if provided
        if input_data.user_message:
            user_message = self._create_user_message(input_data.user_message)
            messages.append(user_message)

        # Agent event loop: model -> tools -> model until done
        final_assistant_text = ""

        while True:
            # Use provider from input, fall back to instance provider, then default to Echo
            current_provider = input_data.provider or self.provider_config or EchoProviderConfig()

            # Call model inference activity (activity handles Strands type conversion)
            model_result = await workflow.execute_activity(
                "model_infer_activity",
                ModelCallInput(messages=messages, provider=current_provider),
                schedule_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=1),
                    maximum_interval=timedelta(seconds=10),
                    maximum_attempts=3,
                ),
            )

            # Accumulate usage metrics - handle both object and dict deserialization
            if hasattr(model_result, "usage"):
                # Object form
                usage = model_result.usage
                if hasattr(usage, "input_tokens"):
                    total_usage.input_tokens += usage.input_tokens
                    total_usage.output_tokens += usage.output_tokens
                    total_usage.total_tokens += usage.total_tokens
                else:
                    # Usage is dict
                    total_usage.input_tokens += usage.get("input_tokens", 0)
                    total_usage.output_tokens += usage.get("output_tokens", 0)
                    total_usage.total_tokens += usage.get("total_tokens", 0)
            else:
                # Dict form
                usage = model_result.get("usage", {})
                total_usage.input_tokens += usage.get("input_tokens", 0)
                total_usage.output_tokens += usage.get("output_tokens", 0)
                total_usage.total_tokens += usage.get("total_tokens", 0)

            # Get text - handle both object and dict deserialization
            if hasattr(model_result, "text"):
                text = model_result.text
            else:
                text = model_result.get("text", "")

            # Add assistant message to conversation
            assistant_message = self._create_assistant_message(text)
            messages.append(assistant_message)
            final_assistant_text = text

            # Check if model requested tool use
            tool_uses = self._extract_tool_uses(assistant_message)

            if not tool_uses:
                # No tools requested, we're done
                break

            # Get stop reason - handle both object and dict deserialization
            if hasattr(model_result, "stop_reason"):
                stop_reason = model_result.stop_reason
            else:
                stop_reason = model_result.get("stop_reason", StopReason.END_TURN)

            if stop_reason == StopReason.MAX_STEPS:
                # Hit max steps, break to avoid infinite loop
                break

            # Execute tools in parallel
            tool_tasks = []
            for tool_use in tool_uses:
                tool_input = ToolCallInput(name=tool_use["name"], arguments=tool_use.get("input", {}))

                task = workflow.execute_activity(
                    "call_registered_tool_activity",
                    tool_input,
                    schedule_to_close_timeout=timedelta(minutes=2),
                    retry_policy=RetryPolicy(
                        initial_interval=timedelta(seconds=1),
                        maximum_interval=timedelta(seconds=5),
                        maximum_attempts=2,
                    ),
                )
                tool_tasks.append((tool_use, task))

            # Wait for all tools to complete
            tool_results = []
            for tool_use, task in tool_tasks:
                try:
                    tool_result = await task
                    tool_results.append((tool_use, tool_result))
                except Exception as e:
                    # Create error result for failed tool
                    error_result = ToolCallResult(content=[{"text": f"Tool execution failed: {str(e)}"}])
                    tool_results.append((tool_use, error_result))

            # Add tool results to conversation
            for tool_use, tool_result in tool_results:
                tool_result_message = self._create_tool_result_message(tool_use["toolUseId"], tool_result)
                messages.append(tool_result_message)

        # Determine final stop reason - handle both object and dict deserialization
        if hasattr(model_result, "stop_reason"):
            final_stop_reason = model_result.stop_reason
        else:
            final_stop_reason = model_result.get("stop_reason", StopReason.END_TURN)

        result = TurnResult(
            session_id=input_data.session_id,
            stop_reason=final_stop_reason,
            assistant_text=final_assistant_text,
            usage=total_usage,
        )

        return result

    def _create_user_message(self, text: str) -> Message:
        """Create a user message using Strands format."""
        return {"role": "user", "content": [{"text": text}]}

    def _create_assistant_message(self, text: str) -> Message:
        """Create an assistant message using Strands format."""
        return {"role": "assistant", "content": [{"text": text}]}

    def _create_tool_result_message(self, tool_use_id: str, tool_result: ToolCallResult) -> Message:
        """Create a tool result message using Strands format."""
        # Create proper Strands ToolResult
        strands_tool_result: ToolResult = {
            "toolUseId": tool_use_id,
            "status": "success",  # Tool activity handles errors internally
            "content": tool_result.content,
        }
        return {
            "role": "user",
            "content": [{"toolResult": strands_tool_result}],
        }

    def _extract_tool_uses(self, assistant_message: Message) -> list[dict[str, Any]]:
        """Extract tool use requests from an assistant message."""
        tool_uses = []

        content_blocks = assistant_message.get("content", [])
        for block in content_blocks:
            if "toolUse" in block:
                tool_use = block["toolUse"]
                # Ensure required fields are present
                if "toolUseId" in tool_use and "name" in tool_use:
                    tool_uses.append(tool_use)

        return tool_uses
````

## File: strands_temporal_plugin/workflows/strands_agent.py
````python
"""High-level Strands agent workflow implementation.

This module provides the main StrandsAgentWorkflow class that users interact with
directly, providing a familiar interface while leveraging Temporal's durable execution.
"""

from __future__ import annotations

import temporalio.workflow as workflow

# Import plugin types and Strands types (now safe with sandbox passthrough)
from ..types import BedrockProviderConfig, ProviderConfig, TurnInput, TurnResult
from .agent import AgentWorkflow
from strands.types.content import Message, Messages
from typing import Any


class AgentState:
    """State maintained by the StrandsAgentWorkflow across executions."""

    def __init__(self, default_provider: ProviderConfig | None = None):
        # Session ID -> conversation history (using Strands types)
        self.conversations: dict[str, Messages] = {}

        # Session-specific provider configurations
        self.provider_configs: dict[str, ProviderConfig] = {}

        # Default provider configuration
        self.default_provider = default_provider or BedrockProviderConfig(
            model_id="us.anthropic.claude-sonnet-4-20250514-v1:0"
        )

        # Agent metadata and configuration
        self.agent_metadata: dict[str, Any] = {}


@workflow.defn
class StrandsAgentWorkflow:
    """Main workflow class providing user-friendly interface for Strands agents.

    This workflow provides session management, conversation continuity, and
    dynamic provider configuration while delegating to AgentWorkflow for
    actual agent execution.
    """

    def __init__(self) -> None:
        """Initialize the workflow with default state."""
        self.state = AgentState()

    @workflow.run
    async def run_conversation(self, input_data: TurnInput) -> TurnResult:
        """Execute a conversation turn for the given session.

        Args:
            input_data: Turn input containing session ID and user message

        Returns:
            Result of the conversation turn
        """
        session_id = input_data.session_id

        # Get or create conversation history for this session
        if session_id not in self.state.conversations:
            self.state.conversations[session_id] = []

        # Get provider configuration for this session (input provider takes priority)
        provider_config = input_data.provider or self._get_provider_for_session(session_id)

        # Add user message to conversation history if provided
        if input_data.user_message:
            user_message = self._create_user_message(input_data.user_message)
            self.state.conversations[session_id].append(user_message)

        # Create enhanced input with conversation context and provider config
        enhanced_input = TurnInput(
            session_id=session_id, user_message=input_data.user_message, provider=provider_config
        )

        try:
            # Delegate to AgentWorkflow for actual execution
            result = await workflow.execute_child_workflow(
                AgentWorkflow.run,
                enhanced_input,
                id=f"agent-execution-{session_id}-{workflow.now().timestamp()}",
                task_queue=workflow.info().task_queue,
            )

            # Add assistant response to conversation history
            if result.assistant_text:
                assistant_message = self._create_assistant_message(result.assistant_text)
                self.state.conversations[session_id].append(assistant_message)

            return result

        except Exception:
            raise

    @workflow.signal
    async def configure_provider(self, session_id: str, provider: ProviderConfig) -> None:
        """Configure the provider for a specific session."""
        self.state.provider_configs[session_id] = provider

    @workflow.signal
    async def set_default_provider(self, provider: ProviderConfig) -> None:
        """Set the default provider configuration for new sessions."""
        self.state.default_provider = provider

    @workflow.signal
    async def reset_conversation(self, session_id: str) -> None:
        """Reset the conversation history for a session."""
        if session_id in self.state.conversations:
            del self.state.conversations[session_id]

    @workflow.signal
    async def update_agent_metadata(self, key: str, value: Any) -> None:
        """Update agent metadata."""
        self.state.agent_metadata[key] = value

    @workflow.query
    def get_conversation_history(self, session_id: str) -> Messages:
        """Get the conversation history for a session."""
        return self.state.conversations.get(session_id, [])

    @workflow.query
    def get_session_provider(self, session_id: str) -> ProviderConfig:
        """Get the provider configuration for a session."""
        return self._get_provider_for_session(session_id)

    @workflow.query
    def get_all_sessions(self) -> list[str]:
        """Get all active session IDs."""
        return list(self.state.conversations.keys())

    @workflow.query
    def get_agent_metadata(self) -> dict[str, Any]:
        """Get all agent metadata."""
        return self.state.agent_metadata.copy()

    def _get_provider_for_session(self, session_id: str) -> ProviderConfig:
        """Get the provider configuration for a session."""
        return self.state.provider_configs.get(session_id, self.state.default_provider)

    def _create_user_message(self, text: str) -> Message:
        """Create a user message using Strands format."""
        return {"role": "user", "content": [{"text": text}]}

    def _create_assistant_message(self, text: str) -> Message:
        """Create an assistant message using Strands format."""
        return {"role": "assistant", "content": [{"text": text}]}


# Convenience functions for common workflow operations


async def execute_conversation_turn(
    client,
    session_id: str,
    user_message: str,
    workflow_id: str | None = None,
    task_queue: str = "strands-agents",
    provider: ProviderConfig | None = None,
) -> TurnResult:
    """Execute a single conversation turn."""
    if workflow_id is None:
        workflow_id = f"agent-session-{session_id}"

    return await client.execute_workflow(
        StrandsAgentWorkflow.run_conversation,
        TurnInput(session_id=session_id, user_message=user_message, provider=provider),
        id=workflow_id,
        task_queue=task_queue,
    )


async def get_or_create_agent_handle(
    client, session_id: str, workflow_id: str | None = None, task_queue: str = "strands-agents"
):
    """Get or create a workflow handle for an agent session."""
    if workflow_id is None:
        workflow_id = f"agent-session-{session_id}"

    try:
        # Try to get existing workflow handle
        return client.get_workflow_handle(workflow_id)
    except Exception:
        # If workflow doesn't exist, start a new one
        # This will be started on first conversation turn
        return client.get_workflow_handle_for(StrandsAgentWorkflow.run_conversation, workflow_id)
````

## File: strands_temporal_plugin/__init__.py
````python
"""Strands Temporal Plugin.

This plugin provides durable execution capabilities for Strands AI agents using
Temporal IO. It enables agents to maintain state and recover from failures while
providing the same familiar interface as standard Strands agents.

## Quick Start

```python
from strands_temporal_plugin import (
    StrandsTemporalPlugin,
    create_bedrock_agent,
    setup_temporal_client,
    setup_temporal_worker,
)

# Create an agent with temporal durability
agent = create_bedrock_agent(model_id="anthropic.claude-3-sonnet-20240229-v1:0", tools=[calculator, web_search])

# Set up Temporal infrastructure
client = await setup_temporal_client()
worker = setup_temporal_worker(client, task_queue="strands-agents")
await worker.run()
```

## Main Components

- **StrandsTemporalPlugin**: Main plugin for configuring Temporal clients and workers
- **StrandsAgentWorkflow**: High-level workflow for agent execution with session management
- **TemporalDelegatingModel**: Model adapter that routes calls through Temporal activities
- **Helper Functions**: Convenience functions for common setup patterns
"""

# Version information
__version__ = "0.1.0"
__author__ = "Strands Team"
__email__ = "support@strands.ai"

# Core plugin and workflow classes
from .plugin import StrandsTemporalPlugin, create_strands_temporal_plugin
from .workflows import (
    AgentWorkflow,
    StrandsAgentWorkflow,
    execute_conversation_turn,
    get_or_create_agent_handle,
)

# Model adapter for Temporal integration
from .adapters.model_adapter import TemporalDelegatingModel

# Type definitions for user code
from .types import (
    # Provider configurations
    ProviderConfig,
    BedrockProviderConfig,
    EchoProviderConfig,
    # Input/Output types
    TurnInput,
    TurnResult,
    ModelCallInput,
    ModelCallResult,
    ToolCallInput,
    ToolCallResult,
    # Configuration types
    ModelActivityParameters,
    Usage,
    StopReason,
)

# Re-export Strands types for convenience
from strands.types.content import Message, Messages
from strands.types.tools import ToolSpec, ToolResult

# Tool registration utilities
from .registry import register_tool, get_registered_tools

# Pydantic converter for advanced serialization
from .pydantic_converter import pydantic_data_converter, PydanticPayloadConverter, ToJsonOptions

# Helper functions for common patterns
from .helpers import (
    # Agent creation helpers
    create_agent_with_temporal_model,
    create_bedrock_agent,
    create_echo_agent,
    # Infrastructure setup helpers
    setup_temporal_client,
    setup_temporal_worker,
    create_complete_temporal_setup,
    # Configuration and validation
    validate_provider_config,
    # Pre-configured defaults
    DEFAULT_MODEL_PARAMS,
    DEFAULT_BEDROCK_CONFIG,
    DEFAULT_ECHO_CONFIG,
    DEFAULT_PLUGIN,
)

# Hook system for observability and extensibility
from .hooks import (
    get_hook_registry,
    emit_workflow_event,
    emit_activity_event,
    initialize_default_hooks,
    TemporalHookRegistry,
    TemporalHookContext,
    DefaultHookProvider,
    hook_context,
)

# Logging utilities
from .logging import get_logger

# Public API exports
__all__ = [
    # Version information
    "__version__",
    # Core classes
    "StrandsTemporalPlugin",
    "create_strands_temporal_plugin",
    "StrandsAgentWorkflow",
    "AgentWorkflow",
    "TemporalDelegatingModel",
    # Workflow helpers
    "execute_conversation_turn",
    "get_or_create_agent_handle",
    # Types
    "ProviderConfig",
    "BedrockProviderConfig",
    "EchoProviderConfig",
    "TurnInput",
    "TurnResult",
    "ModelCallInput",
    "ModelCallResult",
    "ToolCallInput",
    "ToolCallResult",
    "ModelActivityParameters",
    "Usage",
    "StopReason",
    # Re-exported Strands types
    "Message",
    "Messages",
    "ToolSpec",
    "ToolResult",
    # Tool registration
    "register_tool",
    "get_registered_tools",
    # Helper functions
    "create_agent_with_temporal_model",
    "create_bedrock_agent",
    "create_echo_agent",
    "setup_temporal_client",
    "setup_temporal_worker",
    "create_complete_temporal_setup",
    "validate_provider_config",
    # Default configurations
    "DEFAULT_MODEL_PARAMS",
    "DEFAULT_BEDROCK_CONFIG",
    "DEFAULT_ECHO_CONFIG",
    "DEFAULT_PLUGIN",
    # Hook system
    "get_hook_registry",
    "emit_workflow_event",
    "emit_activity_event",
    "initialize_default_hooks",
    "TemporalHookRegistry",
    "TemporalHookContext",
    "DefaultHookProvider",
    "hook_context",
    # Logging
    "get_logger",
    # Pydantic converter
    "pydantic_data_converter",
    "PydanticPayloadConverter",
    "ToJsonOptions",
]
````

## File: strands_temporal_plugin/helpers.py
````python
"""Helper functions for common Strands Temporal plugin usage patterns.

This module provides convenience functions that simplify common setup scenarios
and reduce boilerplate code when integrating Strands agents with Temporal workflows.
"""

from __future__ import annotations

from .adapters.model_adapter import TemporalDelegatingModel
from .plugin import StrandsTemporalPlugin
from .types import BedrockProviderConfig, EchoProviderConfig, ModelActivityParameters, ProviderConfig
from .workflows import AgentWorkflow, StrandsAgentWorkflow
from strands import Agent
from temporalio.client import Client
from temporalio.worker import Worker
from typing import Any


def create_agent_with_temporal_model(
    provider_config: ProviderConfig,
    tools: list[Any] | None = None,
    model_params: ModelActivityParameters | None = None,
    **agent_kwargs: Any,
) -> Agent:
    """Create a Strands Agent with Temporal model delegation.

    This convenience function creates an Agent that uses a TemporalDelegatingModel
    to route model calls through Temporal activities for durability.

    Args:
        provider_config: Configuration for the model provider
        tools: List of tools to provide to the agent
        model_params: Parameters for configuring model activities
        **agent_kwargs: Additional arguments passed to Agent constructor

    Returns:
        Agent instance configured with Temporal model delegation

    Example:
        ```python
        agent = create_agent_with_temporal_model(
            provider_config=BedrockProviderConfig(model_id="anthropic.claude-3-sonnet-20240229-v1:0"),
            tools=[calculator, web_search],
        )

        result = agent("What's 2 + 2?")
        ```
    """
    model = TemporalDelegatingModel(
        provider=provider_config,
    )

    return Agent(model=model, tools=tools or [], **agent_kwargs)


def create_bedrock_agent(
    model_id: str,
    region: str | None = None,
    tools: list[Any] | None = None,
    inference_config: dict[str, Any] | None = None,
    **agent_kwargs: Any,
) -> Agent:
    """Create a Strands Agent with Bedrock model provider.

    Convenience function for creating agents powered by Amazon Bedrock models
    with Temporal durability.

    Args:
        model_id: Bedrock model identifier (e.g., "anthropic.claude-3-sonnet-20240229-v1:0")
        region: AWS region for Bedrock (defaults to agent's default region)
        tools: List of tools to provide to the agent
        inference_config: Bedrock inference configuration parameters
        **agent_kwargs: Additional arguments passed to Agent constructor

    Returns:
        Agent instance configured with Bedrock provider

    Example:
        ```python
        agent = create_bedrock_agent(
            model_id="anthropic.claude-3-sonnet-20240229-v1:0", region="us-west-2", tools=[calculator, web_search]
        )
        ```
    """
    provider_config = BedrockProviderConfig(
        model_id=model_id,
        region=region,
        inference_config=inference_config,
    )

    return create_agent_with_temporal_model(provider_config=provider_config, tools=tools, **agent_kwargs)


def create_echo_agent(
    tools: list[Any] | None = None,
    sleep_s: float = 0.0,
    chunk_chars: int = 20,
    **agent_kwargs: Any,
) -> Agent:
    """Create a Strands Agent with Echo model provider for testing.

    Convenience function for creating agents with the Echo provider, which
    is useful for testing and development without requiring external model APIs.

    Args:
        tools: List of tools to provide to the agent
        sleep_s: Simulated latency per chunk (seconds)
        chunk_chars: Chunk size for simulating streaming
        **agent_kwargs: Additional arguments passed to Agent constructor

    Returns:
        Agent instance configured with Echo provider

    Example:
        ```python
        agent = create_echo_agent(
            tools=[calculator],
            sleep_s=0.1,  # Simulate some latency
            chunk_chars=10,
        )
        ```
    """
    provider_config = EchoProviderConfig(
        sleep_s=sleep_s,
        chunk_chars=chunk_chars,
    )

    return create_agent_with_temporal_model(provider_config=provider_config, tools=tools, **agent_kwargs)


async def setup_temporal_client(
    target_host: str = "localhost:7233",
    plugin: StrandsTemporalPlugin | None = None,
    default_provider: ProviderConfig | None = None,
    model_params: ModelActivityParameters | None = None,
    **client_kwargs: Any,
) -> Client:
    """Set up a Temporal client with Strands plugin configuration.

    This helper function creates and configures a Temporal client with the
    StrandsTemporalPlugin, handling common setup scenarios.

    Args:
        target_host: Temporal server address
        plugin: Pre-configured plugin instance (creates default if None)
        default_provider: Default provider config for new plugin
        model_params: Model activity parameters for new plugin
        **client_kwargs: Additional arguments passed to Client.connect()

    Returns:
        Configured Temporal client instance

    Example:
        ```python
        client = await setup_temporal_client(
            target_host="localhost:7233",
            default_provider=BedrockProviderConfig(model_id="anthropic.claude-3-sonnet-20240229-v1:0"),
        )
        ```
    """
    if plugin is None:
        plugin = StrandsTemporalPlugin(
            default_provider=default_provider,
            model_params=model_params,
        )

    return await Client.connect(target_host, plugins=[plugin], **client_kwargs)


def setup_temporal_worker(
    client: Client,
    task_queue: str,
    workflows: list[Any] | None = None,
    plugin: StrandsTemporalPlugin | None = None,
    **worker_kwargs: Any,
) -> Worker:
    """Set up a Temporal worker with Strands plugin configuration.

    This helper function creates a Temporal worker configured for Strands
    agent execution with proper activity registration.

    Args:
        client: Temporal client instance
        task_queue: Task queue name for the worker
        workflows: List of workflow classes (includes StrandsAgentWorkflow by default)
        plugin: Plugin instance (uses client's plugin if None)
        **worker_kwargs: Additional arguments passed to Worker constructor

    Returns:
        Configured Temporal worker instance

    Example:
        ```python
        worker = setup_temporal_worker(
            client=client, task_queue="strands-agents", workflows=[StrandsAgentWorkflow, CustomWorkflow]
        )

        await worker.run()
        ```
    """
    if workflows is None:
        workflows = [StrandsAgentWorkflow, AgentWorkflow]
    else:
        # Ensure both required workflows are registered
        if StrandsAgentWorkflow not in workflows:
            workflows = [StrandsAgentWorkflow] + list(workflows)
        if AgentWorkflow not in workflows:
            workflows = [AgentWorkflow] + list(workflows)

    return Worker(client, task_queue=task_queue, workflows=workflows, **worker_kwargs)


async def create_complete_temporal_setup(
    target_host: str = "localhost:7233",
    task_queue: str = "strands-agents",
    default_provider: ProviderConfig | None = None,
    model_params: ModelActivityParameters | None = None,
    workflows: list[Any] | None = None,
    **kwargs: Any,
) -> tuple[Client, Worker, StrandsTemporalPlugin]:
    """Create a complete Temporal setup with client, worker, and plugin.

    This is a one-stop helper function that sets up everything needed for
    Strands agent execution with Temporal durability.

    Args:
        target_host: Temporal server address
        task_queue: Task queue name for the worker
        default_provider: Default provider configuration
        model_params: Model activity parameters
        workflows: Additional workflow classes
        **kwargs: Additional configuration options

    Returns:
        Tuple of (client, worker, plugin) ready for use

    Example:
        ```python
        client, worker, plugin = await create_complete_temporal_setup(
            default_provider=BedrockProviderConfig(model_id="anthropic.claude-3-sonnet-20240229-v1:0"),
            task_queue="my-agents",
        )

        # Start the worker
        await worker.run()
        ```
    """
    plugin = StrandsTemporalPlugin(
        default_provider=default_provider,
        model_params=model_params,
    )

    client = await setup_temporal_client(target_host=target_host, plugin=plugin, **kwargs.get("client_kwargs", {}))

    worker = setup_temporal_worker(
        client=client, task_queue=task_queue, workflows=workflows, plugin=plugin, **kwargs.get("worker_kwargs", {})
    )

    return client, worker, plugin


def validate_provider_config(config: ProviderConfig) -> bool:
    """Validate a provider configuration.

    Args:
        config: Provider configuration to validate

    Returns:
        True if configuration is valid

    Raises:
        ValueError: If configuration is invalid

    Example:
        ```python
        config = BedrockProviderConfig(model_id="invalid-model")
        try:
            validate_provider_config(config)
        except ValueError as e:
            print(f"Invalid config: {e}")
        ```
    """
    if config.type == "bedrock":
        if isinstance(config, BedrockProviderConfig):
            if not config.model_id:
                raise ValueError("Bedrock provider requires model_id")
            # Basic model ID format validation
            if not isinstance(config.model_id, str) or len(config.model_id) < 1:
                raise ValueError("Bedrock model_id must be a non-empty string")

    elif config.type == "echo":
        if isinstance(config, EchoProviderConfig):
            if config.sleep_s < 0:
                raise ValueError("Echo provider sleep_s must be non-negative")
            if config.chunk_chars < 1:
                raise ValueError("Echo provider chunk_chars must be positive")

    return True


# Convenience aliases for common configurations
DEFAULT_MODEL_PARAMS = ModelActivityParameters()

DEFAULT_BEDROCK_CONFIG = BedrockProviderConfig(model_id="anthropic.claude-3-sonnet-20240229-v1:0")

DEFAULT_ECHO_CONFIG = EchoProviderConfig()

DEFAULT_PLUGIN = StrandsTemporalPlugin(
    default_provider=DEFAULT_BEDROCK_CONFIG,
    model_params=DEFAULT_MODEL_PARAMS,
)
````

## File: strands_temporal_plugin/hooks.py
````python
"""Hooks and extensibility system for Strands Temporal plugin.

This module provides the integration between Strands' hook system and Temporal's
distributed execution model, enabling observability and extensibility across
workflow and activity boundaries.
"""

from __future__ import annotations

import temporalio.activity
import temporalio.workflow
from collections.abc import Callable
from contextlib import contextmanager
from strands.hooks import HookProvider, HookRegistry
from strands.hooks.events import AfterInvocationEvent, AgentInitializedEvent, BeforeInvocationEvent, MessageAddedEvent
from typing import Any, TypeVar
from uuid import uuid4


# Import experimental events that may not be available in all versions
try:
    from strands.experimental.hooks.events import (
        AfterModelInvocationEvent,
        AfterToolInvocationEvent,
        BeforeModelInvocationEvent,
        BeforeToolInvocationEvent,
    )

    _EXPERIMENTAL_HOOKS_AVAILABLE = True
except ImportError:
    _EXPERIMENTAL_HOOKS_AVAILABLE = False
    # Create placeholder classes to avoid import errors
    BeforeModelInvocationEvent = None
    AfterModelInvocationEvent = None
    BeforeToolInvocationEvent = None
    AfterToolInvocationEvent = None


T = TypeVar("T")

# Context variable keys for hook context propagation
HOOK_CONTEXT_KEY = "strands_temporal_hook_context"
HOOK_TRACE_ID_KEY = "strands_temporal_hook_trace_id"


class TemporalHookContext:
    """Context for propagating hook state across Temporal boundaries."""

    def __init__(self, trace_id: str | None = None):
        self.trace_id = trace_id or str(uuid4())
        self.event_sequence: list[dict[str, Any]] = []
        self.metadata: dict[str, Any] = {}

    def add_event(self, event_type: str, event_data: dict[str, Any]) -> None:
        """Add an event to the context trace."""
        self.event_sequence.append(
            {
                "event_type": event_type,
                "event_data": event_data,
                "timestamp": temporalio.workflow.now().timestamp() if temporalio.workflow.in_workflow() else None,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize context for Temporal propagation."""
        return {"trace_id": self.trace_id, "event_sequence": self.event_sequence, "metadata": self.metadata}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TemporalHookContext:
        """Deserialize context from Temporal data."""
        context = cls(trace_id=data.get("trace_id"))
        context.event_sequence = data.get("event_sequence", [])
        context.metadata = data.get("metadata", {})
        return context


class TemporalHookRegistry:
    """Hook registry that works with Temporal's distributed execution model."""

    def __init__(self):
        self._hook_registry = HookRegistry()
        self._providers: list[HookProvider] = []
        self._workflow_hooks: dict[type, list[Callable]] = {}
        self._activity_hooks: dict[type, list[Callable]] = {}

    def add_provider(self, provider: HookProvider) -> None:
        """Add a hook provider to the registry."""
        self._providers.append(provider)
        provider.register_hooks(self._hook_registry)

    def add_callback(self, event_type: type[T], callback: Callable[[T], None]) -> None:
        """Add a callback for a specific event type."""
        # Note: Skip adding to Strands registry due to type compatibility issues
        # self._hook_registry.add_callback(event_type, callback)

        # Categorize for workflow vs activity execution
        if self._is_workflow_event(event_type):
            if event_type not in self._workflow_hooks:
                self._workflow_hooks[event_type] = []
            self._workflow_hooks[event_type].append(callback)
        else:
            if event_type not in self._activity_hooks:
                self._activity_hooks[event_type] = []
            self._activity_hooks[event_type].append(callback)

    def emit_in_workflow(self, event: Any) -> None:
        """Emit a hook event in workflow context."""
        if not temporalio.workflow.in_workflow():
            return

        event_type = type(event)
        if event_type in self._workflow_hooks:
            context = self._get_current_context()
            context.add_event(event_type.__name__, self._serialize_event(event))

            for callback in self._workflow_hooks[event_type]:
                try:
                    callback(event)
                except Exception:
                    pass  # Silently ignore errors

    def emit_in_activity(self, event: Any) -> None:
        """Emit a hook event in activity context."""
        if not temporalio.activity.in_activity():
            return

        event_type = type(event)
        if event_type in self._activity_hooks:
            # Get context from activity info
            # Note: heartbeat_details might not be available in all Temporal versions
            context = TemporalHookContext()

            context.add_event(event_type.__name__, self._serialize_event(event))

            for callback in self._activity_hooks[event_type]:
                try:
                    callback(event)
                except Exception:
                    pass  # Silently ignore errors

    def _is_workflow_event(self, event_type: type) -> bool:
        """Determine if an event should be handled in workflow context."""
        workflow_events = {
            BeforeInvocationEvent,
            AfterInvocationEvent,
            AgentInitializedEvent,
            MessageAddedEvent,
        }
        return event_type in workflow_events

    def _get_current_context(self) -> TemporalHookContext:
        """Get or create hook context for current execution."""
        if temporalio.workflow.in_workflow():
            # In workflow, context is stored in workflow state
            # This is a placeholder - actual implementation would depend on
            # how workflow state is managed
            return TemporalHookContext()
        elif temporalio.activity.in_activity():
            # In activity, get context from activity info
            # Note: heartbeat_details might not be available in all Temporal versions
            return TemporalHookContext()
        else:
            return TemporalHookContext()

    def _serialize_event(self, event: Any) -> dict[str, Any]:
        """Serialize an event for context storage."""
        # This is a simplified serialization - actual implementation
        # would need to handle complex event data properly
        try:
            if hasattr(event, "__dict__"):
                return {k: str(v) for k, v in event.__dict__.items()}
            else:
                return {"event": str(event)}
        except Exception:
            return {"event": str(type(event).__name__)}


# Global registry instance
_global_registry: TemporalHookRegistry | None = None


def get_hook_registry() -> TemporalHookRegistry:
    """Get the global hook registry instance."""
    global _global_registry
    if _global_registry is None:
        _global_registry = TemporalHookRegistry()
    return _global_registry


@contextmanager
def hook_context(trace_id: str | None = None):
    """Context manager for hook execution with tracing."""
    context = TemporalHookContext(trace_id=trace_id)

    # Store context in appropriate location based on execution context
    if temporalio.workflow.in_workflow():
        # In workflow context, we would store in workflow state
        # This is a placeholder for actual implementation
        pass
    elif temporalio.activity.in_activity():
        # In activity context, store in heartbeat details
        activity_info = temporalio.activity.info()
        # This would require updating heartbeat details
        pass

    try:
        yield context
    finally:
        pass  # Removed logging


def emit_workflow_event(event: Any) -> None:
    """Emit a hook event in workflow context."""
    registry = get_hook_registry()
    registry.emit_in_workflow(event)


def emit_activity_event(event: Any) -> None:
    """Emit a hook event in activity context."""
    registry = get_hook_registry()
    registry.emit_in_activity(event)


class DefaultHookProvider(HookProvider):
    """Default hook provider for basic observability."""

    def register_hooks(self, registry: HookRegistry) -> None:
        """Register default hooks for observability."""
        registry.add_callback(BeforeInvocationEvent, self._log_invocation_start)
        registry.add_callback(AfterInvocationEvent, self._log_invocation_end)
        registry.add_callback(MessageAddedEvent, self._log_message_added)

        if _EXPERIMENTAL_HOOKS_AVAILABLE:
            if BeforeModelInvocationEvent:
                registry.add_callback(BeforeModelInvocationEvent, self._log_model_start)
            if AfterModelInvocationEvent:
                registry.add_callback(AfterModelInvocationEvent, self._log_model_end)
            if BeforeToolInvocationEvent:
                registry.add_callback(BeforeToolInvocationEvent, self._log_tool_start)
            if AfterToolInvocationEvent:
                registry.add_callback(AfterToolInvocationEvent, self._log_tool_end)

    def _log_invocation_start(self, event: BeforeInvocationEvent) -> None:
        """Log agent invocation start."""
        pass  # Removed logging

    def _log_invocation_end(self, event: AfterInvocationEvent) -> None:
        """Log agent invocation end."""
        pass  # Removed logging

    def _log_message_added(self, event: MessageAddedEvent) -> None:
        """Log message addition."""
        pass  # Removed logging

    def _log_model_start(self, event) -> None:
        """Log model invocation start."""
        pass  # Removed logging

    def _log_model_end(self, event) -> None:
        """Log model invocation end."""
        pass  # Removed logging

    def _log_tool_start(self, event) -> None:
        """Log tool invocation start."""
        pass  # Removed logging

    def _log_tool_end(self, event) -> None:
        """Log tool invocation end."""
        pass  # Removed logging


def initialize_default_hooks() -> None:
    """Initialize default hook providers."""
    registry = get_hook_registry()
    registry.add_provider(DefaultHookProvider())
````

## File: strands_temporal_plugin/logging.py
````python
"""Simple logging utilities for Strands Temporal plugin.

This module provides basic logging functionality that's compatible with
Temporal's workflow sandbox restrictions by avoiding rich and other
problematic dependencies.
"""

from __future__ import annotations

import logging
from typing import Any


def _configure_once() -> None:
    """Configure basic logging with sensible defaults."""
    # Avoid configuring root logging; only set a sensible default for our logger if not set.
    logger_name = __name__.replace(".logging", "")
    plugin_logger = logging.getLogger(logger_name)

    if not plugin_logger.handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class SimpleLogger:
    """Simple logger that's compatible with Temporal workflows.

    This logger provides basic logging functionality without the rich
    dependency that causes Temporal sandbox issues.
    """

    def __init__(self, name: str):
        self.name = name
        self._logger = logging.getLogger(name)

    def debug(self, msg: str, **kwargs: Any) -> None:
        """Log debug message with optional structured data."""
        if kwargs:
            formatted_msg = f"{msg} | {self._format_kwargs(kwargs)}"
        else:
            formatted_msg = msg
        self._logger.debug(formatted_msg)

    def info(self, msg: str, **kwargs: Any) -> None:
        """Log info message with optional structured data."""
        if kwargs:
            formatted_msg = f"{msg} | {self._format_kwargs(kwargs)}"
        else:
            formatted_msg = msg
        self._logger.info(formatted_msg)

    def warning(self, msg: str, **kwargs: Any) -> None:
        """Log warning message with optional structured data."""
        if kwargs:
            formatted_msg = f"{msg} | {self._format_kwargs(kwargs)}"
        else:
            formatted_msg = msg
        self._logger.warning(formatted_msg)

    def error(self, msg: str, **kwargs: Any) -> None:
        """Log error message with optional structured data."""
        if kwargs:
            formatted_msg = f"{msg} | {self._format_kwargs(kwargs)}"
        else:
            formatted_msg = msg
        self._logger.error(formatted_msg)

    def _format_kwargs(self, kwargs: dict[str, Any]) -> str:
        """Format keyword arguments as key=value pairs."""
        return " ".join(f"{k}={v}" for k, v in kwargs.items())


def get_logger(name: str | None = None) -> SimpleLogger:
    """Get a simple logger instance.

    Args:
        name: Logger name (defaults to plugin name)

    Returns:
        SimpleLogger instance compatible with Temporal workflows
    """
    _configure_once()
    logger_name = name or __name__.replace(".logging", "")
    return SimpleLogger(logger_name)
````

## File: strands_temporal_plugin/plugin.py
````python
"""Strands Temporal Plugin implementation.

This module provides the main StrandsTemporalPlugin class that configures
Temporal clients and workers for seamless integration with Strands agents.
"""

from __future__ import annotations

import temporalio.client
import temporalio.worker
from .activities.model import model_infer_activity
from .activities.tools import call_registered_tool_activity
from .pydantic_converter import pydantic_data_converter
from .types import ModelActivityParameters, ProviderConfig
from collections.abc import Sequence
from temporalio.client import ClientConfig
from temporalio.worker import WorkerConfig
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions
from typing import Any


class StrandsTemporalPlugin(temporalio.client.Plugin, temporalio.worker.Plugin):
    """Plugin for integrating Strands agents with Temporal workflows.

    This plugin configures Temporal clients and workers to work seamlessly with
    Strands agents by:
    - Setting up Pydantic data converter for type-safe serialization
    - Registering Strands activities (model inference and tool execution)
    - Providing runtime overrides to route Strands calls through Temporal

    Example usage:
        ```python
        plugin = StrandsTemporalPlugin(
            model_params=ModelActivityParameters(start_to_close_timeout=timedelta(minutes=5)),
            default_provider=BedrockProviderConfig(model_id="anthropic.claude-3-sonnet-20240229-v1:0"),
        )

        client = await Client.connect("localhost:7233", plugins=[plugin])
        worker = Worker(client, task_queue="strands-agents", workflows=[AgentWorkflow])
        ```
    """

    def __init__(
        self,
        *,
        model_params: ModelActivityParameters | None = None,
        default_provider: ProviderConfig | None = None,
        plugins: Sequence[temporalio.client.Plugin | temporalio.worker.Plugin] | None = None,
    ) -> None:
        """Initialize the Strands Temporal plugin.

        Args:
            model_params: Parameters for configuring model inference activities
            default_provider: Default provider configuration for model inference
            plugins: Additional plugins to chain with this plugin
        """
        self._model_params = model_params or ModelActivityParameters()
        self._default_provider = default_provider
        self._plugins = list(plugins or [])

        # Store original model behavior for restoration
        self._original_model_behavior: Any | None = None

    def configure_client(self, config: ClientConfig) -> ClientConfig:
        """Configure the Temporal client with Pydantic data converter.

        Args:
            config: The client configuration to modify

        Returns:
            Modified client configuration with Pydantic data converter
        """
        # Chain with other plugins first
        for plugin in self._plugins:
            if isinstance(plugin, temporalio.client.Plugin):
                config = plugin.configure_client(config)

        # Set up Pydantic data converter for type-safe serialization
        config["data_converter"] = pydantic_data_converter

        return config

    def configure_worker(self, config: WorkerConfig) -> WorkerConfig:
        """Configure the Temporal worker with Strands activities.

        Args:
            config: The worker configuration to modify

        Returns:
            Modified worker configuration with registered activities
        """
        # Chain with other plugins first
        for plugin in self._plugins:
            if isinstance(plugin, temporalio.worker.Plugin):
                config = plugin.configure_worker(config)

        # Configure custom sandbox restrictions with passthrough modules
        custom_restrictions = SandboxRestrictions.default.with_passthrough_modules(
            "strands.types.content",
            "strands.types.tools",
            "strands.types.streaming",
            "strands.types.event_loop",
            "botocore",
            "urllib3",
            "watchdog",
        )

        # Set up custom workflow runner with sandbox restrictions
        config["workflow_runner"] = SandboxedWorkflowRunner(restrictions=custom_restrictions)

        # Register Strands activities
        activities = list(config.get("activities") or [])
        activities.extend(
            [
                model_infer_activity,
                call_registered_tool_activity,
            ]
        )
        config["activities"] = activities

        return config

    @property
    def model_params(self) -> ModelActivityParameters:
        """Get the model activity parameters.

        Returns:
            Model activity parameters for configuring timeouts and behavior
        """
        return self._model_params

    @property
    def default_provider(self) -> ProviderConfig | None:
        """Get the default provider configuration.

        Returns:
            Default provider configuration, if set
        """
        return self._default_provider


def create_strands_temporal_plugin(
    *,
    model_params: ModelActivityParameters | None = None,
    default_provider: ProviderConfig | None = None,
    plugins: Sequence[temporalio.client.Plugin | temporalio.worker.Plugin] | None = None,
) -> StrandsTemporalPlugin:
    """Create a Strands Temporal plugin with the specified configuration.

    This is a convenience function for creating a StrandsTemporalPlugin instance.

    Args:
        model_params: Parameters for configuring model inference activities
        default_provider: Default provider configuration for model inference
        plugins: Additional plugins to chain with this plugin

    Returns:
        Configured StrandsTemporalPlugin instance

    Example:
        ```python
        plugin = create_strands_temporal_plugin(
            model_params=ModelActivityParameters(start_to_close_timeout=timedelta(minutes=5)),
            default_provider=BedrockProviderConfig(model_id="anthropic.claude-3-sonnet-20240229-v1:0"),
        )
        ```
    """
    return StrandsTemporalPlugin(
        model_params=model_params,
        default_provider=default_provider,
        plugins=plugins,
    )
````

## File: strands_temporal_plugin/providers.py
````python
"""Provider configuration and factory system for Strands model providers."""

import asyncio
from .types import BedrockProviderConfig, EchoProviderConfig, ProviderConfig
from collections.abc import AsyncGenerator
from strands.models import BedrockModel, Model
from strands.types.content import Messages
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolSpec
from typing import Any


class EchoModel(Model):
    """Mock model for testing that echoes back the input messages.

    This model implements the Strands Model interface for testing purposes.
    It provides deterministic responses by echoing user input with configurable
    streaming simulation (latency and chunk sizes).
    """

    def __init__(self, sleep_s: float = 0.0, chunk_chars: int = 20):
        """Initialize EchoModel.

        Args:
            sleep_s: Simulated latency per chunk in seconds
            chunk_chars: Number of characters per streaming chunk
        """
        self.sleep_s = sleep_s
        self.chunk_chars = chunk_chars

    def update_config(self, **kwargs: Any) -> None:
        """Update model configuration (not used for EchoModel)."""
        pass

    def get_config(self) -> dict[str, Any]:
        """Get model configuration."""
        return {
            "sleep_s": self.sleep_s,
            "chunk_chars": self.chunk_chars,
        }

    async def stream(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent]:
        """Stream conversation with echo responses.

        Args:
            messages: List of message objects to be processed
            tool_specs: List of tool specifications (ignored for echo)
            system_prompt: System prompt (ignored for echo)
            **kwargs: Additional keyword arguments

        Yields:
            StreamEvent objects simulating model response
        """
        # Find the last user message
        user_content = ""
        for message in reversed(messages):
            if message["role"] == "user":
                for content in message["content"]:
                    if "text" in content:
                        user_content = content["text"]
                        break
                break

        if not user_content:
            user_content = "Hello from Echo model!"

        # Simulate streaming by yielding chunks
        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockStart": {"contentBlockIndex": 0, "start": {}}}

        # Split content into chunks and stream
        for i in range(0, len(user_content), self.chunk_chars):
            chunk = user_content[i : i + self.chunk_chars]
            yield {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": chunk}}}

            if self.sleep_s > 0:
                await asyncio.sleep(self.sleep_s)

        yield {"contentBlockStop": {"contentBlockIndex": 0}}
        yield {"messageStop": {"stopReason": "end_turn"}}

        # Mock usage statistics
        word_count = len(user_content.split())
        yield {
            "metadata": {
                "usage": {
                    "inputTokens": word_count,
                    "outputTokens": word_count,
                    "totalTokens": word_count * 2,
                },
                "metrics": {"latencyMs": int(self.sleep_s * 1000)},
            }
        }

    async def structured_output(self, output_model, prompt, system_prompt=None, **kwargs):
        """Get structured output (not implemented for EchoModel)."""
        raise NotImplementedError("EchoModel does not support structured output")


def create_model_from_config(provider: ProviderConfig) -> Model:
    """Create appropriate Strands model instance from provider configuration.

    This factory function takes a provider configuration and returns an instance
    of the corresponding Strands model. It handles the mapping between configuration
    objects and model instantiation parameters.

    Args:
        provider: Provider configuration object

    Returns:
        Strands model instance implementing the Model interface

    Raises:
        ValueError: If provider type is not supported or configuration is invalid
        Exception: If model instantiation fails
    """
    try:
        if provider.type == "bedrock":
            return _create_bedrock_model(provider)
        elif provider.type == "echo":
            return _create_echo_model(provider)
        else:
            raise ValueError(f"Unsupported provider type: {provider.type}")

    except Exception:
        raise


def _create_bedrock_model(provider: ProviderConfig) -> BedrockModel:
    """Create BedrockModel instance from BedrockProviderConfig.

    Args:
        provider: Provider configuration (must be BedrockProviderConfig)

    Returns:
        Configured BedrockModel instance

    Raises:
        ValueError: If configuration is invalid
    """
    if not isinstance(provider, BedrockProviderConfig):
        # Handle both dict and ProviderConfig types
        if isinstance(provider, dict):
            bedrock_config = BedrockProviderConfig(**provider)
        else:
            bedrock_config = BedrockProviderConfig(**provider.model_dump())
    else:
        bedrock_config = provider

    try:
        # Start with the most basic BedrockModel creation with just model_id
        bedrock_model = BedrockModel(model_id=bedrock_config.model_id)
        return bedrock_model

    except Exception as e:
        raise ValueError(f"Failed to create BedrockModel with model_id='{bedrock_config.model_id}': {str(e)}") from e


def _create_echo_model(provider: ProviderConfig) -> EchoModel:
    """Create EchoModel instance from EchoProviderConfig.

    Args:
        provider: Provider configuration (must be EchoProviderConfig)

    Returns:
        Configured EchoModel instance

    Raises:
        ValueError: If configuration is invalid
    """
    if not isinstance(provider, EchoProviderConfig):
        # Handle both dict and ProviderConfig types
        if isinstance(provider, dict):
            echo_config = EchoProviderConfig(**provider)
        else:
            echo_config = EchoProviderConfig(**provider.model_dump())
    else:
        echo_config = provider

    try:
        return EchoModel(sleep_s=echo_config.sleep_s, chunk_chars=echo_config.chunk_chars)
    except Exception as e:
        raise ValueError(f"Failed to create EchoModel: {str(e)}") from e


def validate_provider_config(provider: ProviderConfig) -> None:
    """Validate provider configuration.

    Args:
        provider: Provider configuration to validate

    Raises:
        ValueError: If configuration is invalid
    """
    if provider.type == "bedrock":
        bedrock_config = BedrockProviderConfig(**provider.model_dump())

        if not bedrock_config.model_id:
            raise ValueError("BedrockProviderConfig requires model_id")

        # Validate inference config if provided
        if bedrock_config.inference_config:
            inference_config = bedrock_config.inference_config

            if "temperature" in inference_config:
                temp = inference_config["temperature"]
                if not isinstance(temp, (int, float)) or temp < 0 or temp > 1:
                    raise ValueError("temperature must be a number between 0 and 1")

            if "topP" in inference_config:
                top_p = inference_config["topP"]
                if not isinstance(top_p, (int, float)) or top_p < 0 or top_p > 1:
                    raise ValueError("topP must be a number between 0 and 1")

            if "maxTokens" in inference_config:
                max_tokens = inference_config["maxTokens"]
                if not isinstance(max_tokens, int) or max_tokens < 1:
                    raise ValueError("maxTokens must be a positive integer")

    elif provider.type == "echo":
        echo_config = EchoProviderConfig(**provider.model_dump())

        if echo_config.sleep_s < 0:
            raise ValueError("sleep_s must be non-negative")

        if echo_config.chunk_chars < 1:
            raise ValueError("chunk_chars must be positive")

    else:
        raise ValueError(f"Unknown provider type: {provider.type}")
````

## File: strands_temporal_plugin/pydantic_converter.py
````python
"""A data converter for Pydantic v2.

To use, pass ``pydantic_data_converter`` as the ``data_converter`` argument to
:py:class:`temporalio.client.Client`:

.. code-block:: python

    client = Client(
        data_converter=pydantic_data_converter,
        ...
    )

Pydantic v1 is not supported.
"""

import temporalio.api.common.v1
from dataclasses import dataclass
from pydantic import TypeAdapter
from pydantic_core import SchemaSerializer, to_json
from pydantic_core.core_schema import any_schema
from temporalio.converter import (
    CompositePayloadConverter,
    DataConverter,
    DefaultPayloadConverter,
    EncodingPayloadConverter,
    JSONPlainPayloadConverter,
)
from typing import Any


# Note that in addition to the implementation in this module, _RestrictedProxy
# implements __get_pydantic_core_schema__ so that pydantic unwraps proxied types.


@dataclass
class ToJsonOptions:
    """Options for converting to JSON with pydantic."""

    exclude_unset: bool = False


class PydanticJSONPlainPayloadConverter(EncodingPayloadConverter):
    """Pydantic JSON payload converter.

    Supports conversion of all types supported by Pydantic to and from JSON.

    In addition to Pydantic models, these include all `json.dump`-able types,
    various non-`json.dump`-able standard library types such as dataclasses,
    types from the datetime module, sets, UUID, etc, and custom types composed
    of any of these.

    See https://docs.pydantic.dev/latest/api/standard_library_types/
    """

    def __init__(self, to_json_options: ToJsonOptions | None = None):
        """Create a new payload converter."""
        self._schema_serializer = SchemaSerializer(any_schema())
        self._to_json_options = to_json_options

    @property
    def encoding(self) -> str:
        """See base class."""
        return "json/plain"

    def to_payload(self, value: Any) -> temporalio.api.common.v1.Payload | None:
        """See base class.

        Uses ``pydantic_core.to_json`` to serialize ``value`` to JSON.

        See
        https://docs.pydantic.dev/latest/api/pydantic_core/#pydantic_core.to_json.
        """
        data = (
            self._schema_serializer.to_json(value, exclude_unset=self._to_json_options.exclude_unset)
            if self._to_json_options
            else to_json(value)
        )
        return temporalio.api.common.v1.Payload(metadata={"encoding": self.encoding.encode()}, data=data)

    def from_payload(
        self,
        payload: temporalio.api.common.v1.Payload,
        type_hint: type | None = None,
    ) -> Any:
        """See base class.

        Uses ``pydantic.TypeAdapter.validate_json`` to construct an
        instance of the type specified by ``type_hint`` from the JSON payload.

        See
        https://docs.pydantic.dev/latest/api/type_adapter/#pydantic.type_adapter.TypeAdapter.validate_json.
        """
        _type_hint = type_hint if type_hint is not None else Any
        return TypeAdapter(_type_hint).validate_json(payload.data)


class PydanticPayloadConverter(CompositePayloadConverter):
    """Payload converter for payloads containing pydantic model instances.

    JSON conversion is replaced with a converter that uses
    :py:class:`PydanticJSONPlainPayloadConverter`.
    """

    def __init__(self, to_json_options: ToJsonOptions | None = None) -> None:
        """Initialize object"""
        json_payload_converter = PydanticJSONPlainPayloadConverter(to_json_options)
        super().__init__(
            *(
                c if not isinstance(c, JSONPlainPayloadConverter) else json_payload_converter
                for c in DefaultPayloadConverter.default_encoding_payload_converters
            )
        )


pydantic_data_converter = DataConverter(payload_converter_class=PydanticPayloadConverter)
"""Pydantic data converter.

Supports conversion of all types supported by Pydantic to and from JSON.

In addition to Pydantic models, these include all `json.dump`-able types,
various non-`json.dump`-able standard library types such as dataclasses,
types from the datetime module, sets, UUID, etc, and custom types composed
of any of these.

To use, pass as the ``data_converter`` argument of :py:class:`temporalio.client.Client`
"""
````

## File: strands_temporal_plugin/registry.py
````python
from __future__ import annotations

from collections.abc import Callable
from threading import RLock
from typing import Any


_REGISTRY: dict[str, Callable[..., Any]] = {}
_LOCK = RLock()


def register_tool(name: str, func: Callable[..., Any]) -> None:
    """Register a callable to be dispatched by activities.

    Should be called at worker startup (process-global).
    """
    if not isinstance(func, Callable):
        raise TypeError("func must be callable")

    with _LOCK:
        _REGISTRY[name] = func


def get_registered_tools() -> dict[str, Callable[..., Any]]:
    with _LOCK:
        return dict(_REGISTRY)


def _resolve(name: str) -> Callable[..., Any]:
    try:
        return _REGISTRY[name]
    except KeyError as e:
        raise LookupError(f"No tool registered under name '{name}'. Registered: {list(_REGISTRY)}") from e
````

## File: strands_temporal_plugin/types.py
````python
from __future__ import annotations

from datetime import timedelta
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field, Field as PydanticField

# Import Strands types directly (now safe with sandbox passthrough)
from strands.types.content import Messages
from strands.types.tools import ToolResultContent, ToolSpec
from typing import Annotated, Any, Literal


class StopReason(StrEnum):
    END_TURN = "end_turn"
    TOOL_USE = "tool_use"
    MAX_STEPS = "max_steps"
    ERROR = "error"


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class EchoProviderConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["echo"] = "echo"
    # simulate latency per chunk (seconds)
    sleep_s: float = 0.0
    # chunk size to simulate streaming
    chunk_chars: int = 20


class BedrockProviderConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["bedrock"] = "bedrock"
    model_id: str
    region: str | None = None
    # Optional inference params forwarded to Bedrock Converse API
    inference_config: dict[str, Any] | None = None
    tool_config: dict[str, Any] | None = None


# Define ProviderConfig as a discriminated union using Pydantic v2 syntax
ProviderConfig = Annotated[EchoProviderConfig | BedrockProviderConfig, PydanticField(discriminator="type")]


class ModelCallInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    # Use Strands types directly (now safe with sandbox passthrough)
    messages: Messages
    tool_specs: list[ToolSpec] | None = None
    system_prompt: str | None = None
    provider: ProviderConfig = Field(default_factory=EchoProviderConfig)


class ModelCallResult(BaseModel):
    text: str
    usage: Usage = Field(default_factory=Usage)
    stop_reason: StopReason = StopReason.END_TURN


class ToolCallInput(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallResult(BaseModel):
    # Use Strands ToolResultContent for proper typing
    content: list[ToolResultContent] = Field(default_factory=list)


class TurnInput(BaseModel):
    session_id: str
    user_message: str | None = None
    provider: ProviderConfig | None = None


class TurnResult(BaseModel):
    session_id: str
    stop_reason: StopReason = StopReason.END_TURN
    assistant_text: str | None = None
    usage: Usage = Field(default_factory=Usage)


class ModelActivityParameters(BaseModel):
    """Parameters for configuring model inference activities."""

    start_to_close_timeout: timedelta = Field(default=timedelta(minutes=5))
    schedule_to_close_timeout: timedelta = Field(default=timedelta(minutes=10))
    heartbeat_timeout: timedelta | None = None
    retry_policy: dict[str, Any] | None = None
````
