"""Unit tests for strands_temporal_plugin.mcp_activities module."""

import pytest
from strands_temporal_plugin.mcp_activities import (
    _convert_mcp_result_to_content,
    _convert_mcp_tool_spec_to_strands,
    _convert_mcp_tool_to_spec,
    _create_mcp_client,
    _create_transport,
    _filter_tools,
    execute_mcp_tool_activity,
    get_mcp_server_for_tool,
    list_mcp_tools_activity,
    mcp_tool_specs_to_strands,
)
from strands_temporal_plugin.types import (
    MCPListToolsInput,
    MCPToolExecutionInput,
    MCPToolSpec,
    StdioMCPServerConfig,
    StreamableHTTPMCPServerConfig,
)
from temporalio.exceptions import ApplicationError
from unittest.mock import MagicMock, patch


class TestCreateMCPClient:
    """Tests for _create_mcp_client function."""

    def test_create_mcp_client_stdio(self):
        """Test creating MCP client with stdio transport."""
        config = StdioMCPServerConfig(server_id="test-server", command="uvx", args=["test-mcp-server"])

        mock_mcp_client = MagicMock()
        mock_mcp_module = MagicMock(MCPClient=mock_mcp_client)

        with patch.dict("sys.modules", {"strands.tools.mcp": mock_mcp_module}):
            with patch("strands_temporal_plugin.mcp_activities._create_transport") as mock_transport:
                mock_transport.return_value = MagicMock()
                mock_mcp_client.return_value = MagicMock()

                result = _create_mcp_client(config)

                mock_mcp_client.assert_called_once()
                assert result is mock_mcp_client.return_value


class TestCreateTransport:
    """Tests for _create_transport function."""

    def test_create_stdio_transport(self):
        """Test creating stdio transport."""
        config = StdioMCPServerConfig(server_id="test-server", command="uvx", args=["test-mcp"], env={"KEY": "value"})

        mock_params = MagicMock()
        mock_stdio_client = MagicMock()
        mock_mcp = MagicMock(StdioServerParameters=mock_params, stdio_client=mock_stdio_client)

        with patch.dict("sys.modules", {"mcp": mock_mcp}):
            transport_callable = _create_transport(config)

            # The transport callable should be returned
            assert callable(transport_callable)

            # Call it to verify it creates the transport
            transport_callable()

            mock_params.assert_called_once_with(command="uvx", args=["test-mcp"], env={"KEY": "value"})
            mock_stdio_client.assert_called_once()

    def test_create_http_transport(self):
        """Test creating streamable HTTP transport."""
        config = StreamableHTTPMCPServerConfig(
            server_id="test-server", url="https://api.example.com/mcp", headers={"Authorization": "Bearer token"}
        )

        mock_http_client = MagicMock()
        mock_module = MagicMock(streamablehttp_client=mock_http_client)

        with patch.dict("sys.modules", {"mcp.client.streamable_http": mock_module}):
            transport_callable = _create_transport(config)

            assert callable(transport_callable)

            # Call it to verify it creates the transport
            transport_callable()

            mock_http_client.assert_called_once_with(
                url="https://api.example.com/mcp", headers={"Authorization": "Bearer token"}
            )

    def test_create_http_transport_no_headers(self):
        """Test creating HTTP transport without headers."""
        config = StreamableHTTPMCPServerConfig(server_id="test-server", url="https://api.example.com/mcp")

        mock_http_client = MagicMock()
        mock_module = MagicMock(streamablehttp_client=mock_http_client)

        with patch.dict("sys.modules", {"mcp.client.streamable_http": mock_module}):
            transport_callable = _create_transport(config)
            transport_callable()

            mock_http_client.assert_called_once_with(url="https://api.example.com/mcp", headers=None)

    def test_create_transport_unsupported_type(self):
        """Test error for unsupported transport type."""
        # Create a mock config with unsupported transport
        mock_config = MagicMock()
        mock_config.transport = "unsupported"

        with pytest.raises(ApplicationError) as exc_info:
            _create_transport(mock_config)

        assert exc_info.value.type == "UnsupportedTransport"
        assert exc_info.value.non_retryable is True


