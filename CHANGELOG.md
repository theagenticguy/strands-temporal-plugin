# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## v0.2.0

### Added

- **SDK alignment**: `TemporalModelStub(Model)` and `TemporalToolExecutor(ToolExecutor)` subclass Strands SDK ABCs
- **Parallel tool execution**: Multiple tool calls run concurrently via `asyncio.gather()`
- **Per-tool configuration**: `TemporalToolConfig` for timeout, heartbeat, retry per tool
- **Structured output**: `model.structured_output()` routes to dedicated activity
- **Session management**: `TemporalSessionManager` with S3-backed persistence
- **Custom providers**: `CustomProviderConfig` with import-path resolution
- **MCP client caching**: Reuse server connections across tool calls
- **Heartbeating**: All activities heartbeat (30s model, 25s tools)
- **Versioning gates**: `workflow.patched()` for safe workflow evolution
- **Before/after tool hooks**: Strands hook system fires through `TemporalToolExecutor`
- **Examples 03-09**: Multi-tool, MCP stdio/HTTP, structured output, sessions, custom provider, failure resilience
- **191 unit tests** at 86.53% coverage

### Fixed

- `stream()` signature matches SDK ABC (keyword-only params)
- `structured_output()` takes `Messages` instead of `str`, returns `AsyncGenerator[dict]`
- LLM provider-level retries disabled (Temporal handles retries)

## v0.1.0

### Added

- Initial release
- `TemporalModelStub` for durable model calls
- `TemporalToolExecutor` for durable tool execution
- `StrandsTemporalPlugin` for auto-registration
- `create_durable_agent()` factory
- Bedrock, Anthropic, OpenAI, Ollama provider configs
- MCP server support (stdio + HTTP)
- Examples 01-02 (quickstart, weather agent)
