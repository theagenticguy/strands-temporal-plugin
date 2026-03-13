"""Session Management Workflow

Demonstrates using TemporalSessionManager to persist agent conversation
state across workflow executions via S3.
"""

import logging

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from strands_temporal_plugin import (
        BedrockProviderConfig,
        SessionConfig,
        TemporalSessionManager,
        create_durable_agent,
    )

    from tools import recall_facts, remember_fact

logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()],
)


@workflow.defn
class SessionWorkflow:
    """Workflow with S3-backed session persistence.

    Uses TemporalSessionManager to load/save conversation history between
    workflow executions. The agent can remember facts across turns.

    Example usage:
        result = await client.execute_workflow(
            SessionWorkflow.run,
            {"prompt": "Remember my name is Alice", "session_id": "demo"},
            id="session-1",
            task_queue="strands-session",
        )
    """

    @workflow.run
    async def run(self, input_data: dict) -> str:
        """Run the session-aware agent.

        Args:
            input_data: Dict with keys:
                - prompt: User's message
                - session_id: Session identifier (default: "demo")
                - bucket: S3 bucket name (default: "agent-sessions")
                - region_name: AWS region (default: "us-east-1")

        Returns:
            Agent's response
        """
        prompt = input_data["prompt"]
        session_config = SessionConfig(
            session_id=input_data.get("session_id", "demo"),
            bucket=input_data.get("bucket", "agent-sessions"),
            region_name=input_data.get("region_name", "us-east-1"),
        )

        # Load previous session state from S3
        session = TemporalSessionManager(session_config)
        await session.load()

        # Create durable agent
        agent = create_durable_agent(
            provider_config=BedrockProviderConfig(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            ),
            tools=[remember_fact, recall_facts],
            system_prompt=(
                "You are a helpful assistant with memory. You can remember facts "
                "and recall them later. Use the remember_fact tool to store information "
                "and recall_facts to retrieve it."
            ),
        )

        # Restore conversation history from session
        if session.messages:
            agent.messages.extend(session.messages)

        # Run agent
        result = await agent.invoke_async(prompt)

        # Save updated state to S3
        await session.save(agent)

        return str(result)
