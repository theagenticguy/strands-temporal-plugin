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

import temporalio.client
import temporalio.service
import temporalio.worker
from .activities import execute_model_activity, execute_tool_activity
from .mcp_activities import execute_mcp_tool_activity, list_mcp_tools_activity
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from temporalio.client import ClientConfig, WorkflowHistory
from temporalio.contrib.pydantic import PydanticPayloadConverter
from temporalio.converter import DataConverter
from temporalio.worker import Replayer, ReplayerConfig, Worker, WorkerConfig, WorkflowReplayResult
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions


class StrandsTemporalPlugin(temporalio.client.Plugin, temporalio.worker.Plugin):
    """Plugin for seamless integration of Strands Agents with Temporal workflows.

    This plugin automatically configures Temporal to work with Strands agents by:
    - Setting up Pydantic serialization for Strands types
    - Registering model and tool execution activities
    - Configuring sandbox restrictions for Strands imports

    The plugin follows the DurableAgent pattern where:
    - Model inference runs in activities (where credentials exist)
    - Tool execution runs in activities (with proper retries)
    - Workflow orchestrates the agent loop deterministically

    Example:
        from temporalio.client import Client
        from temporalio.worker import Worker
        from strands_temporal_plugin import StrandsTemporalPlugin, DurableAgent

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

        # In your workflow, use DurableAgent
        @workflow.defn
        class WeatherWorkflow:
            @workflow.run
            async def run(self, prompt: str) -> str:
                agent = DurableAgent(config=DurableAgentConfig(...))
                result = await agent.invoke(prompt)
                return result.text
    """

    def run_replayer(
        self, replayer: Replayer, histories: AsyncIterator[WorkflowHistory]
    ) -> AbstractAsyncContextManager[AsyncIterator[WorkflowReplayResult]]:
        """Delegate replayer execution to next plugin."""
        return self.next_worker_plugin.run_replayer(replayer, histories)

    def configure_replayer(self, config: ReplayerConfig) -> ReplayerConfig:
        """Delegate replayer configuration to next plugin."""
        return self.next_worker_plugin.configure_replayer(config)

    async def run_worker(self, worker: Worker) -> None:
        """Delegate worker execution to next plugin."""
        await self.next_worker_plugin.run_worker(worker)

    def init_client_plugin(self, next: temporalio.client.Plugin) -> None:
        """Initialize client plugin chain."""
        self.next_client_plugin = next

    async def connect_service_client(
        self, config: temporalio.service.ConnectConfig
    ) -> temporalio.service.ServiceClient:
        """Delegate service client connection to next plugin."""
        return await self.next_client_plugin.connect_service_client(config)

    def init_worker_plugin(self, next: temporalio.worker.Plugin) -> None:
        """Initialize worker plugin chain."""
        self.next_worker_plugin = next

    def configure_client(self, config: ClientConfig) -> ClientConfig:
        """Configure client with Pydantic data converter.

        This ensures all Pydantic models (including our types) serialize
        properly through Temporal's payload system.
        """
        config["data_converter"] = DataConverter(payload_converter_class=PydanticPayloadConverter)
        return config

    def configure_worker(self, config: WorkerConfig) -> WorkerConfig:
        """Configure worker with activities and sandbox restrictions.

        This method:
        1. Configures sandbox to allow Strands, MCP, and boto3 imports
        2. Registers model, tool, and MCP execution activities
        """
        # Configure sandbox to allow necessary imports
        # These modules need to pass through the sandbox unchanged
        custom_restrictions = SandboxRestrictions.default.with_passthrough_modules(
            # Strands SDK modules
            "strands",
            "strands.models",
            "strands.event_loop",
            "strands.event_loop.streaming",
            "strands.types",
            "strands.types.content",
            "strands.types.streaming",
            "strands.types.tools",
            "strands.tools",
            "strands.tools.mcp",
            # MCP SDK modules
            "mcp",
            "mcp.client",
            "mcp.client.streamable_http",
            "mcp.client.stdio",
            "mcp.types",
            # AWS SDK (for BedrockModel)
            "botocore",
            "boto3",
            "urllib3",
            # HTTP clients
            "httpx",
            "aiohttp",
            # Pydantic (for data models)
            "pydantic",
            "pydantic_core",
            # Anyio (for async support)
            "anyio",
            "sniffio",
        )

        config["workflow_runner"] = SandboxedWorkflowRunner(restrictions=custom_restrictions)

        # Register activities
        activities = list(config.get("activities") or [])

        # Add model execution activity
        if execute_model_activity not in activities:
            activities.append(execute_model_activity)

        # Add tool execution activity
        if execute_tool_activity not in activities:
            activities.append(execute_tool_activity)

        # Add MCP activities
        if list_mcp_tools_activity not in activities:
            activities.append(list_mcp_tools_activity)

        if execute_mcp_tool_activity not in activities:
            activities.append(execute_mcp_tool_activity)

        config["activities"] = activities

        return config
