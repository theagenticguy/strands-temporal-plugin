# Strands Temporal Plugin

A production-grade integration between [Strands Agents SDK](https://github.com/strands-agents/sdk-python) and [Temporal](https://temporal.io/) for durable AI agent execution.

## Features

- **Durable Agent Execution** - AI agent workflows survive crashes, restarts, and failures
- **Automatic Retries** - Model calls and tool execution automatically retry on failure
- **Multiple LLM Providers** - Support for Bedrock, OpenAI, Anthropic, and Ollama
- **Static Tools** - Use custom Python functions as agent tools
- **MCP Tools** - Integrate [Model Context Protocol](https://modelcontextprotocol.io/) servers for dynamic tooling
- **Full Observability** - Every step visible in Temporal UI with complete history
- **Type-Safe** - Pydantic models for all configurations and data structures

## Installation

```bash
pip install strands-temporal-plugin
```

Or with uv:

```bash
uv add strands-temporal-plugin
```

### Dependencies

- Python 3.10+
- [Temporal Server](https://docs.temporal.io/cli#start-dev)
- [strands-agents](https://github.com/strands-agents/sdk-python)

## Quick Start

### 1. Start Temporal Server

```bash
temporal server start-dev
```

### 2. Create a Workflow

```python
from temporalio import workflow
from strands_temporal_plugin import (
    DurableAgent,
    DurableAgentConfig,
    BedrockProviderConfig,
)


@workflow.defn
class AssistantWorkflow:
    @workflow.run
    async def run(self, prompt: str) -> str:
        agent = DurableAgent(
            DurableAgentConfig(
                provider_config=BedrockProviderConfig(
                    model_id="us.anthropic.claude-sonnet-4-20250514-v1:0"
                ),
                system_prompt="You are a helpful assistant.",
            )
        )
        result = await agent.invoke(prompt)
        return result.text
```

### 3. Create a Worker

```python
import asyncio
from temporalio.client import Client
from temporalio.worker import Worker
from strands_temporal_plugin import StrandsTemporalPlugin
from workflows import AssistantWorkflow


async def main():
    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )

    worker = Worker(
        client,
        task_queue="strands-agents",
        workflows=[AssistantWorkflow],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
```

### 4. Execute the Workflow

```python
import asyncio
from temporalio.client import Client
from strands_temporal_plugin import StrandsTemporalPlugin
from workflows import AssistantWorkflow


async def main():
    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )

    result = await client.execute_workflow(
        AssistantWorkflow.run,
        "What is the capital of France?",
        id="assistant-1",
        task_queue="strands-agents",
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
```

## Architecture

The **DurableAgent** pattern properly separates concerns for Temporal compatibility:

```
┌─────────────────────────────────────────────────────────────────┐
│                        WORKFLOW CONTEXT                          │
│                    (Deterministic, Serializable)                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                     DurableAgent                            │ │
│  │                                                             │ │
│  │  config: DurableAgentConfig (Pydantic)                      │ │
│  │  messages: list[dict] (Serializable)                        │ │
│  │  mcp_tools: list[MCPToolSpec] (Serializable)                │ │
│  │                                                             │ │
│  │  invoke(prompt) ───────────────────────────┐               │ │
│  │     │                                       │               │ │
│  │     ▼                                       ▼               │ │
│  │  ┌────────────────────┐     ┌───────────────────────────┐  │ │
│  │  │ execute_model_     │     │ execute_tool_activity     │  │ │
│  │  │    activity        │     │                           │  │ │
│  │  │                    │     │ execute_mcp_tool_activity │  │ │
│  │  │ (Activity Context) │     │ (Activity Context)        │  │ │
│  │  │ - AWS credentials  │     │ - Tool execution          │  │ │
│  │  │ - Model creation   │     │ - MCP connections         │  │ │
│  │  │ - API calls        │     │ - Retries & timeouts      │  │ │
│  │  └────────────────────┘     └───────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

**Key Principles:**

1. **Workflows are deterministic** - Only orchestration logic, no I/O
2. **Activities handle side effects** - Model calls, tool execution, MCP connections
3. **All state is serializable** - Pydantic models ensure safe serialization
4. **Credentials in activities** - AWS/API keys accessed only in activity context

## Provider Configurations

### Amazon Bedrock

```python
from strands_temporal_plugin import BedrockProviderConfig

config = DurableAgentConfig(
    provider_config=BedrockProviderConfig(
        model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        region_name="us-east-1",  # Optional, uses AWS_REGION env var
        max_tokens=4096,
    ),
    # ...
)
```

### OpenAI

```python
from strands_temporal_plugin import OpenAIProviderConfig

config = DurableAgentConfig(
    provider_config=OpenAIProviderConfig(
        model_id="gpt-4o",
        api_key=None,  # Uses OPENAI_API_KEY env var
    ),
    # ...
)
```

### Anthropic

```python
from strands_temporal_plugin import AnthropicProviderConfig

config = DurableAgentConfig(
    provider_config=AnthropicProviderConfig(
        model_id="claude-sonnet-4-20250514",
        api_key=None,  # Uses ANTHROPIC_API_KEY env var
        max_tokens=4096,
    ),
    # ...
)
```

### Ollama (Local)

```python
from strands_temporal_plugin import OllamaProviderConfig

config = DurableAgentConfig(
    provider_config=OllamaProviderConfig(
        model_id="llama3.2",
        host="http://localhost:11434",
    ),
    # ...
)
```

## Static Tools

Define custom Python functions as agent tools:

```python
# tools.py
def get_weather(city: str) -> dict:
    """Get current weather for a city."""
    # Your implementation
    return {"city": city, "temperature": 72, "condition": "sunny"}
```

```python
# workflow.py
WEATHER_TOOL_SPEC = {
    "name": "get_weather",
    "description": "Get the current weather for a city.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"}
            },
            "required": ["city"],
        }
    },
}

