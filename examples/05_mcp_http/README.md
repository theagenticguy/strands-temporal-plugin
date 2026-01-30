# 05 - MCP HTTP

Use remote HTTP-based MCP servers for enterprise and cloud deployments.

## What You'll Learn

- Configuring HTTP-based MCP servers
- Using the AWS Knowledge MCP server
- Authentication headers for private MCP servers

## When to Use HTTP MCP

HTTP MCP servers are ideal for:
- Cloud-hosted MCP services
- Enterprise MCP gateways
- Shared MCP infrastructure
- Production deployments
- When you don't want to install servers locally

## Prerequisites

1. **Temporal Server**: Start the development server
   ```bash
   temporal server start-dev
   ```

2. **AWS Credentials**: Configure for Bedrock access
   ```bash
   export AWS_REGION=us-east-1
   ```

3. **Network Access**: Ensure connectivity to HTTP MCP server

## Running the Example

### 1. Start the Worker

```bash
cd examples/05_mcp_http
uv run python run_worker.py
```

### 2. Run the Client

```bash
# Use AWS Knowledge MCP (pre-configured)
uv run python run_client.py

# Custom prompt
uv run python run_client.py --prompt "How do I configure an S3 bucket policy?"

# Use custom HTTP MCP server
uv run python run_client.py --url "https://your-mcp-server.com"
```

### 3. View in Temporal UI

Open http://localhost:8233 to see the workflow execution.

## Files

| File | Description |
|------|-------------|
| `workflow.py` | HTTPMCPWorkflow and AWSKnowledgeMCPWorkflow |
| `run_worker.py` | Starts the Temporal worker |
| `run_client.py` | Executes the workflow |

## Key Concepts

### StreamableHTTPMCPServerConfig

```python
StreamableHTTPMCPServerConfig(
    server_id="aws-knowledge",                    # Unique identifier
    url="https://knowledge-mcp.global.api.aws",   # Server URL
    headers={                                      # Optional auth headers
        "Authorization": "Bearer token",
    },
)
```

### Authentication

For private MCP servers, pass headers:

```python
StreamableHTTPMCPServerConfig(
    server_id="private-mcp",
    url="https://internal-mcp.example.com",
    headers={
        "Authorization": "Bearer your-token",
        "X-API-Key": "your-api-key",
    },
)
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      WORKFLOW                                │
│                                                             │
│   TemporalToolExecutor with StreamableHTTPMCPServerConfig   │
│         │                                                    │
│         ▼                                                    │
│   ┌─────────────────────────────────────────────────────┐   │
│   │     discover_mcp_tools_activity                      │   │
│   │     → HTTP GET to MCP server /tools                 │   │
│   │     → Returns tool definitions                       │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   agent.invoke_async(prompt)                                │
│         │                                                    │
│         ▼                                                    │
│   ┌─────────────────────────────────────────────────────┐   │
│   │     execute_mcp_tool_activity                        │   │
│   │     → HTTP POST to MCP server /tools/{name}         │   │
│   │     → Returns result                                 │   │
│   └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Available HTTP MCP Servers

| Server | URL | Description |
|--------|-----|-------------|
| AWS Knowledge | `https://knowledge-mcp.global.api.aws` | AWS documentation and best practices |

## Comparison: Stdio vs HTTP MCP

| Feature | Stdio MCP | HTTP MCP |
|---------|-----------|----------|
| Installation | Required locally | Not needed |
| Startup time | Spawns process | Instant |
| Authentication | N/A | Headers support |
| Scaling | Per-worker | Centralized |
| Use case | Development | Production |
