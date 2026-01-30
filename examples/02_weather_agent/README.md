# 02 - Weather Agent

Your first agent with tools. This example demonstrates using `create_durable_agent()` to build a weather assistant.

## What You'll Learn

- Using `create_durable_agent()` for full durability
- Adding tools to your agent
- How tool calls are routed through Temporal activities

## Prerequisites

1. **Temporal Server**: Start the development server
   ```bash
   temporal server start-dev
   ```

2. **AWS Credentials**: Configure for Bedrock access
   ```bash
   export AWS_REGION=us-east-1
   ```

## Running the Example

### 1. Start the Worker

```bash
cd examples/02_weather_agent
uv run python run_worker.py
```

### 2. Run the Client

```bash
# Default prompt
uv run python run_client.py

# Custom prompt
uv run python run_client.py "What's the weather in Paris?"
```

### 3. View in Temporal UI

Open http://localhost:8233 to see the workflow execution and tool calls.

## Files

| File | Description |
|------|-------------|
| `workflow.py` | WeatherAgentWorkflow definition |
| `tools.py` | get_weather tool implementation |
| `run_worker.py` | Starts the Temporal worker |
| `run_client.py` | Executes the workflow |

## Key Concept: `create_durable_agent()`

```python
agent = create_durable_agent(
    provider_config=BedrockProviderConfig(...),
    tools=[get_weather],
    system_prompt="You are a weather assistant...",
)
```

This factory function creates an agent with:
- **TemporalModelStub**: Routes model calls to activities (durable)
- **TemporalToolExecutor**: Routes tool calls to activities (durable)
- **Auto tool discovery**: Finds tool modules automatically

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     WORKFLOW                             │
│                                                         │
│   create_durable_agent() creates:                        │
│   ├── TemporalModelStub  → model calls to activity      │
│   └── TemporalToolExecutor → tool calls to activity     │
│                                                         │
│   agent.invoke_async(prompt)                            │
│        │                                                 │
│        ▼                                                 │
│   ┌───────────────────────────────────────────────────┐ │
│   │           Strands Agent Event Loop                 │ │
│   │   1. model.stream() → execute_model_activity      │ │
│   │   2. Parse tool request                            │ │
│   │   3. tool() → execute_tool_activity               │ │
│   │   4. model.stream() → execute_model_activity      │ │
│   │   5. Return final response                         │ │
│   └───────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## Durability Benefits

- **Model calls**: Survive worker restarts, automatic retries
- **Tool calls**: Survive worker restarts, configurable retries
- **Full visibility**: See each step in Temporal UI
- **Replay safe**: Workflow state reconstructed from history

## Next Steps

Once you're comfortable with this example, move on to:
- **03_multi_tool_agent** - Multiple tools and workflow patterns
