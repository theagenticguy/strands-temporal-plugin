# Clean Strands Weather Agent - New Architecture

This demonstrates the new clean architecture that follows the OpenAI Agents pattern.

## Key Differences from Old Architecture

### Old (Complex):
- Multiple workflow classes with manual configuration propagation
- `TemporalDelegatingModel` wrappers  
- Manual tool registration with `register_tool()`
- Complex provider configuration flow
- Echo provider fallbacks

### New (Clean):
- Single workflow using normal Strands `Agent()` API
- Plugin automatically handles everything  
- Tools defined directly in workflow
- No configuration complexity
- Real BedrockModel by default

## Usage

### 1. Start Worker
```bash
python examples/basic_weather_agent/run_new_worker.py
```

### 2. Run Client  
```bash  
python examples/basic_weather_agent/run_new_client.py
```

## How It Works

### Clean Workflow Definition
```python
@workflow.defn
class StrandsWeatherAgent:
    @workflow.run
    async def run(self, prompt: str) -> str:
        # Just normal Strands Agent API!
        agent = Agent(
            model=BedrockModel(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0"),
            tools=[get_weather],
            system_prompt="You are a weather assistant"
        )
        # Plugin automatically makes this durable
        result = await agent(prompt) 
        return result
```

### Plugin Magic
When `StrandsTemporalPlugin` is active:
1. Any `Agent()` call inside a workflow gets intercepted
2. Agent configuration is extracted (model, tools, system prompt)
3. Routed to `execute_strands_agent` activity  
4. Activity creates real Strands Agent with BedrockModel
5. Runs full agent loop with tools and streaming
6. Returns final result to workflow

### Architecture Flow
```
Client → Workflow → Agent() Call
                        ↓ (Plugin intercepts)
                   Activity → Real Strands Agent → BedrockModel → Tool Calls → Result
```

## Benefits

✅ **Same Strands API** - no new concepts to learn  
✅ **No Echo provider** - uses real BedrockModel  
✅ **Automatic tool discovery** - no manual registration  
✅ **Clean workflows** - just call Agent() normally  
✅ **True durability** - complete agent loop in activities  
✅ **OpenAI pattern** - familiar setup for Temporal users

## Testing

This should now work exactly like your Temporal UI input shows:
- Bedrock provider with proper model_id
- Tool specs automatically extracted and passed  
- Real Claude responses with weather tool usage
- No more echo fallbacks!
