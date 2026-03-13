"""Unit tests for strands_temporal_plugin.session module."""

import json
import pytest
from datetime import timedelta
from strands_temporal_plugin.session import (
    TemporalSessionManager,
    _get_s3_client,
    _session_key,
    load_session_activity,
    save_session_activity,
)
from strands_temporal_plugin.types import SessionConfig, SessionData, SessionLoadInput, SessionSaveInput
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError
from unittest.mock import AsyncMock, MagicMock, patch


class TestTemporalSessionManagerInit:
    """Test TemporalSessionManager initialization."""

    def test_init_defaults(self):
        """Test TemporalSessionManager with default activity_timeout and retry_policy."""
        config = SessionConfig(
            session_id="user-123",
            bucket="my-sessions",
        )
        manager = TemporalSessionManager(config)

        assert manager.config == config
        assert manager.session_id == "user-123"
        assert manager._activity_timeout == 60.0
        assert manager._retry_policy.maximum_attempts == 3
        assert manager._retry_policy.initial_interval == timedelta(seconds=1)
        assert manager._retry_policy.maximum_interval == timedelta(seconds=30)
        assert manager._retry_policy.backoff_coefficient == 2.0
        assert manager.is_loaded is False
        assert manager.messages == []
        assert manager.agent_state == {}

    def test_init_custom_config(self):
        """Test TemporalSessionManager with custom activity_timeout and retry_policy."""
        config = SessionConfig(
            session_id="user-456",
            bucket="custom-bucket",
            prefix="prod/",
            region_name="us-west-2",
        )
        custom_retry = RetryPolicy(
            maximum_attempts=5,
            initial_interval=timedelta(seconds=2),
            maximum_interval=timedelta(seconds=60),
            backoff_coefficient=3.0,
        )
        manager = TemporalSessionManager(
            config=config,
            activity_timeout=120.0,
            retry_policy=custom_retry,
        )

        assert manager.config == config
        assert manager.session_id == "user-456"
        assert manager._activity_timeout == 120.0
        assert manager._retry_policy.maximum_attempts == 5
        assert manager._retry_policy.initial_interval == timedelta(seconds=2)
        assert manager._retry_policy.maximum_interval == timedelta(seconds=60)
        assert manager._retry_policy.backoff_coefficient == 3.0


class TestTemporalSessionManagerProperties:
    """Test TemporalSessionManager properties."""

    def test_session_id(self):
        """Test session_id property returns config session_id."""
        config = SessionConfig(session_id="abc-123", bucket="bucket")
        manager = TemporalSessionManager(config)

        assert manager.session_id == "abc-123"

    def test_messages_empty_before_load(self):
        """Test messages returns empty list before load."""
        config = SessionConfig(session_id="test", bucket="bucket")
        manager = TemporalSessionManager(config)

        assert manager.messages == []

    def test_agent_state_empty_before_load(self):
        """Test agent_state returns empty dict before load."""
        config = SessionConfig(session_id="test", bucket="bucket")
        manager = TemporalSessionManager(config)

        assert manager.agent_state == {}

    def test_conversation_manager_state_empty_before_load(self):
        """Test conversation_manager_state returns empty dict before load."""
        config = SessionConfig(session_id="test", bucket="bucket")
        manager = TemporalSessionManager(config)

        assert manager.conversation_manager_state == {}

    def test_is_loaded_false_before_load(self):
        """Test is_loaded is False before calling load."""
        config = SessionConfig(session_id="test", bucket="bucket")
        manager = TemporalSessionManager(config)

        assert manager.is_loaded is False


