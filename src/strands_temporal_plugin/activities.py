"""Strands Agent Execution Activity

Single activity that runs the complete Strands agent loop with full durability.
"""

from pydantic import BaseModel

# Import Strands components (allowed via sandbox passthrough)
from strands.models import BedrockModel
from strands.types.content import Messages
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolSpec
from temporalio import activity


class ModelExecutionInput(BaseModel):
    """Input for the agent execution activity."""

    model_id: str
    tool_specs: list[ToolSpec]
    system_prompt: str | None = None
    messages: Messages | None = None


class ModelExecutionResult(BaseModel):
    """Result from agent execution."""

    events: list[StreamEvent]


@activity.defn
async def execute_strands_model(input_data: ModelExecutionInput) -> ModelExecutionResult:
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
    # Create the model from configuration
    model = BedrockModel(model_id=input_data.model_id)

    # Run the agent with the prompt
    result = model.stream(input_data.messages, input_data.tool_specs, input_data.system_prompt)

    results = [event async for event in result]

    return ModelExecutionResult(events=results)


#
# def _create_model_from_config(model_config: dict[str, Any]) -> Model:
#     """Create a Strands model from configuration.
#
#     Args:
#         model_config: Model configuration dictionary
#
#     Returns:
#         Strands Model instance
#     """
#     model_type = model_config.get("type", "bedrock")
#
#     if model_type == "bedrock":
#         return BedrockModel(
#             model_id=model_config.get("model_id", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
#             region_name=model_config.get("region"),
#             max_tokens=model_config.get("max_tokens", 4000),
#             temperature=model_config.get("temperature"),
#             top_p=model_config.get("top_p"),
#         )
#     else:
#         raise ValueError(f"Unsupported model type: {model_type}")
