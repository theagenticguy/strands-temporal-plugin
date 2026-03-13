"""Custom Provider Workflow

Demonstrates using CustomProviderConfig with create_durable_agent() to plug
in a custom model provider via import path.
"""

import logging

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from strands_temporal_plugin import CustomProviderConfig, create_durable_agent

logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()],
)


@workflow.defn
class CustomProviderWorkflow:
    """Workflow using a custom model provider.

    Uses CustomProviderConfig to load LoggingBedrockModel via its import path.
    The activity resolves the class at runtime using importlib.

    Example usage:
        result = await client.execute_workflow(
            CustomProviderWorkflow.run,
            "What is the meaning of life?",
            id="custom-provider-1",
            task_queue="strands-custom-provider",
        )
    """

    @workflow.run
    async def run(self, prompt: str) -> str:
        """Run agent with the custom model provider.

        Args:
            prompt: User's question

        Returns:
            Agent's response
        """
        agent = create_durable_agent(
            provider_config=CustomProviderConfig(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                provider_class_path="custom_model.LoggingBedrockModel",
            ),
            system_prompt="You are a helpful assistant powered by a custom model provider.",
        )

        result = await agent.invoke_async(prompt)
        return str(result)
