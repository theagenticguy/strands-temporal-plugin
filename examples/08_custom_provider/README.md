# 08 - Custom Provider

Plug in a custom model provider using `CustomProviderConfig`. This example demonstrates wrapping `BedrockModel` with logging, but the pattern works for any Strands-compatible Model implementation.

## What You'll Learn

- Using `CustomProviderConfig` to load a custom model class via import path
- Extending `BedrockModel` with custom behavior (logging)
- How the activity resolves the provider class at runtime via `importlib`

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
cd examples/08_custom_provider
uv run python run_worker.py
```

### 2. Run the Client

```bash
# Default prompt
uv run python run_client.py

# Custom prompt
uv run python run_client.py "Explain quantum computing in one paragraph."
```

### 3. Check Worker Logs

The worker output will show `[CustomProvider]` log messages from the custom model:

```
INFO | custom_model | [CustomProvider] Initializing LoggingBedrockModel: us.anthropic.claude-sonnet-4-20250514-v1:0
INFO | custom_model | [CustomProvider] stream() called
INFO | custom_model | [CustomProvider] stream() completed
```

### 4. View in Temporal UI

Open http://localhost:8233 to see the workflow execution.

## Files

| File | Description |
|------|-------------|
| `custom_model.py` | LoggingBedrockModel - custom provider with logging |
| `workflow.py` | CustomProviderWorkflow using CustomProviderConfig |
| `run_worker.py` | Starts the Temporal worker |
| `run_client.py` | Executes the workflow |

## Key Concept: `CustomProviderConfig`

```python
agent = create_durable_agent(
    provider_config=CustomProviderConfig(
        model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        provider_class_path="custom_model.LoggingBedrockModel",
    ),
    system_prompt="...",
)
```

The `provider_class_path` is a dotted import path (e.g., `custom_model.LoggingBedrockModel`). The activity uses `importlib` to resolve this at runtime. The worker's `sys.path` must include the directory containing the custom module.

Your custom class must implement the Strands Model interface (typically by subclassing an existing provider like `BedrockModel`).
