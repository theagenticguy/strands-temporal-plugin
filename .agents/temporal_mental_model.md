Here’s a clean, up-to-date mental model of Temporal’s Python SDK—and exactly where Pydantic/serialization and agentic AI fit in.

Temporal (Python) programming model & architecture

Core pieces

Workflows: long-lived, deterministic state machines written as async methods with the @workflow.defn/@workflow.run decorators. They orchestrate, don’t do I/O, and advance by replaying an event history. Use Temporal’s deterministic APIs (timers, random, time, waits) rather than standard library calls. 
Temporal
Temporal

Activities: short-lived, side-effecting code that does I/O (HTTP, DB, LLM calls, etc.). They run outside the workflow sandbox and are automatically retried/heart-beated. Can be sync or async; default to sync unless you’re sure your async path never blocks the event loop. 
Temporal Documentation

Workers: long-running processes that poll Task Queues for workflow and activity tasks and execute your code. Python workers run workflow tasks in a thread pool and activities either on the event loop (async) or in executors (sync). 
Temporal Documentation

Client: starts workflows, sends Signals/Updates, issues Queries, lists and manages executions. 
Temporal Documentation

Determinism & sandbox: Python workflows execute in a Temporal sandbox that restricts known non-deterministic calls. You can pass through deterministic third-party modules, or (rarely) disable sandboxing—though that removes guardrails. 
Temporal Documentation

Versioning: for changing workflow code/data shape safely over months/years. Use Patching (workflow.patched/deprecate_patch) and/or Worker Build-ID Versioning to roll out new logic without breaking replay. 
Temporal Documentation

Converters/codecs: Temporal serializes inputs/returns into payloads via a DataConverter (default JSON/Protobuf JSON). You can add Payload Codecs (e.g., compression/encryption). 
Temporal

Nexus (pre-release in Python): a native RPC bridge to expose operations (including “start a workflow”) across namespaces with a typed contract—useful for external callers or composing services. 
Temporal Documentation

Testing: in-process test server with time-skipping for fast end-to-end/integration tests; ActivityEnvironment for isolated activity tests; replayer for determinism. 
Temporal Documentation

Pydantic & data serialization: what works and what bites

Your options

Default DataConverter (JSON/Protobuf JSON) + plain Python types/dataclasses. Cross-SDK friendly. 
Temporal

temporalio.contrib.pydantic DataConverter for Pydantic v2 models—makes datetimes, enums, and complex types painless, with v2’s TypeAdapter/model_dump under the hood. Pydantic v1 is not supported.

Sharp edges & patterns (Python ↔ Python and polyglot)

Standardize the DataConverter everywhere
The client, all workers (workflow & activity), and replayers must use the same DataConverter (and codecs), or decoding will fail on the other side. Treat it as part of your ABI. 
Temporal

Prefer a single, typed envelope parameter
Temporal recommends one parameter (a dataclass or Pydantic model) over multiple parameters so you can add fields later without signature breaks and nondeterminism risk. This is explicitly called out in Python docs. 
Temporal Documentation

Datetime handling
Temporal’s JSON converter doesn’t natively handle Python datetime everywhere—but the Pydantic converter does (ISO 8601). If you must interop with other SDKs/languages, be consistent about timezone awareness (store as UTC+offset) and formats. 
Temporal

Enums & unions
Stick to string enums to be safe across languages. For unions, pin to discriminated unions in Pydantic where practical to avoid ambiguity in JSON payloads. (Ref: Pydantic v2 JSON serialization guidance.)

Optional/None vs omitted
Pydantic’s exclude_none/exclude_unset change your JSON shape. Once a workflow history contains one shape, later code that expects a different shape can break determinism. Freeze your model config and evolve with patching/versioning if you change omission rules. 
Temporal Documentation

Bytes/Decimal/Set
JSON has no native bytes/decimal. Decide on a convention (e.g., base64 bytes, decimal as string) and encode/decode symmetrically in custom serializers if you’re not using Pydantic’s default behaviors. The default converter supports sets/UUID/decimal via JSON mappings, but polyglot consumers must agree. 
Temporal

