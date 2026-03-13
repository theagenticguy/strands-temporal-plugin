# Example 09: Failure Resilience

Demonstrates Temporal's automatic retry, heartbeat timeout, and graceful degradation for durable AI agents.

## Scenarios

### 1. Transient Failures (`transient`)

The `flaky_api_call` tool fails with `ConnectionError` on the first 2 attempts, then succeeds on the 3rd. Temporal retries automatically — no retry logic in the tool code.

**What to observe:**
- Worker logs show `Attempt 1`, `Attempt 2` (both fail), `Attempt 3` (success)
- Temporal UI shows the activity with multiple retry attempts in event history
- The agent receives the successful result and responds normally

### 2. Heartbeat Timeout (`timeout`)

The `slow_database_query` tool takes 5 seconds. Heartbeat timeout is set to 10s, so it completes normally. Set `SLOW_DB_SECONDS=15` to trigger a timeout.

**What to observe:**
- Worker logs show per-second progress updates
- Temporal UI shows heartbeat details on the activity
- With `SLOW_DB_SECONDS=15`: activity gets cancelled and retried

### 3. Graceful Degradation (`degradation`)

The `unreliable_webhook` tool always fails (simulates a permanently down service). After exhausting 3 retries, the error reaches the agent, which reports the failure and continues with other tasks.

**What to observe:**
- Worker logs show 3 failed webhook attempts
- Temporal UI shows the activity failing all retries
- The agent tells the user the webhook failed but still completes the calculation
- The workflow succeeds (not crashes) despite the tool failure

## Usage

```bash
temporal server start-dev

# Terminal 1: Start worker
cd examples/09_failure_resilience
uv run python run_worker.py

# Terminal 2: Run scenarios
uv run python run_client.py transient
uv run python run_client.py timeout
uv run python run_client.py degradation
uv run python run_client.py all

# Trigger heartbeat timeout (optional)
SLOW_DB_SECONDS=15 uv run python run_worker.py  # In terminal 1
uv run python run_client.py timeout              # In terminal 2
```

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `FLAKY_FAILURES` | `2` | Number of failures before `flaky_api_call` succeeds |
| `SLOW_DB_SECONDS` | `5` | How long `slow_database_query` takes |

## Per-Tool Temporal Config

| Tool | Timeout | Retries | Heartbeat |
|------|---------|---------|-----------|
| `flaky_api_call` | 30s | 5 max, 1s initial, 2x backoff | default |
| `slow_database_query` | 60s | default | 10s |
| `unreliable_webhook` | 10s | 3 max, 1s initial | default |
| `reliable_calculator` | default (60s) | default | default |
