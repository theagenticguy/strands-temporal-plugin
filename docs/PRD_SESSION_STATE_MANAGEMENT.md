# PRD: Session & State Management for Strands Temporal Plugin

## Document Info

| Field | Value |
|-------|-------|
| Author | AI Engineering |
| Status | Draft |
| Created | 2026-01-30 |

---

## 1. Executive Summary

The `strands-temporal-plugin` currently provides durable AI agent execution by routing model and tool calls to Temporal activities. However, it does not integrate with Strands' native session and state management capabilities:

- **SessionManager** - Not used (no cross-workflow conversation persistence)
- **AgentState** - Not serialized (tool state lost on replay/across workflows)
- **ConversationManager** - Not explicitly configured (using defaults)

This PRD documents the current architecture, identifies gaps, and proposes enhancements to bring full Strands state management to Temporal workflows.

---

## 2. Current Architecture

### 2.1 How It Works Today

```
┌─────────────────────────────────────────────────────────────────┐
│                    TEMPORAL WORKFLOW                             │
│                                                                  │
│   prompt ──► Agent.invoke_async() ──► result                    │
│                    │                                             │
│                    ▼                                             │
│        ┌───────────────────────────────────┐                    │
│        │      Strands Event Loop           │                    │
│        │   (manages messages in-memory)    │                    │
│        └───────────────────────────────────┘                    │
│                    │                                             │
│        ┌───────────┴───────────┐                                │
│        ▼                       ▼                                │
│  TemporalModelStub      TemporalToolExecutor                    │
│        │                       │                                │
└────────┼───────────────────────┼────────────────────────────────┘
         │                       │
         ▼                       ▼
   ┌─────────────┐        ┌──────────────┐
   │   Model     │        │    Tool      │
   │  Activity   │        │  Activity    │
   └─────────────┘        └──────────────┘
```

### 2.2 What Gets Serialized

| Data | Serialization | Location |
|------|---------------|----------|
| Conversation messages | `ModelExecutionInput.messages` | Activity input |
| Tool specs | `ModelExecutionInput.tool_specs` | Activity input |
| System prompt | `ModelExecutionInput.system_prompt` | Activity input |
| Provider config | `ModelExecutionInput.provider_config` | Activity input |
| Tool input args | `ToolExecutionInput.tool_input` | Activity input |
| Tool module path | `ToolExecutionInput.tool_module` | Activity input |

### 2.3 What Does NOT Get Serialized

| Data | Impact |
|------|--------|
| `agent.state` | Tool-written state lost on replay |
| Session ID | No way to resume conversations |
| ConversationManager state | Context window management resets |
| Callbacks/hooks | Cannot be serialized (functions) |

### 2.4 Key Files

| File | Purpose |
|------|---------|
| `src/strands_temporal_plugin/plugin.py` | Plugin registration, sandbox config |
| `src/strands_temporal_plugin/runner.py` | `TemporalModelStub`, `create_durable_agent()` |
| `src/strands_temporal_plugin/tool_executor.py` | `TemporalToolExecutor` |
| `src/strands_temporal_plugin/activities.py` | Model and tool activities |
| `src/strands_temporal_plugin/types.py` | Pydantic models for serialization |

---

## 3. Strands State Management Concepts

### 3.1 AgentState

A JSON-serializable key-value store accessible to tools:

```python
@tool(context=True)
def save_preference(key: str, value: str, tool_context: ToolContext) -> dict:
    tool_context.agent.state[key] = value
    return {"status": "success", "content": [{"text": f"Saved {key}={value}"}]}

agent = Agent(state={"theme": "dark"})
agent("Save my language preference as English")
print(agent.state)  # {"theme": "dark", "language": "English"}
```

**Current gap**: State modifications are lost when workflow replays or completes.

### 3.2 SessionManager

Persists both messages and state to external storage:

```python
from strands.session.file_session_manager import FileSessionManager

session_manager = FileSessionManager(session_id="user-123")
agent = Agent(session_manager=session_manager)

agent("My name is Alice")  # Persisted
agent.state["pref"] = "dark"  # Persisted after invocation

# Later, new process...
agent = Agent(session_manager=FileSessionManager(session_id="user-123"))
# Conversation and state restored automatically
```

**Available implementations**:
- `FileSessionManager` - Local filesystem
- `S3SessionManager` - AWS S3
- `RepositorySessionManager` - Custom backends

**Current gap**: Not integrated at all.

### 3.3 ConversationManager

Manages context window limits (not persistence):

```python
from strands.agent.conversation_manager import SlidingWindowConversationManager

manager = SlidingWindowConversationManager(
    window_size=40,
    should_truncate_results=True,
    per_turn=True
)
agent = Agent(conversation_manager=manager)
```

**Current gap**: Not explicitly configured; using defaults.

---

## 4. Gap Analysis

### 4.1 Single Workflow Scope

