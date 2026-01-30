# 04 - MCP Stdio

Use MCP (Model Context Protocol) servers that run as local processes via stdio communication.

## What You'll Learn

- Configuring stdio-based MCP servers
- Discovering MCP tools dynamically
- Using MCP tools with Temporal durability

## When to Use Stdio MCP

Stdio MCP servers are ideal for:
- Local development and testing
- Self-contained MCP tools (time, filesystem, etc.)
- When you have the MCP server installed locally

## Prerequisites

1. **Temporal Server**: Start the development server
   ```bash
   temporal server start-dev
   ```

2. **AWS Credentials**: Configure for Bedrock access
   ```bash
   export AWS_REGION=us-east-1
   ```

3. **MCP Server**: Install an MCP server (optional, for testing)
   ```bash
   # Time server (tells time in different timezones)
   uvx mcp-server-time --help

   # Filesystem server (file operations)
   uvx mcp-server-filesystem --help
   ```

## Running the Example

### 1. Start the Worker

```bash
cd examples/04_mcp_stdio
uv run python run_worker.py
```

### 2. Run the Client

```bash
# Using mcp-server-time
uv run python run_client.py

# Using mcp-server-filesystem
uv run python run_client.py --simple
```

### 3. View in Temporal UI

Open http://localhost:8233 to see the workflow execution and MCP tool calls.

## Files

| File | Description |
|------|-------------|
| `workflow.py` | MCPDiscoveryWorkflow and SimpleMCPWorkflow |
| `run_worker.py` | Starts the Temporal worker |
| `run_client.py` | Executes the workflow |

## Key Concepts

### StdioMCPServerConfig

```python
StdioMCPServerConfig(
    server_id="time-server",      # Unique identifier
    command="uvx",                 # Command to run
    args=["mcp-server-time"],      # Arguments
    startup_timeout=30.0,          # Wait for server startup
)
```

### Tool Discovery

```python
tool_executor = TemporalToolExecutor(
    mcp_servers=[stdio_config],
)

# Discover available tools from MCP server
# This is durable - results are replayed on workflow restart
mcp_tools = await tool_executor.discover_mcp_tools()

# Get proxy tools for the Agent
agent_tools = tool_executor.get_mcp_tools()
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      WORKFLOW                                │
│                                                             │
│   TemporalToolExecutor with StdioMCPServerConfig            │
│         │                                                    │
│         ▼                                                    │
│   ┌─────────────────────────────────────────────────────┐   │
│   │     discover_mcp_tools_activity                      │   │
│   │     → Spawns local MCP server process               │   │
│   │     → Queries available tools via stdio             │   │
│   │     → Returns tool definitions                       │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   agent.invoke_async(prompt)                                │
│         │                                                    │
│         ▼                                                    │
│   ┌─────────────────────────────────────────────────────┐   │
│   │     execute_mcp_tool_activity                        │   │
│   │     → Spawns MCP server (or reuses)                 │   │
│   │     → Sends tool call via stdio                     │   │
│   │     → Returns result                                 │   │
│   └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Available MCP Servers

Some popular stdio MCP servers:

| Server | Install | Description |
|--------|---------|-------------|
| mcp-server-time | `uvx mcp-server-time` | Time and timezone queries |
| mcp-server-filesystem | `uvx mcp-server-filesystem /path` | File operations |
| mcp-server-sqlite | `uvx mcp-server-sqlite db.sqlite` | SQLite database |
| mcp-server-fetch | `uvx mcp-server-fetch` | HTTP fetching |

## Next Steps

Once you're comfortable with stdio MCP, explore:
- **05_mcp_http** - Remote HTTP-based MCP servers
