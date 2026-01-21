"""Strands Temporal Activities

Activities for executing model inference and tool calls.
These activities run in the worker process where credentials and
external resources are available.

Activities properly handle:
- Model creation with provider-specific configuration
- Heartbeating for long-running operations
- Error translation to Temporal ApplicationError
- Proper retry behavior
"""

from __future__ import annotations

import importlib
import logging
from .types import ModelExecutionInput, ModelExecutionResult, ToolExecutionInput, ToolExecutionResult
from temporalio import activity
from temporalio.exceptions import ApplicationError
from typing import Any


logger = logging.getLogger(__name__)


# =============================================================================
# Model Factory
# =============================================================================


def _create_model_from_config(provider_config: Any) -> Any:
    """Create a Strands Model from provider configuration.

    This function dynamically creates the appropriate model based on
    the provider type in the configuration.

    Args:
        provider_config: Provider configuration (Pydantic model)

    Returns:
        Strands Model instance

    Raises:
        ApplicationError: If provider is not supported
    """
    provider = provider_config.provider

    if provider == "bedrock":
        from strands.models import BedrockModel

        # Build kwargs from config, excluding None values
        kwargs: dict[str, Any] = {"model_id": provider_config.model_id}

        if provider_config.region_name:
            kwargs["region_name"] = provider_config.region_name
        if provider_config.max_tokens:
            kwargs["max_tokens"] = provider_config.max_tokens
        if provider_config.temperature is not None:
            kwargs["temperature"] = provider_config.temperature
        if provider_config.top_p is not None:
            kwargs["top_p"] = provider_config.top_p
        if provider_config.stop_sequences:
            kwargs["stop_sequences"] = provider_config.stop_sequences

        return BedrockModel(**kwargs)

    elif provider == "anthropic":
        try:
            from strands.models import AnthropicModel
        except ImportError as e:
            raise ApplicationError(
                "AnthropicModel not available. Install strands-agents with anthropic extra.",
                type="ProviderNotAvailable",
                non_retryable=True,
            ) from e

        kwargs = {"model_id": provider_config.model_id}
        if provider_config.max_tokens:
            kwargs["max_tokens"] = provider_config.max_tokens
        if provider_config.temperature is not None:
            kwargs["temperature"] = provider_config.temperature
        if provider_config.top_p is not None:
            kwargs["top_p"] = provider_config.top_p
        if provider_config.stop_sequences:
            kwargs["stop_sequences"] = provider_config.stop_sequences

        return AnthropicModel(**kwargs)

    elif provider == "openai":
        try:
            from strands.models import OpenAIModel
        except ImportError as e:
            raise ApplicationError(
                "OpenAIModel not available. Install strands-agents with openai extra.",
                type="ProviderNotAvailable",
                non_retryable=True,
            ) from e

        kwargs = {"model_id": provider_config.model_id}
        if provider_config.max_tokens:
            kwargs["max_tokens"] = provider_config.max_tokens
        if provider_config.temperature is not None:
            kwargs["temperature"] = provider_config.temperature
        if provider_config.top_p is not None:
            kwargs["top_p"] = provider_config.top_p

        return OpenAIModel(**kwargs)

    elif provider == "ollama":
        try:
            from strands.models import OllamaModel
        except ImportError as e:
            raise ApplicationError(
                "OllamaModel not available. Install strands-agents with ollama extra.",
                type="ProviderNotAvailable",
                non_retryable=True,
            ) from e

        kwargs = {"model_id": provider_config.model_id}
        if provider_config.host:
            kwargs["host"] = provider_config.host
        if provider_config.temperature is not None:
            kwargs["temperature"] = provider_config.temperature
        if provider_config.top_p is not None:
            kwargs["top_p"] = provider_config.top_p

        return OllamaModel(**kwargs)

    else:
        raise ApplicationError(
            f"Unsupported provider type: {provider}",
            type="UnsupportedProvider",
            non_retryable=True,
        )


# =============================================================================
# Model Execution Activity
# =============================================================================


