# Task 1: Model Inference Activity Implementation

## Background Context

This task implements the core `model_infer_activity` Temporal activity that serves as the bridge between Temporal workflows and Strands model providers. This activity performs all non-deterministic LLM inference operations while maintaining Temporal's durability guarantees.

## Key Concepts

**Strands Model Interface**: Strands provides model providers like `BedrockModel`, `AnthropicModel`, etc. that implement the `Model` abstract base class with a `stream()` method returning `AsyncIterable[StreamEvent]`.

**Strands Streaming System**: The `strands.event_loop.streaming` module provides utilities for processing streaming responses:
- `process_stream()` - Aggregates streaming deltas into final messages
- `StreamEvent` types - `messageStart`, `contentBlockDelta`, `messageStop`, etc.
- Event handlers for tool use accumulation, text aggregation, usage tracking

**Temporal Activities**: Non-deterministic operations that can perform I/O, with automatic retries if they fail partway through.

## Architecture

```python
# The activity receives provider configuration and creates actual Strands models:
input = ModelCallInput(
    messages=...,           # Strands message format  
    tool_specs=...,         # Tool specifications for the model
    system_prompt=...,      # Optional system prompt
    provider=ProviderConfig # Config specifying which Strands model to use
)

# Activity creates the appropriate Strands model and processes its stream:
if input.provider.type == "bedrock":
    model = BedrockModel(model_id=input.provider.model_id, ...)
    
stream = model.stream(input.messages, input.tool_specs, input.system_prompt)
# Use Strands' process_stream() to aggregate results
```

## Implementation Requirements

1. **Complete `src/strands_temporal_plugin/activities/model.py`**:
   - Create the `model_infer_activity` function with `@activity.defn` decorator
   - Import and use existing Strands model providers (BedrockModel, etc.)
   - Use Strands' `process_stream()` utility for event processing
   - Handle provider routing based on `ProviderConfig.type`

2. **Provider Factory Function**:
   - Create function to instantiate Strands models from `ProviderConfig`
   - Handle `BedrockProviderConfig` -> `BedrockModel()` mapping
   - Handle `EchoProviderConfig` for testing (simple mock responses)

3. **Response Processing**:
   - Use `strands.event_loop.streaming.process_stream()` to aggregate stream events
   - Extract final text content, usage metrics, and stop reason
   - Return `ModelCallResult` with aggregated data

4. **Error Handling**:
   - Catch and re-raise Strands model exceptions appropriately
   - Ensure proper cleanup and logging
   - Handle timeout and retry scenarios

## File Structure

```
src/strands_temporal_plugin/activities/model.py
```

## Dependencies

- `temporalio` - For @activity.defn decorator and activity context
- `strands.models` - BedrockModel and other model providers  
- `strands.event_loop.streaming` - For process_stream() utility
- `..types` - ModelCallInput, ModelCallResult, ProviderConfig types
- `..logging` - Structured logging

## Expected Outcome

After completion, the plugin will be able to:
- Execute LLM inference durably within Temporal workflows
- Support multiple Strands model providers (Bedrock, Echo, etc.)  
- Process streaming responses using Strands' native utilities
- Provide proper error handling and observability

## Testing

The activity should be testable with:
- BedrockProviderConfig pointing to real AWS Bedrock models
- EchoProviderConfig for deterministic test responses
- Various message formats and tool specifications
- Error scenarios and timeout conditions

## Notes

- This activity must be **registered with the Temporal worker** (handled in later tasks)
- All I/O and non-deterministic operations happen **only within this activity**
- The activity uses **Strands' existing streaming processing** rather than reimplementing it
- Provider configurations are **passed from workflows** to maintain determinism
