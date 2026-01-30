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
| [03_multi_tool_agent](./03_multi_tool_agent/) | Multiple tools and workflow patterns | Intermediate |
| [04_mcp_stdio](./04_mcp_stdio/) | MCP with local stdio servers | Advanced |
| [05_mcp_http](./05_mcp_http/) | MCP with remote HTTP servers | Advanced |

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
- Configuration options
- Retry and timeout handling

### 4. MCP Integration: External Tools
The [04_mcp_stdio](./04_mcp_stdio/) and [05_mcp_http](./05_mcp_http/) examples cover:
- Model Context Protocol (MCP) integration
- Local stdio-based MCP servers
- Remote HTTP-based MCP servers
- Tool discovery at runtime

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
- **Timeouts**: Configurable per-activity
- **Visibility**: Full history in Temporal UI
- **Replay**: State reconstructed from history
