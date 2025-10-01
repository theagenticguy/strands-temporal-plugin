# Task 4: Plugin Configuration System Implementation

## Background Context

This task implements the main `StrandsTemporalPlugin` class that configures Temporal clients and workers for seamless integration with Strands agents. This plugin follows the same pattern as Temporal's `OpenAIAgentsPlugin` but is adapted for Strands' architecture and streaming system.

## Key Concepts

**Temporal Plugin System**: Temporal uses plugins to configure clients and workers. Plugins implement both `temporalio.client.Plugin` and `temporalio.worker.Plugin` interfaces to customize:
- Data converters for serialization
- Interceptors for tracing and context propagation  
- Activity registration
- Runtime overrides

**Pydantic Data Converter**: Temporal's Pydantic converter enables type-safe serialization of complex objects like Strands' `Messages`, `ToolSpec`, etc.

**Runtime Overrides**: Context managers that replace default Strands behavior to route calls through Temporal activities.

## Architecture

The plugin configuration flow:
1. **Client Configuration**: Set up Pydantic data converter for type-safe serialization
2. **Worker Configuration**: Register activities and add interceptors for tracing
3. **Runtime Setup**: Override Strands model behavior to use Temporal activities

```python
class StrandsTemporalPlugin(temporalio.client.Plugin, temporalio.worker.Plugin):
    def configure_client(self, config: ClientConfig) -> ClientConfig:
        # Configure Pydantic data converter
    
    def configure_worker(self, config: WorkerConfig) -> WorkerConfig:
        # Register activities and interceptors
    
    async def run_worker(self, worker: Worker) -> None:
        # Set up runtime overrides
```

## Implementation Requirements

1. **Plugin Class** (`src/strands_temporal_plugin/plugin.py`):
   - Create `StrandsTemporalPlugin` implementing both client and worker plugin interfaces
   - Handle plugin initialization with model parameters
   - Support custom provider configurations

2. **Client Configuration**:
   - Set up Pydantic data converter using `temporalio.contrib.pydantic.PydanticPayloadConverter`
   - Configure with `exclude_unset=True` for efficient serialization
   - Ensure compatibility with Strands type system

3. **Worker Configuration**:
   - Register model inference activity (`model_infer_activity`)
   - Register tool execution activity (`call_registered_tool_activity`)
   - Add tracing interceptors for observability
   - Configure activity execution parameters

4. **Runtime Overrides Context Manager**:
   - Create context manager to override Strands behavior during workflow execution
   - Replace default model providers with `TemporalDelegatingModel`
   - Ensure overrides are properly restored after execution

5. **Model Parameters Configuration**:
   - Support `ModelActivityParameters` for configuring activity timeouts
   - Allow custom provider configurations
   - Handle default parameter values appropriately

6. **Plugin Integration Points**:
   - Implement plugin chain pattern for composability
   - Support replayer configuration for workflow testing
   - Handle plugin lifecycle properly

## File Structure

```
src/strands_temporal_plugin/plugin.py           # New file to create
```

## Dependencies

- `temporalio.client` - Client, Plugin, ClientConfig
- `temporalio.worker` - Worker, Plugin, WorkerConfig  
- `temporalio.contrib.pydantic` - PydanticPayloadConverter, ToJsonOptions
- `temporalio.converter` - DataConverter
- `contextlib` - For context manager implementation
- `..types` - ProviderConfig and parameter types
- `..activities.model` - model_infer_activity
- `..activities.tools` - call_registered_tool_activity
- `..adapters.model_adapter` - TemporalDelegatingModel

## Expected Outcome

After completion:
- Users can create clients/workers with `StrandsTemporalPlugin([...])`
- All Strands types serialize properly through Temporal
- Activities are automatically registered with workers
- Tracing and observability work correctly
- Runtime overrides enable transparent Temporal integration

## Plugin Usage Pattern

```python
# Client setup
client = await Client.connect(
    "localhost:7233",
    plugins=[StrandsTemporalPlugin(
        model_params=ModelActivityParameters(
            start_to_close_timeout=timedelta(minutes=5)
        ),
        default_provider=BedrockProviderConfig(
            model_id="anthropic.claude-3-sonnet-20240229-v1:0"
        )
    )]
)

# Worker setup  
worker = Worker(
    client,
    task_queue="strands-agents",
    workflows=[AgentWorkflow],
)
await worker.run()
```

## Context Manager Requirements

The runtime overrides should:
- Replace Strands' default model behavior with Temporal delegation
- Be transparent to user code
- Restore previous state when context exits
- Handle nested context scenarios properly

## Integration with OpenAI Plugin Pattern

Follow similar structure to `OpenAIAgentsPlugin`:
- Use composition pattern for plugin chaining
- Implement all required plugin interface methods
- Support both client and worker plugin interfaces
- Handle serialization and activity registration consistently

## Notes

- **Use existing Temporal Pydantic converter** - don't reimplement serialization
- **Follow OpenAI plugin patterns** - leverage proven architecture  
- **Activities are imported, not reimplemented** - use existing activity definitions
- **Plugin is the main integration point** - users interact through this class
