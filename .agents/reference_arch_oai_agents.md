Directory structure:
└── openai_agents/
    ├── README.md
    ├── __init__.py
    ├── _heartbeat_decorator.py
    ├── _invoke_model_activity.py
    ├── _model_parameters.py
    ├── _openai_runner.py
    ├── _temporal_model_stub.py
    ├── _temporal_openai_agents.py
    ├── _temporal_trace_provider.py
    ├── _trace_interceptor.py
    └── workflow.py


Files Content:

================================================
FILE: temporalio/contrib/openai_agents/README.md
================================================
# OpenAI Agents SDK Integration for Temporal

⚠️ **Public Preview** - The interface to this module is subject to change prior to General Availability.
We welcome questions and feedback in the [#python-sdk](https://temporalio.slack.com/archives/CTT84RS0P) Slack channel at [temporalio.slack.com](https://temporalio.slack.com/).


## Introduction

This integration combines [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) with [Temporal's durable execution](https://docs.temporal.io/evaluate/understanding-temporal#durable-execution).
It allows you to build durable agents that never lose their progress and handle long-running, asynchronous, and human-in-the-loop workflows with production-grade reliability.

Temporal and OpenAI Agents SDK are complementary technologies, both of which contribute to simplifying what it takes to build highly capable, high-quality AI systems.
Temporal provides a crash-proof system foundation, taking care of the distributed systems challenges inherent to production agentic systems.
OpenAI Agents SDK offers a lightweight yet powerful framework for defining those agents.

This document is organized as follows:
 - **[Hello World Durable Agent](#hello-world-durable-agent).** Your first durable agent example.
 - **[Background Concepts](#core-concepts).** Background on durable execution and AI agents.
 - **[Full Example](#full-example)** Running the Hello World Durable Agent example.
 - **[Tool Calling](#tool-calling).** Calling agent Tools in Temporal.
 - **[Feature Support](#feature-support).** Compatibility matrix.

The [samples repository](https://github.com/temporalio/samples-python/tree/main/openai_agents) contains examples including basic usage, common agent patterns, and more complete samples.


## Hello World Durable Agent

The code below shows how to wrap an agent for durable execution.

### File 1: Durable Agent (`hello_world.py`)

```python
from temporalio import workflow
from agents import Agent, Runner

@workflow.defn
class HelloWorldAgent:
    @workflow.run
    async def run(self, prompt: str) -> str:
        agent = Agent(
            name="Assistant",
            instructions="You only respond in haikus.",
        )

        result = await Runner.run(agent, input=prompt)
        return result.final_output
```

In this example, Temporal provides the durable execution wrapper: the `HelloWorldAgent.run` method.
The content of that method, is regular OpenAI Agents SDK code.

If you are familiar with Temporal and with Open AI Agents SDK, this code will look very familiar.
The `@workflow.defn` annotation on the `HelloWorldAgent` indicates that this class will contain durable execution logic. The `@workflow.run` annotation defines the entry point.
We use the `Agent` class from OpenAI Agents SDK to define a simple agent, instructing it to always respond with haikus.
We then run that agent, using the `Runner` class from OpenAI Agents SDK, passing through `prompt` as an argument.


We will [complete this example below](#full-example).
Before digging further into the code, we will review some background that will make it easier to understand.

## Background Concepts

We encourage you to review this section thoroughly to gain a solid understanding of AI agents and durable execution with Temporal.
This knowledge will make it easier to design and build durable agents.
If you are already well versed in these topics, feel free to skim this section or skip ahead.

### AI Agents

In the OpenAI Agents SDK, an agent is an AI model configured with instructions, tools, MCP servers, guardrails, handoffs, context, and more.

We describe each of these briefly:

- *AI model*. An LLM such as OpenAI's GPT, Google's Gemini, or one of many others.
- *Instructions*. Also known as a system prompt, the instructions contain the initial input to the model, which configures it for the job it will do.
- *Tools*. Typically, Python functions that the model may choose to invoke. Tools are functions with text-descriptions that explain their functionality to the model.
- *MCP servers*. Best known for providing tools, MCP offers a pluggable standard for interoperability, including file-like resources, prompt templates, and human approvals. MCP servers may be accessed over the network or run in a local process.
- *Guardrails*. Checks on the input or the output of an agent to ensure compliance or safety. Guardrails may be implemented as regular code or as AI agents.
- *Handoffs*. A handoff occurs when an agent delegates a task to another agent. During a handoff the conversation history remains the same, and passes to a new agent with its own model, instructions, tools.
- *Context*. This is an overloaded term. Here, context refers to a framework object that is shared across tools and other code, but is not passed to the model.

Now, let's see how these components work together.
In a common pattern, the model first receives user input and then reasons about which tool to invoke.
The tool's response is passed back to the model, which may call additional tools, repeating this loop until the task is complete.

The diagram below illustrates this flow.

```text
           +-------------------+
           |     User Input    |
           +-------------------+
                     |
                     v
          +---------------------+
          |  Reasoning (Model)  |  <--+
          +---------------------+     |
                     |                |
           (decides which action)     |
                     v                |
          +---------------------+     |
          |       Action        |     |
          | (e.g., use a Tool)  |     |
          +---------------------+     |
                     |                |
                     v                |
          +---------------------+     |
          |     Observation     |     |
          |    (Tool Output)    |     |
          +---------------------+     |
                     |                |
                     +----------------+
          (loop: uses new info to reason
           again, until task is complete)
```

Even in a simple example like this, there are many places where things can go wrong.
Tools call APIs that sometimes fail, while models can encounter rate limits, requiring retries.
The longer the agent runs, the more costly it is to start the job over.
We next describe durable execution, which handles such failures seamlessly.

### Durable Execution

In Temporal's durable execution implementation, a program that crashes or encounters an exception while interacting with a model or API will retry until it can successfully complete.

Temporal relies primarily on a replay mechanism to recover from failures.
As the program makes progress, Temporal saves key inputs and decisions, allowing a re-started program to pick up right where it left off.

The key to making this work is to separate the applications repeatable (deterministic) and non-repeatable (non-deterministic) parts:

1. Deterministic pieces, termed *workflows*, execute the same way when re-run with the same inputs.
2. Non-deterministic pieces, termed *activities*, can run arbitrary code, performing I/O and any other operations.

Workflow code can run for extended periods and, if interrupted, resume exactly where it left off.
Activity code faces no restrictions on I/O or external interactions, but if it fails part-way through it restarts from the beginning.

In the AI-agent example above, model invocations and tool calls run inside activities, while the logic that coordinates them lives in the workflow.
This pattern generalizes to more sophisticated agents.
We refer to that coordinating logic as *agent orchestration*.

As a general rule, agent orchestration code executes within the Temporal workflow, whereas model calls and any I/O-bound tool invocations execute as Temporal activities.

The diagram below shows the overall architecture of an agentic application in Temporal.
The Temporal Server is responsible to tracking program execution and making sure associated state is preserved reliably (i.e., stored to a database, possibly replicated across cloud regions).
Temporal Server manages data in encrypted form, so all data processing occurs on the Worker, which runs the workflow and activities.


```text
            +---------------------+
            |   Temporal Server   |      (Stores workflow state,
            +---------------------+       schedules activities,
                     ^                    persists progress)
                     |
        Save state,  |   Schedule Tasks,
        progress,    |   load state on resume
        timeouts     |
                     |
+------------------------------------------------------+
|                      Worker                          |
|   +----------------------------------------------+   |
|   |              Workflow Code                   |   |
|   |       (Agent Orchestration Loop)             |   |
|   +----------------------------------------------+   |
|          |          |                |               |
|          v          v                v               |
|   +-----------+ +-----------+ +-------------+        |
|   | Activity  | | Activity  | |  Activity   |        |
|   | (Tool 1)  | | (Tool 2)  | | (Model API) |        |
|   +-----------+ +-----------+ +-------------+        |
|         |           |                |               |
+------------------------------------------------------+
          |           |                |
          v           v                v
      [External APIs, services, databases, etc.]
```


See the [Temporal documentation](https://docs.temporal.io/evaluate/understanding-temporal#temporal-application-the-building-blocks) for more information.


## Complete Example

To make the [Hello World durable agent](#hello-world-durable-agent) shown earlier available in Temporal, we need to create a worker program.
To see it run, we also need a client to launch it.
We show these files below.


### File 2: Launch Worker (`run_worker.py`)

```python
# File: run_worker.py

import asyncio
from datetime import timedelta

from temporalio.client import Client
from temporalio.contrib.openai_agents import OpenAIAgentsPlugin, ModelActivityParameters
from temporalio.worker import Worker

from hello_world_workflow import HelloWorldAgent


async def worker_main():
    # Use the plugin to configure Temporal for use with OpenAI Agents SDK
    client = await Client.connect(
        "localhost:7233",
        plugins=[
            OpenAIAgentsPlugin(
                model_params=ModelActivityParameters(
                    start_to_close_timeout=timedelta(seconds=30)
                )
            ),
        ],
    )

    worker = Worker(
        client,
        task_queue="my-task-queue",
        workflows=[HelloWorldAgent],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(worker_main())
```

We use the `OpenAIAgentsPlugin` to configure Temporal for use with OpenAI Agents SDK.
The plugin automatically handles several important setup tasks:
- Ensures proper serialization of Pydantic types
- Propagates context for [OpenAI Agents tracing](https://openai.github.io/openai-agents-python/tracing/).
- Registers an activity for invoking model calls with the Temporal worker.
- Configures OpenAI Agents SDK to run model calls as Temporal activities.


### File 3: Client Execution (`run_hello_world_workflow.py`)

```python
# File: run_hello_world_workflow.py

import asyncio

from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.contrib.openai_agents import OpenAIAgentsPlugin

from hello_world_workflow import HelloWorldAgent

async def main():
    # Create client connected to server at the given address
    client = await Client.connect(
        "localhost:7233",
        plugins=[OpenAIAgentsPlugin()],
    )

    # Execute a workflow
    result = await client.execute_workflow(
        HelloWorldAgent.run,
        "Tell me about recursion in programming.",
        id="my-workflow-id",
        task_queue="my-task-queue",
        id_reuse_policy=WorkflowIDReusePolicy.TERMINATE_IF_RUNNING,
    )
    print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(main())
```

This file is a standard Temporal launch script.
We also configure the client with the `OpenAIAgentsPlugin` to ensure serialization is compatible with the worker.


To run this example, see the detailed instructions in the [Temporal Python Samples Repository](https://github.com/temporalio/samples-python/tree/main/openai_agents).

## Tool Calling

### Temporal Activities as OpenAI Agents Tools

One of the powerful features of this integration is the ability to convert Temporal activities into agent tools using `activity_as_tool`.
This allows your agent to leverage Temporal's durable execution for tool calls.

In the example below, we apply the `@activity.defn` decorator to the `get_weather` function to create a Temporal activity.
We then pass this through the `activity_as_tool` helper function to create an OpenAI Agents tool that is passed to the `Agent`.

```python
from dataclasses import dataclass
from datetime import timedelta
from temporalio import activity, workflow
from temporalio.contrib import openai_agents
from agents import Agent, Runner

@dataclass
class Weather:
    city: str
    temperature_range: str
    conditions: str

@activity.defn
async def get_weather(city: str) -> Weather:
    """Get the weather for a given city."""
    return Weather(city=city, temperature_range="14-20C", conditions="Sunny with wind.")

@workflow.defn
class WeatherAgent:
    @workflow.run
    async def run(self, question: str) -> str:
        agent = Agent(
            name="Weather Assistant",
            instructions="You are a helpful weather agent.",
            tools=[
                openai_agents.workflow.activity_as_tool(
                    get_weather, 
                    start_to_close_timeout=timedelta(seconds=10)
                )
            ],
        )
        result = await Runner.run(starting_agent=agent, input=question)
        return result.final_output
```

### Calling OpenAI Agents Tools inside Temporal Workflows

For simple computations that don't involve external calls you can call the tool directly from the workflow by using the standard OpenAI Agents SDK `@functiontool` annotation.

```python
from temporalio import workflow
from agents import Agent, Runner
from agents import function_tool

@function_tool
def calculate_circle_area(radius: float) -> float:
    """Calculate the area of a circle given its radius."""
    import math
    return math.pi * radius ** 2

@workflow.defn
class MathAssistantAgent:
    @workflow.run
    async def run(self, message: str) -> str:
        agent = Agent(
            name="Math Assistant",
            instructions="You are a helpful math assistant. Use the available tools to help with calculations.",
            tools=[calculate_circle_area],
        )
        result = await Runner.run(agent, input=message)
        return result.final_output
```

Note that any tools that run in the workflow must respect the workflow execution restrictions, meaning no I/O or non-deterministic operations.
Of course, code running in the workflow can invoke a Temporal activity at any time.

Tools that run in the workflow can also update OpenAI Agents context, which is read-only for tools run as Temporal activities.


## Feature Support

This integration is presently subject to certain limitations.
Streaming and voice agents are not supported.
Certain tools are not suitable for a distributed computing environment, so these have been disabled as well.

### Model Providers

| Model Provider | Supported |
|:--------------|:---------:|
| OpenAI        |    Yes    |
| LiteLLM       |    Yes    |

### Model Response format

This integration does not presently support streaming.

| Model Response | Supported |
|:--------------|:---------:|
| Get Response  |    Yes    |
| Streaming     |    No     |

### Tools

#### Tool Type

`LocalShellTool` and `ComputerTool` are not suited to a distributed computing setting.

| Tool Type           | Supported |
|:-------------------|:---------:|
| FunctionTool        |    Yes    |
| LocalShellTool      |    No     |
| WebSearchTool       |    Yes    |
| FileSearchTool      |    Yes    |
| HostedMCPTool       |    Yes    |
| ImageGenerationTool |    Yes    |
| CodeInterpreterTool |    Yes    |
| ComputerTool        |    No     |

#### Tool Context

As described in [Tool Calling](#tool-calling), context propagation is read-only when Temporal activities are used as tools.

| Context Propagation                     | Supported |
|:----------------------------------------|:---------:|
| Activity Tool receives copy of context  |    Yes    |
| Activity Tool can update context        |    No     |
| Function Tool received context          |    Yes    |
| Function Tool can update context        |    Yes    |

### MCP

Presently, MCP is supported only via `HostedMCPTool`, which uses the OpenAI Responses API and cloud MCP client behind it.
The OpenAI Agents SDK also supports MCP clients that run in application code, but this integration does not.

| MCP Class              | Supported |
|:-----------------------|:---------:|
| MCPServerStdio         |    No     |
| MCPServerSse           |    No     |
| MCPServerStreamableHttp|    No     |

### Guardrails

| Guardrail Type | Supported |
|:---------------|:---------:|
| Code           |    Yes    |
| Agent          |    Yes    |

### Sessions

SQLite storage is not suited to a distributed environment.

| Feature        | Supported |
|:---------------|:---------:|
| SQLiteSession  |    No     |

### Tracing

| Tracing Provider | Supported |
|:-----------------|:---------:|
| OpenAI platform  |    Yes    |

### Voice 

| Mode                    | Supported |
|:------------------------|:---------:|
| Voice agents (pipelines)|    No     |
| Realtime agents         |    No     |

### Utilities

The REPL utility is not suitable for a distributed setting.

| Utility | Supported |
|:--------|:---------:|
| REPL    |    No     |


## Additional Examples

You can find additional examples in the [Temporal Python Samples Repository](https://github.com/temporalio/samples-python/tree/main/openai_agents).




================================================
FILE: temporalio/contrib/openai_agents/__init__.py
================================================
"""Support for using the OpenAI Agents SDK as part of Temporal workflows.

This module provides compatibility between the
`OpenAI Agents SDK <https://github.com/openai/openai-agents-python>`_ and Temporal workflows.

.. warning::
    This module is experimental and may change in future versions.
    Use with caution in production environments.
"""

from temporalio.contrib.openai_agents._model_parameters import ModelActivityParameters
from temporalio.contrib.openai_agents._temporal_openai_agents import (
    OpenAIAgentsPlugin,
    TestModel,
    TestModelProvider,
)
from temporalio.contrib.openai_agents._trace_interceptor import (
    OpenAIAgentsTracingInterceptor,
)

from . import workflow

__all__ = [
    "OpenAIAgentsPlugin",
    "ModelActivityParameters",
    "workflow",
    "TestModel",
    "TestModelProvider",
]



================================================
FILE: temporalio/contrib/openai_agents/_heartbeat_decorator.py
================================================
import asyncio
from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar, cast

from temporalio import activity

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def _auto_heartbeater(fn: F) -> F:
    # Propagate type hints from the original callable.
    @wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        heartbeat_timeout = activity.info().heartbeat_timeout
        heartbeat_task = None
        if heartbeat_timeout:
            # Heartbeat twice as often as the timeout
            heartbeat_task = asyncio.create_task(
                heartbeat_every(heartbeat_timeout.total_seconds() / 2)
            )
        try:
            return await fn(*args, **kwargs)
        finally:
            if heartbeat_task:
                heartbeat_task.cancel()
                # Wait for heartbeat cancellation to complete
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

    return cast(F, wrapper)


async def heartbeat_every(delay: float, *details: Any) -> None:
    """Heartbeat every so often while not cancelled"""
    while True:
        await asyncio.sleep(delay)
        activity.heartbeat(*details)



================================================
FILE: temporalio/contrib/openai_agents/_invoke_model_activity.py
================================================
"""A temporal activity that invokes a LLM model.

Implements mapping of OpenAI datastructures to Pydantic friendly types.
"""

import enum
import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Optional, Union

from agents import (
    AgentOutputSchemaBase,
    CodeInterpreterTool,
    FileSearchTool,
    FunctionTool,
    Handoff,
    HostedMCPTool,
    ImageGenerationTool,
    ModelProvider,
    ModelResponse,
    ModelSettings,
    ModelTracing,
    OpenAIProvider,
    RunContextWrapper,
    Tool,
    TResponseInputItem,
    UserError,
    WebSearchTool,
)
from openai import (
    APIStatusError,
    AsyncOpenAI,
)
from openai.types.responses.tool_param import Mcp
from pydantic_core import to_json
from typing_extensions import Required, TypedDict

from temporalio import activity
from temporalio.contrib.openai_agents._heartbeat_decorator import _auto_heartbeater
from temporalio.exceptions import ApplicationError


@dataclass
class HandoffInput:
    """Data conversion friendly representation of a Handoff. Contains only the fields which are needed by the model
    execution to determine what to handoff to, not the actual handoff invocation, which remains in the workflow context.
    """

    tool_name: str
    tool_description: str
    input_json_schema: dict[str, Any]
    agent_name: str
    strict_json_schema: bool = True


@dataclass
class FunctionToolInput:
    """Data conversion friendly representation of a FunctionTool. Contains only the fields which are needed by the model
    execution to determine what tool to call, not the actual tool invocation, which remains in the workflow context.
    """

    name: str
    description: str
    params_json_schema: dict[str, Any]
    strict_json_schema: bool = True


@dataclass
class HostedMCPToolInput:
    """Data conversion friendly representation of a HostedMCPTool. Contains only the fields which are needed by the model
    execution to determine what tool to call, not the actual tool invocation, which remains in the workflow context.
    """

    tool_config: Mcp


ToolInput = Union[
    FunctionToolInput,
    FileSearchTool,
    WebSearchTool,
    ImageGenerationTool,
    CodeInterpreterTool,
    HostedMCPToolInput,
]


@dataclass
class AgentOutputSchemaInput(AgentOutputSchemaBase):
    """Data conversion friendly representation of AgentOutputSchema."""

    output_type_name: Optional[str]
    is_wrapped: bool
    output_schema: Optional[dict[str, Any]]
    strict_json_schema: bool

    def is_plain_text(self) -> bool:
        """Whether the output type is plain text (versus a JSON object)."""
        return self.output_type_name is None or self.output_type_name == "str"

    def is_strict_json_schema(self) -> bool:
        """Whether the JSON schema is in strict mode."""
        return self.strict_json_schema

    def json_schema(self) -> dict[str, Any]:
        """The JSON schema of the output type."""
        if self.is_plain_text():
            raise UserError("Output type is plain text, so no JSON schema is available")
        if self.output_schema is None:
            raise UserError("Output schema is not defined")
        return self.output_schema

    def validate_json(self, json_str: str) -> Any:
        """Validate the JSON string against the schema."""
        raise NotImplementedError()

    def name(self) -> str:
        """Get the name of the output type."""
        if self.output_type_name is None:
            raise ValueError("output_type_name is None")
        return self.output_type_name


class ModelTracingInput(enum.IntEnum):
    """Conversion friendly representation of ModelTracing.

    Needed as ModelTracing is enum.Enum instead of IntEnum
    """

    DISABLED = 0
    ENABLED = 1
    ENABLED_WITHOUT_DATA = 2


class ActivityModelInput(TypedDict, total=False):
    """Input for the invoke_model_activity activity."""

    model_name: Optional[str]
    system_instructions: Optional[str]
    input: Required[Union[str, list[TResponseInputItem]]]
    model_settings: Required[ModelSettings]
    tools: list[ToolInput]
    output_schema: Optional[AgentOutputSchemaInput]
    handoffs: list[HandoffInput]
    tracing: Required[ModelTracingInput]
    previous_response_id: Optional[str]
    prompt: Optional[Any]


class ModelActivity:
    """Class wrapper for model invocation activities to allow model customization. By default, we use an OpenAIProvider with retries disabled.
    Disabling retries in your model of choice is recommended to allow activity retries to define the retry model.
    """

    def __init__(self, model_provider: Optional[ModelProvider] = None):
        """Initialize the activity with a model provider."""
        self._model_provider = model_provider or OpenAIProvider(
            openai_client=AsyncOpenAI(max_retries=0)
        )

    @activity.defn
    @_auto_heartbeater
    async def invoke_model_activity(self, input: ActivityModelInput) -> ModelResponse:
        """Activity that invokes a model with the given input."""
        model = self._model_provider.get_model(input.get("model_name"))

        async def empty_on_invoke_tool(ctx: RunContextWrapper[Any], input: str) -> str:
            return ""

        async def empty_on_invoke_handoff(
            ctx: RunContextWrapper[Any], input: str
        ) -> Any:
            return None

        # workaround for https://github.com/pydantic/pydantic/issues/9541
        # ValidatorIterator returned
        input_json = to_json(input["input"])
        input_input = json.loads(input_json)

        def make_tool(tool: ToolInput) -> Tool:
            if isinstance(
                tool,
                (
                    FileSearchTool,
                    WebSearchTool,
                    ImageGenerationTool,
                    CodeInterpreterTool,
                ),
            ):
                return tool
            elif isinstance(tool, HostedMCPToolInput):
                return HostedMCPTool(
                    tool_config=tool.tool_config,
                )
            elif isinstance(tool, FunctionToolInput):
                return FunctionTool(
                    name=tool.name,
                    description=tool.description,
                    params_json_schema=tool.params_json_schema,
                    on_invoke_tool=empty_on_invoke_tool,
                    strict_json_schema=tool.strict_json_schema,
                )
            else:
                raise UserError(f"Unknown tool type: {tool.name}")

        tools = [make_tool(x) for x in input.get("tools", [])]
        handoffs: list[Handoff[Any, Any]] = [
            Handoff(
                tool_name=x.tool_name,
                tool_description=x.tool_description,
                input_json_schema=x.input_json_schema,
                agent_name=x.agent_name,
                strict_json_schema=x.strict_json_schema,
                on_invoke_handoff=empty_on_invoke_handoff,
            )
            for x in input.get("handoffs", [])
        ]

        try:
            return await model.get_response(
                system_instructions=input.get("system_instructions"),
                input=input_input,
                model_settings=input["model_settings"],
                tools=tools,
                output_schema=input.get("output_schema"),
                handoffs=handoffs,
                tracing=ModelTracing(input["tracing"]),
                previous_response_id=input.get("previous_response_id"),
                prompt=input.get("prompt"),
            )
        except APIStatusError as e:
            # Listen to server hints
            retry_after = None
            retry_after_ms_header = e.response.headers.get("retry-after-ms")
            if retry_after_ms_header is not None:
                retry_after = timedelta(milliseconds=float(retry_after_ms_header))

            if retry_after is None:
                retry_after_header = e.response.headers.get("retry-after")
                if retry_after_header is not None:
                    retry_after = timedelta(seconds=float(retry_after_header))

            should_retry_header = e.response.headers.get("x-should-retry")
            if should_retry_header == "true":
                raise e
            if should_retry_header == "false":
                raise ApplicationError(
                    "Non retryable OpenAI error",
                    non_retryable=True,
                    next_retry_delay=retry_after,
                ) from e

            # Specifically retryable status codes
            if e.response.status_code in [408, 409, 429, 500]:
                raise ApplicationError(
                    "Retryable OpenAI status code",
                    non_retryable=False,
                    next_retry_delay=retry_after,
                ) from e

            raise ApplicationError(
                "Non retryable OpenAI status code",
                non_retryable=True,
                next_retry_delay=retry_after,
            ) from e



================================================
FILE: temporalio/contrib/openai_agents/_model_parameters.py
================================================
"""Parameters for configuring Temporal activity execution for model calls."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from temporalio.common import Priority, RetryPolicy
from temporalio.workflow import ActivityCancellationType, VersioningIntent


@dataclass
class ModelActivityParameters:
    """Parameters for configuring Temporal activity execution for model calls.

    This class encapsulates all the parameters that can be used to configure
    how Temporal activities are executed when making model calls through the
    OpenAI Agents integration.
    """

    task_queue: Optional[str] = None
    """Specific task queue to use for model activities."""

    schedule_to_close_timeout: Optional[timedelta] = None
    """Maximum time from scheduling to completion."""

    schedule_to_start_timeout: Optional[timedelta] = None
    """Maximum time from scheduling to starting."""

    start_to_close_timeout: Optional[timedelta] = timedelta(seconds=60)
    """Maximum time for the activity to complete."""

    heartbeat_timeout: Optional[timedelta] = None
    """Maximum time between heartbeats."""

    retry_policy: Optional[RetryPolicy] = None
    """Policy for retrying failed activities."""

    cancellation_type: ActivityCancellationType = ActivityCancellationType.TRY_CANCEL
    """How the activity handles cancellation."""

    versioning_intent: Optional[VersioningIntent] = None
    """Versioning intent for the activity."""

    summary_override: Optional[str] = None
    """Summary for the activity execution."""

    priority: Priority = Priority.default
    """Priority for the activity execution."""



================================================
FILE: temporalio/contrib/openai_agents/_openai_runner.py
================================================
import json
import typing
from dataclasses import replace
from typing import Any, Union

from agents import (
    Agent,
    RunConfig,
    RunResult,
    RunResultStreaming,
    SQLiteSession,
    TContext,
    Tool,
    TResponseInputItem,
)
from agents.run import DEFAULT_AGENT_RUNNER, DEFAULT_MAX_TURNS, AgentRunner
from pydantic_core import to_json

from temporalio import workflow
from temporalio.contrib.openai_agents._model_parameters import ModelActivityParameters
from temporalio.contrib.openai_agents._temporal_model_stub import _TemporalModelStub


class TemporalOpenAIRunner(AgentRunner):
    """Temporal Runner for OpenAI agents.

    Forwards model calls to a Temporal activity.

    """

    def __init__(self, model_params: ModelActivityParameters) -> None:
        """Initialize the Temporal OpenAI Runner."""
        self._runner = DEFAULT_AGENT_RUNNER or AgentRunner()
        self.model_params = model_params

    async def run(
        self,
        starting_agent: Agent[TContext],
        input: Union[str, list[TResponseInputItem]],
        **kwargs: Any,
    ) -> RunResult:
        """Run the agent in a Temporal workflow."""
        if not workflow.in_workflow():
            return await self._runner.run(
                starting_agent,
                input,
                **kwargs,
            )

        tool_types = typing.get_args(Tool)
        for t in starting_agent.tools:
            if not isinstance(t, tool_types):
                raise ValueError(
                    "Provided tool is not a tool type. If using an activity, make sure to wrap it with openai_agents.workflow.activity_as_tool."
                )

        if starting_agent.mcp_servers:
            raise ValueError(
                "Temporal OpenAI agent does not support on demand MCP servers."
            )

        # workaround for https://github.com/pydantic/pydantic/issues/9541
        # ValidatorIterator returned
        input_json = to_json(input)
        input = json.loads(input_json)

        context = kwargs.get("context")
        max_turns = kwargs.get("max_turns", DEFAULT_MAX_TURNS)
        hooks = kwargs.get("hooks")
        run_config = kwargs.get("run_config")
        previous_response_id = kwargs.get("previous_response_id")
        session = kwargs.get("session")

        if isinstance(session, SQLiteSession):
            raise ValueError("Temporal workflows don't support SQLite sessions.")

        if run_config is None:
            run_config = RunConfig()

        model_name = run_config.model or starting_agent.model
        if model_name is not None and not isinstance(model_name, str):
            raise ValueError(
                "Temporal workflows require a model name to be a string in the run config and/or agent."
            )
        updated_run_config = replace(
            run_config,
            model=_TemporalModelStub(
                model_name=model_name,
                model_params=self.model_params,
            ),
        )

        return await self._runner.run(
            starting_agent=starting_agent,
            input=input,
            context=context,
            max_turns=max_turns,
            hooks=hooks,
            run_config=updated_run_config,
            previous_response_id=previous_response_id,
            session=session,
        )

    def run_sync(
        self,
        starting_agent: Agent[TContext],
        input: Union[str, list[TResponseInputItem]],
        **kwargs: Any,
    ) -> RunResult:
        """Run the agent synchronously (not supported in Temporal workflows)."""
        if not workflow.in_workflow():
            return self._runner.run_sync(
                starting_agent,
                input,
                **kwargs,
            )
        raise RuntimeError("Temporal workflows do not support synchronous model calls.")

    def run_streamed(
        self,
        starting_agent: Agent[TContext],
        input: Union[str, list[TResponseInputItem]],
        **kwargs: Any,
    ) -> RunResultStreaming:
        """Run the agent with streaming responses (not supported in Temporal workflows)."""
        if not workflow.in_workflow():
            return self._runner.run_streamed(
                starting_agent,
                input,
                **kwargs,
            )
        raise RuntimeError("Temporal workflows do not support streaming.")



================================================
FILE: temporalio/contrib/openai_agents/_temporal_model_stub.py
================================================
from __future__ import annotations

import logging
from typing import Optional

from temporalio import workflow
from temporalio.contrib.openai_agents._model_parameters import ModelActivityParameters

logger = logging.getLogger(__name__)

from typing import Any, AsyncIterator, Union, cast

from agents import (
    AgentOutputSchema,
    AgentOutputSchemaBase,
    CodeInterpreterTool,
    FileSearchTool,
    FunctionTool,
    Handoff,
    HostedMCPTool,
    ImageGenerationTool,
    Model,
    ModelResponse,
    ModelSettings,
    ModelTracing,
    Tool,
    TResponseInputItem,
    WebSearchTool,
)
from agents.items import TResponseStreamEvent
from openai.types.responses.response_prompt_param import ResponsePromptParam

from temporalio.contrib.openai_agents._invoke_model_activity import (
    ActivityModelInput,
    AgentOutputSchemaInput,
    FunctionToolInput,
    HandoffInput,
    HostedMCPToolInput,
    ModelActivity,
    ModelTracingInput,
    ToolInput,
)


class _TemporalModelStub(Model):
    """A stub that allows invoking models as Temporal activities."""

    def __init__(
        self,
        model_name: Optional[str],
        *,
        model_params: ModelActivityParameters,
    ) -> None:
        self.model_name = model_name
        self.model_params = model_params

    async def get_response(
        self,
        system_instructions: Optional[str],
        input: Union[str, list[TResponseInputItem]],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: Optional[AgentOutputSchemaBase],
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: Optional[str],
        prompt: Optional[ResponsePromptParam],
    ) -> ModelResponse:
        def make_tool_info(tool: Tool) -> ToolInput:
            if isinstance(
                tool,
                (
                    FileSearchTool,
                    WebSearchTool,
                    ImageGenerationTool,
                    CodeInterpreterTool,
                ),
            ):
                return tool
            elif isinstance(tool, HostedMCPTool):
                return HostedMCPToolInput(tool_config=tool.tool_config)
            elif isinstance(tool, FunctionTool):
                return FunctionToolInput(
                    name=tool.name,
                    description=tool.description,
                    params_json_schema=tool.params_json_schema,
                    strict_json_schema=tool.strict_json_schema,
                )
            else:
                raise ValueError(f"Unsupported tool type: {tool.name}")

        tool_infos = [make_tool_info(x) for x in tools]
        handoff_infos = [
            HandoffInput(
                tool_name=x.tool_name,
                tool_description=x.tool_description,
                input_json_schema=x.input_json_schema,
                agent_name=x.agent_name,
                strict_json_schema=x.strict_json_schema,
            )
            for x in handoffs
        ]
        if output_schema is not None and not isinstance(
            output_schema, AgentOutputSchema
        ):
            raise TypeError(
                f"Only AgentOutputSchema is supported by Temporal Model, got {type(output_schema).__name__}"
            )
        agent_output_schema = output_schema
        output_schema_input = (
            None
            if agent_output_schema is None
            else AgentOutputSchemaInput(
                output_type_name=agent_output_schema.name(),
                is_wrapped=agent_output_schema._is_wrapped,
                output_schema=agent_output_schema.json_schema()
                if not agent_output_schema.is_plain_text()
                else None,
                strict_json_schema=agent_output_schema.is_strict_json_schema(),
            )
        )

        activity_input = ActivityModelInput(
            model_name=self.model_name,
            system_instructions=system_instructions,
            input=cast(Union[str, list[TResponseInputItem]], input),
            model_settings=model_settings,
            tools=tool_infos,
            output_schema=output_schema_input,
            handoffs=handoff_infos,
            tracing=ModelTracingInput(tracing.value),
            previous_response_id=previous_response_id,
            prompt=prompt,
        )

        return await workflow.execute_activity_method(
            ModelActivity.invoke_model_activity,
            activity_input,
            summary=self.model_params.summary_override or _extract_summary(input),
            task_queue=self.model_params.task_queue,
            schedule_to_close_timeout=self.model_params.schedule_to_close_timeout,
            schedule_to_start_timeout=self.model_params.schedule_to_start_timeout,
            start_to_close_timeout=self.model_params.start_to_close_timeout,
            heartbeat_timeout=self.model_params.heartbeat_timeout,
            retry_policy=self.model_params.retry_policy,
            cancellation_type=self.model_params.cancellation_type,
            versioning_intent=self.model_params.versioning_intent,
            priority=self.model_params.priority,
        )

    def stream_response(
        self,
        system_instructions: Optional[str],
        input: Union[str, list[TResponseInputItem]],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: Optional[AgentOutputSchemaBase],
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: Optional[str],
        prompt: ResponsePromptParam | None,
    ) -> AsyncIterator[TResponseStreamEvent]:
        raise NotImplementedError("Temporal model doesn't support streams yet")


def _extract_summary(input: Union[str, list[TResponseInputItem]]) -> str:
    ### Activity summary shown in the UI
    try:
        max_size = 100
        if isinstance(input, str):
            return input[:max_size]
        elif isinstance(input, list):
            # Find all message inputs, which are reasonably summarizable
            messages: list[TResponseInputItem] = [
                item for item in input if item.get("type", "message") == "message"
            ]
            if not messages:
                return ""

            content: Any = messages[-1].get("content", "")

            # In the case of multiple contents, take the last one
            if isinstance(content, list):
                if not content:
                    return ""
                content = content[-1]

            # Take the text field from the content if present
            if isinstance(content, dict) and content.get("text") is not None:
                content = content.get("text")
            return str(content)[:max_size]
    except Exception as e:
        logger.error(f"Error getting summary: {e}")
    return ""



================================================
FILE: temporalio/contrib/openai_agents/_temporal_openai_agents.py
================================================
"""Initialize Temporal OpenAI Agents overrides."""

from contextlib import asynccontextmanager, contextmanager
from datetime import timedelta
from typing import AsyncIterator, Callable, Optional, Union

from agents import (
    AgentOutputSchemaBase,
    Handoff,
    Model,
    ModelProvider,
    ModelResponse,
    ModelSettings,
    ModelTracing,
    Tool,
    TResponseInputItem,
    set_trace_provider,
)
from agents.items import TResponseStreamEvent
from agents.run import get_default_agent_runner, set_default_agent_runner
from agents.tracing import get_trace_provider
from agents.tracing.provider import DefaultTraceProvider
from openai.types.responses import ResponsePromptParam

import temporalio.client
import temporalio.worker
from temporalio.client import ClientConfig, Plugin
from temporalio.contrib.openai_agents._invoke_model_activity import ModelActivity
from temporalio.contrib.openai_agents._model_parameters import ModelActivityParameters
from temporalio.contrib.openai_agents._openai_runner import TemporalOpenAIRunner
from temporalio.contrib.openai_agents._temporal_trace_provider import (
    TemporalTraceProvider,
)
from temporalio.contrib.openai_agents._trace_interceptor import (
    OpenAIAgentsTracingInterceptor,
)
from temporalio.contrib.pydantic import (
    PydanticPayloadConverter,
    ToJsonOptions,
)
from temporalio.converter import (
    DataConverter,
)
from temporalio.worker import (
    Replayer,
    ReplayerConfig,
    Worker,
    WorkerConfig,
    WorkflowReplayResult,
)


@contextmanager
def set_open_ai_agent_temporal_overrides(
    model_params: ModelActivityParameters,
    auto_close_tracing_in_workflows: bool = False,
):
    """Configure Temporal-specific overrides for OpenAI agents.

    .. warning::
        This API is experimental and may change in future versions.
        Use with caution in production environments. Future versions may wrap the worker directly
        instead of requiring this context manager.

    This context manager sets up the necessary Temporal-specific runners and trace providers
    for running OpenAI agents within Temporal workflows. It should be called in the main
    entry point of your application before initializing the Temporal client and worker.

    The context manager handles:
    1. Setting up a Temporal-specific runner for OpenAI agents
    2. Configuring a Temporal-aware trace provider
    3. Restoring previous settings when the context exits

    Args:
        model_params: Configuration parameters for Temporal activity execution of model calls.
        auto_close_tracing_in_workflows: If set to true, close tracing spans immediately.

    Returns:
        A context manager that yields the configured TemporalTraceProvider.
    """
    previous_runner = get_default_agent_runner()
    previous_trace_provider = get_trace_provider()
    provider = TemporalTraceProvider(
        auto_close_in_workflows=auto_close_tracing_in_workflows
    )

    try:
        set_default_agent_runner(TemporalOpenAIRunner(model_params))
        set_trace_provider(provider)
        yield provider
    finally:
        set_default_agent_runner(previous_runner)
        set_trace_provider(previous_trace_provider or DefaultTraceProvider())


class TestModelProvider(ModelProvider):
    """Test model provider which simply returns the given module."""

    def __init__(self, model: Model):
        """Initialize a test model provider with a model."""
        self._model = model

    def get_model(self, model_name: Union[str, None]) -> Model:
        """Get a model from the model provider."""
        return self._model


class TestModel(Model):
    """Test model for use mocking model responses."""

    def __init__(self, fn: Callable[[], ModelResponse]) -> None:
        """Initialize a test model with a callable."""
        self.fn = fn

    async def get_response(
        self,
        system_instructions: Union[str, None],
        input: Union[str, list[TResponseInputItem]],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: Union[AgentOutputSchemaBase, None],
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: Union[str, None],
        prompt: Union[ResponsePromptParam, None] = None,
    ) -> ModelResponse:
        """Get a response from the model."""
        return self.fn()

    def stream_response(
        self,
        system_instructions: Optional[str],
        input: Union[str, list[TResponseInputItem]],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: Optional[AgentOutputSchemaBase],
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: Optional[str],
        prompt: Optional[ResponsePromptParam],
    ) -> AsyncIterator[TResponseStreamEvent]:
        """Get a streamed response from the model. Unimplemented."""
        raise NotImplementedError()


class _OpenAIPayloadConverter(PydanticPayloadConverter):
    def __init__(self) -> None:
        super().__init__(ToJsonOptions(exclude_unset=True))


class OpenAIAgentsPlugin(temporalio.client.Plugin, temporalio.worker.Plugin):
    """Temporal plugin for integrating OpenAI agents with Temporal workflows.

    .. warning::
        This class is experimental and may change in future versions.
        Use with caution in production environments.

    This plugin provides seamless integration between the OpenAI Agents SDK and
    Temporal workflows. It automatically configures the necessary interceptors,
    activities, and data converters to enable OpenAI agents to run within
    Temporal workflows with proper tracing and model execution.

    The plugin:
    1. Configures the Pydantic data converter for type-safe serialization
    2. Sets up tracing interceptors for OpenAI agent interactions
    3. Registers model execution activities
    4. Manages the OpenAI agent runtime overrides during worker execution

    Args:
        model_params: Configuration parameters for Temporal activity execution
            of model calls. If None, default parameters will be used.
        model_provider: Optional model provider for custom model implementations.
            Useful for testing or custom model integrations.

    Example:
        >>> from temporalio.client import Client
        >>> from temporalio.worker import Worker
        >>> from temporalio.contrib.openai_agents import OpenAIAgentsPlugin, ModelActivityParameters
        >>> from datetime import timedelta
        >>>
        >>> # Configure model parameters
        >>> model_params = ModelActivityParameters(
        ...     start_to_close_timeout=timedelta(seconds=30),
        ...     retry_policy=RetryPolicy(maximum_attempts=3)
        ... )
        >>>
        >>> # Create plugin
        >>> plugin = OpenAIAgentsPlugin(model_params=model_params)
        >>>
        >>> # Use with client and worker
        >>> client = await Client.connect(
        ...     "localhost:7233",
        ...     plugins=[plugin]
        ... )
        >>> worker = Worker(
        ...     client,
        ...     task_queue="my-task-queue",
        ...     workflows=[MyWorkflow],
        ... )
    """

    def __init__(
        self,
        model_params: Optional[ModelActivityParameters] = None,
        model_provider: Optional[ModelProvider] = None,
    ) -> None:
        """Initialize the OpenAI agents plugin.

        Args:
            model_params: Configuration parameters for Temporal activity execution
                of model calls. If None, default parameters will be used.
            model_provider: Optional model provider for custom model implementations.
                Useful for testing or custom model integrations.
        """
        if model_params is None:
            model_params = ModelActivityParameters()

        # For the default provider, we provide a default start_to_close_timeout of 60 seconds.
        # Other providers will need to define their own.
        if (
            model_params.start_to_close_timeout is None
            and model_params.schedule_to_close_timeout is None
        ):
            if model_provider is None:
                model_params.start_to_close_timeout = timedelta(seconds=60)
            else:
                raise ValueError(
                    "When configuring a custom provider, the model activity must have start_to_close_timeout or schedule_to_close_timeout"
                )

        self._model_params = model_params
        self._model_provider = model_provider

    def init_client_plugin(self, next: temporalio.client.Plugin) -> None:
        """Set the next client plugin"""
        self.next_client_plugin = next

    async def connect_service_client(
        self, config: temporalio.service.ConnectConfig
    ) -> temporalio.service.ServiceClient:
        """No modifications to service client"""
        return await self.next_client_plugin.connect_service_client(config)

    def init_worker_plugin(self, next: temporalio.worker.Plugin) -> None:
        """Set the next worker plugin"""
        self.next_worker_plugin = next

    def configure_client(self, config: ClientConfig) -> ClientConfig:
        """Configure the Temporal client for OpenAI agents integration.

        This method sets up the Pydantic data converter to enable proper
        serialization of OpenAI agent objects and responses.

        Args:
            config: The client configuration to modify.

        Returns:
            The modified client configuration.
        """
        config["data_converter"] = DataConverter(
            payload_converter_class=_OpenAIPayloadConverter
        )
        return self.next_client_plugin.configure_client(config)

    def configure_worker(self, config: WorkerConfig) -> WorkerConfig:
        """Configure the Temporal worker for OpenAI agents integration.

        This method adds the necessary interceptors and activities for OpenAI
        agent execution:
        - Adds tracing interceptors for OpenAI agent interactions
        - Registers model execution activities

        Args:
            config: The worker configuration to modify.

        Returns:
            The modified worker configuration.
        """
        config["interceptors"] = list(config.get("interceptors") or []) + [
            OpenAIAgentsTracingInterceptor()
        ]
        config["activities"] = list(config.get("activities") or []) + [
            ModelActivity(self._model_provider).invoke_model_activity
        ]
        return self.next_worker_plugin.configure_worker(config)

    async def run_worker(self, worker: Worker) -> None:
        """Run the worker with OpenAI agents temporal overrides.

        This method sets up the necessary runtime overrides for OpenAI agents
        to work within the Temporal worker context, including custom runners
        and trace providers.

        Args:
            worker: The worker instance to run.
        """
        with set_open_ai_agent_temporal_overrides(self._model_params):
            await self.next_worker_plugin.run_worker(worker)

    def configure_replayer(self, config: ReplayerConfig) -> ReplayerConfig:
        """Configure the replayer for OpenAI Agents."""
        config["interceptors"] = list(config.get("interceptors") or []) + [
            OpenAIAgentsTracingInterceptor()
        ]
        config["data_converter"] = DataConverter(
            payload_converter_class=_OpenAIPayloadConverter
        )
        return config

    @asynccontextmanager
    async def run_replayer(
        self,
        replayer: Replayer,
        histories: AsyncIterator[temporalio.client.WorkflowHistory],
    ) -> AsyncIterator[AsyncIterator[WorkflowReplayResult]]:
        """Set the OpenAI Overrides during replay"""
        with set_open_ai_agent_temporal_overrides(self._model_params):
            async with self.next_worker_plugin.run_replayer(
                replayer, histories
            ) as results:
                yield results



================================================
FILE: temporalio/contrib/openai_agents/_temporal_trace_provider.py
================================================
"""Provides support for integration with OpenAI Agents SDK tracing across workflows"""

import uuid
from types import TracebackType
from typing import Any, Optional, cast

from agents import SpanData, Trace, TracingProcessor
from agents.tracing import (
    get_trace_provider,
)
from agents.tracing.provider import (
    DefaultTraceProvider,
    SynchronousMultiTracingProcessor,
)
from agents.tracing.spans import Span

from temporalio import workflow
from temporalio.contrib.openai_agents._trace_interceptor import RunIdRandom
from temporalio.workflow import ReadOnlyContextError


class ActivitySpanData(SpanData):
    """Captures fields from ActivityTaskScheduledEventAttributes for tracing."""

    def __init__(
        self,
        activity_id: str,
        activity_type: str,
        task_queue: str,
        schedule_to_close_timeout: Optional[float] = None,
        schedule_to_start_timeout: Optional[float] = None,
        start_to_close_timeout: Optional[float] = None,
        heartbeat_timeout: Optional[float] = None,
    ):
        """Initialize an ActivitySpanData instance."""
        self.activity_id = activity_id
        self.activity_type = activity_type
        self.task_queue = task_queue
        self.schedule_to_close_timeout = schedule_to_close_timeout
        self.schedule_to_start_timeout = schedule_to_start_timeout
        self.start_to_close_timeout = start_to_close_timeout
        self.heartbeat_timeout = heartbeat_timeout

    @property
    def type(self) -> str:
        """Return the type of this span data."""
        return "temporal-activity"

    def export(self) -> dict[str, Any]:
        """Export the span data as a dictionary."""
        return {
            "type": self.type,
            "activity_id": self.activity_id,
            "activity_type": self.activity_type,
            "task_queue": self.task_queue,
            "schedule_to_close_timeout": self.schedule_to_close_timeout,
            "schedule_to_start_timeout": self.schedule_to_start_timeout,
            "start_to_close_timeout": self.start_to_close_timeout,
            "heartbeat_timeout": self.heartbeat_timeout,
        }


def activity_span(
    activity_id: str,
    activity_type: str,
    task_queue: str,
    start_to_close_timeout: float,
) -> Span[ActivitySpanData]:
    """Create a trace span for a Temporal activity."""
    return get_trace_provider().create_span(
        span_data=ActivitySpanData(
            activity_id=activity_id,
            activity_type=activity_type,
            task_queue=task_queue,
            start_to_close_timeout=start_to_close_timeout,
        ),
    )


class _TemporalTracingProcessor(SynchronousMultiTracingProcessor):
    def __init__(
        self, impl: SynchronousMultiTracingProcessor, auto_close_in_workflows: bool
    ):
        super().__init__()
        self._impl = impl
        self._auto_close_in_workflows = auto_close_in_workflows

    def add_tracing_processor(self, tracing_processor: TracingProcessor):
        self._impl.add_tracing_processor(tracing_processor)

    def set_processors(self, processors: list[TracingProcessor]):
        self._impl.set_processors(processors)

    def on_trace_start(self, trace: Trace) -> None:
        if workflow.in_workflow() and workflow.unsafe.is_replaying():
            # In replay mode, don't report
            return

        self._impl.on_trace_start(trace)
        if self._auto_close_in_workflows and workflow.in_workflow():
            self._impl.on_trace_end(trace)

    def on_trace_end(self, trace: Trace) -> None:
        if workflow.in_workflow() and workflow.unsafe.is_replaying():
            # In replay mode, don't report
            return
        if self._auto_close_in_workflows and workflow.in_workflow():
            return

        self._impl.on_trace_end(trace)

    def on_span_start(self, span: Span[Any]) -> None:
        if workflow.in_workflow() and workflow.unsafe.is_replaying():
            # In replay mode, don't report
            return

        self._impl.on_span_start(span)
        if self._auto_close_in_workflows and workflow.in_workflow():
            self._impl.on_span_end(span)

    def on_span_end(self, span: Span[Any]) -> None:
        if workflow.in_workflow() and workflow.unsafe.is_replaying():
            # In replay mode, don't report
            return
        if self._auto_close_in_workflows and workflow.in_workflow():
            return

        self._impl.on_span_end(span)

    def shutdown(self) -> None:
        self._impl.shutdown()

    def force_flush(self) -> None:
        self._impl.force_flush()


def _workflow_uuid() -> str:
    random = cast(
        RunIdRandom, getattr(workflow.instance(), "__temporal_openai_tracing_random")
    )
    return random.uuid4()


class TemporalTraceProvider(DefaultTraceProvider):
    """A trace provider that integrates with Temporal workflows."""

    def __init__(self, auto_close_in_workflows: bool = False):
        """Initialize the TemporalTraceProvider."""
        super().__init__()
        self._original_provider = cast(DefaultTraceProvider, get_trace_provider())
        self._multi_processor = _TemporalTracingProcessor(
            self._original_provider._multi_processor,
            auto_close_in_workflows,
        )

    def time_iso(self) -> str:
        """Return the current deterministic time in ISO 8601 format."""
        if workflow.in_workflow():
            return workflow.now().isoformat()
        return super().time_iso()

    def gen_trace_id(self) -> str:
        """Generate a new trace ID."""
        if workflow.in_workflow():
            try:
                """Generate a new trace ID."""
                return f"trace_{_workflow_uuid()}"
            except ReadOnlyContextError:
                return f"trace_{uuid.uuid4().hex}"
        return super().gen_trace_id()

    def gen_span_id(self) -> str:
        """Generate a span ID."""
        if workflow.in_workflow():
            try:
                """Generate a deterministic span ID."""
                return f"span_{_workflow_uuid()}"
            except ReadOnlyContextError:
                return f"span_{uuid.uuid4().hex[:24]}"
        return super().gen_span_id()

    def gen_group_id(self) -> str:
        """Generate a group ID."""
        if workflow.in_workflow():
            try:
                """Generate a deterministic group ID."""
                return f"group_{_workflow_uuid()}"
            except ReadOnlyContextError:
                return f"group_{uuid.uuid4().hex[:24]}"
        return super().gen_group_id()

    def __enter__(self):
        """Enter the context of the Temporal trace provider."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException],
        exc_val: BaseException,
        exc_tb: TracebackType,
    ):
        """Exit the context of the Temporal trace provider."""
        self._multi_processor.shutdown()



================================================
FILE: temporalio/contrib/openai_agents/_trace_interceptor.py
================================================
"""Adds OpenAI Agents traces and spans to Temporal workflows and activities."""

from __future__ import annotations

import random
import uuid
from contextlib import contextmanager
from typing import Any, Mapping, Protocol, Type

from agents import CustomSpanData, custom_span, get_current_span, trace
from agents.tracing import (
    get_trace_provider,
)
from agents.tracing.scope import Scope
from agents.tracing.spans import NoOpSpan

import temporalio.activity
import temporalio.api.common.v1
import temporalio.client
import temporalio.converter
import temporalio.worker
import temporalio.workflow
from temporalio import activity, workflow

HEADER_KEY = "__openai_span"


class _InputWithHeaders(Protocol):
    headers: Mapping[str, temporalio.api.common.v1.Payload]


def set_header_from_context(
    input: _InputWithHeaders, payload_converter: temporalio.converter.PayloadConverter
) -> None:
    """Inserts the OpenAI Agents trace/span data in the input header."""
    current = get_current_span()
    if current is None or isinstance(current, NoOpSpan):
        return

    trace = get_trace_provider().get_current_trace()
    input.headers = {
        **input.headers,
        HEADER_KEY: payload_converter.to_payload(
            {
                "traceName": trace.name if trace else "Unknown Workflow",
                "spanId": current.span_id,
                "traceId": current.trace_id,
            }
        ),
    }


@contextmanager
def context_from_header(
    span_name: str,
    input: _InputWithHeaders,
    payload_converter: temporalio.converter.PayloadConverter,
):
    """Extracts and initializes trace information the input header."""
    payload = input.headers.get(HEADER_KEY)
    span_info = payload_converter.from_payload(payload) if payload else None
    if span_info is None:
        yield
    else:
        workflow_type = (
            activity.info().workflow_type
            if activity.in_activity()
            else workflow.info().workflow_type
        )
        data = (
            {
                "activityId": activity.info().activity_id,
                "activity": activity.info().activity_type,
            }
            if activity.in_activity()
            else None
        )
        current_trace = get_trace_provider().get_current_trace()
        if current_trace is None:
            metadata = {
                "temporal:workflowId": activity.info().workflow_id
                if activity.in_activity()
                else workflow.info().workflow_id,
                "temporal:runId": activity.info().workflow_run_id
                if activity.in_activity()
                else workflow.info().run_id,
                "temporal:workflowType": workflow_type,
            }
            current_trace = trace(
                span_info["traceName"],
                trace_id=span_info["traceId"],
                metadata=metadata,
            )
            Scope.set_current_trace(current_trace)
        current_span = get_trace_provider().get_current_span()
        if current_span is None:
            current_span = get_trace_provider().create_span(
                span_data=CustomSpanData(name="", data={}), span_id=span_info["spanId"]
            )
            Scope.set_current_span(current_span)

        with custom_span(name=span_name, parent=current_span, data=data):
            yield


class OpenAIAgentsTracingInterceptor(
    temporalio.client.Interceptor, temporalio.worker.Interceptor
):
    """Interceptor that propagates OpenAI agent tracing context through Temporal workflows and activities.

    .. warning::
        This API is experimental and may change in future versions.
        Use with caution in production environments.

    This interceptor enables tracing of OpenAI agent operations across Temporal workflows
    and activities. It propagates trace context through workflow and activity boundaries,
    allowing for end-to-end tracing of agent operations.

    The interceptor handles:
    1. Propagating trace context from client to workflow
    2. Propagating trace context from workflow to activities
    3. Maintaining trace context across workflow and activity boundaries

    Example usage:
        interceptor = OpenAIAgentsTracingInterceptor()
        client = await Client.connect("localhost:7233", interceptors=[interceptor])
        worker = Worker(client, task_queue="my-task-queue", interceptors=[interceptor])
    """

    def __init__(
        self,
        payload_converter: temporalio.converter.PayloadConverter = temporalio.converter.default().payload_converter,
    ) -> None:
        """Initialize the interceptor with a payload converter.

        Args:
            payload_converter: The payload converter to use for serializing/deserializing
                trace context. Defaults to the default Temporal payload converter.
        """
        self._payload_converter = payload_converter

    def intercept_client(
        self, next: temporalio.client.OutboundInterceptor
    ) -> temporalio.client.OutboundInterceptor:
        """Intercepts client calls to propagate trace context.

        Args:
            next: The next interceptor in the chain.

        Returns:
            An interceptor that propagates trace context for client operations.
        """
        return _ContextPropagationClientOutboundInterceptor(
            next, self._payload_converter
        )

    def intercept_activity(
        self, next: temporalio.worker.ActivityInboundInterceptor
    ) -> temporalio.worker.ActivityInboundInterceptor:
        """Intercepts activity calls to propagate trace context.

        Args:
            next: The next interceptor in the chain.

        Returns:
            An interceptor that propagates trace context for activity operations.
        """
        return _ContextPropagationActivityInboundInterceptor(next)

    def workflow_interceptor_class(
        self, input: temporalio.worker.WorkflowInterceptorClassInput
    ) -> Type[_ContextPropagationWorkflowInboundInterceptor]:
        """Returns the workflow interceptor class to propagate trace context.

        Args:
            input: The input for creating the workflow interceptor.

        Returns:
            The class of the workflow interceptor that propagates trace context.
        """
        return _ContextPropagationWorkflowInboundInterceptor


class _ContextPropagationClientOutboundInterceptor(
    temporalio.client.OutboundInterceptor
):
    def __init__(
        self,
        next: temporalio.client.OutboundInterceptor,
        payload_converter: temporalio.converter.PayloadConverter,
    ) -> None:
        super().__init__(next)
        self._payload_converter = payload_converter

    async def start_workflow(
        self, input: temporalio.client.StartWorkflowInput
    ) -> temporalio.client.WorkflowHandle[Any, Any]:
        metadata = {
            "temporal:workflowType": input.workflow,
            **({"temporal:workflowId": input.id} if input.id else {}),
        }
        data = {"workflowId": input.id} if input.id else None
        span_name = "temporal:startWorkflow"
        if get_trace_provider().get_current_trace() is None:
            with trace(
                span_name + ":" + input.workflow, metadata=metadata, group_id=input.id
            ):
                with custom_span(name=span_name + ":" + input.workflow, data=data):
                    set_header_from_context(input, self._payload_converter)
                    return await super().start_workflow(input)
        else:
            with custom_span(name=span_name, data=data):
                set_header_from_context(input, self._payload_converter)
                return await super().start_workflow(input)

    async def query_workflow(self, input: temporalio.client.QueryWorkflowInput) -> Any:
        metadata = {
            "temporal:queryWorkflow": input.query,
            **({"temporal:workflowId": input.id} if input.id else {}),
        }
        data = {"workflowId": input.id, "query": input.query}
        span_name = "temporal:queryWorkflow"
        if get_trace_provider().get_current_trace() is None:
            with trace(span_name, metadata=metadata, group_id=input.id):
                with custom_span(name=span_name, data=data):
                    set_header_from_context(input, self._payload_converter)
                    return await super().query_workflow(input)
        else:
            with custom_span(name=span_name, data=data):
                set_header_from_context(input, self._payload_converter)
                return await super().query_workflow(input)

    async def signal_workflow(
        self, input: temporalio.client.SignalWorkflowInput
    ) -> None:
        metadata = {
            "temporal:signalWorkflow": input.signal,
            **({"temporal:workflowId": input.id} if input.id else {}),
        }
        data = {"workflowId": input.id, "signal": input.signal}
        span_name = "temporal:signalWorkflow"
        if get_trace_provider().get_current_trace() is None:
            with trace(span_name, metadata=metadata, group_id=input.id):
                with custom_span(name=span_name, data=data):
                    set_header_from_context(input, self._payload_converter)
                    await super().signal_workflow(input)
        else:
            with custom_span(name=span_name, data=data):
                set_header_from_context(input, self._payload_converter)
                await super().signal_workflow(input)

    async def start_workflow_update(
        self, input: temporalio.client.StartWorkflowUpdateInput
    ) -> temporalio.client.WorkflowUpdateHandle[Any]:
        metadata = {
            "temporal:updateWorkflow": input.update,
            **({"temporal:workflowId": input.id} if input.id else {}),
        }
        data = {
            **({"workflowId": input.id} if input.id else {}),
            "update": input.update,
        }
        span_name = "temporal:updateWorkflow"
        if get_trace_provider().get_current_trace() is None:
            with trace(span_name, metadata=metadata, group_id=input.id):
                with custom_span(name=span_name, data=data):
                    set_header_from_context(input, self._payload_converter)
                    return await self.next.start_workflow_update(input)
        else:
            with custom_span(name=span_name, data=data):
                set_header_from_context(input, self._payload_converter)
                return await self.next.start_workflow_update(input)


class _ContextPropagationActivityInboundInterceptor(
    temporalio.worker.ActivityInboundInterceptor
):
    async def execute_activity(
        self, input: temporalio.worker.ExecuteActivityInput
    ) -> Any:
        with context_from_header(
            "temporal:executeActivity", input, temporalio.activity.payload_converter()
        ):
            return await self.next.execute_activity(input)


class RunIdRandom:
    """Random uuid generator seeded by the run id of the workflow.
    Doesn't currently support replay over reset correctly.
    """

    def __init__(self):
        """Create a new random UUID generator."""
        self._random = random.Random("OpenAIPlugin" + workflow.info().run_id)

    def uuid4(self) -> str:
        """Generate a random UUID."""
        return uuid.UUID(
            bytes=random.getrandbits(16 * 8).to_bytes(16, "big"), version=4
        ).hex[:24]


def _ensure_tracing_random() -> None:
    """We use a custom uuid generator for spans to ensure that changes to user code workflow.random usage
    do not affect tracing and vice versa.
    """
    instance = workflow.instance()
    if not hasattr(instance, "__temporal_openai_tracing_random"):
        setattr(
            workflow.instance(),
            "__temporal_openai_tracing_random",
            RunIdRandom(),
        )


class _ContextPropagationWorkflowInboundInterceptor(
    temporalio.worker.WorkflowInboundInterceptor
):
    def init(self, outbound: temporalio.worker.WorkflowOutboundInterceptor) -> None:
        self.next.init(_ContextPropagationWorkflowOutboundInterceptor(outbound))

    async def execute_workflow(
        self, input: temporalio.worker.ExecuteWorkflowInput
    ) -> Any:
        _ensure_tracing_random()
        with context_from_header(
            "temporal:executeWorkflow", input, temporalio.workflow.payload_converter()
        ):
            return await self.next.execute_workflow(input)

    async def handle_signal(self, input: temporalio.worker.HandleSignalInput) -> None:
        _ensure_tracing_random()
        with context_from_header(
            "temporal:handleSignal", input, temporalio.workflow.payload_converter()
        ):
            return await self.next.handle_signal(input)

    async def handle_query(self, input: temporalio.worker.HandleQueryInput) -> Any:
        _ensure_tracing_random()
        with context_from_header(
            "temporal:handleQuery", input, temporalio.workflow.payload_converter()
        ):
            return await self.next.handle_query(input)

    def handle_update_validator(
        self, input: temporalio.worker.HandleUpdateInput
    ) -> None:
        with context_from_header(
            "temporal:handleUpdateValidator",
            input,
            temporalio.workflow.payload_converter(),
        ):
            self.next.handle_update_validator(input)

    async def handle_update_handler(
        self, input: temporalio.worker.HandleUpdateInput
    ) -> Any:
        _ensure_tracing_random()
        with context_from_header(
            "temporal:handleUpdateHandler",
            input,
            temporalio.workflow.payload_converter(),
        ):
            return await self.next.handle_update_handler(input)


class _ContextPropagationWorkflowOutboundInterceptor(
    temporalio.worker.WorkflowOutboundInterceptor
):
    async def signal_child_workflow(
        self, input: temporalio.worker.SignalChildWorkflowInput
    ) -> None:
        with custom_span(
            name="temporal:signalChildWorkflow",
            data={"workflowId": input.child_workflow_id},
        ):
            set_header_from_context(input, temporalio.workflow.payload_converter())
            await self.next.signal_child_workflow(input)

    async def signal_external_workflow(
        self, input: temporalio.worker.SignalExternalWorkflowInput
    ) -> None:
        with custom_span(
            name="temporal:signalExternalWorkflow",
            data={"workflowId": input.workflow_id},
        ):
            set_header_from_context(input, temporalio.workflow.payload_converter())
            await self.next.signal_external_workflow(input)

    def start_activity(
        self, input: temporalio.worker.StartActivityInput
    ) -> temporalio.workflow.ActivityHandle:
        span = custom_span(
            name="temporal:startActivity", data={"activity": input.activity}
        )
        span.start(mark_as_current=True)
        set_header_from_context(input, temporalio.workflow.payload_converter())
        handle = self.next.start_activity(input)
        handle.add_done_callback(lambda _: span.finish())
        return handle

    async def start_child_workflow(
        self, input: temporalio.worker.StartChildWorkflowInput
    ) -> temporalio.workflow.ChildWorkflowHandle:
        span = custom_span(
            name="temporal:startChildWorkflow", data={"workflow": input.workflow}
        )
        span.start(mark_as_current=True)
        set_header_from_context(input, temporalio.workflow.payload_converter())
        handle = await self.next.start_child_workflow(input)
        handle.add_done_callback(lambda _: span.finish())
        return handle

    def start_local_activity(
        self, input: temporalio.worker.StartLocalActivityInput
    ) -> temporalio.workflow.ActivityHandle:
        span = custom_span(
            name="temporal:startLocalActivity", data={"activity": input.activity}
        )
        span.start(mark_as_current=True)
        set_header_from_context(input, temporalio.workflow.payload_converter())
        handle = self.next.start_local_activity(input)
        handle.add_done_callback(lambda _: span.finish())
        return handle



================================================
FILE: temporalio/contrib/openai_agents/workflow.py
================================================
"""Workflow-specific primitives for working with the OpenAI Agents SDK in a workflow context"""

import functools
import inspect
import json
from datetime import timedelta
from typing import Any, Callable, Optional, Type, Union, overload

import nexusrpc
from agents import (
    Agent,
    RunContextWrapper,
    Tool,
)
from agents.function_schema import DocstringStyle, function_schema
from agents.tool import (
    FunctionTool,
    ToolErrorFunction,
    ToolFunction,
    ToolParams,
    default_tool_error_function,
    function_tool,
)
from agents.util._types import MaybeAwaitable

from temporalio import activity
from temporalio import workflow as temporal_workflow
from temporalio.common import Priority, RetryPolicy
from temporalio.exceptions import ApplicationError, TemporalError
from temporalio.workflow import ActivityCancellationType, VersioningIntent


def activity_as_tool(
    fn: Callable,
    *,
    task_queue: Optional[str] = None,
    schedule_to_close_timeout: Optional[timedelta] = None,
    schedule_to_start_timeout: Optional[timedelta] = None,
    start_to_close_timeout: Optional[timedelta] = None,
    heartbeat_timeout: Optional[timedelta] = None,
    retry_policy: Optional[RetryPolicy] = None,
    cancellation_type: ActivityCancellationType = ActivityCancellationType.TRY_CANCEL,
    activity_id: Optional[str] = None,
    versioning_intent: Optional[VersioningIntent] = None,
    summary: Optional[str] = None,
    priority: Priority = Priority.default,
) -> Tool:
    """Convert a single Temporal activity function to an OpenAI agent tool.

    .. warning::
        This API is experimental and may change in future versions.
        Use with caution in production environments.

    This function takes a Temporal activity function and converts it into an
    OpenAI agent tool that can be used by the agent to execute the activity
    during workflow execution. The tool will automatically handle the conversion
    of inputs and outputs between the agent and the activity. Note that if you take a context,
    mutation will not be persisted, as the activity may not be running in the same location.

    Args:
        fn: A Temporal activity function to convert to a tool.
        For other arguments, refer to :py:mod:`workflow` :py:meth:`start_activity`

    Returns:
        An OpenAI agent tool that wraps the provided activity.

    Raises:
        ApplicationError: If the function is not properly decorated as a Temporal activity.

    Example:
        >>> @activity.defn
        >>> def process_data(input: str) -> str:
        ...     return f"Processed: {input}"
        >>>
        >>> # Create tool with custom activity options
        >>> tool = activity_as_tool(
        ...     process_data,
        ...     start_to_close_timeout=timedelta(seconds=30),
        ...     retry_policy=RetryPolicy(maximum_attempts=3),
        ...     heartbeat_timeout=timedelta(seconds=10)
        ... )
        >>> # Use tool with an OpenAI agent
    """
    ret = activity._Definition.from_callable(fn)
    if not ret:
        raise ApplicationError(
            "Bare function without tool and activity decorators is not supported",
            "invalid_tool",
        )
    if ret.name is None:
        raise ApplicationError(
            "Input activity must have a name to be made into a tool",
            "invalid_tool",
        )
    # If the provided callable has a first argument of `self`, partially apply it with the same metadata
    # The actual instance will be picked up by the activity execution, the partially applied function will never actually be executed
    params = list(inspect.signature(fn).parameters.keys())
    if len(params) > 0 and params[0] == "self":
        partial = functools.partial(fn, None)
        setattr(partial, "__name__", fn.__name__)
        partial.__annotations__ = getattr(fn, "__annotations__")
        setattr(
            partial,
            "__temporal_activity_definition",
            getattr(fn, "__temporal_activity_definition"),
        )
        partial.__doc__ = fn.__doc__
        fn = partial
    schema = function_schema(fn)

    async def run_activity(ctx: RunContextWrapper[Any], input: str) -> Any:
        try:
            json_data = json.loads(input)
        except Exception as e:
            raise ApplicationError(
                f"Invalid JSON input for tool {schema.name}: {input}"
            ) from e

        # Activities don't support keyword only arguments, so we can ignore the kwargs_dict return
        args, _ = schema.to_call_args(schema.params_pydantic_model(**json_data))

        # Add the context to the arguments if it takes that
        if schema.takes_context:
            args = [ctx] + args
        result = await temporal_workflow.execute_activity(
            ret.name,  # type: ignore
            args=args,
            task_queue=task_queue,
            schedule_to_close_timeout=schedule_to_close_timeout,
            schedule_to_start_timeout=schedule_to_start_timeout,
            start_to_close_timeout=start_to_close_timeout,
            heartbeat_timeout=heartbeat_timeout,
            retry_policy=retry_policy,
            cancellation_type=cancellation_type,
            activity_id=activity_id,
            versioning_intent=versioning_intent,
            summary=summary or schema.description,
            priority=priority,
        )
        try:
            return str(result)
        except Exception as e:
            raise ToolSerializationError(
                "You must return a string representation of the tool output, or something we can call str() on"
            ) from e

    return FunctionTool(
        name=schema.name,
        description=schema.description or "",
        params_json_schema=schema.params_json_schema,
        on_invoke_tool=run_activity,
        strict_json_schema=True,
    )


def nexus_operation_as_tool(
    operation: nexusrpc.Operation[Any, Any],
    *,
    service: Type[Any],
    endpoint: str,
    schedule_to_close_timeout: Optional[timedelta] = None,
) -> Tool:
    """Convert a Nexus operation into an OpenAI agent tool.

    .. warning::
        This API is experimental and may change in future versions.
        Use with caution in production environments.

    This function takes a Nexus operation and converts it into an
    OpenAI agent tool that can be used by the agent to execute the operation
    during workflow execution. The tool will automatically handle the conversion
    of inputs and outputs between the agent and the operation.

    Args:
        fn: A Nexus operation to convert into a tool.
        service: The Nexus service class that contains the operation.
        endpoint: The Nexus endpoint to use for the operation.

    Returns:
        An OpenAI agent tool that wraps the provided operation.

    Example:
        >>> @nexusrpc.service
        ... class WeatherService:
        ...     get_weather_object_nexus_operation: nexusrpc.Operation[WeatherInput, Weather]
        >>>
        >>> # Create tool with custom activity options
        >>> tool = nexus_operation_as_tool(
        ...     WeatherService.get_weather_object_nexus_operation,
        ...     service=WeatherService,
        ...     endpoint="weather-service",
        ... )
        >>> # Use tool with an OpenAI agent
    """

    def operation_callable(input):
        raise NotImplementedError("This function definition is used as a type only")

    operation_callable.__annotations__ = {
        "input": operation.input_type,
        "return": operation.output_type,
    }
    operation_callable.__name__ = operation.name

    schema = function_schema(operation_callable)

    async def run_operation(ctx: RunContextWrapper[Any], input: str) -> Any:
        try:
            json_data = json.loads(input)
        except Exception as e:
            raise ApplicationError(
                f"Invalid JSON input for tool {schema.name}: {input}"
            ) from e

        nexus_client = temporal_workflow.create_nexus_client(
            service=service, endpoint=endpoint
        )
        args, _ = schema.to_call_args(schema.params_pydantic_model(**json_data))
        assert len(args) == 1, "Nexus operations must have exactly one argument"
        [arg] = args
        result = await nexus_client.execute_operation(
            operation,
            arg,
            schedule_to_close_timeout=schedule_to_close_timeout,
        )
        try:
            return str(result)
        except Exception as e:
            raise ToolSerializationError(
                "You must return a string representation of the tool output, or something we can call str() on"
            ) from e

    return FunctionTool(
        name=schema.name,
        description=schema.description or "",
        params_json_schema=schema.params_json_schema,
        on_invoke_tool=run_operation,
        strict_json_schema=True,
    )


class ToolSerializationError(TemporalError):
    """Error that occurs when a tool output could not be serialized.

    .. warning::
        This exception is experimental and may change in future versions.
        Use with caution in production environments.

    This exception is raised when a tool (created from an activity or Nexus operation)
    returns a value that cannot be properly serialized for use by the OpenAI agent.
    All tool outputs must be convertible to strings for the agent to process them.

    The error typically occurs when:
    - A tool returns a complex object that doesn't have a meaningful string representation
    - The returned object cannot be converted using str()
    - Custom serialization is needed but not implemented

    Example:
        >>> @activity.defn
        >>> def problematic_tool() -> ComplexObject:
        ...     return ComplexObject()  # This might cause ToolSerializationError

    To fix this error, ensure your tool returns string-convertible values or
    modify the tool to return a string representation of the result.
    """


