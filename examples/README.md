# Strands Temporal Plugin Examples

Examples demonstrating how to build durable AI agents with Strands and Temporal.

## Quick Start

```bash
# Start Temporal server
temporal server start-dev

# Pick an example and run it
cd examples/01_quickstart
uv run python run_worker.py  # Terminal 1
uv run python run_client.py  # Terminal 2

# View in Temporal UI
open http://localhost:8233
```

## Examples Overview

| Example | Description | Complexity |
|---------|-------------|------------|
| [01_quickstart](./01_quickstart/) | Simplest possible agent, no tools | Beginner |
| [02_weather_agent](./02_weather_agent/) | First agent with a tool | Beginner |
| [03_multi_tool_agent](./03_multi_tool_agent/) | Multiple tools, per-tool config, parallel execution | Intermediate |
| [04_mcp_stdio](./04_mcp_stdio/) | MCP with local stdio servers | Advanced |
| [05_mcp_http](./05_mcp_http/) | MCP with remote HTTP servers | Advanced |
| [06_structured_output](./06_structured_output/) | Validated Pydantic model responses | Intermediate |
| [07_session_management](./07_session_management/) | S3-backed conversation persistence | Advanced |
| [08_custom_provider](./08_custom_provider/) | Custom model provider via import path | Intermediate |

## v0.2.0 Features

These features are available across the examples:

| Feature | Example(s) | Description |
|---------|-----------|-------------|
| Parallel tool execution | 03 | Multiple tool calls run concurrently via `asyncio.gather()` |
| Per-tool configuration | 03 | Override timeout, heartbeat, retry per tool with `TemporalToolConfig` |
| Structured output | 06 | Validated Pydantic responses via `model.structured_output()` |
| Session management | 07 | S3-backed conversation persistence with `TemporalSessionManager` |
| Custom providers | 08 | Plug in any model via `CustomProviderConfig` |
| MCP client caching | 04 | Reuse MCP server connections across tool calls |
| Heartbeating | All | Activities send heartbeats; stuck detection via `heartbeat_timeout` |
| Versioning gates | All | `workflow.patched()` for safe workflow evolution |

## Learning Path

### 1. Start Here: Quickstart
The [01_quickstart](./01_quickstart/) example shows the absolute minimum needed:
- A Temporal workflow
- A Strands Agent with `TemporalModelStub`
- No tools, just conversation

### 2. Add Tools: Weather Agent
The [02_weather_agent](./02_weather_agent/) example introduces:
- `create_durable_agent()` factory
- Adding tools to your agent
- Full durability for model AND tool calls

### 3. Multiple Tools: Multi-Tool Agent
The [03_multi_tool_agent](./03_multi_tool_agent/) example shows:
- Multiple tools (weather, search, calculate, etc.)
- Various workflow patterns
- Per-tool configuration with `TemporalToolConfig`
- Parallel tool execution (automatic in v0.2.0)
- Retry and timeout handling

### 4. MCP Integration: External Tools
The [04_mcp_stdio](./04_mcp_stdio/) and [05_mcp_http](./05_mcp_http/) examples cover:
- Model Context Protocol (MCP) integration
- Local stdio-based MCP servers
- Remote HTTP-based MCP servers
- Tool discovery at runtime
- MCP client caching and cleanup

### 5. Structured Output
The [06_structured_output](./06_structured_output/) example demonstrates:
- Getting validated Pydantic model responses from LLMs
- `TemporalModelStub.structured_output()` via Temporal activities
- No tools needed - direct model-to-schema extraction

### 6. Session Management
The [07_session_management](./07_session_management/) example shows:
- S3-backed conversation persistence with `TemporalSessionManager`
- Multi-turn conversations across workflow executions
- LocalStack setup for local development

### 7. Custom Providers
The [08_custom_provider](./08_custom_provider/) example demonstrates:
- Plugging in custom model implementations via `CustomProviderConfig`
- Import-path-based provider resolution
- Wrapping existing providers with custom logic

## Prerequisites

All examples require:

1. **Temporal Server**
   ```bash
   temporal server start-dev
   ```

2. **AWS Credentials** (for Bedrock)
   ```bash
   export AWS_REGION=us-east-1
   # Or use AWS SSO/credentials file
   ```

3. **Dependencies**
   ```bash
   uv sync
   ```

Additional requirements for specific examples:
- **07_session_management**: S3 bucket (or LocalStack for local dev)
- **04_mcp_stdio**: MCP server binary (e.g., `uvx awslabs.aws-documentation-mcp-server@latest`)

## Running Any Example

Each example follows the same pattern:

```bash
# 1. Navigate to the example
cd examples/<example_name>

# 2. Start the worker (Terminal 1)
uv run python run_worker.py

# 3. Run the client (Terminal 2)
uv run python run_client.py

# 4. View in Temporal UI
open http://localhost:8233
```

## Key Concepts

### TemporalModelStub
Routes model calls to Temporal activities for durability:
```python
agent = Agent(
    model=TemporalModelStub(BedrockProviderConfig(...))
)
```

### create_durable_agent()
Factory function for full durability (model + tools):
```python
agent = create_durable_agent(
    provider_config=BedrockProviderConfig(...),
    tools=[my_tool],
)
```

### TemporalToolExecutor
Routes tool calls to Temporal activities:
```python
tool_executor = TemporalToolExecutor(
    mcp_servers=[...],  # Optional MCP servers
)
```

### TemporalToolConfig
Per-tool configuration for timeout, heartbeat, and retry:
```python
agent = create_durable_agent(
    provider_config=BedrockProviderConfig(...),
    tools=[fast_tool, slow_tool],
    tool_configs={
        "slow_tool": TemporalToolConfig(
            start_to_close_timeout=300.0,
            heartbeat_timeout=30.0,
        ),
    },
)
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    TEMPORAL WORKFLOW                         │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │                 Strands Agent                        │   │
│   │   model = TemporalModelStub (routes to activity)    │   │
│   │   tool_executor = TemporalToolExecutor              │   │
│   └─────────────────────────────────────────────────────┘   │
│         │                        │                           │
│         ▼                        ▼                           │
│   ┌───────────────┐      ┌───────────────────┐              │
│   │ Model Activity │      │  Tool Activity    │              │
│   │ → AWS Bedrock  │      │ → Execute @tool   │              │
│   └───────────────┘      └───────────────────┘              │
└─────────────────────────────────────────────────────────────┘
```

## Durability Benefits

- **Crash-proof**: Workflows survive worker restarts
- **Automatic retries**: Transient failures handled
- **Timeouts**: Configurable per-activity and per-tool
- **Visibility**: Full history in Temporal UI
- **Replay**: State reconstructed from history
- **Heartbeating**: Stuck activity detection

## Testing Guide

See [TESTING_v2.md](./TESTING_v2.md) for a comprehensive guide to testing all v0.2.0 features.