Cross-language interop
If Java/Go/TS workers will share data, prefer plain JSON schemas (or Protobuf) and avoid Python-specific types/serializers. Keep field names stable; never repurpose fields—add new ones and gate behavior via patches. 
Temporal
Temporal Documentation

Activity sync vs async
Async activities that accidentally do blocking I/O (e.g., requests.get) can starve the event loop and stall workflows. Use sync activities for blocking work (worker runs them in threadpool) or fully async libraries (aiohttp, httpx). 
Temporal Documentation

Sandbox imports
If a workflow imports Pydantic or other libs, use imports pass-through to avoid heavy re-imports and keep determinism (only for side-effect-free libs). 
Temporal Documentation

Where agentic AI fits (and the OpenAI Agents SDK contrib)

The gist
Temporal orchestrates long-running, reliable processes; the OpenAI Agents SDK (the “Agent loop” with tools, handoffs, sessions, tracing) handles reasoning + tool use. Temporal’s Python contrib ties them together so LLM tool calls are durable, observable, retried, and cancelable. 
OpenAI GitHub

What Temporal ships (Python contrib)

temporalio.contrib.openai_agents includes helpers to:

Wrap Temporal activities as OpenAI tools (activity_as_tool),

Expose Nexus operations as tools (nexus_operation_as_tool),

Configure interceptors, tracing, and a DataConverter set suitable for agents (plus utilities like heartbeat_every to keep long LLM/tool calls healthy). It’s labeled experimental but documented in the official API site. 
Temporal

Practical pattern

Agent loop ↔ Temporal:

The agent chooses a tool → that tool is a Temporal activity (e.g., fetch docs, run SQL, call bedrock/openai).

The agent’s session state (messages/results) lives in workflow state; Signals/Updates can push human feedback or external events into the workflow while it’s running.

Long tasks stream progress via heartbeats, and failures auto-retry according to policy.

Use Continue-As-New to cap history size for long chat sessions; Patching/Build-ID to evolve the orchestration without bricking in-flight conversations. 
Temporal Documentation
+1

Why not run the agent loop inside a workflow?
Because workflows must be deterministic and cannot do network I/O; the LLM calls and tool I/O belong in activities (or Nexus operations). Keep the loop’s policy/state in the workflow; execute side effects in activities. 
Temporal

Gotcha checklist (field-tested)

Use one envelope param (@dataclass or Pydantic v2 model) for every workflow/activity/start/query/signal/update. Safer evolution. 
Temporal Documentation

Pin & share the same DataConverter and PayloadCodec across clients/workers/tests. Treat it as part of your contract. 
Temporal

Pydantic v2 only for the contrib converter; never mix v1.

No blocking in async activities—use sync activities or truly async libs. 
Temporal Documentation

Gate breaking changes with Patching; roll out code with Worker Versioning. 
Temporal Documentation

Use Signals/Updates for bidirectional, typed interactions with running conversations/agents. Queries don’t mutate state and must not be async. 
Temporal Documentation

Leverage time-skipping tests to TDD your orchestration. Start with integration tests using the test server. 
Temporal Documentation

Consider Nexus if you need external callers to invoke your agent workflows via a stable RPC layer (pre-release in Python). 
Temporal Documentation

Minimal TDD starter (what I’d write first)

Pick & wire the converter (once):
Create a tiny test that asserts you can start_workflow() and round-trip a Pydantic v2 model through an activity using pydantic_data_converter, with a datetime and enum field.

Determinism test:
A workflow that sleeps (timer), calls an activity, and handles a signal/update. Re-run with the replayer after you refactor the control flow behind a patch. Expect replay to pass before/after. 
Temporal Documentation

Agent tool test (OpenAI contrib):
Wrap a real activity with activity_as_tool and run an Agents SDK Runner end-to-end in a Temporal test env, asserting that a tool call becomes an activity execution (inspect heartbeats/trace). 
Temporal
OpenAI GitHub