config = DurableAgentConfig(
    provider_config=BedrockProviderConfig(model_id="..."),
    tool_specs=[WEATHER_TOOL_SPEC],
    tool_modules={"get_weather": "tools"},  # Module containing the function
)
```

## MCP Tools

Integrate [Model Context Protocol](https://modelcontextprotocol.io/) servers for dynamic tooling:

### STDIO Transport (Local Servers)

```python
from strands_temporal_plugin import StdioMCPServerConfig

config = DurableAgentConfig(
    provider_config=BedrockProviderConfig(model_id="..."),
    mcp_servers=[
        StdioMCPServerConfig(
            server_id="docs",
            command="uvx",
            args=["awslabs.aws-documentation-mcp-server@latest"],
            tool_prefix="docs",  # Tools: docs_search, docs_read, etc.
            startup_timeout=60.0,
        ),
    ],
)
```

### HTTP Transport (Remote Servers)

```python
from strands_temporal_plugin import StreamableHTTPMCPServerConfig

config = DurableAgentConfig(
    provider_config=BedrockProviderConfig(model_id="..."),
    mcp_servers=[
        StreamableHTTPMCPServerConfig(
            server_id="api",
            url="https://mcp.example.com/v1",
            headers={"Authorization": "Bearer token"},
            tool_prefix="api",
        ),
    ],
)
```

### Tool Filtering

```python
StdioMCPServerConfig(
    server_id="server",
    command="uvx",
    args=["my-mcp-server"],
    allowed_tools=["search_*", "get_*"],  # Whitelist patterns
    rejected_tools=["admin_*", "delete_*"],  # Blacklist patterns
)
```

## Configuration Reference

### DurableAgentConfig

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `provider_config` | `ProviderConfig` | Required | LLM provider configuration |
| `system_prompt` | `str \| None` | `None` | System prompt for the agent |
| `tool_specs` | `list[dict]` | `[]` | Static tool specifications |
| `tool_modules` | `dict[str, str]` | `{}` | Tool name to module mapping |
| `mcp_servers` | `list[MCPServerConfig]` | `[]` | MCP server configurations |
| `model_activity_timeout` | `float` | `300.0` | Model call timeout (seconds) |
| `tool_activity_timeout` | `float` | `60.0` | Tool execution timeout |
| `mcp_activity_timeout` | `float` | `120.0` | MCP operation timeout |
| `max_retries` | `int` | `3` | Maximum retry attempts |
| `initial_retry_interval_seconds` | `float` | `1.0` | Initial retry delay |
| `backoff_coefficient` | `float` | `2.0` | Exponential backoff multiplier |

## Examples

### Basic Weather Agent

A simple agent with a custom weather tool:

```bash
cd examples/basic_weather_agent
uv run python run_worker.py  # Terminal 1
uv run python run_client.py "What's the weather in Seattle?"  # Terminal 2
```

### MCP Agent

An agent using MCP servers for dynamic tooling:

```bash
cd examples/mcp_agent
uv run python run_worker.py  # Terminal 1
uv run python run_client.py "What is Amazon Bedrock?"  # Terminal 2
```

## Testing

```bash
# Run all tests
uv run pytest

# Run unit tests only
uv run pytest tests/unit

# Run with coverage
uv run pytest --cov=strands_temporal_plugin
```

## Development

```bash
# Clone the repository
git clone https://github.com/strands-agents/strands-temporal-plugin.git
cd strands-temporal-plugin

# Install dependencies
uv sync

# Run linting
uv run ruff check .
uv run ruff format .

# Run type checking
uv run pyright
```

## API Reference

### Main Exports

```python
from strands_temporal_plugin import (
    # Plugin
    StrandsTemporalPlugin,

    # DurableAgent
    DurableAgent,
    DurableAgentResult,
    DurableAgentConfig,

    # Provider Configurations
    BedrockProviderConfig,
    AnthropicProviderConfig,
    OpenAIProviderConfig,
    OllamaProviderConfig,

    # MCP Server Configurations
    StdioMCPServerConfig,
    StreamableHTTPMCPServerConfig,

    # Activity Types (for custom registration)
    ModelExecutionInput,
    ModelExecutionResult,
    ToolExecutionInput,
    ToolExecutionResult,
    MCPToolSpec,
    MCPListToolsInput,
    MCPListToolsResult,
    MCPToolExecutionInput,
    MCPToolExecutionResult,

    # Activities (for custom registration)
    execute_model_activity,
    execute_tool_activity,
    list_mcp_tools_activity,
    execute_mcp_tool_activity,
)
```

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please read our contributing guidelines and submit pull requests to the main repository.