class TestTemporalSessionManagerLoad:
    """Test TemporalSessionManager.load method."""

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.session.workflow")
    async def test_load_returns_session_data(self, mock_workflow):
        """Test load calls workflow.execute_activity and returns SessionData."""
        config = SessionConfig(session_id="user-123", bucket="my-sessions")
        manager = TemporalSessionManager(config)

        mock_session_data = SessionData(
            messages=[
                {"role": "user", "content": [{"text": "Hello"}]},
                {"role": "assistant", "content": [{"text": "Hi there!"}]},
            ],
            agent_state={"turn_count": 1},
            conversation_manager_state={"summary": "greeting"},
        )
        mock_workflow.execute_activity = AsyncMock(return_value=mock_session_data)

        result = await manager.load()

        assert result == mock_session_data
        assert manager.is_loaded is True
        assert len(manager.messages) == 2
        assert manager.messages[0]["role"] == "user"
        assert manager.agent_state == {"turn_count": 1}
        assert manager.conversation_manager_state == {"summary": "greeting"}

        # Verify execute_activity was called with correct args
        mock_workflow.execute_activity.assert_called_once()
        call_args = mock_workflow.execute_activity.call_args
        assert call_args[0][0] == load_session_activity
        activity_input = call_args[0][1]
        assert isinstance(activity_input, SessionLoadInput)
        assert activity_input.config == config

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.session.workflow")
    async def test_load_empty_session(self, mock_workflow):
        """Test load with no prior session returns empty SessionData."""
        config = SessionConfig(session_id="new-user", bucket="my-sessions")
        manager = TemporalSessionManager(config)

        mock_session_data = SessionData()
        mock_workflow.execute_activity = AsyncMock(return_value=mock_session_data)

        result = await manager.load()

        assert result.messages == []
        assert result.agent_state == {}
        assert result.conversation_manager_state == {}
        assert manager.is_loaded is True


class TestTemporalSessionManagerSave:
    """Test TemporalSessionManager.save method."""

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.session.workflow")
    async def test_save_extracts_messages_and_state(self, mock_workflow):
        """Test save extracts messages, state, and conversation_manager_state from agent."""
        config = SessionConfig(session_id="user-123", bucket="my-sessions")
        manager = TemporalSessionManager(config)

        # Create mock agent
        mock_agent = MagicMock()
        mock_agent.messages = [
            {"role": "user", "content": [{"text": "Hello"}]},
            {"role": "assistant", "content": [{"text": "Hi!"}]},
        ]
        mock_agent.state = {"turn_count": 1}
        mock_agent.conversation_manager = MagicMock()
        mock_agent.conversation_manager.get_state.return_value = {"summary": "test"}

        mock_workflow.execute_activity = AsyncMock(return_value=None)

        await manager.save(mock_agent)

        # Verify execute_activity was called with correct args
        mock_workflow.execute_activity.assert_called_once()
        call_args = mock_workflow.execute_activity.call_args
        assert call_args[0][0] == save_session_activity
        activity_input = call_args[0][1]
        assert isinstance(activity_input, SessionSaveInput)
        assert activity_input.config == config
        assert len(activity_input.data.messages) == 2
        assert activity_input.data.agent_state == {"turn_count": 1}
        assert activity_input.data.conversation_manager_state == {"summary": "test"}

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.session.workflow")
    async def test_save_agent_without_messages(self, mock_workflow):
        """Test save handles agent without messages attribute gracefully."""
        config = SessionConfig(session_id="user-123", bucket="my-sessions")
        manager = TemporalSessionManager(config)

        # Create mock agent without messages
        mock_agent = MagicMock(spec=[])  # No attributes

        mock_workflow.execute_activity = AsyncMock(return_value=None)

        await manager.save(mock_agent)

        call_args = mock_workflow.execute_activity.call_args
        activity_input = call_args[0][1]
        assert activity_input.data.messages == []
        assert activity_input.data.agent_state == {}
        assert activity_input.data.conversation_manager_state == {}

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.session.workflow")
    async def test_save_agent_without_conversation_manager(self, mock_workflow):
        """Test save handles agent without conversation_manager attribute."""
        config = SessionConfig(session_id="user-123", bucket="my-sessions")
        manager = TemporalSessionManager(config)

        mock_agent = MagicMock()
        mock_agent.messages = [{"role": "user", "content": [{"text": "Hi"}]}]
        mock_agent.state = {}
        # Remove conversation_manager attribute
        del mock_agent.conversation_manager

        mock_workflow.execute_activity = AsyncMock(return_value=None)

        await manager.save(mock_agent)

        call_args = mock_workflow.execute_activity.call_args
        activity_input = call_args[0][1]
        assert activity_input.data.conversation_manager_state == {}