@activity.defn
async def execute_model_activity(input_data: ModelExecutionInput) -> ModelExecutionResult:
    """Execute a model inference call.

    This activity:
    1. Creates the appropriate model from configuration
    2. Calls model.stream() with messages and tool specs
    3. Collects all stream events
    4. Returns the events for workflow processing

    The activity supports heartbeating for long-running model calls.

    Args:
        input_data: Model execution input with provider config, messages, etc.

    Returns:
        ModelExecutionResult with collected stream events

    Raises:
        ApplicationError: For non-retryable errors (invalid config, etc.)
    """
    logger.info(
        f"Executing model activity: provider={input_data.provider_config.provider}, "
        f"model_id={input_data.provider_config.model_id}"
    )

    try:
        # Create model from configuration
        model = _create_model_from_config(input_data.provider_config)

        # Convert messages back to proper format if needed
        messages = input_data.messages

        # Convert tool specs back to proper format if needed
        tool_specs = input_data.tool_specs

        # Call model.stream() and collect events
        result = model.stream(
            messages=messages,
            tool_specs=tool_specs,
            system_prompt=input_data.system_prompt,
        )

        # Collect events, heartbeating periodically
        events: list[dict[str, Any]] = []
        event_count = 0

        async for event in result:
            events.append(dict(event) if hasattr(event, "keys") else event)
            event_count += 1

            # Heartbeat every 10 events to show progress
            if event_count % 10 == 0:
                activity.heartbeat(f"Processed {event_count} events")

        logger.info(f"Model activity completed: {len(events)} events collected")

        return ModelExecutionResult(events=events)

    except ApplicationError:
        # Re-raise ApplicationErrors as-is
        raise

    except Exception as e:
        # Check for specific exception types that should not be retried
        error_type = type(e).__name__

        # Context window overflow - don't retry
        if "ContextWindowOverflow" in error_type or "context" in str(e).lower():
            raise ApplicationError(
                f"Context window overflow: {e}",
                type="ContextOverflow",
                non_retryable=True,
            ) from e

        # Model not found - don't retry
        if "ModelNotFound" in error_type or "not found" in str(e).lower():
            raise ApplicationError(
                f"Model not found: {e}",
                type="ModelNotFound",
                non_retryable=True,
            ) from e

        # Throttling - allow retry
        if "Throttl" in error_type or "throttl" in str(e).lower():
            raise ApplicationError(
                f"Model throttled: {e}",
                type="ModelThrottled",
                non_retryable=False,
            ) from e

        # Default: allow retry for unknown errors
        logger.exception(f"Unexpected error in model activity: {e}")
        raise ApplicationError(
            f"Model execution failed: {e}",
            type="ModelExecutionError",
            non_retryable=False,
        ) from e


# =============================================================================
# Tool Execution Activity
# =============================================================================


def _load_tool_function(tool_name: str, tool_module: str) -> Any:
    """Dynamically load a tool function from a module.

    Args:
        tool_name: Name of the tool function
        tool_module: Module path to import from

    Returns:
        The tool function

    Raises:
        ApplicationError: If tool cannot be loaded
    """
    if not tool_module:
        raise ApplicationError(
            f"No module specified for tool: {tool_name}",
            type="ToolNotFound",
            non_retryable=True,
        )

    try:
        module = importlib.import_module(tool_module)
        tool_func = getattr(module, tool_name, None)

        if tool_func is None:
            raise ApplicationError(
                f"Tool '{tool_name}' not found in module '{tool_module}'",
                type="ToolNotFound",
                non_retryable=True,
            )

        return tool_func

    except ImportError as e:
        raise ApplicationError(
            f"Failed to import module '{tool_module}' for tool '{tool_name}': {e}",
            type="ToolModuleNotFound",
            non_retryable=True,
        ) from e


@activity.defn
async def execute_tool_activity(input_data: ToolExecutionInput) -> ToolExecutionResult:
    """Execute a tool call.

    This activity:
    1. Dynamically loads the tool function from the specified module
    2. Calls the tool with the provided input
    3. Returns the result in Strands ToolResult format

    Args:
        input_data: Tool execution input with tool name, module, and input

    Returns:
        ToolExecutionResult with tool output

    Raises:
        ApplicationError: For non-retryable errors (tool not found, etc.)
    """
    logger.info(f"Executing tool activity: tool={input_data.tool_name}, module={input_data.tool_module}")

    try:
        # Load the tool function
        tool_func = _load_tool_function(input_data.tool_name, input_data.tool_module)

        # Get the actual function if it's a Strands @tool decorated function
        if hasattr(tool_func, "__wrapped__"):
            actual_func = tool_func.__wrapped__
        else:
            actual_func = tool_func

        # Execute the tool
        import inspect

        if inspect.iscoroutinefunction(actual_func):
            result = await actual_func(**input_data.tool_input)
        else:
            result = actual_func(**input_data.tool_input)

        # Format result as content blocks
        if isinstance(result, str):
            content = [{"text": result}]
        elif isinstance(result, dict):
            import json

            content = [{"text": json.dumps(result)}]
        elif isinstance(result, list):
            content = result
        else:
            content = [{"text": str(result)}]

        logger.info(f"Tool activity completed: tool={input_data.tool_name}")

        return ToolExecutionResult(
            tool_use_id=input_data.tool_use_id,
            status="success",
            content=content,
        )

    except ApplicationError:
        # Re-raise ApplicationErrors as-is
        raise

    except Exception as e:
        logger.exception(f"Tool execution failed: {input_data.tool_name}: {e}")

        return ToolExecutionResult(
            tool_use_id=input_data.tool_use_id,
            status="error",
            content=[{"text": f"Tool execution failed: {e}"}],
        )
