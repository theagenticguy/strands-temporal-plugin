# 01 - Quickstart

The simplest possible Strands + Temporal example. A basic conversational agent without any tools.

## What You'll Learn

- Setting up a Temporal workflow with Strands
- Using `TemporalModelStub` for durable model calls
- Basic agent invocation

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
cd examples/01_quickstart
uv run python run_worker.py
```

### 2. Run the Client

```bash
# Default prompt
uv run python run_client.py

# Custom prompt
uv run python run_client.py "What is 2 + 2?"
```

### 3. View in Temporal UI

Open http://localhost:8233 to see the workflow execution.

## Files

| File | Description |
|------|-------------|
| `workflow.py` | QuickstartWorkflow definition |
| `run_worker.py` | Starts the Temporal worker |
| `run_client.py` | Executes the workflow |

## How It Works

```
┌─────────────────────────────────────────────────┐
│                  WORKFLOW                        │
│                                                 │
│   QuickstartWorkflow.run(prompt)                │
│         │                                       │
│         ▼                                       │
│   ┌─────────────────────────────────────────┐  │
│   │           Strands Agent                  │  │
│   │   model = TemporalModelStub(...)         │  │
│   │   result = agent.invoke_async(prompt)    │  │
│   └─────────────────────────────────────────┘  │
│                     │                           │
│                     ▼                           │
│   ┌─────────────────────────────────────────┐  │
│   │     execute_model_activity               │  │
│   │     → Calls AWS Bedrock API              │  │
│   │     → Returns response                   │  │
│   └─────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

## Next Steps

Once you're comfortable with this example, move on to:
- **02_weather_agent** - Add tools to your agent
