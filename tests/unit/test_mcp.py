"""Unit tests for MCP integration."""

from strands_temporal_plugin import (
    MCPListToolsInput,
    MCPListToolsResult,
    MCPToolExecutionInput,
    MCPToolExecutionResult,
    MCPToolSpec,
    StdioMCPServerConfig,
    StreamableHTTPMCPServerConfig,
)
from strands_temporal_plugin.mcp_activities import get_mcp_server_for_tool, mcp_tool_specs_to_strands


# =============================================================================
# MCP Server Configuration Tests
# =============================================================================


class TestStdioMCPServerConfig:
    """Test StdioMCPServerConfig."""

    def test_minimal_config(self):
        """Test minimal STDIO config."""
        config = StdioMCPServerConfig(
            server_id="test-server",
            command="uvx",
        )
        assert config.server_id == "test-server"
        assert config.transport == "stdio"
        assert config.command == "uvx"
        assert config.args == []
        assert config.env is None
        assert config.cwd is None
        assert config.startup_timeout == 30.0

    def test_full_config(self):
        """Test full STDIO config."""
        config = StdioMCPServerConfig(
            server_id="aws-docs",
            command="uvx",
            args=["awslabs.aws-documentation-mcp-server@latest"],
            env={"AWS_REGION": "us-east-1"},
            cwd="/tmp",
            startup_timeout=60.0,
            allowed_tools=["search_*"],
            rejected_tools=["admin_*"],
            tool_prefix="docs",
        )
        assert config.server_id == "aws-docs"
        assert config.transport == "stdio"
        assert config.command == "uvx"
        assert config.args == ["awslabs.aws-documentation-mcp-server@latest"]
        assert config.env == {"AWS_REGION": "us-east-1"}
        assert config.cwd == "/tmp"
        assert config.startup_timeout == 60.0
        assert config.allowed_tools == ["search_*"]
        assert config.rejected_tools == ["admin_*"]
        assert config.tool_prefix == "docs"

    def test_serialization(self):
        """Test STDIO config serialization."""
        config = StdioMCPServerConfig(
            server_id="test-server",
            command="uvx",
            args=["test@latest"],
        )
        data = config.model_dump()
        assert data["server_id"] == "test-server"
        assert data["transport"] == "stdio"
        assert data["command"] == "uvx"

        # Roundtrip
        restored = StdioMCPServerConfig.model_validate(data)
        assert restored == config


class TestStreamableHTTPMCPServerConfig:
    """Test StreamableHTTPMCPServerConfig."""

    def test_minimal_config(self):
        """Test minimal HTTP config."""
        config = StreamableHTTPMCPServerConfig(
            server_id="remote-mcp",
            url="https://example.com/mcp",
        )
        assert config.server_id == "remote-mcp"
        assert config.transport == "streamable_http"
        assert config.url == "https://example.com/mcp"
        assert config.headers == {}
        assert config.timeout == 30.0

    def test_full_config(self):
        """Test full HTTP config."""
        config = StreamableHTTPMCPServerConfig(
            server_id="bedrock-mcp",
            url="https://gateway.bedrock-agentcore.amazonaws.com/mcp",
            headers={"Authorization": "Bearer token123"},
            timeout=60.0,
            startup_timeout=45.0,
            tool_prefix="bedrock",
        )
        assert config.server_id == "bedrock-mcp"
        assert config.transport == "streamable_http"
        assert config.url == "https://gateway.bedrock-agentcore.amazonaws.com/mcp"
        assert config.headers == {"Authorization": "Bearer token123"}
        assert config.timeout == 60.0
        assert config.startup_timeout == 45.0
        assert config.tool_prefix == "bedrock"

    def test_serialization(self):
        """Test HTTP config serialization."""
        config = StreamableHTTPMCPServerConfig(
            server_id="test-server",
            url="https://example.com/mcp",
            headers={"X-Api-Key": "secret"},
        )
        data = config.model_dump()
        assert data["server_id"] == "test-server"
        assert data["transport"] == "streamable_http"
        assert data["url"] == "https://example.com/mcp"

        # Roundtrip
        restored = StreamableHTTPMCPServerConfig.model_validate(data)
        assert restored == config


# =============================================================================
# MCP Tool Spec Tests
# =============================================================================


class TestMCPToolSpec:
    """Test MCPToolSpec."""

    def test_minimal_spec(self):
        """Test minimal tool spec."""
        spec = MCPToolSpec(
            name="search",
            input_schema={"type": "object", "properties": {}},
            server_id="test-server",
        )
        assert spec.name == "search"
        assert spec.description is None
        assert spec.input_schema == {"type": "object", "properties": {}}
        assert spec.output_schema is None
        assert spec.server_id == "test-server"

    def test_full_spec(self):
        """Test full tool spec."""
        spec = MCPToolSpec(
            name="search_documentation",
            description="Search AWS documentation",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
            output_schema={
                "type": "array",
                "items": {"type": "object"},
            },
            server_id="aws-docs",
        )
        assert spec.name == "search_documentation"
        assert spec.description == "Search AWS documentation"
        assert "query" in spec.input_schema["properties"]
        assert spec.output_schema is not None
        assert spec.server_id == "aws-docs"

    def test_serialization(self):
        """Test tool spec serialization."""
        spec = MCPToolSpec(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object"},
            server_id="test",
        )
        data = spec.model_dump()
        restored = MCPToolSpec.model_validate(data)
        assert restored == spec


