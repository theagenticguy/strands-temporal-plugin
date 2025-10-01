"""Strands Agent Execution Activity

Single activity that runs the complete Strands agent loop with full durability.
"""

from pydantic import BaseModel

# Import Strands components (allowed via sandbox passthrough)
from strands import Agent
from strands.models import BedrockModel, Model
from strands.types.content import Messages
from strands.types.tools import ToolSpec
from temporalio import activity
from typing import Any


class AgentExecutionInput(BaseModel):
    """Input for the agent execution activity."""

    prompt: str
    ai_model_config: dict[str, Any]
    tool_specs: list[ToolSpec]
    system_prompt: str | None = None
    messages: Messages | None = None


class AgentExecutionResult(BaseModel):
    """Result from agent execution."""

    text: str
    usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    stop_reason: str = "end_turn"


@activity.defn
async def execute_strands_agent(input_data: AgentExecutionInput) -> AgentExecutionResult:
    """Execute a complete Strands agent with model and tools.

    This activity runs the full Strands agent loop:
    1. Creates the model from config
    2. Creates agent with model, tools, and system prompt
    3. Runs agent(prompt) with full event loop
    4. Returns the final result

    Args:
        input_data: Agent configuration and prompt

    Returns:
        Agent execution result with text and usage
    """
    try:
        # Create the model from configuration
        model = _create_model_from_config(input_data.ai_model_config)

        # Create tools from tool specs
        tools = _create_tools_from_specs(input_data.tool_specs)

        # Create the agent with normal Strands API (no overrides in activities)
        agent = Agent(
            model=model,
            tools=tools,
            system_prompt=input_data.system_prompt,
            callback_handler=None,  # No output in activities
        )

        # Run the agent with the prompt
        result = agent(input_data.prompt)

        # Extract the result text
        result_text = str(result)

        # Extract usage information from AgentResult.metrics
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        if hasattr(result, "metrics") and result.metrics:
            accumulated_usage = result.metrics.accumulated_usage
            usage = {
                "input_tokens": accumulated_usage.get("inputTokens", 0),
                "output_tokens": accumulated_usage.get("outputTokens", 0),
                "total_tokens": accumulated_usage.get("totalTokens", 0),
            }

        return AgentExecutionResult(text=result_text, usage=usage, stop_reason="end_turn")

    except Exception as e:
        # Return error as text to maintain workflow determinism
        return AgentExecutionResult(
            text=f"Error executing agent: {str(e)}",
            usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            stop_reason="error",
        )


def _create_model_from_config(model_config: dict[str, Any]) -> Model:
    """Create a Strands model from configuration.

    Args:
        model_config: Model configuration dictionary

    Returns:
        Strands Model instance
    """
    model_type = model_config.get("type", "bedrock")

    if model_type == "bedrock":
        return BedrockModel(
            model_id=model_config.get("model_id", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
            region_name=model_config.get("region"),
            max_tokens=model_config.get("max_tokens", 4000),
            temperature=model_config.get("temperature"),
            top_p=model_config.get("top_p"),
        )
    else:
        raise ValueError(f"Unsupported model type: {model_type}")


def _create_tools_from_specs(tool_specs: list[ToolSpec]) -> list[Any]:
    """Create tool functions from tool specifications.

    Args:
        tool_specs: List of tool specifications

    Returns:
        List of tool functions (simplified for now)
    """
    # TODO: Implement proper tool recreation from specs
    # For now, return empty list - tools need to be registered separately
    # This allows the architecture to work while we implement tool recreation
    return []
