"""Unit tests for strands_temporal_plugin.tool_executor module."""

import json
import pytest
from strands.tools.executors._executor import ToolExecutor as StrandsToolExecutor
from strands_temporal_plugin.tool_executor import TemporalToolExecutor
from strands_temporal_plugin.types import MCPToolSpec, StdioMCPServerConfig, ToolExecutorConfig
from unittest.mock import AsyncMock, MagicMock, patch


class TestTemporalToolExecutor:
    """Test TemporalToolExecutor class."""

    def test_init_defaults(self):
        """Test TemporalToolExecutor initialization with defaults."""
        executor = TemporalToolExecutor()

        assert executor.tool_modules == {}
        assert executor.mcp_tools == []
        assert executor._activity_timeout == 60.0

    def test_init_with_tool_modules(self):
        """Test TemporalToolExecutor with tool modules."""
        tool_modules = {
            "get_weather": "myapp.tools.weather",
            "search": "myapp.tools.search",
        }
        executor = TemporalToolExecutor(tool_modules=tool_modules)

        assert executor.tool_modules == tool_modules

    def test_init_with_mcp_servers(self):
        """Test TemporalToolExecutor with MCP server configs."""
        mcp_servers = [
            StdioMCPServerConfig(
                server_id="aws-docs",
                command="uvx",
                args=["awslabs.aws-documentation-mcp-server@latest"],
            )
        ]
        executor = TemporalToolExecutor(mcp_servers=mcp_servers)

        assert len(executor._mcp_servers) == 1
        assert executor._mcp_servers[0].server_id == "aws-docs"

    def test_init_with_custom_timeout(self):
        """Test TemporalToolExecutor with custom timeout."""
        executor = TemporalToolExecutor(activity_timeout=120.0)

        assert executor._activity_timeout == 120.0

    def test_tool_modules_returns_copy(self):
        """Test that tool_modules property returns a copy."""
        tool_modules = {"tool1": "module1"}
        executor = TemporalToolExecutor(tool_modules=tool_modules)

        returned = executor.tool_modules
        returned["tool2"] = "module2"

        assert "tool2" not in executor.tool_modules

    def test_mcp_tools_returns_copy(self):
        """Test that mcp_tools property returns a copy."""
        executor = TemporalToolExecutor()
        executor._mcp_tools = [
            MCPToolSpec(
                name="test_tool",
                description="A test tool",
                input_schema={},
                server_id="test-server",
            )
        ]

        returned = executor.mcp_tools
        returned.append(
            MCPToolSpec(
                name="another_tool",
                description="Another tool",
                input_schema={},
                server_id="test-server",
            )
        )

        assert len(executor.mcp_tools) == 1

    def test_get_mcp_tool_specs_empty(self):
        """Test get_mcp_tool_specs with no MCP tools."""
        executor = TemporalToolExecutor()

        specs = executor.get_mcp_tool_specs()

        assert specs == []

    def test_get_mcp_tool_specs_with_tools(self):
        """Test get_mcp_tool_specs with MCP tools."""
        executor = TemporalToolExecutor()
        executor._mcp_tools = [
            MCPToolSpec(
                name="search_docs",
                description="Search AWS documentation",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
                server_id="aws-docs",
            )
        ]

        specs = executor.get_mcp_tool_specs()

        assert len(specs) == 1
        assert specs[0]["name"] == "search_docs"
        assert specs[0]["description"] == "Search AWS documentation"
        assert "inputSchema" in specs[0]


