# 03 - Multi-Tool Agent

Comprehensive examples demonstrating multiple tools and workflow patterns with `create_durable_agent()`.

## What is `create_durable_agent()`?

The `create_durable_agent()` factory creates a Strands Agent with full Temporal durability:

```python
from strands_temporal_plugin import create_durable_agent, BedrockProviderConfig

agent = create_durable_agent(
    provider_config=BedrockProviderConfig(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0"),
    tools=[get_weather, search_web],
    system_prompt="You are a helpful assistant.",
)

result = await agent.invoke_async("What's the weather in Seattle?")
```

This factory:
1. Creates a `TemporalModelStub` - routes model inference to Temporal activities
2. Creates a `TemporalToolExecutor` - routes tool execution to Temporal activities
3. Auto-discovers tool modules from `@tool` decorated functions
4. Returns a standard Strands Agent

## Benefits

- **Crash-proof**: Both model calls and tool calls survive worker restarts
- **Automatic retries**: Transient failures are retried with exponential backoff
- **Timeouts**: Long-running operations are properly handled
- **Observability**: Full visibility in Temporal UI

## Quick Start

### 1. Start Temporal Server

```bash
temporal server start-dev
```

### 2. Start the Worker

```bash
cd examples/03_multi_tool_agent
uv run python run_worker.py
```

### 3. Run Example Workflows

```bash
# Weather assistant (single tool)
uv run python run_client.py weather

# Research assistant (search + calculate)
uv run python run_client.py research

# Notification agent (user lookup + notifications)
uv run python run_client.py notify

# Finance assistant (stocks + calculate)
uv run python run_client.py finance

# General assistant (all tools)
uv run python run_client.py general

# Run all examples
uv run python run_client.py all

# Custom prompt
uv run python run_client.py weather --prompt "What's the weather in Paris?"
```

### 4. View in Temporal UI

Open http://localhost:8233 to see workflow history, activity attempts, and more.

## Example Workflows

### WeatherAssistant

Simple single-tool agent for weather queries.

```python
@workflow.defn
class WeatherAssistant:
    @workflow.run
    async def run(self, prompt: str) -> str:
        agent = create_durable_agent(
            provider_config=BedrockProviderConfig(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            ),
            tools=[get_weather],
            system_prompt="You are a helpful weather assistant.",
        )
        result = await agent.invoke_async(prompt)
        return str(result)
```

### ResearchAssistant

Multi-tool agent with web search and calculations.

```python
@workflow.defn
class ResearchAssistant:
    @workflow.run
    async def run(self, prompt: str) -> str:
        agent = create_durable_agent(
            provider_config=BedrockProviderConfig(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                max_tokens=4096,
            ),
            tools=[search_web, calculate],
            system_prompt="You are a research assistant...",
            tool_timeout=120.0,  # Custom timeout for slow searches
        )
        result = await agent.invoke_async(prompt)
        return str(result)
```

### GeneralAssistant

Full-featured agent with all available tools.

```python
@workflow.defn
class GeneralAssistant:
    @workflow.run
    async def run(self, prompt: str) -> str:
        agent = create_durable_agent(
            provider_config=BedrockProviderConfig(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                max_tokens=4096,
            ),
            tools=[
                get_weather,
                search_web,
                calculate,
                get_stock_price,
                get_user_info,
                send_notification,
            ],
            system_prompt="You are a versatile assistant...",
            model_timeout=300.0,
            tool_timeout=120.0,
        )
        result = await agent.invoke_async(prompt)
        return str(result)
```

## Configuration Options

### `create_durable_agent()` Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `provider_config` | `ProviderConfig` | Required | Model provider configuration |
| `tools` | `list` | `None` | List of @tool decorated functions |
| `tool_modules` | `dict` | `None` | Override tool module discovery |
| `system_prompt` | `str` | `None` | System prompt for the agent |
| `model_timeout` | `float` | `300.0` | Timeout for model calls (seconds) |
| `tool_timeout` | `float` | `60.0` | Timeout for tool calls (seconds) |
| `**agent_kwargs` | `Any` | - | Additional Strands Agent arguments |

### BedrockProviderConfig Options

```python
BedrockProviderConfig(
    model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
    max_tokens=4096,
    temperature=0.7,
    top_p=0.9,
    # ... other Bedrock parameters
)
```

## Tools

The example includes several tools demonstrating different patterns:

| Tool | Description | Notes |
|------|-------------|-------|
| `get_weather` | Weather lookup | Simple synchronous tool |
| `search_web` | Web search | May fail transiently (demonstrates retries) |
| `calculate` | Math evaluation | Pure function, no I/O |
| `get_stock_price` | Stock prices | Simulated financial API |
| `get_user_info` | User lookup | Simulated database query |
| `send_notification` | Send notifications | May fail transiently |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        WORKFLOW CONTEXT                          │
│                                                                  │
│   create_durable_agent() creates:                                │
│   ├── TemporalModelStub → routes model.stream() to activity     │
│   └── TemporalToolExecutor → routes tool calls to activity      │
│                                                                  │
│   agent.invoke_async(prompt)                                     │
│        │                                                         │
│        ▼                                                         │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │              Strands Agent Event Loop                     │  │
│   │   1. model.stream() → execute_model_activity             │  │
│   │   2. Parse response                                       │  │
│   │   3. tool_executor() → execute_tool_activity             │  │
│   │   4. Loop until done                                      │  │
│   └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       ACTIVITY CONTEXT                           │
│                                                                  │
│   execute_model_activity():                                      │
│   ├── Creates real BedrockModel                                  │
│   ├── Calls AWS Bedrock API                                      │
│   └── Returns streamed events                                    │
│                                                                  │
│   execute_tool_activity():                                       │
│   ├── Imports tool from module                                   │
│   ├── Executes tool function                                     │
│   └── Returns result                                             │
└─────────────────────────────────────────────────────────────────┘
```

## Testing Crash Recovery

To test the crash-proof capabilities:

1. Start a workflow with a multi-tool query
2. Kill the worker mid-execution
3. Restart the worker
4. Watch the workflow resume from where it left off

See the `tests/integration/test_failure_simulation.py` and `scripts/` directory for automated failure testing.

## Next Steps

Once you're comfortable with this example, explore:
- **04_mcp_stdio** - MCP with local stdio servers
- **05_mcp_http** - MCP with remote HTTP servers