class TestFilterTools:
    """Tests for _filter_tools function."""

    def test_filter_tools_no_filters(self):
        """Test filtering with no allowed/rejected patterns."""
        mock_tools = [MagicMock(tool_name="tool1"), MagicMock(tool_name="tool2")]
        config = StdioMCPServerConfig(server_id="test", command="uvx", args=["test"])

        result = _filter_tools(mock_tools, config)

        assert result == mock_tools

    def test_filter_tools_allowed_whitelist(self):
        """Test filtering with allowed tools whitelist."""
        mock_tools = [
            MagicMock(tool_name="read_file"),
            MagicMock(tool_name="write_file"),
            MagicMock(tool_name="delete"),
        ]
        config = StdioMCPServerConfig(server_id="test", command="uvx", args=["test"], allowed_tools=["*_file"])

        result = _filter_tools(mock_tools, config)

        assert len(result) == 2
        assert all(t.tool_name.endswith("_file") for t in result)

    def test_filter_tools_rejected_blacklist(self):
        """Test filtering with rejected tools blacklist."""
        mock_tools = [
            MagicMock(tool_name="safe_tool"),
            MagicMock(tool_name="dangerous_delete"),
            MagicMock(tool_name="dangerous_format"),
        ]
        config = StdioMCPServerConfig(server_id="test", command="uvx", args=["test"], rejected_tools=["dangerous_*"])

        result = _filter_tools(mock_tools, config)

        assert len(result) == 1
        assert result[0].tool_name == "safe_tool"

    def test_filter_tools_combined_filters(self):
        """Test filtering with both allowed and rejected patterns."""
        mock_tools = [
            MagicMock(tool_name="read_safe"),
            MagicMock(tool_name="read_dangerous"),
            MagicMock(tool_name="write_file"),
        ]
        config = StdioMCPServerConfig(
            server_id="test",
            command="uvx",
            args=["test"],
            allowed_tools=["read_*"],
            rejected_tools=["*_dangerous"],
        )

        result = _filter_tools(mock_tools, config)

        assert len(result) == 1
        assert result[0].tool_name == "read_safe"


class TestConvertMCPToolToSpec:
    """Tests for _convert_mcp_tool_to_spec function."""

    def test_convert_basic_tool(self):
        """Test converting basic MCP tool to spec."""
        mock_tool = MagicMock()
        mock_tool.tool_name = "my_tool"
        mock_tool.tool_spec = {
            "name": "my_tool",
            "description": "A test tool",
            "inputSchema": {"json": {"type": "object", "properties": {"arg": {"type": "string"}}}},
        }

        result = _convert_mcp_tool_to_spec(mock_tool, "test-server")

        assert result.name == "my_tool"
        assert result.description == "A test tool"
        assert result.server_id == "test-server"
        assert result.input_schema == {"type": "object", "properties": {"arg": {"type": "string"}}}

    def test_convert_tool_with_prefix(self):
        """Test converting tool with prefix."""
        mock_tool = MagicMock()
        mock_tool.tool_name = "read"
        mock_tool.tool_spec = {"name": "read", "description": "Read something", "inputSchema": {"json": {}}}

        result = _convert_mcp_tool_to_spec(mock_tool, "test-server", tool_prefix="fs")

        assert result.name == "fs_read"

    def test_convert_tool_with_output_schema(self):
        """Test converting tool with output schema."""
        mock_tool = MagicMock()
        mock_tool.tool_name = "query"
        mock_tool.tool_spec = {
            "name": "query",
            "description": "Query data",
            "inputSchema": {"json": {"type": "object"}},
            "outputSchema": {"json": {"type": "array"}},
        }

        result = _convert_mcp_tool_to_spec(mock_tool, "test-server")

        assert result.output_schema == {"type": "array"}