class TestToolExecutorConfig:
    """Test ToolExecutorConfig class."""

    def test_config_defaults(self):
        """Test ToolExecutorConfig with defaults."""
        config = ToolExecutorConfig()

        assert config.tool_modules == {}
        assert config.mcp_servers == []
        assert config.activity_timeout == 60.0
        assert config.max_retries == 3
        assert config.initial_retry_interval_seconds == 1.0
        assert config.max_retry_interval_seconds == 30.0
        assert config.backoff_coefficient == 2.0

    def test_config_with_tool_modules(self):
        """Test ToolExecutorConfig with tool modules."""
        config = ToolExecutorConfig(
            tool_modules={"get_weather": "myapp.tools"},
        )

        assert config.tool_modules == {"get_weather": "myapp.tools"}

    def test_config_with_mcp_servers(self):
        """Test ToolExecutorConfig with MCP servers."""
        config = ToolExecutorConfig(
            mcp_servers=[
                StdioMCPServerConfig(
                    server_id="test",
                    command="test-cmd",
                    args=["arg1"],
                )
            ],
        )

        assert len(config.mcp_servers) == 1
        assert config.mcp_servers[0].server_id == "test"

    def test_config_get_retry_policy(self):
        """Test ToolExecutorConfig retry policy generation."""
        config = ToolExecutorConfig(
            max_retries=5,
            initial_retry_interval_seconds=2.0,
            max_retry_interval_seconds=120.0,
            backoff_coefficient=3.0,
        )

        policy = config.get_retry_policy()

        assert policy.maximum_attempts == 5
        assert policy.initial_interval.total_seconds() == 2.0
        assert policy.maximum_interval.total_seconds() == 120.0
        assert policy.backoff_coefficient == 3.0

    def test_config_serialization(self):
        """Test ToolExecutorConfig JSON serialization."""
        config = ToolExecutorConfig(
            tool_modules={"get_weather": "myapp.tools"},
            activity_timeout=120.0,
            max_retries=5,
        )

        json_str = config.model_dump_json()
        data = json.loads(json_str)

        assert data["tool_modules"] == {"get_weather": "myapp.tools"}
        assert data["activity_timeout"] == 120.0
        assert data["max_retries"] == 5

        # Deserialize
        restored = ToolExecutorConfig.model_validate_json(json_str)
        assert restored == config


class TestTemporalToolExecutorExecution:
    """Test TemporalToolExecutor execution methods."""

    @pytest.mark.asyncio
    async def test_execute_static_tool_not_found(self):
        """Test _execute_static_tool with tool not in tool_modules."""
        executor = TemporalToolExecutor(tool_modules={})

        result = await executor._execute_static_tool(
            tool_name="unknown_tool",
            tool_input={"arg": "value"},
            tool_use_id="tool_123",
        )

        assert result.status == "error"
        assert "not found" in result.content[0]["text"]

    @pytest.mark.asyncio
    async def test_execute_mcp_tool_server_not_found(self):
        """Test _execute_mcp_tool with server not in configs."""
        executor = TemporalToolExecutor()

        result = await executor._execute_mcp_tool(
            server_id="unknown_server",
            tool_name="some_tool",
            tool_input={},
            tool_use_id="tool_456",
        )

        assert result.status == "error"
        assert "not found" in result.content[0]["text"]


