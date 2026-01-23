"""Weather Agent Worker

Starts a Temporal worker that can execute weather agent workflows.

The worker uses the StrandsTemporalPlugin which automatically:
- Registers model and tool execution activities
- Configures Pydantic serialization
- Sets up sandbox restrictions for Strands imports

Usage:
    # Start Temporal server first:
    temporal server start-dev

    # Then run this worker:
    cd examples/basic_weather_agent
    uv run python run_worker.py
"""

import asyncio
from mcp_workflow import MCPDiscoveryWorkflow, SimpleMCPWorkflow
from http_mcp_workflow import HTTPMCPWorkflow, AWSKnowledgeMCPWorkflow
from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client
from temporalio.worker import Worker
from workflows import FullyDurableWeatherAgent, SimpleAgentWorkflow, StrandsWeatherAgent


async def main():
    """Set up and run the weather agent worker."""
    print("Strands Weather Agent Worker")
    print("============================")
    print()

    # Connect to Temporal with the plugin
    # The plugin configures Pydantic serialization for our types
    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )

    # Create the worker
    # The plugin automatically registers the model and tool activities
    worker = Worker(
        client,
        task_queue="strands-agents",
        workflows=[
            FullyDurableWeatherAgent,  # RECOMMENDED: Full durability
            StrandsWeatherAgent,  # Model-only durability
            SimpleAgentWorkflow,
            MCPDiscoveryWorkflow,  # MCP tool discovery (stdio)
            SimpleMCPWorkflow,  # Simple MCP pattern (stdio)
            HTTPMCPWorkflow,  # Generic HTTP MCP
            AWSKnowledgeMCPWorkflow,  # AWS Knowledge HTTP MCP
        ],
        # Note: Activities are auto-registered by the plugin
    )

    print("Worker configuration:")
    print("  - Task queue: strands-agents")
    print("  - Workflows:")
    print("      • FullyDurableWeatherAgent (static tools)")
    print("      • StrandsWeatherAgent (model-only durability)")
    print("      • MCPDiscoveryWorkflow (stdio MCP)")
    print("      • SimpleMCPWorkflow (stdio MCP)")
    print("      • HTTPMCPWorkflow (HTTP MCP)")
    print("      • AWSKnowledgeMCPWorkflow (AWS Knowledge HTTP MCP)")
    print()
    print("Plugin automatically handles:")
    print("  - Model execution activity (execute_model_activity)")
    print("  - Tool execution activity (execute_tool_activity)")
    print("  - Pydantic serialization for all types")
    print("  - Sandbox restrictions for Strands imports")
    print()
    print("Worker starting... Press Ctrl+C to stop")
    print()

    try:
        await worker.run()
    except KeyboardInterrupt:
        print("\nShutting down worker...")
    finally:
        print("Worker stopped.")


if __name__ == "__main__":
    asyncio.run(main())
