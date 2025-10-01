# Task 5: Agent Workflow Implementation

## Background Context

This task implements the main agent workflow class that users will interact with directly. This workflow provides a familiar interface similar to standard Strands agents while leveraging Temporal's durable execution for reliability. It bridges the gap between user code and the underlying Temporal infrastructure.

## Key Concepts

**User Experience**: Users should be able to write code like:
```python
# Standard Strands agent usage, but durable
agent = Agent(model=TemporalDelegatingModel(...), tools=[...])
result = agent("What's the weather like?")
```

**Workflow as Agent Interface**: The workflow presents itself as the execution mechanism for agent conversations while coordinating with activities behind the scenes.

**Session Continuity**: Agents can continue conversations across multiple workflow executions, maintaining state and context through Temporal's persistence.

## Architecture

The main workflow should provide high-level agent execution:

```python
@workflow.defn  
class StrandsAgentWorkflow:
    def __init__(self):
        self.provider_config: ProviderConfig = ...
        self.session_storage: dict[str, Messages] = {}
    
    @workflow.run
    async def run_conversation(self, input: TurnInput) -> TurnResult:
        # Use AgentWorkflow from Task 3 for actual execution
        return await AgentWorkflow().run(input)
    
    @workflow.signal
    async def configure_provider(self, provider: ProviderConfig) -> None:
        # Allow runtime provider configuration changes
    
    @workflow.query  
    def get_conversation_history(self, session_id: str) -> Messages:
        # Query current conversation state
```

## Implementation Requirements

1. **Main Workflow Class** (`src/strands_temporal_plugin/workflows/strands_agent.py`):
   - Create `StrandsAgentWorkflow` with user-friendly interface
   - Implement conversation management and session handling
   - Delegate to `AgentWorkflow` for actual execution

2. **Session Management Integration**:
   - Store conversation history as workflow state
   - Support session-based conversation continuity
   - Handle session initialization and cleanup
   - Integrate with Strands session management patterns

3. **Provider Configuration Management**:
   - Allow dynamic provider configuration via signals
   - Support default provider configuration
   - Handle provider validation and error cases
   - Enable per-session provider overrides

4. **Conversation Flow Control**:
   - Support single-turn and multi-turn conversations
   - Handle conversation reset and continuation
   - Manage conversation context and history
   - Provide conversation querying capabilities

5. **Integration with Strands Agent Patterns**:
   - Support Strands' conversation manager patterns
   - Handle agent state and context properly
   - Maintain compatibility with Strands agent lifecycle
   - Support agent configuration options

6. **User Interface Design**:
   - Provide simple, intuitive workflow execution methods
   - Support both programmatic and declarative usage patterns
   - Handle common use cases with minimal configuration
   - Provide clear error messages and debugging support

## File Structure

```
src/strands_temporal_plugin/workflows/strands_agent.py    # New file to create
src/strands_temporal_plugin/workflows/__init__.py         # Update with exports
```

## Dependencies

- `temporalio` - For @workflow.defn, signals, queries, etc.
- `..workflows.agent` - AgentWorkflow from Task 3
- `..types` - TurnInput, TurnResult, ProviderConfig
- `..logging` - Structured logging
- `strands.types.content` - Messages type
- `strands.agent.state` - Agent state management
- `typing` - Type annotations

## Expected Outcome

After completion:
- Users have a high-level workflow interface for agent execution
- Session-based conversations work seamlessly
- Provider configuration can be managed dynamically
- Integration with existing Strands patterns is maintained
- Workflow provides debugging and introspection capabilities

## User Experience Examples

```python
# Execute single conversation turn
result = await client.execute_workflow(
    StrandsAgentWorkflow.run_conversation,
    TurnInput(session_id="user123", user_message="Hello!"),
    id="agent-session-user123",
    task_queue="strands-agents"
)

# Configure provider for session
await client.get_workflow_handle("agent-session-user123").signal(
    StrandsAgentWorkflow.configure_provider,
    BedrockProviderConfig(model_id="claude-3-sonnet")
)

# Query conversation history
history = await client.get_workflow_handle("agent-session-user123").query(
    StrandsAgentWorkflow.get_conversation_history,
    "user123"
)
```

## State Management Pattern

The workflow should maintain:
```python
class AgentState:
    conversations: dict[str, Messages]              # Session ID -> conversation history
    provider_configs: dict[str, ProviderConfig]     # Session-specific provider config
    default_provider: ProviderConfig                # Fallback provider configuration
    agent_metadata: dict[str, Any]                  # Agent configuration and state
```

## Integration Points

- **Builds on Task 3's AgentWorkflow** for core execution logic
- **Uses Task 4's plugin system** for proper Temporal configuration
- **Leverages existing types** from current `types.py`
- **Prepares for Task 6's hooks system** integration

## Notes

- **Workflow provides user-facing interface** - high-level abstraction over Temporal details
- **Session management is workflow-based** - persistent across executions  
- **Provider config is mutable via signals** - allows runtime customization
- **Delegates to lower-level workflows** - separation of concerns
- **Maintains Strands compatibility** - familiar patterns and interfaces
