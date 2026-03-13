"""Failure resilience workflows demonstrating Temporal's retry and recovery.

Three scenarios:
1. TransientFailureWorkflow - Tool fails 2x then succeeds (automatic retry)
2. TimeoutRecoveryWorkflow - Slow tool + fast fallback (heartbeat timeout)
3. GracefulDegradationWorkflow - Mix of reliable and unreliable tools
"""

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from strands_temporal_plugin import BedrockProviderConfig, TemporalToolConfig, create_durable_agent
    from tools import (
        flaky_api_call,
        reliable_calculator,
        reset_counters,
        slow_database_query,
        unreliable_webhook,
    )


@workflow.defn
class TransientFailureWorkflow:
    """Demonstrates automatic retry of transient tool failures.

    The flaky_api_call tool fails with ConnectionError on the first 2 attempts,
    then succeeds on the 3rd. Temporal retries automatically — the agent never
    sees the failures, only the successful result.

    What to observe in Temporal UI:
    - The execute_tool_activity shows multiple attempts
    - Each failed attempt has the ConnectionError in the event history
    - The final attempt succeeds and the workflow completes normally
    """

    @workflow.run
    async def run(self, prompt: str) -> str:
        reset_counters()

        agent = create_durable_agent(
            provider_config=BedrockProviderConfig(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            ),
            tools=[flaky_api_call, reliable_calculator],
            system_prompt=(
                "You are a research assistant. Use flaky_api_call to search for information "
                "and reliable_calculator for math. Answer the user's question."
            ),
            tool_configs={
                "flaky_api_call": TemporalToolConfig(
                    start_to_close_timeout=30.0,
                    retry_max_attempts=5,
                    retry_initial_interval=1.0,
                    retry_backoff_coefficient=2.0,
                ),
            },
        )

        result = await agent.invoke_async(prompt)
        return str(result)


@workflow.defn
class TimeoutRecoveryWorkflow:
    """Demonstrates heartbeat timeout detection for stuck activities.

    The slow_database_query tool takes longer than its heartbeat timeout,
    causing Temporal to cancel and retry it. Combined with a fast calculator
    tool to show mixed reliability.

    What to observe in Temporal UI:
    - The slow_database_query activity starts, heartbeats for a while
    - If it exceeds heartbeat_timeout, Temporal cancels and retries
    - The workflow still completes because Temporal retries the activity
    """

    @workflow.run
    async def run(self, prompt: str) -> str:
        agent = create_durable_agent(
            provider_config=BedrockProviderConfig(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            ),
            tools=[slow_database_query, reliable_calculator],
            system_prompt=(
                "You are a data analyst. Use slow_database_query to fetch data "
                "and reliable_calculator for computations. Answer the user's question."
            ),
            tool_configs={
                "slow_database_query": TemporalToolConfig(
                    start_to_close_timeout=60.0,
                    heartbeat_timeout=10.0,
                ),
            },
        )

        result = await agent.invoke_async(prompt)
        return str(result)


@workflow.defn
class GracefulDegradationWorkflow:
    """Demonstrates how the agent handles permanent tool failures gracefully.

    The unreliable_webhook tool always fails (simulating a down service).
    After exhausting retries, the error propagates to the agent, which
    informs the user about the failure while still completing other tasks.

    What to observe in Temporal UI:
    - The unreliable_webhook activity fails all retry attempts
    - The agent receives the error and incorporates it into its response
    - Other tools (calculator) still work fine
    - The workflow completes (doesn't crash) — the agent handles the error
    """

    @workflow.run
    async def run(self, prompt: str) -> str:
        reset_counters()

        agent = create_durable_agent(
            provider_config=BedrockProviderConfig(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            ),
            tools=[unreliable_webhook, reliable_calculator],
            system_prompt=(
                "You are a task assistant. Try to complete all tasks the user asks for. "
                "If a tool fails after retries, inform the user about the failure and "
                "continue with any remaining tasks."
            ),
            tool_configs={
                "unreliable_webhook": TemporalToolConfig(
                    start_to_close_timeout=10.0,
                    retry_max_attempts=3,
                    retry_initial_interval=1.0,
                ),
            },
        )

        result = await agent.invoke_async(prompt)
        return str(result)
