# Task 2: Provider Configuration and Factory System

## Background Context

This task implements the provider factory system that maps `ProviderConfig` objects to actual Strands model instances. This allows Temporal workflows to specify which model provider to use via configuration data, while the activities instantiate the appropriate Strands models.

## Key Concepts

**Provider Configuration**: The plugin uses Pydantic models to describe model provider settings:
- `BedrockProviderConfig` - AWS Bedrock configuration (model_id, region, inference_config, etc.)
- `EchoProviderConfig` - Simple echo provider for testing (sleep_s, chunk_chars)

**Strands Model Providers**: Strands provides pre-built model providers:
- `BedrockModel` - AWS Bedrock integration with full streaming support
- Can create simple echo/mock models for testing

**Factory Pattern**: Convert configuration objects to actual model instances within Temporal activities.

## Architecture

The provider factory takes a `ProviderConfig` and returns an appropriate Strands `Model`:

```python
def create_model_from_config(provider: ProviderConfig) -> Model:
    if provider.type == "bedrock":
        return BedrockModel(
            model_id=provider.model_id,
            region_name=provider.region,
            **provider.inference_config or {}
        )
    elif provider.type == "echo":
        return EchoModel(
            sleep_s=provider.sleep_s,
            chunk_chars=provider.chunk_chars
        )
    else:
        raise ValueError(f"Unknown provider type: {provider.type}")
```

## Implementation Requirements

1. **Provider Factory Module** (`src/strands_temporal_plugin/providers.py`):
   - Create `create_model_from_config()` function
   - Handle `BedrockProviderConfig` -> `BedrockModel` instantiation
   - Handle `EchoProviderConfig` -> `EchoModel` instantiation
   - Proper error handling for invalid configurations

2. **Bedrock Provider Integration**:
   - Import `strands.models.BedrockModel`
   - Map config fields to BedrockModel constructor parameters:
     - `model_id` -> `model_id`
     - `region` -> `region_name`  
     - `inference_config` -> forwarded as model parameters
     - `tool_config` -> forwarded as model parameters

3. **Echo Provider Implementation**:
   - Create simple `EchoModel` class that implements Strands `Model` interface
   - Generate deterministic responses for testing
   - Support configurable latency simulation (`sleep_s`)
   - Support configurable chunk size for streaming simulation (`chunk_chars`)

4. **Model Configuration Validation**:
   - Validate required parameters for each provider type
   - Provide helpful error messages for missing/invalid configs
   - Handle optional parameters with sensible defaults

5. **Error Handling**:
   - Catch model instantiation errors and wrap with descriptive messages
   - Handle AWS credential/region errors for Bedrock
   - Validate model IDs and configurations before instantiation

## File Structure

```
src/strands_temporal_plugin/providers.py    # New file to create
```

## Dependencies

- `strands.models` - BedrockModel and Model base class
- `strands.types.streaming` - StreamEvent types for echo implementation  
- `strands.types.content` - Messages type
- `strands.types.tools` - ToolSpec type
- `..types` - ProviderConfig, BedrockProviderConfig, EchoProviderConfig
- `..logging` - Structured logging
- `pydantic` - For model validation
- `asyncio` - For sleep simulation in echo provider

## Expected Outcome

After completion:
- Any `ProviderConfig` can be converted to a working Strands `Model`
- BedrockProviderConfig creates properly configured `BedrockModel` instances
- EchoProviderConfig creates deterministic test models  
- Clear error messages for configuration problems
- Full compatibility with Strands model interface

## Echo Model Specification

The `EchoModel` should:
- Accept messages and return them as echoed text
- Simulate streaming with configurable delays and chunk sizes
- Support tool specs (but ignore them for simplicity)
- Return proper `StreamEvent` sequences compatible with Strands
- Be deterministic for testing purposes

## Integration Points

- Used by Task 1's `model_infer_activity` to create model instances
- Configurations are defined in existing `types.py` 
- Models follow Strands' streaming interface for consistency
- Provider factory is stateless and suitable for activity usage

## Example Usage

```python
# In activity:
model = create_model_from_config(input.provider)
stream = model.stream(input.messages, input.tool_specs, input.system_prompt)
async for event in process_stream(stream):
    # Process events...
```

## Notes

- **Do not reimplement AWS SDK or Bedrock integration** - use existing `strands.models.BedrockModel`
- **Echo provider is for testing only** - simple, deterministic responses
- **Provider configs are passed from workflows** to maintain Temporal determinism
- **All model instantiation happens within activities** to isolate non-deterministic operations
