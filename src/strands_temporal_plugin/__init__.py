"""Strands Temporal Plugin - Clean Architecture

This plugin provides seamless integration between Strands Agents and Temporal workflows,
following the same design patterns as OpenAI's Temporal integration.

## Usage

```python
from temporalio import workflow
from temporalio.client import Client
from temporalio.worker import Worker
from strands import Agent
from strands.models import BedrockModel
from strands_temporal_plugin import StrandsTemporalPlugin


# Just use normal Strands Agent API in workflows!
@workflow.defn
class WeatherAgent:
    @workflow.run
    async def run(self, prompt: str) -> str:
        agent = Agent(
            model=BedrockModel(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0"),
            tools=[get_weather],
            system_prompt="You are a weather assistant",
        )
        result = agent(prompt)  # Automatically becomes durable!
        return str(result)


# Setup (same as OpenAI pattern)
client = await Client.connect("localhost:7233", plugins=[StrandsTemporalPlugin()])
worker = Worker(client, task_queue="strands-agents", workflows=[WeatherAgent])
await worker.run()
```

The plugin automatically handles all the complexity - no manual configuration needed!
"""

from .plugin import StrandsTemporalPlugin

__version__ = "0.1.0"
__all__ = ["StrandsTemporalPlugin"]
