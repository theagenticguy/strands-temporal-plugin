"""Quickstart Workflow - Simplest Possible Example

This is the most basic Strands Temporal workflow - a simple agent
without any tools. It demonstrates:
- Setting up a Temporal workflow with Strands
- Using TemporalModelStub for durable model calls
- Basic agent invocation

This is the starting point for understanding Strands + Temporal.
"""

import logging
from temporalio import workflow

# Import strands with sandbox passthrough to avoid I/O library restrictions
with workflow.unsafe.imports_passed_through():
    from strands import Agent
    from strands_temporal_plugin import BedrockProviderConfig, TemporalModelStub


# Configure logging
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()],
)


@workflow.defn
class QuickstartWorkflow:
    """The simplest possible Strands + Temporal workflow.

    This workflow demonstrates:
    - Creating an Agent with TemporalModelStub
    - Durable model calls via Temporal activities
    - No tools - just a conversational agent

    Example usage:
        result = await client.execute_workflow(
            QuickstartWorkflow.run,
            "What is the capital of France?",
            id="quickstart-1",
            task_queue="strands-quickstart",
        )
    """

    @workflow.run
    async def run(self, prompt: str) -> str:
        """Run the quickstart agent.

        Args:
            prompt: User's question

        Returns:
            Agent's response
        """
        # Create a Strands Agent with TemporalModelStub
        # The stub routes model calls to Temporal activities for durability
        agent = Agent(
            model=TemporalModelStub(
                BedrockProviderConfig(
                    model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                )
            ),
            system_prompt="You are a helpful assistant. Answer questions clearly and concisely.",
        )

        # Invoke the agent - model calls are durable via Temporal
        result = await agent.invoke_async(prompt)
        return str(result)