class TestConvertMCPToolSpecToStrands:
    """Tests for _convert_mcp_tool_spec_to_strands function."""

    def test_convert_basic_spec(self):
        """Test converting MCPToolSpec to Strands format."""
        spec = MCPToolSpec(
            name="my_tool",
            description="A test tool",
            input_schema={"type": "object"},
            server_id="test-server",
        )

        result = _convert_mcp_tool_spec_to_strands(spec)

        assert result["name"] == "my_tool"
        assert result["description"] == "A test tool"
        assert result["inputSchema"] == {"json": {"type": "object"}}

    def test_convert_spec_with_output_schema(self):
        """Test converting spec with output schema."""
        spec = MCPToolSpec(
            name="query",
            description="Query data",
            input_schema={"type": "object"},
            output_schema={"type": "array"},
            server_id="test-server",
        )

        result = _convert_mcp_tool_spec_to_strands(spec)

        assert result["outputSchema"] == {"json": {"type": "array"}}


class TestListMCPToolsActivity:
    """Tests for list_mcp_tools_activity function."""

    @pytest.mark.asyncio
    async def test_list_tools_success(self):
        """Test successful MCP tool listing."""
        config = StdioMCPServerConfig(server_id="test-server", command="uvx", args=["test"])
        input_data = MCPListToolsInput(server_config=config)

        mock_tools = [
            MagicMock(
                tool_name="tool1", tool_spec={"name": "tool1", "description": "Test", "inputSchema": {"json": {}}}
            )
        ]

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.list_tools_sync.return_value = mock_tools

        with patch("strands_temporal_plugin.mcp_activities._create_mcp_client", return_value=mock_client):
            with patch("temporalio.activity.heartbeat"):
                result = await list_mcp_tools_activity(input_data)

        assert len(result.tools) == 1
        assert result.tools[0].name == "tool1"
        assert result.tools[0].server_id == "test-server"

    @pytest.mark.asyncio
    async def test_list_tools_connection_error_retryable(self):
        """Test connection error is retryable."""
        config = StdioMCPServerConfig(server_id="test-server", command="uvx", args=["test"])
        input_data = MCPListToolsInput(server_config=config)

        with patch(
            "strands_temporal_plugin.mcp_activities._create_mcp_client",
            side_effect=ConnectionError("Connection refused"),
        ):
            with pytest.raises(ApplicationError) as exc_info:
                await list_mcp_tools_activity(input_data)

        assert exc_info.value.type == "MCPConnectionError"
        assert exc_info.value.non_retryable is False

    @pytest.mark.asyncio
    async def test_list_tools_timeout_error_retryable(self):
        """Test timeout error is retryable."""
        config = StdioMCPServerConfig(server_id="test-server", command="uvx", args=["test"])
        input_data = MCPListToolsInput(server_config=config)

        with patch(
            "strands_temporal_plugin.mcp_activities._create_mcp_client", side_effect=Exception("connection timeout")
        ):
            with pytest.raises(ApplicationError) as exc_info:
                await list_mcp_tools_activity(input_data)

        assert exc_info.value.type == "MCPConnectionError"
        assert exc_info.value.non_retryable is False

    @pytest.mark.asyncio
    async def test_list_tools_other_error(self):
        """Test other errors are non-retryable."""
        config = StdioMCPServerConfig(server_id="test-server", command="uvx", args=["test"])
        input_data = MCPListToolsInput(server_config=config)

        with patch(
            "strands_temporal_plugin.mcp_activities._create_mcp_client", side_effect=ValueError("Invalid config")
        ):
            with pytest.raises(ApplicationError) as exc_info:
                await list_mcp_tools_activity(input_data)

        assert exc_info.value.type == "MCPError"
        assert exc_info.value.non_retryable is True

    @pytest.mark.asyncio
    async def test_list_tools_reraises_application_error(self):
        """Test ApplicationError is re-raised as-is."""
        config = StdioMCPServerConfig(server_id="test-server", command="uvx", args=["test"])
        input_data = MCPListToolsInput(server_config=config)

        original_error = ApplicationError("Custom error", type="CustomType", non_retryable=True)

        with patch("strands_temporal_plugin.mcp_activities._create_mcp_client", side_effect=original_error):
            with pytest.raises(ApplicationError) as exc_info:
                await list_mcp_tools_activity(input_data)

        assert exc_info.value is original_error