class TestSessionKey:
    """Test _session_key helper."""

    def test_session_key_no_prefix(self):
        """Test _session_key with no prefix."""
        config = SessionConfig(session_id="user-123", bucket="bucket")
        key = _session_key(config)

        assert key == "session_user-123/session_data.json"

    def test_session_key_with_prefix(self):
        """Test _session_key with prefix."""
        config = SessionConfig(session_id="user-123", bucket="bucket", prefix="prod/")
        key = _session_key(config)

        assert key == "prod/session_user-123/session_data.json"

    def test_session_key_with_prefix_no_trailing_slash(self):
        """Test _session_key with prefix that has no trailing slash."""
        config = SessionConfig(session_id="user-123", bucket="bucket", prefix="prod")
        key = _session_key(config)

        assert key == "prod/session_user-123/session_data.json"


class TestLoadSessionActivity:
    """Test load_session_activity function."""

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.session.activity")
    @patch("strands_temporal_plugin.session._get_s3_client")
    async def test_load_existing_session(self, mock_get_s3_client, mock_activity):
        """Test loading an existing session from S3."""
        config = SessionConfig(session_id="user-123", bucket="my-sessions")
        input_data = SessionLoadInput(config=config)

        # Mock S3 client
        mock_s3 = MagicMock()
        mock_get_s3_client.return_value = mock_s3

        session_payload = {
            "messages": [
                {"role": "user", "content": [{"text": "Hello"}]},
                {"role": "assistant", "content": [{"text": "Hi!"}]},
            ],
            "agent_state": {"turn_count": 1},
            "conversation_manager_state": {"summary": "greeting"},
        }
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(session_payload).encode("utf-8")
        mock_s3.get_object.return_value = {"Body": mock_body}

        result = await load_session_activity(input_data)

        assert isinstance(result, SessionData)
        assert len(result.messages) == 2
        assert result.messages[0]["role"] == "user"
        assert result.agent_state == {"turn_count": 1}
        assert result.conversation_manager_state == {"summary": "greeting"}

        # Verify S3 was called with correct bucket and key
        mock_s3.get_object.assert_called_once_with(
            Bucket="my-sessions",
            Key="session_user-123/session_data.json",
        )

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.session.activity")
    @patch("strands_temporal_plugin.session._get_s3_client")
    async def test_load_new_session_no_such_key(self, mock_get_s3_client, mock_activity):
        """Test loading a session that doesn't exist returns empty SessionData."""
        config = SessionConfig(session_id="new-user", bucket="my-sessions")
        input_data = SessionLoadInput(config=config)

        # Mock S3 client with NoSuchKey exception
        mock_s3 = MagicMock()
        mock_get_s3_client.return_value = mock_s3

        # Create a NoSuchKey exception class
        no_such_key_error = type("NoSuchKey", (Exception,), {})
        mock_s3.exceptions.NoSuchKey = no_such_key_error
        mock_s3.get_object.side_effect = no_such_key_error("No such key")

        result = await load_session_activity(input_data)

        assert isinstance(result, SessionData)
        assert result.messages == []
        assert result.agent_state == {}
        assert result.conversation_manager_state == {}

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.session.activity")
    @patch("strands_temporal_plugin.session._get_s3_client")
    async def test_load_s3_error_raises_application_error(self, mock_get_s3_client, mock_activity):
        """Test loading a session when S3 raises an unexpected error."""
        config = SessionConfig(session_id="user-123", bucket="my-sessions")
        input_data = SessionLoadInput(config=config)

        # Mock S3 client with a generic error
        mock_s3 = MagicMock()
        mock_get_s3_client.return_value = mock_s3

        # Make NoSuchKey not match the raised exception
        mock_s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        mock_s3.get_object.side_effect = RuntimeError("Connection refused")

        with pytest.raises(ApplicationError) as exc_info:
            await load_session_activity(input_data)

        assert "Failed to load session from S3" in str(exc_info.value)
        assert exc_info.value.type == "SessionLoadError"
        assert exc_info.value.non_retryable is False


