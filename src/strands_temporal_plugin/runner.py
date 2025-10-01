"""Strands Agent Runtime Override System

Override Agent.__init__ to inject TemporalModelStub when in workflow context.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from typing import Any
from collections.abc import AsyncIterable

from temporalio import workflow
from strands import Agent
from strands.models import Model, BedrockModel
from strands.types.tools import ToolSpec
from strands.types.content import Messages
from strands.types.streaming import StreamEvent

from .activities import AgentExecutionInput, AgentExecutionResult, execute_strands_agent


class TemporalModelStub(Model):
    """Model stub that routes calls to Temporal activities when in workflow context."""

    def __init__(self, original_model: Model, agent_tools: list, agent_system_prompt: str | None = None):
        """Initialize with the original model configuration."""
        self.original_model = original_model
        self.agent_tools = agent_tools
        self.agent_system_prompt = agent_system_prompt

    def update_config(self, **kwargs: Any) -> None:
        """Delegate to original model."""
        self.original_model.update_config(**kwargs)

    def get_config(self) -> Any:
        """Get configuration from original model."""
        return self.original_model.get_config()

    async def stream(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[StreamEvent]:
        """Route model calls to Temporal activity when in workflow."""
        if not workflow.in_workflow():
            # Not in workflow - use original model
            async for event in self.original_model.stream(messages, tool_specs, system_prompt, **kwargs):
                yield event
            return

        # In workflow - route to activity for durable execution
        model_config = self._extract_model_config()

        # Extract prompt from messages
        prompt = self._extract_prompt_from_messages(messages)

        activity_input = AgentExecutionInput(
            prompt=prompt,
            ai_model_config=model_config,
            tool_specs=self.agent_tools,  # Use agent tools, not model tool_specs
            system_prompt=self.agent_system_prompt or system_prompt,
            messages=messages,
        )

        # Execute via activity
        activity_result: AgentExecutionResult = await workflow.execute_activity(
            execute_strands_agent,
            activity_input,
            start_to_close_timeout=timedelta(minutes=5),
        )

        # Convert activity result back to stream format
        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockStart": {"contentBlockIndex": 0}}

        # Stream text in chunks to simulate normal streaming
        text = activity_result.text or ""
        chunk_size = 50
        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size]
            yield {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": chunk}}}

        yield {"contentBlockStop": {"contentBlockIndex": 0}}
        # Map stop reason properly
        stop_reason = "end_turn"  # Default
        if activity_result.stop_reason == "tool_use":
            stop_reason = "tool_use"
        elif activity_result.stop_reason == "max_tokens":
            stop_reason = "max_tokens"

        yield {"messageStop": {"stopReason": stop_reason}}

    def _extract_model_config(self) -> dict[str, Any]:
        """Extract model configuration for serialization."""
        if isinstance(self.original_model, BedrockModel):
            config = self.original_model.get_config()
            return {
                "type": "bedrock",
                "model_id": config.get("model_id", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
                "region": config.get("region_name"),
                "max_tokens": config.get("max_tokens"),
                "temperature": config.get("temperature"),
                "top_p": config.get("top_p"),
            }
        else:
            return {
                "type": "bedrock",
                "model_id": "us.anthropic.claude-sonnet-4-20250514-v1:0",
            }

    def _extract_prompt_from_messages(self, messages: Messages) -> str:
        """Extract user prompt from messages."""
        # Find the last user message
        for message in reversed(messages):
            if message["role"] == "user":
                for content in message["content"]:
                    if "text" in content:
                        return content["text"]
        return ""

    async def structured_output(self, output_model, prompt, system_prompt=None, **kwargs):
        """Not implemented for Temporal stub."""
        raise NotImplementedError("Structured output not implemented in Temporal context")


# Store original init safely to avoid recursion
_ORIGINAL_AGENT_INIT = None
_OVERRIDE_ACTIVE = False


# CRITICAL: Capture the original at module load time before any overrides
_ORIGINAL_AGENT_INIT = Agent.__init__


def _get_original_agent_init():
    """Get the true original Agent.__init__ method."""
    return _ORIGINAL_AGENT_INIT


def _temporal_agent_init(self, *args, **kwargs):
    """Modified Agent.__init__ that uses TemporalModelStub for models in workflows."""
    global _OVERRIDE_ACTIVE

    # Prevent recursion - more robust check
    if getattr(self, "_temporal_init_in_progress", False):
        # Use the module-level original directly to avoid any reference issues
        return _ORIGINAL_AGENT_INIT(self, *args, **kwargs)

    # Mark that we're in progress
    self._temporal_init_in_progress = True

    try:
        # Get the model from kwargs
        model = kwargs.get("model")
        tools = kwargs.get("tools", [])
        system_prompt = kwargs.get("system_prompt")

        if model and _OVERRIDE_ACTIVE:
            # Replace model with Temporal stub that has agent context
            kwargs["model"] = TemporalModelStub(model, tools, system_prompt)

        # Call original init using module-level reference
        return _ORIGINAL_AGENT_INIT(self, *args, **kwargs)

    finally:
        # Clean up the flag
        if hasattr(self, "_temporal_init_in_progress"):
            delattr(self, "_temporal_init_in_progress")


@contextmanager
def set_strands_temporal_overrides():
    """Override Agent.__init__ to inject TemporalModelStub when needed.

    This follows the OpenAI Agents pattern of intercepting at model level.
    """
    global _OVERRIDE_ACTIVE

    # Get the original before we start
    original_init = _get_original_agent_init()

    # Check if we're already overridden to prevent nested overrides
    if Agent.__init__ == _temporal_agent_init:
        # Already overridden, just yield
        yield
        return

    try:
        # Set override active and replace Agent.__init__
        _OVERRIDE_ACTIVE = True
        Agent.__init__ = _temporal_agent_init
        yield

    finally:
        # Restore original and clear flag
        _OVERRIDE_ACTIVE = False
        Agent.__init__ = original_init