class TestExecuteMCPToolActivity:
    """Tests for execute_mcp_tool_activity function."""

    @pytest.mark.asyncio
    async def test_execute_tool_success(self):
        """Test successful MCP tool execution."""
        config = StdioMCPServerConfig(server_id="test-server", command="uvx", args=["test"])
        input_data = MCPToolExecutionInput(
            server_config=config,
            tool_name="my_tool",
            tool_use_id="tool_123",
            tool_input={"arg": "value"},
        )

        # Create mock result with proper spec to avoid MagicMock for undefined attrs
        mock_result = MagicMock(spec=["content"])
        mock_result.content = [MagicMock(text="Tool output")]

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.call_tool_sync.return_value = mock_result

        with patch("strands_temporal_plugin.mcp_activities._create_mcp_client", return_value=mock_client):
            result = await execute_mcp_tool_activity(input_data)

        assert result.tool_use_id == "tool_123"
        assert result.status == "success"
        assert result.content[0]["text"] == "Tool output"

    @pytest.mark.asyncio
    async def test_execute_tool_with_prefix_stripping(self):
        """Test tool name prefix is stripped before calling MCP."""
        config = StdioMCPServerConfig(server_id="test-server", command="uvx", args=["test"], tool_prefix="fs")
        input_data = MCPToolExecutionInput(
            server_config=config,
            tool_name="fs_read",
            tool_use_id="tool_456",
            tool_input={},
        )

        mock_result = MagicMock()
        mock_result.content = []

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.call_tool_sync.return_value = mock_result

        with patch("strands_temporal_plugin.mcp_activities._create_mcp_client", return_value=mock_client):
            await execute_mcp_tool_activity(input_data)

        # Should call with "read" not "fs_read"
        mock_client.call_tool_sync.assert_called_once_with("tool_456", "read", {})

    @pytest.mark.asyncio
    async def test_execute_tool_not_found(self):
        """Test tool not found returns error result."""
        config = StdioMCPServerConfig(server_id="test-server", command="uvx", args=["test"])
        input_data = MCPToolExecutionInput(
            server_config=config,
            tool_name="nonexistent",
            tool_use_id="tool_nf",
            tool_input={},
        )

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.call_tool_sync.side_effect = Exception("Tool not found")

        with patch("strands_temporal_plugin.mcp_activities._create_mcp_client", return_value=mock_client):
            result = await execute_mcp_tool_activity(input_data)

        assert result.status == "error"
        assert "not found" in result.content[0]["text"].lower()

    @pytest.mark.asyncio
    async def test_execute_tool_connection_error(self):
        """Test connection error during execution is retryable."""
        config = StdioMCPServerConfig(server_id="test-server", command="uvx", args=["test"])
        input_data = MCPToolExecutionInput(
            server_config=config,
            tool_name="my_tool",
            tool_use_id="tool_ce",
            tool_input={},
        )

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.call_tool_sync.side_effect = ConnectionError("Connection lost")

        with patch("strands_temporal_plugin.mcp_activities._create_mcp_client", return_value=mock_client):
            with pytest.raises(ApplicationError) as exc_info:
                await execute_mcp_tool_activity(input_data)

        assert exc_info.value.type == "MCPConnectionError"
        assert exc_info.value.non_retryable is False

    @pytest.mark.asyncio
    async def test_execute_tool_other_error(self):
        """Test other execution errors return error result."""
        config = StdioMCPServerConfig(server_id="test-server", command="uvx", args=["test"])
        input_data = MCPToolExecutionInput(
            server_config=config,
            tool_name="my_tool",
            tool_use_id="tool_oe",
            tool_input={},
        )

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.call_tool_sync.side_effect = ValueError("Invalid argument")

        with patch("strands_temporal_plugin.mcp_activities._create_mcp_client", return_value=mock_client):
            result = await execute_mcp_tool_activity(input_data)

        assert result.status == "error"
        assert "failed" in result.content[0]["text"].lower()


