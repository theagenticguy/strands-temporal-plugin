# Task 8: Examples and Testing Implementation

## Background Context

This task implements comprehensive examples and tests to demonstrate the Strands Temporal plugin functionality and ensure robust operation. It includes working multi-agent examples, unit tests, integration tests, and documentation that shows users how to leverage the plugin effectively.

## Key Concepts

**Example-Driven Development**: Provide working examples that demonstrate:
- Basic agent execution with Temporal durability
- Multi-agent workflows similar to the research bot example
- Tool integration and registration
- Session management and conversation continuity

**Testing Strategy**: Cover all aspects of the plugin:
- Unit tests for individual components
- Integration tests for end-to-end workflows
- Provider-specific testing (Bedrock, Echo)
- Error handling and edge cases

**Documentation**: Clear examples showing the developer experience and migration from standard Strands usage.

## Architecture

Create examples that mirror the OpenAI research bot but using Strands:

```python
# Example: Weather Agent with Temporal durability
@workflow.defn
class WeatherAgentWorkflow:
    @workflow.run
    async def run(self, query: str) -> str:
        agent = Agent(
            model=TemporalDelegatingModel(BedrockProviderConfig(...)),
            tools=[weather_tool],
            system_prompt="You are a weather assistant..."
        )
        
        result = await execute_strands_agent(agent, query)
        return result.final_output
```

## Implementation Requirements

1. **Basic Agent Example** (`examples/basic_weather_agent/`):
   - Create simple weather agent using the plugin
   - Show tool registration and usage
   - Demonstrate worker/client setup
   - Include README with setup instructions

2. **Multi-Agent Research Bot** (`examples/research_bot/`):
   - Port OpenAI research bot example to Strands
   - Use multiple specialized agents (planner, searcher, writer)
   - Demonstrate complex workflow orchestration
   - Show parallel tool execution and coordination

3. **Unit Test Suite** (`tests/unit/`):
   - Test provider factory functionality
   - Test model adapter behavior
   - Test type serialization/deserialization
   - Test hook system components

4. **Integration Test Suite** (`tests/integration/`):
   - Test full workflow execution with Echo provider
   - Test conversation continuity and session management
   - Test error handling and recovery scenarios
   - Test plugin configuration and setup

5. **Performance and Load Tests** (`tests/performance/`):
   - Test workflow execution under load
   - Test conversation memory usage and scalability
   - Test activity retry and timeout behavior
   - Benchmark against standard Strands execution

6. **Documentation Examples** (`docs/`):
   - Quick start guide with minimal setup
   - Migration guide from standard Strands
   - Advanced configuration examples
   - Troubleshooting guide and common issues

## File Structure

```
examples/
├── basic_weather_agent/
│   ├── README.md
│   ├── run_worker.py
│   ├── run_weather_client.py
│   └── weather_agent.py
├── research_bot/
│   ├── README.md  
│   ├── run_worker.py
│   ├── run_research_workflow.py
│   └── agents/
│       ├── planner.py
│       ├── searcher.py
│       └── writer.py
└── multi_agent_demo/
    ├── README.md
    ├── run_demo.py
    └── specialized_agents.py

tests/
├── unit/
│   ├── test_providers.py
│   ├── test_model_adapter.py
│   ├── test_types.py
│   └── test_hooks.py
├── integration/
│   ├── test_workflow_execution.py
│   ├── test_session_management.py
│   └── test_error_handling.py
└── performance/
    ├── test_load_scenarios.py
    └── test_memory_usage.py
```

## Dependencies

- All plugin modules from previous tasks
- `pytest` and `pytest-asyncio` for testing framework
- `temporalio.testing` for workflow testing utilities
- `strands` and `strands-agents-tools` for example implementations
- `boto3` for Bedrock integration testing (optional)

## Expected Outcome

After completion:
- Working examples demonstrate all plugin capabilities
- Comprehensive test coverage ensures reliability
- Clear documentation enables user adoption
- Migration path from standard Strands is documented
- Plugin is ready for production use

## Basic Weather Agent Example

```python
# weather_agent.py
from strands import Agent, tool
from strands_temporal_plugin import (
    TemporalDelegatingModel, 
    BedrockProviderConfig,
    register_tool
)

@tool
def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"Sunny and 72°F in {city}"

register_tool("get_weather", get_weather)

# run_worker.py  
async def main():
    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()]
    )
    
    worker = Worker(
        client,
        task_queue="weather-agents",
        workflows=[StrandsAgentWorkflow]
    )
    await worker.run()

# run_weather_client.py
async def main():
    client = await Client.connect(
        "localhost:7233", 
        plugins=[StrandsTemporalPlugin()]
    )
    
    result = await client.execute_workflow(
        StrandsAgentWorkflow.run_conversation,
        TurnInput(
            session_id="weather-session",
            user_message="What's the weather in Seattle?"
        ),
        id="weather-workflow",
        task_queue="weather-agents"
    )
    
    print(result.assistant_text)
```

## Test Coverage Requirements

Tests should cover:
- **Provider Factory**: All provider types and configurations
- **Model Activity**: Various input scenarios and error cases  
- **Tool Activity**: Tool registration and execution
- **Workflow Logic**: Conversation flows and state management
- **Plugin Configuration**: Client/worker setup scenarios
- **Session Management**: Conversation persistence and continuity
- **Error Handling**: Activity failures, timeout scenarios, invalid inputs
- **Performance**: Memory usage, execution time, scalability

## Research Bot Example Structure

The research bot should mirror the OpenAI example but use:
- Strands agents instead of OpenAI agents
- Strands tools (http_request) instead of WebSearchTool
- Strands model providers instead of OpenAI models
- Plugin configuration instead of OpenAI plugin setup

## Example Migration Guide

Show users how to migrate from:
```python
# Standard Strands
agent = Agent(
    model=BedrockModel(...),
    tools=[weather_tool]
)
result = agent("What's the weather?")
```

To:
```python  
# Temporal-powered Strands
agent = Agent(
    model=TemporalDelegatingModel(BedrockProviderConfig(...)),
    tools=[weather_tool] # Tools run as Temporal activities
)
result = await execute_temporal_agent(agent, "What's the weather?")
```

## Notes

- **Examples should be runnable** - include all necessary setup code
- **Tests should be comprehensive** - cover happy path and edge cases  
- **Documentation should be clear** - enable quick adoption
- **Migration guide essential** - help users transition from standard Strands
- **Performance tests important** - ensure scalability and reliability
