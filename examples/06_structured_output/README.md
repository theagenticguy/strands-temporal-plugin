# 06 - Structured Output

Get validated, typed responses from your agent using Pydantic models. This example demonstrates `TemporalModelStub.structured_output()` which returns parsed Pydantic objects instead of free-form text.

## What You'll Learn

- Using `structured_output()` to get typed Pydantic responses
- Defining output models with validation constraints
- Running structured output through Temporal activities

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
cd examples/06_structured_output
uv run python run_worker.py
```

### 2. Run the Client

```bash
# Weather analysis (default)
uv run python run_client.py weather

# Movie review
uv run python run_client.py movie

# Custom prompt
uv run python run_client.py weather --prompt "Analyze the weather in Tokyo"
```

### 3. View in Temporal UI

Open http://localhost:8233 to see the workflow execution. Look for the `execute_structured_output_activity` in the event history -- this is where the LLM call and Pydantic validation happen.

## Files

| File | Description |
|------|-------------|
| `models.py` | Pydantic output models (WeatherAnalysis, MovieReview) |
| `workflow.py` | WeatherAnalysisWorkflow and MovieReviewWorkflow |
| `run_worker.py` | Starts the Temporal worker |
| `run_client.py` | Executes workflows with argparse |

## Key Concept: `structured_output()`

```python
model = TemporalModelStub(BedrockProviderConfig(...))
result = await model.structured_output(WeatherAnalysis, prompt)
# result is a validated WeatherAnalysis instance
```

The Pydantic class is serialized as its import path (e.g., `models.WeatherAnalysis`) and reconstructed on the worker side where inference and validation happen. This means the worker's `sys.path` must include the directory containing `models.py`.

## Next Steps

- **07_session_management** - Persist agent conversation state across workflow executions