| Capability | Status | Impact |
|------------|--------|--------|
| Durable model calls | ✅ Works | Activities record in Temporal history |
| Durable tool calls | ✅ Works | Activities record in Temporal history |
| Crash recovery | ✅ Works | Replay reconstructs via activity results |
| Tool state persistence | ❌ Missing | `agent.state` lost on replay |
| Context window management | ⚠️ Default | No explicit configuration |

### 4.2 Cross-Workflow Scope

| Capability | Status | Impact |
|------------|--------|--------|
| Resume conversation | ❌ Missing | Each workflow starts fresh |
| Cross-workflow state | ❌ Missing | No shared state between runs |
| Session identification | ❌ Missing | No session_id concept |

### 4.3 Temporal vs Strands Philosophy

| Aspect | Temporal Approach | Strands Approach |
|--------|-------------------|------------------|
| Durability | Workflow event history | SessionManager to external store |
| State | Workflow variables (deterministic) | `agent.state` dict |
| Recovery | Replay from history | Load from session store |
| Multi-turn | Signals/queries or continue-as-new | Same Agent instance with SessionManager |

**Key tension**: Temporal workflows are meant to be deterministic and short-lived. Strands SessionManager assumes a persistent Agent across interactions.

---

## 5. Proposed Enhancements

### 5.1 Option A: Temporal-Native State (Recommended)

Serialize `agent.state` alongside messages in activity inputs. Keep Temporal as the source of truth.

**Pros**:
- No additional infrastructure
- Consistent with Temporal philosophy
- Single source of truth

**Cons**:
- State still scoped to single workflow
- Cross-workflow requires continue-as-new

### 5.2 Option B: SessionManager Integration

Add optional SessionManager support for cross-workflow persistence.

**Pros**:
- Full Strands compatibility
- Cross-workflow conversations "just work"
- Users can choose persistence backend

**Cons**:
- Two sources of truth (Temporal history + session store)
- Additional infrastructure (S3, etc.)
- Complexity in reconciling state

### 5.3 Option C: Hybrid Approach

- Use Temporal for durability within workflow
- Use SessionManager for cross-workflow persistence
- Sync at workflow boundaries

**Pros**:
- Best of both worlds
- Clear separation of concerns

**Cons**:
- Most complex implementation
- Need to handle conflicts

---

## 6. Implementation Tasks

### Phase 1: AgentState Serialization (Temporal-Native)

#### Task 1.1: Add state to ModelExecutionInput
**Priority**: High
**Complexity**: Low
**Dependencies**: None

Extend `ModelExecutionInput` to include agent state:
```python
class ModelExecutionInput(BaseModel):
    # ... existing fields ...
    agent_state: dict[str, Any] | None = None
```

#### Task 1.2: Serialize state in TemporalModelStub
**Priority**: High
**Complexity**: Low
**Dependencies**: Task 1.1

Update `TemporalModelStub.stream()` to include state in activity input and restore it from result.

#### Task 1.3: Return state from model activity
**Priority**: High
**Complexity**: Low
**Dependencies**: Task 1.1

Update `ModelExecutionResult` to include state and `execute_model_activity` to return it.

#### Task 1.4: Add state to tool activities
**Priority**: High
**Complexity**: Medium
**Dependencies**: Task 1.1

Tools may modify state. Need to:
- Pass state to tool activity
- Return modified state from activity
- Merge state changes back into agent

#### Task 1.5: Handle state in tool context
**Priority**: Medium
**Complexity**: Medium
**Dependencies**: Task 1.4

Tools using `@tool(context=True)` access `tool_context.agent.state`. Need to ensure this works in activity context.

---

### Phase 2: ConversationManager Support

#### Task 2.1: Add conversation_manager to create_durable_agent
**Priority**: Medium
**Complexity**: Low
**Dependencies**: None

Allow passing `conversation_manager` parameter:
```python
agent = create_durable_agent(
    provider_config=...,
    conversation_manager=SlidingWindowConversationManager(window_size=40),
)
```

#### Task 2.2: Document context window best practices
**Priority**: Medium
**Complexity**: Low
**Dependencies**: Task 2.1

Add documentation for:
- When to use SlidingWindowConversationManager
- Token limits and truncation
- Long-running agent patterns

---

### Phase 3: SessionManager Integration (Optional)

#### Task 3.1: Research SessionManager lifecycle hooks
**Priority**: Low
**Complexity**: Medium
**Dependencies**: Phase 1 complete

Understand when SessionManager:
- Calls `initialize()`
- Calls `append_message()`
- Calls `sync_agent()`

Determine if these fit Temporal's model.

#### Task 3.2: Design session-aware workflow pattern
**Priority**: Low
**Complexity**: High
**Dependencies**: Task 3.1

Options:
- Load session at workflow start, save at end
- Use Temporal queries to expose session state
- Continue-as-new with session passthrough

#### Task 3.3: Implement TemporalSessionManager
**Priority**: Low
**Complexity**: High
**Dependencies**: Task 3.2

Custom SessionManager that:
- Uses Temporal workflow state internally
- Optionally syncs to external store at boundaries
- Handles replay correctly