class TestSaveSessionActivity:
    """Test save_session_activity function."""

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.session.activity")
    @patch("strands_temporal_plugin.session._get_s3_client")
    async def test_save_session_success(self, mock_get_s3_client, mock_activity):
        """Test saving a session to S3 successfully."""
        config = SessionConfig(session_id="user-123", bucket="my-sessions")
        data = SessionData(
            messages=[
                {"role": "user", "content": [{"text": "Hello"}]},
                {"role": "assistant", "content": [{"text": "Hi!"}]},
            ],
            agent_state={"turn_count": 1},
            conversation_manager_state={},
        )
        input_data = SessionSaveInput(config=config, data=data)

        # Mock S3 client
        mock_s3 = MagicMock()
        mock_get_s3_client.return_value = mock_s3

        await save_session_activity(input_data)

        # Verify S3 put_object was called
        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "my-sessions"
        assert call_kwargs["Key"] == "session_user-123/session_data.json"
        assert call_kwargs["ContentType"] == "application/json"

        # Verify the body content
        body_bytes = call_kwargs["Body"]
        body_data = json.loads(body_bytes.decode("utf-8"))
        assert len(body_data["messages"]) == 2
        assert body_data["agent_state"] == {"turn_count": 1}

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.session.activity")
    @patch("strands_temporal_plugin.session._get_s3_client")
    async def test_save_session_s3_error(self, mock_get_s3_client, mock_activity):
        """Test saving a session when S3 write fails."""
        config = SessionConfig(session_id="user-123", bucket="my-sessions")
        data = SessionData(messages=[], agent_state={})
        input_data = SessionSaveInput(config=config, data=data)

        # Mock S3 client with error
        mock_s3 = MagicMock()
        mock_get_s3_client.return_value = mock_s3
        mock_s3.put_object.side_effect = RuntimeError("Access Denied")

        with pytest.raises(ApplicationError) as exc_info:
            await save_session_activity(input_data)

        assert "Failed to save session to S3" in str(exc_info.value)
        assert exc_info.value.type == "SessionSaveError"
        assert exc_info.value.non_retryable is False

    @pytest.mark.asyncio
    @patch("strands_temporal_plugin.session.activity")
    @patch("strands_temporal_plugin.session._get_s3_client")
    async def test_save_session_with_prefix(self, mock_get_s3_client, mock_activity):
        """Test saving a session uses correct S3 key with prefix."""
        config = SessionConfig(
            session_id="user-123",
            bucket="my-sessions",
            prefix="production/",
        )
        data = SessionData(messages=[], agent_state={})
        input_data = SessionSaveInput(config=config, data=data)

        mock_s3 = MagicMock()
        mock_get_s3_client.return_value = mock_s3

        await save_session_activity(input_data)

        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["Key"] == "production/session_user-123/session_data.json"


class TestGetS3Client:
    """Test _get_s3_client helper."""

    @patch.dict("sys.modules", {"boto3": MagicMock()})
    def test_get_s3_client_no_region(self):
        """Test _get_s3_client without region_name."""
        import sys

        config = SessionConfig(session_id="test", bucket="bucket")
        mock_boto3 = sys.modules["boto3"]
        mock_boto3.client.return_value = MagicMock()

        _get_s3_client(config)

        mock_boto3.client.assert_called_once_with("s3")

    @patch.dict("sys.modules", {"boto3": MagicMock()})
    def test_get_s3_client_with_region(self):
        """Test _get_s3_client with region_name."""
        import sys

        config = SessionConfig(
            session_id="test",
            bucket="bucket",
            region_name="us-west-2",
        )
        mock_boto3 = sys.modules["boto3"]
        mock_boto3.client.return_value = MagicMock()

        _get_s3_client(config)

        mock_boto3.client.assert_called_once_with("s3", region_name="us-west-2")
