# 07 - Session Management

Persist agent conversation state across workflow executions using S3. This example demonstrates `TemporalSessionManager` which loads and saves agent state through Temporal activities.

## What You'll Learn

- Using `TemporalSessionManager` for cross-turn persistence
- Loading and restoring conversation history from S3
- Running multi-turn conversations across separate workflow executions

## Prerequisites

1. **Temporal Server**: Start the development server
   ```bash
   temporal server start-dev
   ```

2. **AWS Credentials**: Configure for Bedrock access
   ```bash
   export AWS_REGION=us-east-1
   ```

3. **S3 Bucket**: Create a bucket for session storage (or use LocalStack)

### LocalStack Setup (Recommended for Local Development)

```bash
# Install and start LocalStack
uv tool install localstack
localstack start -d

# Create the S3 bucket
AWS_ENDPOINT_URL=http://localhost:4566 aws s3 mb s3://agent-sessions --region us-east-1
```

## Running the Example

### 1. Start the Worker

```bash
cd examples/07_session_management

# With LocalStack
AWS_ENDPOINT_URL=http://localhost:4566 uv run python run_worker.py

# With real AWS S3
uv run python run_worker.py
```

### 2. Run the Client

```bash
# Multi-turn demo (recommended - shows session persistence)
AWS_ENDPOINT_URL=http://localhost:4566 uv run python run_client.py --multi-turn

# Single turn
AWS_ENDPOINT_URL=http://localhost:4566 uv run python run_client.py --prompt "Remember my name is Alice"

# Custom session ID
AWS_ENDPOINT_URL=http://localhost:4566 uv run python run_client.py --session-id user-123 --prompt "Hello!"
```

### 3. View in Temporal UI

Open http://localhost:8233 to see the workflow executions. Look for `load_session_activity` and `save_session_activity` in the event history.

## Files

| File | Description |
|------|-------------|
| `workflow.py` | SessionWorkflow with TemporalSessionManager |
| `tools.py` | remember_fact and recall_facts tools |
| `run_worker.py` | Starts the Temporal worker |
| `run_client.py` | Executes workflows (single or multi-turn) |

## Key Concept: `TemporalSessionManager`

```python
session = TemporalSessionManager(SessionConfig(
    session_id="user-123",
    bucket="agent-sessions",
    region_name="us-east-1",
))

# Load previous state from S3
await session.load()

# Create agent and restore history
agent = create_durable_agent(...)
agent.messages.extend(session.messages)

# Run agent
result = await agent.invoke_async(prompt)

# Save updated state to S3
await session.save(agent)
```

Session load/save happen through Temporal activities (not directly in workflow context), which preserves determinism. S3 is the source of truth for conversation state, and `session_id` is the pointer into that state.

## Note on LocalStack

`SessionConfig` has no `endpoint_url` field. Instead, boto3 reads the `AWS_ENDPOINT_URL` environment variable natively (since v1.34). Set this env var when running both the worker and client to use LocalStack.

## Next Steps

- **08_custom_provider** - Plug in a custom model provider