#### Task 3.4: Add session_id to workflow inputs
**Priority**: Low
**Complexity**: Low
**Dependencies**: Task 3.3

Allow workflows to receive session_id for continuation:
```python
@workflow.defn
class ChatWorkflow:
    @workflow.run
    async def run(self, input: ChatInput) -> ChatOutput:
        session_manager = TemporalSessionManager(session_id=input.session_id)
        agent = create_durable_agent(..., session_manager=session_manager)
```

---

### Phase 4: Multi-Turn Conversation Patterns

#### Task 4.1: Document signal-based conversation pattern
**Priority**: Medium
**Complexity**: Low
**Dependencies**: None

Show how to use Temporal signals for multi-turn:
```python
@workflow.defn
class ConversationWorkflow:
    def __init__(self):
        self.messages = []

    @workflow.signal
    async def send_message(self, message: str):
        self.messages.append(message)
        # Process with agent...

    @workflow.query
    def get_history(self) -> list[str]:
        return self.messages
```

#### Task 4.2: Document continue-as-new pattern
**Priority**: Medium
**Complexity**: Low
**Dependencies**: Phase 1 complete

Show how to pass conversation state to new workflow:
```python
if workflow.info().is_continue_as_new_suggested():
    workflow.continue_as_new(
        ConversationInput(
            messages=agent.messages,
            state=agent.state,
        )
    )
```

#### Task 4.3: Create multi-turn example
**Priority**: Medium
**Complexity**: Medium
**Dependencies**: Task 4.1 or 4.2

Add `examples/06_multi_turn/` demonstrating:
- Long-running workflow with signals
- Session resumption
- State persistence across turns

---

## 7. Task Dependency Graph

```
Phase 1: AgentState (Temporal-Native)
┌─────────────────────────────────────────────────┐
│                                                 │
│  [1.1] Add state to ModelExecutionInput         │
│         │                                       │
│         ├──► [1.2] Serialize in TemporalModelStub
│         │                                       │
│         ├──► [1.3] Return state from activity   │
│         │                                       │
│         └──► [1.4] Add state to tool activities │
│                    │                            │
│                    └──► [1.5] Handle tool context
│                                                 │
└─────────────────────────────────────────────────┘

Phase 2: ConversationManager
┌─────────────────────────────────────────────────┐
│                                                 │
│  [2.1] Add conversation_manager param           │
│         │                                       │
│         └──► [2.2] Document best practices      │
│                                                 │
└─────────────────────────────────────────────────┘

Phase 3: SessionManager (Optional)
┌─────────────────────────────────────────────────┐
│                                                 │
│  [Phase 1 Complete]                             │
│         │                                       │
│         └──► [3.1] Research lifecycle hooks     │
│                    │                            │
│                    └──► [3.2] Design pattern    │
│                              │                  │
│                              └──► [3.3] Implement│
│                                        │        │
│                                        └──► [3.4] Add session_id
│                                                 │
└─────────────────────────────────────────────────┘

Phase 4: Multi-Turn Patterns
┌─────────────────────────────────────────────────┐
│                                                 │
│  [4.1] Document signal pattern ──┐              │
│                                  │              │
│  [4.2] Document continue-as-new ─┼──► [4.3] Example
│        (depends on Phase 1)      │              │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## 8. Success Criteria

### Phase 1 Complete
- [ ] `agent.state` survives workflow replay
- [ ] Tools can read/write state that persists within workflow
- [ ] State included in Temporal event history for debugging

### Phase 2 Complete
- [ ] `conversation_manager` parameter available in `create_durable_agent()`
- [ ] SlidingWindowConversationManager works correctly
- [ ] Documentation explains context window management

### Phase 3 Complete (Optional)
- [ ] `session_id` enables conversation resumption
- [ ] State persists across workflow invocations
- [ ] S3SessionManager works with Temporal workflows

### Phase 4 Complete
- [ ] Multi-turn example demonstrates long-running conversations
- [ ] Documentation covers all conversation patterns
- [ ] Clear guidance on when to use each pattern

---

## 9. Open Questions

1. **State conflicts on replay**: If a tool modifies state, and we replay from an earlier point, how do we handle the state divergence?

2. **Session store vs Temporal history**: For SessionManager integration, which is the source of truth? How do we handle conflicts?

3. **Tool context in activities**: Tools with `@tool(context=True)` expect access to the full Agent. In activity context, we only have serialized data. How do we bridge this?

4. **Continue-as-new state size**: Temporal has limits on continue-as-new payload size. Large conversation histories may exceed this.

5. **Determinism with SessionManager**: If SessionManager does I/O (S3, filesystem), this violates workflow determinism. Should it only be called at workflow boundaries?

---

## 10. References

- [Strands Agents SDK Documentation](https://strandsagents.com/latest/)
- [Temporal Workflow Determinism](https://docs.temporal.io/workflows#deterministic-constraints)
- [Temporal Continue-As-New](https://docs.temporal.io/workflows#continue-as-new)
- [Temporal Signals and Queries](https://docs.temporal.io/workflows#signals-and-queries)
