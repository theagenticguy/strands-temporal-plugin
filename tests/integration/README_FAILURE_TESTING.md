# Failure Simulation Testing

This document describes how to test the crash-proof capabilities and retry behavior of the strands-temporal-plugin.

## Overview

The plugin routes model inference and tool execution to Temporal activities, which provides:

1. **Automatic Retries**: Transient failures are automatically retried with exponential backoff
2. **Durability**: Workflow state survives worker crashes
3. **Heartbeating**: Long-running operations checkpoint progress for recovery

## Automated Tests

### Running the Test Suite

```bash
# Run all failure simulation tests
pytest tests/integration/test_failure_simulation.py -v

# Run specific test class
pytest tests/integration/test_failure_simulation.py::TestTransientFailures -v

# Run with detailed output
pytest tests/integration/test_failure_simulation.py -v -s
```

### Test Scenarios

| Test Class | Description |
|------------|-------------|
| `TestTransientFailures` | Tests recovery from temporary network errors |
| `TestMidStreamFailures` | Tests recovery when activity crashes mid-stream |
| `TestPermanentFailures` | Tests non-retryable errors fail immediately |
| `TestRetryPolicyConfiguration` | Tests retry exhaustion behavior |

### What the Tests Verify

1. **Single retry success**: Workflow recovers from 1 failure
2. **Multiple retry success**: Workflow recovers from 2 failures
3. **Tool workflow recovery**: Tool-using workflows handle failures
4. **Mid-stream crash recovery**: Activities can resume from heartbeat checkpoints
5. **Non-retryable failures**: Permanent errors fail immediately without retry
6. **Retry exhaustion**: Workflow fails after max retries exceeded

## Manual Network Failure Testing

For realistic testing with actual Bedrock calls, you can manually block network traffic.

### Prerequisites

1. Running Temporal server
2. AWS credentials configured
3. sudo access (for network manipulation)

### Quick Test with Shell Script (macOS)

```bash
# Terminal 1: Start Temporal
temporal server start-dev

# Terminal 2: Start the worker
cd examples/basic_weather_agent
python run_worker.py

# Terminal 3: Start a workflow
python run_client.py

# Terminal 4: Block network (while workflow is running)
sudo ./scripts/macos_block_bedrock.sh block

# Watch the Temporal UI at http://localhost:8233
# You should see activity retries

# After observing retries, unblock
sudo ./scripts/macos_block_bedrock.sh unblock

# The workflow should complete successfully
```

### Automated Manual Test

```bash
# Run the full automated test (requires sudo)
sudo python scripts/network_failure_test.py

# With custom timing
sudo python scripts/network_failure_test.py \
    --block-after 3.0 \
    --unblock-after 10.0 \
    --prompt "What's the weather in Seattle?"

# Just block network (for manual observation)
sudo python scripts/network_failure_test.py --block-only

# Cleanup
sudo python scripts/network_failure_test.py --unblock-only
```

### What to Observe

1. **Temporal UI** (http://localhost:8233):
   - Navigate to the workflow
   - Look at the "Activity" section
   - See retry attempts with timestamps
   - Observe backoff intervals increasing

2. **Worker Logs**:
   - Activity failure messages
   - Retry attempt logs
   - Success after unblocking

3. **Workflow Result**:
   - Should complete successfully after network restored
   - Result should include weather information

## How It Works

### Network Blocking (macOS)

The scripts use macOS's packet filter (`pf`) to block traffic:

```bash
# What the script does:
# 1. Resolves Bedrock hostnames to IPs
# 2. Creates pf rules to block those IPs on port 443
# 3. Enables pf with those rules

# Example generated rule:
block drop out quick proto tcp to 52.94.133.131 port 443
```

### Temporal Activity Retries

When network is blocked, the activity experiences:

1. **Connection timeout** → Activity fails
2. **Temporal retry policy** kicks in:
   - Initial interval: 1 second
   - Backoff coefficient: 2.0
   - Maximum interval: 60 seconds
   - Maximum attempts: 3 (default)

3. **After unblock**: Next retry succeeds
4. **Workflow continues**: Uses successful activity result

### Heartbeat Recovery

For long-running operations, activities checkpoint progress:

```python
# In execute_model_activity:
for event in result:
    events.append(event)
    if len(events) % 10 == 0:
        activity.heartbeat(f"Processed {len(events)} events")
```

If the activity crashes, the next retry can retrieve heartbeat details and resume.

## Retry Policy Configuration

The default retry policy in `TemporalModelStub`:

```python
RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=60),
    backoff_coefficient=2.0,
)
```

You can customize this when creating the model stub:

```python
from temporalio.common import RetryPolicy
from datetime import timedelta

model = TemporalModelStub(
    provider_config=BedrockProviderConfig(model_id="..."),
    retry_policy=RetryPolicy(
        maximum_attempts=5,
        initial_interval=timedelta(seconds=2),
        maximum_interval=timedelta(seconds=120),
        backoff_coefficient=1.5,
    ),
)
```

## Troubleshooting

### "Permission denied" when blocking network

```bash
# Must run with sudo
sudo ./scripts/macos_block_bedrock.sh block
```

### Network still blocked after test

```bash
# Cleanup manually
sudo ./scripts/macos_block_bedrock.sh unblock
# Or
sudo pfctl -F all && sudo pfctl -d
```

### Tests fail with "Could not connect to Temporal"

```bash
# Make sure Temporal is running
temporal server start-dev
```

### Activities not retrying

Check the retry policy - some errors are marked `non_retryable=True`:
- `ModelNotFound`
- `ContextOverflow`
- `UnsupportedProvider`

These fail immediately by design.

## Architecture Reference

```
┌─────────────────────────────────────────────────────────────────┐
│                    WORKFLOW CONTEXT                              │
│                                                                  │
│   Agent.invoke_async(prompt)                                     │
│        │                                                         │
│        ▼                                                         │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │              Strands Agent Event Loop                     │  │
│   │   model.stream() ──▶ TemporalModelStub ──▶ Activity      │  │
│   └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Network blocked here
                              │ ──────────────────▶ Activity fails
                              │                    ▶ Temporal retries
                              │ Network restored   ▶ Activity succeeds
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ACTIVITY CONTEXT                              │
│                                                                  │
│   execute_model_activity()                                       │
│   ├─ Creates BedrockModel                                        │
│   ├─ Calls model.stream() ──▶ HTTPS to Bedrock ──▶ BLOCKED      │
│   └─ Returns events                                              │
└─────────────────────────────────────────────────────────────────┘
```