class TestTemporalToolExecutorIntegration:
    """Integration-style tests for TemporalToolExecutor."""

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.tool_executor.workflow")
    async def test_discover_mcp_tools(self, mock_workflow):
        """Test MCP tool discovery via activity."""
        from strands_temporal_plugin.types import MCPListToolsResult

        # Mock the activity execution
        mock_result = MCPListToolsResult(
            tools=[
                MCPToolSpec(
                    name="search_docs",
                    description="Search documentation",
                    input_schema={"type": "object"},
                    server_id="aws-docs",
                )
            ]
        )
        mock_workflow.execute_activity = AsyncMock(return_value=mock_result)

        # Create executor with MCP server config
        executor = TemporalToolExecutor(
            mcp_servers=[
                StdioMCPServerConfig(
                    server_id="aws-docs",
                    command="uvx",
                    args=["test"],
                )
            ]
        )

        # Discover tools
        tools = await executor.discover_mcp_tools()

        # Verify
        assert len(tools) == 1
        assert tools[0].name == "search_docs"
        assert executor._mcp_tools == tools
        assert "aws-docs" in executor._mcp_server_configs

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.tool_executor.workflow")
    @patch("strands_temporal_plugin.tool_executor.StrandsToolExecutor._invoke_after_tool_call_hook")
    @patch("strands_temporal_plugin.tool_executor.StrandsToolExecutor._invoke_before_tool_call_hook")
    async def test_execute_routes_to_mcp_activity(self, mock_before_hook, mock_after_hook, mock_workflow):
        """Test that _execute routes MCP tools to MCP activity."""
        from strands_temporal_plugin.types import MCPToolExecutionResult

        # Set up executor with MCP tool
        executor = TemporalToolExecutor()
        executor._mcp_tools = [
            MCPToolSpec(
                name="search_docs",
                description="Search documentation",
                input_schema={},
                server_id="aws-docs",
            )
        ]
        executor._mcp_server_configs = {
            "aws-docs": StdioMCPServerConfig(
                server_id="aws-docs",
                command="uvx",
                args=["test"],
            )
        }

        # Mock hooks
        mock_before_event = MagicMock()
        mock_before_event.cancel_tool = False
        mock_before_event.tool_use = {"name": "search_docs", "toolUseId": "tool_123", "input": {"query": "lambda"}}
        mock_before_event.selected_tool = MagicMock()
        mock_before_hook.return_value = (mock_before_event, [])

        mock_after_event = MagicMock()
        mock_after_event.result = {"toolUseId": "tool_123", "status": "success", "content": [{"text": "Found 5 results"}]}
        mock_after_hook.return_value = (mock_after_event, [])

        # Mock activity result
        mock_result = MCPToolExecutionResult(
            tool_use_id="tool_123",
            status="success",
            content=[{"text": "Found 5 results"}],
        )
        mock_workflow.execute_activity = AsyncMock(return_value=mock_result)

        # Create mock agent and tool_uses
        mock_agent = MagicMock()
        mock_agent.tool_registry.dynamic_tools = {}
        mock_agent.tool_registry.registry = {}
        tool_uses = [
            {
                "name": "search_docs",
                "toolUseId": "tool_123",
                "input": {"query": "lambda"},
            }
        ]
        tool_results = []

        # Execute
        events = []
        async for event in executor._execute(
            agent=mock_agent,
            tool_uses=tool_uses,
            tool_results=tool_results,
            cycle_trace=None,
            cycle_span=None,
            invocation_state={},
        ):
            events.append(event)

        # Verify - events are now ToolResultEvent objects
        assert len(events) == 1
        assert "tool_result" in events[0]
        assert events[0]["tool_result"]["status"] == "success"
        assert len(tool_results) == 1

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.tool_executor.workflow")
    @patch("strands_temporal_plugin.tool_executor.StrandsToolExecutor._invoke_after_tool_call_hook")
    @patch("strands_temporal_plugin.tool_executor.StrandsToolExecutor._invoke_before_tool_call_hook")
    async def test_execute_routes_to_static_activity(self, mock_before_hook, mock_after_hook, mock_workflow):
        """Test that _execute routes static tools to tool activity."""
        from strands_temporal_plugin.types import ToolExecutionResult

        # Set up executor with tool module
        executor = TemporalToolExecutor(
            tool_modules={"get_weather": "myapp.tools"}
        )

        # Mock hooks
        mock_before_event = MagicMock()
        mock_before_event.cancel_tool = False
        mock_before_event.tool_use = {"name": "get_weather", "toolUseId": "tool_456", "input": {"city": "Seattle"}}
        mock_before_event.selected_tool = MagicMock()
        mock_before_hook.return_value = (mock_before_event, [])

        mock_after_event = MagicMock()
        mock_after_event.result = {"toolUseId": "tool_456", "status": "success", "content": [{"text": "Weather: Sunny, 72°F"}]}
        mock_after_hook.return_value = (mock_after_event, [])

        # Mock activity result
        mock_result = ToolExecutionResult(
            tool_use_id="tool_456",
            status="success",
            content=[{"text": "Weather: Sunny, 72°F"}],
        )
        mock_workflow.execute_activity = AsyncMock(return_value=mock_result)

        # Create mock agent and tool_uses
        mock_agent = MagicMock()
        mock_agent.tool_registry.dynamic_tools = {}
        mock_agent.tool_registry.registry = {"get_weather": MagicMock()}
        tool_uses = [
            {
                "name": "get_weather",
                "toolUseId": "tool_456",
                "input": {"city": "Seattle"},
            }
        ]
        tool_results = []

        # Execute
        events = []
        async for event in executor._execute(
            agent=mock_agent,
            tool_uses=tool_uses,
            tool_results=tool_results,
            cycle_trace=None,
            cycle_span=None,
            invocation_state={},
        ):
            events.append(event)

        # Verify - events are now ToolResultEvent objects
        assert len(events) == 1
        assert "tool_result" in events[0]
        assert events[0]["tool_result"]["status"] == "success"
        assert len(tool_results) == 1
        assert tool_results[0]["toolUseId"] == "tool_456"


