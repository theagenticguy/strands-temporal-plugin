# Testing Guide: v0.2.0 Features

End-to-end verification guide for all v0.2.0 production-readiness features.

## Prerequisites

- **Temporal CLI**: `brew install temporal` or [install guide](https://docs.temporal.io/cli)
- **Python 3.12+**: `python --version`
- **uv**: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **AWS Credentials**: For Bedrock model access (`aws sts get-caller-identity`)
- **LocalStack** (optional, for session management): `uv tool install localstack`

## Setup

```bash
git checkout v0.2.0-rc
uv sync

# Start Temporal dev server (leave running)
temporal server start-dev
```

Temporal UI is available at http://localhost:8233

---

## Test 1: Parallel Tool Execution

**Feature**: Multiple tool calls from a single model response execute concurrently via `asyncio.gather()`.

**Example**: `03_multi_tool_agent`

```bash
cd examples/03_multi_tool_agent
uv run python run_worker.py &
uv run python run_client.py general --prompt "Check the weather in Seattle, Tokyo, and London"
```

**Verification in Temporal UI**:
1. Open http://localhost:8233 and find the workflow
2. Click on the workflow execution to see the event history
3. Look for multiple `execute_tool_activity` calls — their start times should overlap (parallel) rather than being sequential
4. The activity bars in the timeline view should show concurrent execution

**What to look for**:
- `HasChange` marker for `parallel-tool-execution-v1` in the workflow history
- Overlapping activity execution timestamps

---

## Test 2: Per-Tool Configuration

**Feature**: Override timeout, heartbeat, and retry settings per tool using `TemporalToolConfig`.

**Example**: `03_multi_tool_agent` (per-tool-config workflow)

```bash
cd examples/03_multi_tool_agent
# Worker should already be running from Test 1
uv run python run_client.py per-tool-config
```

**Verification in Temporal UI**:
1. Find the `per-tool-config-*` workflow execution
2. Inspect each `execute_tool_activity` in the event history
3. Verify different `start_to_close_timeout` values per activity:
   - `search_web`: 120s timeout
   - `calculate`: 10s timeout
   - `send_notification`: default timeout with 10 max retries
4. Check `heartbeat_timeout` on `search_web` activities (20s)

---

## Test 3: Structured Output

**Feature**: Get validated Pydantic model responses from LLMs via `model.structured_output()`.

**Example**: `06_structured_output`

```bash
cd examples/06_structured_output
uv run python run_worker.py &
uv run python run_client.py weather
uv run python run_client.py movie
```

**Verification**:
- Terminal output should show a typed dict with the correct fields:
  - Weather: `city`, `temperature_f`, `condition`, `recommendation`
  - Movie: `title`, `rating`, `genre`, `summary`, `recommended`
- In Temporal UI: the workflow history should show `execute_structured_output_activity` (not `execute_model_activity`)
- The activity input should contain `output_model_path` like `models.WeatherAnalysis`

---

## Test 4: Session Management

**Feature**: S3-backed conversation persistence across workflow executions with `TemporalSessionManager`.

**Example**: `07_session_management`

### LocalStack Setup (one-time)

```bash
# Start LocalStack
localstack start -d

# Create S3 bucket
AWS_ENDPOINT_URL=http://localhost:4566 aws s3 mb s3://agent-sessions --region us-east-1
```

### Run

```bash
cd examples/07_session_management
AWS_ENDPOINT_URL=http://localhost:4566 uv run python run_worker.py &
AWS_ENDPOINT_URL=http://localhost:4566 uv run python run_client.py --multi-turn
```

**Verification**:
- **Turn 1**: Agent remembers facts (e.g., "favorite color is blue")
- **Turn 2**: Agent recalls facts from the previous turn
- In Temporal UI: two separate workflow executions with the same session_id pattern
- Each workflow should show `load_session_activity` at the start and `save_session_activity` at the end
- Check S3 for persisted data:
  ```bash
  AWS_ENDPOINT_URL=http://localhost:4566 aws s3 ls s3://agent-sessions/ --recursive
  ```

---

## Test 5: Custom Provider

**Feature**: Plug in any model implementation via `CustomProviderConfig` with import-path-based resolution.

**Example**: `08_custom_provider`

```bash
cd examples/08_custom_provider
uv run python run_worker.py &
uv run python run_client.py
```

**Verification**:
- Terminal output should show `[CustomProvider]` log lines from the `LoggingBedrockModel`
- In Temporal UI: the `execute_model_activity` input should show `provider: "custom"` and `provider_class_path: "custom_model.LoggingBedrockModel"`
- The workflow should complete successfully (proving the custom model was loaded and used)

---

## Test 6: Heartbeating

**Feature**: All activities send heartbeats; `heartbeat_timeout` enables stuck activity detection.

**Observable in**: All examples

**Verification in Temporal UI**:
1. Open any workflow execution
2. Click on an `execute_model_activity` event
3. Look for `last_heartbeat_details` in the activity details
4. Model activities heartbeat every 10 events: `"Processed 10 events"`, `"Processed 20 events"`, etc.
5. Tool activities heartbeat at: `"loading tool"`, `"executing"`, `"completed: success"`

**Default timeouts** (v0.2.0):
- Model activities: `heartbeat_timeout=30s`
- Tool activities: `heartbeat_timeout=25s` (overridable per-tool)

---

## Test 7: Versioning Gates

**Feature**: `workflow.patched()` enables safe workflow code evolution without breaking replay.

**Observable in**: All examples

**Verification in Temporal UI**:
1. Open any workflow execution
2. Look for `HasChange` markers in the event history
3. Expected patches:
   - `model-stream-v1`: On the model execution path
   - `parallel-tool-execution-v1`: On the tool execution path (only in workflows with tools)

These markers allow the plugin to safely change model invocation or tool execution behavior in future versions without breaking replay of existing workflow histories.

---

## Test 8: MCP Client Caching

**Feature**: MCP server connections are reused across tool calls (not restarted per call).

**Example**: `04_mcp_stdio`

```bash
cd examples/04_mcp_stdio
uv run python run_worker.py &
uv run python run_client.py
```

**Verification**:
- Worker logs should show `"Closed cached MCP client: ..."` on shutdown (Ctrl+C)
- Only one MCP server process should be running per configured server (check with `ps aux | grep <mcp-server-name>`)
- The `close_mcp_clients()` call in the worker's `finally` block cleans up on shutdown

**Note**: This example requires an MCP server binary. See the example's README for setup.

---

## Test Matrix

| Feature | Example | Infra Required | Verification Method |
|---------|---------|---------------|-------------------|
| Parallel tool execution | 03 (`general`) | Temporal only | Overlapping activity bars in UI |
| Per-tool configuration | 03 (`per-tool-config`) | Temporal only | Different timeouts in activity details |
| Structured output | 06 (`weather`, `movie`) | Temporal only | Typed dict output + activity type in history |
| Session management | 07 (`--multi-turn`) | Temporal + S3/LocalStack | Cross-turn memory + S3 data |
| Custom provider | 08 | Temporal only | `provider: "custom"` in activity input |
| Heartbeating | All | Temporal only | `last_heartbeat_details` in UI |
| Versioning gates | All | Temporal only | `HasChange` markers in history |
| MCP client caching | 04 | Temporal + MCP server | Single server process + cleanup logs |

---

## Troubleshooting

### "Connection refused" on localhost:7233

Temporal server isn't running. Start it:
```bash
temporal server start-dev
```

### "Could not resolve model" / "Access denied" from Bedrock

AWS credentials aren't configured or lack Bedrock access:
```bash
aws sts get-caller-identity  # Check credentials
aws bedrock list-foundation-models --region us-east-1  # Check Bedrock access
```

### "Tool 'X' is defined in __main__ module"

Tools must be in importable modules (not `__main__`). Move tools to a separate `.py` file and ensure the worker's `sys.path` includes the directory.

### Session management: "NoSuchBucket"

The S3 bucket doesn't exist. Create it:
```bash
# LocalStack
AWS_ENDPOINT_URL=http://localhost:4566 aws s3 mb s3://agent-sessions --region us-east-1

# Real AWS
aws s3 mb s3://agent-sessions --region us-east-1
```

### Structured output: "Failed to load output model"

The worker can't import the Pydantic model class. Ensure:
1. The model file is in a directory on `sys.path`
2. `run_worker.py` has `sys.path.insert(0, str(Path(__file__).parent))`
3. The model class path resolves (e.g., `models.WeatherAnalysis`)

### Custom provider: "Failed to load custom provider"

The worker can't import the custom model class. Same `sys.path` requirements as structured output.

### "NondeterminismError" during replay

Workflow code changed in a way that breaks replay of existing histories. Check:
1. Are `workflow.patched()` gates in place for behavioral changes?
2. Did activity signatures change?
3. Run `tests/unit/test_replay.py` to verify versioning gates

### Activities stuck / no heartbeat timeout

If activities appear stuck, check that `heartbeat_timeout` is set. In v0.2.0, default timeouts are:
- Model: 30s
- Tools: 25s

For custom timeouts, use `TemporalToolConfig`:
```python
tool_configs={"slow_tool": TemporalToolConfig(heartbeat_timeout=60.0)}
```
