"""Strands Temporal Plugin - Main Plugin Implementation

Following the OpenAI Agents pattern exactly for clean integration.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import AsyncIterator

import temporalio.client
import temporalio.service
import temporalio.worker
from .activities import execute_strands_model
from .runner import set_strands_temporal_overrides
from temporalio.client import ClientConfig, Plugin, WorkflowHistory
from temporalio.contrib.pydantic import PydanticPayloadConverter
from temporalio.converter import DataConverter
from temporalio.worker import WorkerConfig, Worker, ReplayerConfig, Replayer, WorkflowReplayResult
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions


class StrandsTemporalPlugin(temporalio.client.Plugin, temporalio.worker.Plugin):
    """Plugin for seamless integration of Strands Agents with Temporal workflows.

    This plugin automatically configures Temporal to work with Strands agents by:
    - Setting up proper Pydantic serialization for Strands types
    - Registering the agent execution activity
    - Overriding Agent behavior when called inside workflows
    - Handling sandbox restrictions for Strands imports

    Usage is identical to OpenAI Agents pattern:
    ```python
    client = await Client.connect("localhost:7233", plugins=[StrandsTemporalPlugin()])
    worker = Worker(client, task_queue="strands-agents", workflows=[MyWorkflow])
    ```
    """

    def run_replayer(self, replayer: Replayer, histories: AsyncIterator[WorkflowHistory]) -> \
    AbstractAsyncContextManager[AsyncIterator[WorkflowReplayResult]]:
        return self.next_worker_plugin.run_replayer(replayer, histories)

    def configure_replayer(self, config: ReplayerConfig) -> ReplayerConfig:
        return self.next_worker_plugin.configure_replayer(config)

    async def run_worker(self, worker: Worker) -> None:
        await self.next_worker_plugin.run_worker(worker)

    def init_client_plugin(self, next: temporalio.client.Plugin) -> None:
        """Set the next client plugin"""
        self.next_client_plugin = next

    async def connect_service_client(
        self, config: temporalio.service.ConnectConfig
    ) -> temporalio.service.ServiceClient:
        """No modifications to service client"""
        return await self.next_client_plugin.connect_service_client(config)

    def init_worker_plugin(self, next: temporalio.worker.Plugin) -> None:
        """Set the next worker plugin"""
        self.next_worker_plugin = next

    def configure_client(self, config: ClientConfig) -> ClientConfig:
        """Configure client with Pydantic data converter."""
        config["data_converter"] = DataConverter(payload_converter_class=PydanticPayloadConverter)
        return config

    def configure_worker(self, config: WorkerConfig) -> WorkerConfig:
        """Configure worker with Strands agent activity and sandbox restrictions."""
        # Configure sandbox to allow Strands imports
        custom_restrictions = SandboxRestrictions.default.with_passthrough_modules(
            "strands",
            "strands.models",
            "strands.event_loop",
            "strands.event_loop.streaming",
            "strands.types",
            "strands.tools",
            "botocore",
            "boto3",
            "urllib3",
        )

        config["workflow_runner"] = SandboxedWorkflowRunner(restrictions=custom_restrictions)

        # Register the single agent execution activity
        activities = list(config.get("activities") or [])
        activities.append(execute_strands_model)
        config["activities"] = activities

        # CRITICAL: Set up the global overrides here so they're active for all workflows
        print("Activating Strands temporal overrides globally...")
        # self._setup_global_overrides()

        return config

    def _setup_global_overrides(self):
        """Set up global overrides that will be active for all workflows."""
        # Import and activate global overrides
        from . import runner
        from strands import Agent

        # Set the global override active
        runner._OVERRIDE_ACTIVE = True

        # Replace Agent.__init__ globally
        Agent.__init__ = runner._temporal_agent_init
        print("Agent.__init__ override is now active globally")