If you want, I can sketch these three tests and the corresponding minimal implementation using Python 3.12+ with pytest and the official contrib packages.

You said:
What else does the open ai agent sdk contrib package do?
ChatGPT said:

Great question — here’s a more comprehensive breakdown of what the temporalio.contrib.openai_agents package offers, especially beyond what we’ve already explored.

What This Contrib Package Adds
1. OpenAIAgentsPlugin — Seamless Plugin Integration

A centralized way to wire up the OpenAI Agents SDK with Temporal workflows, this plugin handles:

Injecting the Pydantic data converter so agent-related inputs and outputs serialize safely and consistently.

Installing tracing interceptors for monitoring agent operations within workflows and activities.

Registering the essential model execution activities (e.g., calling LLMs).

Ensuring all necessary runtime overrides are activated when running the worker or replayer.

YouTube
+14
Temporal
+14
Temporal
+14

2. Temporally-Aware Runner: TemporalOpenAIRunner

This class extends OpenAI’s Agent Runner to work inside Temporal workflows:

Wraps model calls into Temporal activities under the hood.

Offers a .run() method that executes an agent run deterministically in a workflow context (streaming and sync methods are not supported within workflows).

Temporal

3. Workflow Helpers: activity_as_tool & nexus_operation_as_tool

These functions bridge agent tooling with Temporal orchestration:

activity_as_tool converts any Temporal activity into an OpenAI agent tool, complete with built-in serialization and execution controls like timeouts, heartbeats, and retry policy.

YouTube
+11
Temporal
+11
Temporal
+11

nexus_operation_as_tool does the same for Nexus RPC operations, allowing agents to invoke cross-service operations as tools.

Temporal
+1

4. Tracing & Context Propagation Interceptors

Robust observability is critical for agent workflows:

Under the hood, a full suite of trace interceptors captures spans for activities, workflows, and the "hand-offs" of agent operations.

Context (such as trace headers or run_id) propagates cleanly across process boundaries.

Temporal
+12
Temporal
+12
GitHub
+12
Temporal

5. Payload Conversion – _OpenAIPayloadConverter

Joins the stack of payload converters to ensure consistent serialization of agent-specific data types:

Inherits from PydanticPayloadConverter to guarantee payload round-tripping.

Used internally to support the agent's payload conventions under Temporal’s Data Converter pipeline.

Temporal
+4
Temporal
+4
Temporal
+4

6. Testing Support: TestModel and TestModelProvider

For testability and mocking:

TestModel emulates a model that feeds back predetermined responses—great for unit tests.

TestModelProvider nicely wraps a test model for injection into workflows/workers.

Temporal
+3
Temporal
+3
Temporal
+3

7. Contextual Management for Workflows & Plugins

Supporting modules include:

A workflow-specific module to work seamlessly with agents in workflows.

A _heartbeat decorator that integrates with agent-running activities to send heartbeats for long LLM calls and avoid activity timeouts.

Temporal
+1
Temporal
+1

Summary Table
Feature	Purpose & Functionality
OpenAIAgentsPlugin	Central plugin to enable agents with proper serialization, tracing, and activity wiring
TemporalOpenAIRunner	Runs agents inside Temporal workflows via activities
activity_as_tool	Wraps activity as an agent tool with full Temporal execution config
nexus_operation_as_tool	Wraps Nexus RPC operations as agent tools
Tracing Interceptors	Propagate trace contexts and capture agent spans
_OpenAIPayloadConverter	Ensures agent payloads are serialized via Pydantic
TestModel / TestModelProvider	Mock model behavior for testing workflows and activities
How It Fits Together

Use OpenAIAgentsPlugin when initializing your client & worker to avoid manual setup.

Incorporate activity_as_tool (and optionally nexus_operation_as_tool) to expose your domain-specific actions as tools to the agent.

Within your workflow, use TemporalOpenAIRunner to orchestrate the agent loop (state, tool invocation, reasoning).

Observability and reliability are ensured via tracing interceptors and heartbeating logic.

Complete repeatability and isolation for tests via the TestModel utilities.