class TestTemporalToolExecutorABC:
    """Test TemporalToolExecutor ABC subclassing."""

    def test_is_strands_tool_executor(self):
        """Test that TemporalToolExecutor is a subclass of the Strands ToolExecutor ABC."""
        executor = TemporalToolExecutor()
        assert isinstance(executor, StrandsToolExecutor)

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.tool_executor.workflow")
    @patch("strands_temporal_plugin.tool_executor.StrandsToolExecutor._invoke_after_tool_call_hook")
    @patch("strands_temporal_plugin.tool_executor.StrandsToolExecutor._invoke_before_tool_call_hook")
    async def test_hooks_are_fired(self, mock_before_hook, mock_after_hook, mock_workflow):
        """Test that before/after tool call hooks are fired during execution."""
        from strands_temporal_plugin.types import ToolExecutionResult

        mock_workflow.patched.return_value = False

        # Mock before hook: no interrupts, no cancel
        mock_before_event = MagicMock()
        mock_before_event.cancel_tool = False
        mock_before_event.tool_use = {"name": "get_weather", "toolUseId": "t1", "input": {"city": "Seattle"}}
        mock_before_event.selected_tool = MagicMock()
        mock_before_hook.return_value = (mock_before_event, [])

        # Mock after hook
        mock_after_event = MagicMock()
        mock_after_event.result = {"toolUseId": "t1", "status": "success", "content": [{"text": "Sunny"}]}
        mock_after_hook.return_value = (mock_after_event, [])

        # Mock activity result
        mock_result = ToolExecutionResult(
            tool_use_id="t1", status="success", content=[{"text": "Sunny"}]
        )
        mock_workflow.execute_activity = AsyncMock(return_value=mock_result)

        executor = TemporalToolExecutor(tool_modules={"get_weather": "myapp.tools"})

        mock_agent = MagicMock()
        mock_agent.tool_registry.dynamic_tools = {}
        mock_agent.tool_registry.registry = {"get_weather": MagicMock()}

        tool_uses = [{"name": "get_weather", "toolUseId": "t1", "input": {"city": "Seattle"}}]
        tool_results = []

        events = []
        async for event in executor._execute(
            agent=mock_agent,
            tool_uses=tool_uses,
            tool_results=tool_results,
            cycle_trace=None,
            cycle_span=None,
            invocation_state={},
        ):
            events.append(event)

        # Verify hooks were called
        mock_before_hook.assert_called_once()
        mock_after_hook.assert_called_once()

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.tool_executor.workflow")
    @patch("strands_temporal_plugin.tool_executor.StrandsToolExecutor._invoke_after_tool_call_hook")
    @patch("strands_temporal_plugin.tool_executor.StrandsToolExecutor._invoke_before_tool_call_hook")
    async def test_cancel_tool_skips_execution(self, mock_before_hook, mock_after_hook, mock_workflow):
        """Test that cancel_tool in before hook skips activity execution."""
        mock_workflow.patched.return_value = False

        # Mock before hook: cancel the tool
        mock_before_event = MagicMock()
        mock_before_event.cancel_tool = "User cancelled this tool"
        mock_before_hook.return_value = (mock_before_event, [])

        # Mock after hook for cancel path
        mock_after_event = MagicMock()
        mock_after_event.result = {"toolUseId": "t1", "status": "error", "content": [{"text": "User cancelled this tool"}]}
        mock_after_hook.return_value = (mock_after_event, [])

        executor = TemporalToolExecutor(tool_modules={"get_weather": "myapp.tools"})

        mock_agent = MagicMock()
        mock_agent.tool_registry.dynamic_tools = {}
        mock_agent.tool_registry.registry = {"get_weather": MagicMock()}

        tool_uses = [{"name": "get_weather", "toolUseId": "t1", "input": {"city": "Seattle"}}]
        tool_results = []

        events = []
        async for event in executor._execute(
            agent=mock_agent,
            tool_uses=tool_uses,
            tool_results=tool_results,
            cycle_trace=None,
            cycle_span=None,
            invocation_state={},
        ):
            events.append(event)

        # Should have cancel event + result event, but NO activity call
        assert len(events) == 2  # ToolCancelEvent + ToolResultEvent
        mock_workflow.execute_activity.assert_not_called()
