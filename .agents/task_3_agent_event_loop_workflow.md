# Task 3: Agent Event Loop Workflow Implementation

## Background Context

This task implements the core Temporal workflow that orchestrates the Strands agent event loop. Unlike traditional Strands agents that run entirely in-process, this workflow coordinates model inference and tool execution through durable Temporal activities while maintaining the familiar Strands agent behavior.

## Key Concepts

**Strands Agent Loop**: The Strands agent follows this pattern:
1. Process user input with LLM
2. If LLM requests tools, execute them and feed results back  
3. Continue until LLM provides final response
4. Return complete conversation with usage/metrics

**Temporal Workflows**: Deterministic coordination logic that can resume after crashes. Workflows orchestrate activities but cannot perform I/O themselves.

**Activity Coordination**: The workflow calls:
- `model_infer_activity` for all LLM inference
- `call_registered_tool_activity` for all tool execution

## Architecture

```python
@workflow.defn
class AgentWorkflow:
    @workflow.run
    async def run(self, input: TurnInput) -> TurnResult:
        # 1. Load/initialize conversation state
        # 2. Add user message to conversation
        # 3. Event loop: model -> tools -> model until done
        # 4. Return final result with usage metrics
```

The workflow maintains conversation state and coordinates the agent loop:

```
User Input -> [Add to Messages] -> Model Activity -> Tool Activities -> Model Activity -> Final Response
```

## Implementation Requirements

1. **Agent Workflow Class** (`src/strands_temporal_plugin/workflows/agent.py`):
   - Create `AgentWorkflow` class with `@workflow.defn`
   - Implement `run()` method accepting `TurnInput` and returning `TurnResult`
   - Handle conversation state management across multiple turns

2. **Conversation State Management**:
   - Maintain conversation history as workflow state
   - Add user messages to conversation
   - Accumulate assistant responses and tool results
   - Handle session persistence integration points

3. **Event Loop Coordination**:
   - Implement multi-turn conversation loop
   - Call `model_infer_activity` with current conversation state
   - Process model responses for tool use requests
   - Execute tools via `call_registered_tool_activity` when needed
   - Continue loop until final response (no more tool requests)

4. **Tool Execution Handling**:
   - Extract tool use requests from model responses
   - Execute multiple tools in parallel when possible
   - Format tool results back into conversation format
   - Handle tool execution errors gracefully

5. **Usage and Metrics Aggregation**:
   - Accumulate token usage across multiple model calls
   - Track conversation metadata and timing
   - Return comprehensive `TurnResult` with all metrics

6. **Error Handling and Recovery**:
   - Handle activity failures with appropriate retry logic
   - Manage conversation state consistency
   - Provide meaningful error messages to users

## File Structure

```
src/strands_temporal_plugin/workflows/agent.py       # New file to create
src/strands_temporal_plugin/workflows/__init__.py    # New file to create
```

## Dependencies

- `temporalio` - For @workflow.defn, workflow.execute_activity, etc.
- `..types` - TurnInput, TurnResult, ModelCallInput, ToolCallInput, etc.
- `..logging` - Structured logging
- `strands.types.content` - Messages, ContentBlock types
- `strands.types.tools` - ToolUse, ToolResult types
- `typing` - Type annotations

## Expected Outcome

After completion:
- Users can execute agent conversations through Temporal workflows
- Multi-turn conversations work with proper state management
- Tool execution is handled durably through activities
- Usage metrics and conversation state are properly tracked
- Workflow can resume from any point if interrupted

## Workflow State Management

The workflow should maintain:
```python
class WorkflowState:
    messages: Messages                    # Full conversation history
    session_id: str                      # Session identifier
    total_usage: Usage                   # Accumulated token usage
    provider_config: ProviderConfig      # Model provider configuration
```

## Event Loop Pattern

```python
async def run(self, input: TurnInput) -> TurnResult:
    # Initialize state
    messages = load_conversation_history(input.session_id)
    
    # Add user message
    if input.user_message:
        messages.append(create_user_message(input.user_message))
    
    # Agent loop
    while True:
        # Get model response
        model_result = await workflow.execute_activity(
            "model_infer_activity",
            ModelCallInput(messages=messages, provider=self.provider_config),
            schedule_to_close_timeout=timedelta(minutes=5)
        )
        
        # Add assistant message
        messages.append(create_assistant_message(model_result.text))
        
        # Check if tools needed
        tool_uses = extract_tool_uses(messages[-1])
        if not tool_uses:
            break  # No tools, we're done
            
        # Execute tools in parallel
        tool_tasks = [
            workflow.execute_activity(
                "call_registered_tool_activity", 
                ToolCallInput(name=tool.name, arguments=tool.input)
            )
            for tool in tool_uses
        ]
        
        tool_results = await asyncio.gather(*tool_tasks)
        
        # Add tool results to conversation
        for tool_use, tool_result in zip(tool_uses, tool_results):
            messages.append(create_tool_result_message(tool_use.toolUseId, tool_result))
    
    return TurnResult(
        session_id=input.session_id,
        assistant_text=model_result.text,
        usage=accumulated_usage
    )
```

## Notes

- **Workflow must be deterministic** - no I/O, random numbers, or system calls
- **All model/tool calls go through activities** for durability
- **State is managed as workflow variables** that survive restarts
- **Built on existing activities from Tasks 1 & 2** 
- **Follows Strands conversation format** for compatibility