# =============================================================================
# MCP Activity Input/Output Tests
# =============================================================================


class TestMCPListToolsTypes:
    """Test MCPListToolsInput and MCPListToolsResult."""

    def test_list_tools_input(self):
        """Test list tools input."""
        server_config = StdioMCPServerConfig(
            server_id="test",
            command="test",
        )
        input_data = MCPListToolsInput(server_config=server_config)
        assert input_data.server_config == server_config

    def test_list_tools_result(self):
        """Test list tools result."""
        tools = [
            MCPToolSpec(
                name="tool1",
                input_schema={},
                server_id="test",
            ),
            MCPToolSpec(
                name="tool2",
                description="Second tool",
                input_schema={"type": "object"},
                server_id="test",
            ),
        ]
        result = MCPListToolsResult(tools=tools)
        assert len(result.tools) == 2
        assert result.tools[0].name == "tool1"
        assert result.tools[1].name == "tool2"


class TestMCPToolExecutionTypes:
    """Test MCPToolExecutionInput and MCPToolExecutionResult."""

    def test_execution_input(self):
        """Test tool execution input."""
        server_config = StdioMCPServerConfig(
            server_id="test",
            command="test",
        )
        input_data = MCPToolExecutionInput(
            server_config=server_config,
            tool_name="search",
            tool_input={"query": "test"},
            tool_use_id="tool_123",
        )
        assert input_data.server_config == server_config
        assert input_data.tool_name == "search"
        assert input_data.tool_input == {"query": "test"}
        assert input_data.tool_use_id == "tool_123"

    def test_execution_result_success(self):
        """Test successful execution result."""
        result = MCPToolExecutionResult(
            tool_use_id="tool_123",
            status="success",
            content=[{"text": "Search results..."}],
        )
        assert result.tool_use_id == "tool_123"
        assert result.status == "success"
        assert len(result.content) == 1

    def test_execution_result_error(self):
        """Test error execution result."""
        result = MCPToolExecutionResult(
            tool_use_id="tool_123",
            status="error",
            content=[{"text": "Tool not found"}],
        )
        assert result.status == "error"

    def test_execution_result_with_metadata(self):
        """Test execution result with metadata."""
        result = MCPToolExecutionResult(
            tool_use_id="tool_123",
            status="success",
            content=[{"text": "Result"}],
            structured_content={"data": [1, 2, 3]},
            metadata={"source": "cache"},
        )
        assert result.structured_content == {"data": [1, 2, 3]}
        assert result.metadata == {"source": "cache"}


# =============================================================================
# MCP Helper Function Tests
# =============================================================================


class TestMCPHelperFunctions:
    """Test MCP helper functions."""

    def test_mcp_tool_specs_to_strands_empty(self):
        """Test converting empty list."""
        result = mcp_tool_specs_to_strands([])
        assert result == []

    def test_mcp_tool_specs_to_strands_basic(self):
        """Test converting basic tool specs."""
        mcp_specs = [
            MCPToolSpec(
                name="search",
                description="Search docs",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
                server_id="test",
            ),
        ]
        result = mcp_tool_specs_to_strands(mcp_specs)

        assert len(result) == 1
        assert result[0]["name"] == "search"
        assert result[0]["description"] == "Search docs"
        # Check that inputSchema is wrapped in {"json": ...} for Bedrock
        assert "json" in result[0]["inputSchema"]
        assert result[0]["inputSchema"]["json"]["type"] == "object"

    def test_mcp_tool_specs_to_strands_with_output_schema(self):
        """Test converting tool specs with output schema."""
        mcp_specs = [
            MCPToolSpec(
                name="get_data",
                description="Get data",
                input_schema={"type": "object"},
                output_schema={"type": "array"},
                server_id="test",
            ),
        ]
        result = mcp_tool_specs_to_strands(mcp_specs)

        assert "outputSchema" in result[0]
        assert result[0]["outputSchema"]["json"]["type"] == "array"

    def test_get_mcp_server_for_tool_found(self):
        """Test finding MCP server for tool."""
        mcp_tools = [
            MCPToolSpec(name="docs_search", input_schema={}, server_id="docs"),
            MCPToolSpec(name="code_analyze", input_schema={}, server_id="code"),
        ]

        result = get_mcp_server_for_tool("docs_search", mcp_tools)
        assert result is not None
        server_id, spec = result
        assert server_id == "docs"
        assert spec.name == "docs_search"

    def test_get_mcp_server_for_tool_not_found(self):
        """Test tool not found in MCP tools."""
        mcp_tools = [
            MCPToolSpec(name="docs_search", input_schema={}, server_id="docs"),
        ]

        result = get_mcp_server_for_tool("unknown_tool", mcp_tools)
        assert result is None
