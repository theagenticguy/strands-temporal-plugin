"""Strands Temporal Plugin - Main Plugin Implementation

This plugin provides seamless integration between Strands Agents and Temporal workflows.
It handles:
- Pydantic-based data conversion for proper serialization
- Activity registration for model and tool execution
- Sandbox configuration for Strands imports

Usage:
    from temporalio.client import Client
    from temporalio.worker import Worker
    from strands_temporal_plugin import StrandsTemporalPlugin

    # Connect with plugin
    client = await Client.connect("localhost:7233", plugins=[StrandsTemporalPlugin()])

    # Create worker - plugin auto-registers activities
    worker = Worker(
        client,
        task_queue="strands-agents",
        workflows=[MyWorkflow],
    )
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.plugin import SimplePlugin
from temporalio.worker._workflow_instance import WorkflowRunner
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

from .activities import execute_model_activity, execute_structured_output_activity, execute_tool_activity
from .mcp_activities import execute_mcp_tool_activity, list_mcp_tools_activity
from .session import load_session_activity, save_session_activity


# Modules that are safe to pass through the sandbox.
# These should only be data types and pure modules - NO I/O libraries.
# I/O operations (boto3, httpx, urllib3, etc.) must stay in activities only.
_SAFE_PASSTHROUGH_MODULES = (
    # Pydantic (for data models - required for serialization)
    "pydantic",
    "pydantic_core",
    # Strands type definitions (NOT strands.models which does I/O)
    "strands.types",
    "strands.types.content",
    "strands.types.streaming",
    "strands.types.tools",
    "strands.types.event",
    "strands.types._events",  # TypedEvent and event classes (needed for tool executor)
    "strands.types.event_loop",
    "strands.types.interrupt",  # Interrupt type (needed for hook return values)
    # Strands Model ABC (for TemporalModelStub subclassing)
    "strands.models",
    "strands.models.model",
    # Strands tool executor base class (for TemporalToolExecutor subclassing)
    "strands.tools",
    "strands.tools.executor",
    "strands.tools.executors",
    "strands.tools.executors._executor",
    # Strands hooks (for before/after tool call events in TemporalToolExecutor)
    "strands.hooks",
    "strands.experimental",
    "strands.experimental.hooks",
    "strands.experimental.hooks.events",
    # Strands telemetry (for Trace type in ToolExecutor._execute signature)
    "strands.telemetry",
    "strands.telemetry.metrics",
    "strands.telemetry.tracer",
    # Strands agent core (for Agent class - models do I/O but are replaced)
    "strands.agent",
    # Strands conversation manager (for ConversationManager in workflow context)
    "strands.agent.conversation_manager",
    # Strands structured output context (for ToolExecutor._execute signature)
    "strands.tools.structured_output",
    "strands.tools.structured_output._structured_output_context",
    # Note: strands.models.* provider implementations are NOT passed through
    # - use TemporalModelStub instead (I/O happens in activities)
    # Plugin modules (activities/tool_executor/mcp_activities contain activity
    # references used in workflow context via workflow.execute_activity().
    # Actual I/O libraries like boto3/httpx/mcp are imported inside functions,
    # not at module level, so they remain sandbox-restricted.)
    "strands_temporal_plugin",
)


def _merge_workflow_runner(existing: WorkflowRunner | None) -> WorkflowRunner:
    """Merge sandbox restrictions instead of replacing them.

    This callable is used by SimplePlugin to configure the workflow runner.
    It respects any existing sandbox restrictions from other plugins and
    adds our passthrough modules on top.

    Args:
        existing: The existing workflow runner from earlier plugins, if any.

    Returns:
        A SandboxedWorkflowRunner with merged restrictions.
    """
    # Get base restrictions from existing runner or use defaults
    if existing is None:
        base_restrictions = SandboxRestrictions.default
    elif isinstance(existing, SandboxedWorkflowRunner):
        base_restrictions = existing.restrictions
    else:
        # Non-sandboxed runner - start from defaults
        base_restrictions = SandboxRestrictions.default

    # Add our passthrough modules to existing restrictions
    merged_restrictions = base_restrictions.with_passthrough_modules(*_SAFE_PASSTHROUGH_MODULES)

    return SandboxedWorkflowRunner(restrictions=merged_restrictions)


def _merge_activities(
    existing: Sequence[Callable] | None,
) -> Sequence[Callable]:
    """Merge activities instead of replacing them.

    This callable is used by SimplePlugin to configure activities.
    It preserves any existing activities from other plugins and adds ours.

    Args:
        existing: The existing activities from earlier plugins, if any.

    Returns:
        A sequence containing both existing and plugin activities.
    """
    activities: list[Callable] = list(existing) if existing else []

    # Add our activities if not already present
    plugin_activities = [
        execute_model_activity,
        execute_tool_activity,
        execute_structured_output_activity,
        list_mcp_tools_activity,
        execute_mcp_tool_activity,
        load_session_activity,
        save_session_activity,
    ]

    for activity in plugin_activities:
        if activity not in activities:
            activities.append(activity)

    return activities


class StrandsTemporalPlugin(SimplePlugin):
    """Plugin for seamless integration of Strands Agents with Temporal workflows.

    This plugin automatically configures Temporal to work with Strands agents by:
    - Setting up Pydantic serialization for Strands types
    - Registering model and tool execution activities
    - Configuring sandbox restrictions for safe imports (data types only)

    The plugin enables the durable agent pattern where:
    - Model inference runs in activities (where credentials exist)
    - Tool execution runs in activities (with proper retries)
    - Workflow orchestrates the agent loop deterministically

    Important: I/O libraries (boto3, httpx, urllib3, etc.) are intentionally NOT
    passed through the sandbox. They should only be used in activities, not workflows.
    This ensures workflow determinism during replay.

    Example:
        from temporalio.client import Client
        from temporalio.worker import Worker
        from strands_temporal_plugin import (
            StrandsTemporalPlugin,
            create_durable_agent,
            BedrockProviderConfig,
        )

        # Connect with plugin
        client = await Client.connect(
            "localhost:7233",
            plugins=[StrandsTemporalPlugin()]
        )

        # Create worker
        worker = Worker(
            client,
            task_queue="strands-agents",
            workflows=[WeatherWorkflow],
            # Note: activities auto-registered by plugin
        )

        # In your workflow, use create_durable_agent()
        @workflow.defn
        class WeatherWorkflow:
            @workflow.run
            async def run(self, prompt: str) -> str:
                agent = create_durable_agent(
                    provider_config=BedrockProviderConfig(model_id="..."),
                    tools=[get_weather],
                    system_prompt="You are helpful.",
                )
                result = await agent.invoke_async(prompt)
                return str(result)
    """

    def __init__(self) -> None:
        """Initialize the Strands Temporal Plugin.

        Uses SimplePlugin's declarative approach to configure:
        - Pydantic data converter for serialization
        - Activities for model/tool execution (merged with existing)
        - Sandbox restrictions for safe imports (merged with existing)
        """
        super().__init__(
            name="strands-temporal-plugin",
            data_converter=pydantic_data_converter,
            activities=_merge_activities,
            workflow_runner=_merge_workflow_runner,
        )