class TestConvertMCPResultToContent:
    """Tests for _convert_mcp_result_to_content function."""

    def test_convert_text_content(self):
        """Test converting text content."""
        mock_result = MagicMock()
        mock_item = MagicMock()
        mock_item.text = "Hello, world!"
        mock_result.content = [mock_item]

        result = _convert_mcp_result_to_content(mock_result)

        assert result == [{"text": "Hello, world!"}]

    def test_convert_image_content(self):
        """Test converting image content."""
        mock_result = MagicMock()
        mock_item = MagicMock(spec=["source"])
        mock_item.text = None  # No text attribute
        del mock_item.text
        mock_item.source = {"media_type": "image/png", "data": "base64data=="}
        mock_result.content = [mock_item]

        result = _convert_mcp_result_to_content(mock_result)

        assert result[0]["image"]["format"] == "png"
        assert result[0]["image"]["source"]["bytes"] == "base64data=="

    def test_convert_unknown_content(self):
        """Test converting unknown content type."""
        mock_result = MagicMock()
        mock_item = MagicMock(spec=[])  # No known attributes
        mock_result.content = [mock_item]

        result = _convert_mcp_result_to_content(mock_result)

        # Should convert to string
        assert len(result) == 1
        assert "text" in result[0]

    def test_convert_empty_content(self):
        """Test converting result with no content."""
        mock_result = MagicMock()
        mock_result.content = []
        mock_result.model_dump.return_value = {"result": "data"}

        result = _convert_mcp_result_to_content(mock_result)

        assert len(result) == 1
        assert '{"result": "data"}' in result[0]["text"]

    def test_convert_no_content_fallback_dict(self):
        """Test fallback when result has __dict__ but no model_dump."""
        mock_result = MagicMock(spec=["content", "__dict__"])
        mock_result.content = []
        del mock_result.model_dump
        mock_result.__dict__ = {"key": "value"}

        result = _convert_mcp_result_to_content(mock_result)

        assert len(result) == 1

    def test_convert_no_content_fallback_str(self):
        """Test fallback to str() when all else fails."""
        mock_result = MagicMock(spec=["content"])
        mock_result.content = []

        # Remove model_dump and __dict__ access
        def raise_attr(_attr):
            raise AttributeError()

        type(mock_result).model_dump = property(lambda _self: raise_attr("model_dump"))

        result = _convert_mcp_result_to_content(mock_result)

        assert len(result) == 1


class TestMCPToolSpecsToStrands:
    """Tests for mcp_tool_specs_to_strands helper function."""

    def test_convert_multiple_specs(self):
        """Test converting multiple MCPToolSpecs."""
        specs = [
            MCPToolSpec(name="tool1", description="First tool", input_schema={"type": "object"}, server_id="server1"),
            MCPToolSpec(name="tool2", description="Second tool", input_schema={"type": "string"}, server_id="server2"),
        ]

        result = mcp_tool_specs_to_strands(specs)

        assert len(result) == 2
        assert result[0]["name"] == "tool1"
        assert result[1]["name"] == "tool2"


class TestGetMCPServerForTool:
    """Tests for get_mcp_server_for_tool helper function."""

    def test_find_tool_in_list(self):
        """Test finding a tool in the list."""
        specs = [
            MCPToolSpec(name="tool1", input_schema={}, server_id="server1"),
            MCPToolSpec(name="tool2", input_schema={}, server_id="server2"),
        ]

        result = get_mcp_server_for_tool("tool2", specs)

        assert result is not None
        assert result[0] == "server2"
        assert result[1].name == "tool2"

    def test_tool_not_found(self):
        """Test when tool is not in list."""
        specs = [MCPToolSpec(name="tool1", input_schema={}, server_id="server1")]

        result = get_mcp_server_for_tool("nonexistent", specs)

        assert result is None
