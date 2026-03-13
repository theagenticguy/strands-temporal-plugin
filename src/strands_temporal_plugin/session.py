"""Temporal Session Manager — S3-backed session persistence via activities.

This module provides session management for durable agents using S3 as the
state store and Temporal activities for I/O. This implements the offset/stream
model recommended by Bryan Burkholder (SFDC):

- S3 is the source of truth (the "stream" of conversation state)
- Temporal is the orchestrator (schedules work, retries, moves executors)
- session_id is the pointer/offset into the stream

Why not use Strands' built-in SessionManager directly?
Strands' SessionManager hooks fire synchronously in workflow context, where
S3 I/O is forbidden (violates Temporal determinism). Instead, we load/save
session state at workflow boundaries through Temporal activities.

Usage:
    from strands_temporal_plugin import TemporalSessionManager, SessionConfig

    @workflow.defn
    class MyWorkflow:
        @workflow.run
        async def run(self, prompt: str) -> str:
            session = TemporalSessionManager(SessionConfig(
                session_id="user-123",
                bucket="my-sessions",
                region_name="us-west-2",
            ))

            # Load previous state from S3
            await session.load()

            # Create agent with restored messages
            agent = create_durable_agent(
                provider_config=BedrockProviderConfig(model_id="..."),
                tools=[my_tool],
            )
            agent.messages.extend(session.messages)

            # Run agent
            result = await agent.invoke_async(prompt)

            # Persist updated state to S3
            await session.save(agent)

            return str(result)
"""

from __future__ import annotations

import json
import logging
from .types import SessionConfig, SessionData, SessionLoadInput, SessionSaveInput
from datetime import timedelta
from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError
from typing import Any


logger = logging.getLogger(__name__)


# =============================================================================
# TemporalSessionManager (workflow-side orchestrator)
# =============================================================================


class TemporalSessionManager:
    """Manages session persistence for durable agents via Temporal activities.

    Uses S3 as the state store. Load/save happen through activities at
    workflow boundaries. This is the Temporal-native pattern — not a Strands
    SessionManager hook (which would try to do I/O in workflow context).

    The load/save pattern works naturally with continue-as-new: each new
    workflow execution loads the latest state from S3, and saves back when done.

    Args:
        config: S3 session configuration (bucket, prefix, region)
        activity_timeout: Timeout for session load/save activities
        retry_policy: Custom retry policy for session activities

    Example:
        session = TemporalSessionManager(SessionConfig(
            session_id="user-123",
            bucket="my-sessions",
        ))
        await session.load()

        # ... create and run agent ...

        await session.save(agent)
    """

    def __init__(
        self,
        config: SessionConfig,
        activity_timeout: float = 60.0,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._config = config
        self._activity_timeout = activity_timeout
        self._retry_policy = retry_policy or RetryPolicy(
            maximum_attempts=3,
            initial_interval=timedelta(seconds=1),
            maximum_interval=timedelta(seconds=30),
            backoff_coefficient=2.0,
        )
        self._data: SessionData = SessionData()
        self._loaded = False

    @property
    def config(self) -> SessionConfig:
        """Get the session configuration."""
        return self._config

    @property
    def session_id(self) -> str:
        """Get the session ID."""
        return self._config.session_id

    @property
    def messages(self) -> list[dict[str, Any]]:
        """Get the loaded messages (empty if not yet loaded)."""
        return self._data.messages

    @property
    def agent_state(self) -> dict[str, Any]:
        """Get the loaded agent state (empty if not yet loaded)."""
        return self._data.agent_state

    @property
    def conversation_manager_state(self) -> dict[str, Any]:
        """Get the loaded conversation manager state."""
        return self._data.conversation_manager_state

    @property
    def is_loaded(self) -> bool:
        """Whether session data has been loaded."""
        return self._loaded

    async def load(self) -> SessionData:
        """Load session state from S3 via activity.

        Call this at the start of your workflow to restore previous state.
        If the session doesn't exist yet, returns empty SessionData.

        Returns:
            SessionData with messages, agent_state, and conversation_manager_state
        """
        logger.info(f"Loading session: {self._config.session_id}")

        self._data = await workflow.execute_activity(
            load_session_activity,
            SessionLoadInput(config=self._config),
            start_to_close_timeout=timedelta(seconds=self._activity_timeout),
            retry_policy=self._retry_policy,
        )

        self._loaded = True
        logger.info(
            f"Session loaded: {self._config.session_id}, "
            f"{len(self._data.messages)} messages"
        )
        return self._data

    async def save(self, agent: Any) -> None:
        """Save session state to S3 via activity.

        Call this at the end of your workflow (or before continue-as-new)
        to persist the agent's current state.

        Args:
            agent: Strands Agent instance whose state to persist
        """
        logger.info(f"Saving session: {self._config.session_id}")

        # Extract state from agent
        messages = list(agent.messages) if hasattr(agent, "messages") else []
        if hasattr(agent, "state"):
            state = agent.state
            # JSONSerializableDict.get() with no args returns all data
            # Regular dict needs dict() conversion
            try:
                agent_state = state.get() if hasattr(state, "get") and not isinstance(state, dict) else dict(state)
            except TypeError:
                agent_state = {}
        else:
            agent_state = {}
        conversation_manager_state = {}
        if hasattr(agent, "conversation_manager") and hasattr(agent.conversation_manager, "get_state"):
            conversation_manager_state = agent.conversation_manager.get_state()

        data = SessionData(
            messages=messages,
            agent_state=agent_state,
            conversation_manager_state=conversation_manager_state,
        )

        await workflow.execute_activity(
            save_session_activity,
            SessionSaveInput(config=self._config, data=data),
            start_to_close_timeout=timedelta(seconds=self._activity_timeout),
            retry_policy=self._retry_policy,
        )

        logger.info(
            f"Session saved: {self._config.session_id}, "
            f"{len(messages)} messages"
        )


# =============================================================================
# Session Activities (worker-side, S3 I/O)
# =============================================================================


def _get_s3_client(config: SessionConfig) -> Any:
    """Create an S3 client from session configuration.

    Args:
        config: Session configuration with optional region

    Returns:
        boto3 S3 client
    """
    try:
        import boto3
    except ImportError as e:
        raise ApplicationError(
            "boto3 is required for session persistence. Install it with: pip install boto3",
            type="DependencyMissing",
            non_retryable=True,
        ) from e

    kwargs: dict[str, Any] = {}
    if config.region_name:
        kwargs["region_name"] = config.region_name

    return boto3.client("s3", **kwargs)


def _session_key(config: SessionConfig) -> str:
    """Build the S3 key for a session's data file."""
    prefix = config.prefix.rstrip("/") + "/" if config.prefix else ""
    return f"{prefix}session_{config.session_id}/session_data.json"


@activity.defn
async def load_session_activity(input_data: SessionLoadInput) -> SessionData:
    """Load session state from S3.

    Returns empty SessionData if the session doesn't exist yet.

    Args:
        input_data: Session load input with S3 configuration

    Returns:
        SessionData with messages, agent_state, and conversation_manager_state
    """
    config = input_data.config
    s3 = _get_s3_client(config)
    key = _session_key(config)

    logger.info(f"Loading session from s3://{config.bucket}/{key}")

    try:
        activity.heartbeat("loading session from S3")
        response = s3.get_object(Bucket=config.bucket, Key=key)
        body = response["Body"].read().decode("utf-8")
        data = json.loads(body)

        result = SessionData(
            messages=data.get("messages", []),
            agent_state=data.get("agent_state", {}),
            conversation_manager_state=data.get("conversation_manager_state", {}),
        )

        logger.info(f"Session loaded: {len(result.messages)} messages")
        return result

    except s3.exceptions.NoSuchKey:
        logger.info(f"Session not found (new session): {config.session_id}")
        return SessionData()

    except Exception as e:
        if "NoSuchKey" in str(type(e).__name__) or "404" in str(e):
            logger.info(f"Session not found (new session): {config.session_id}")
            return SessionData()

        logger.exception(f"Failed to load session: {e}")
        raise ApplicationError(
            f"Failed to load session from S3: {e}",
            type="SessionLoadError",
            non_retryable=False,
        ) from e


@activity.defn
async def save_session_activity(input_data: SessionSaveInput) -> None:
    """Save session state to S3.

    Creates or overwrites the session data file.

    Args:
        input_data: Session save input with S3 configuration and data
    """
    config = input_data.config
    data = input_data.data
    s3 = _get_s3_client(config)
    key = _session_key(config)

    logger.info(f"Saving session to s3://{config.bucket}/{key}")

    try:
        activity.heartbeat("saving session to S3")

        payload = json.dumps(
            {
                "messages": data.messages,
                "agent_state": data.agent_state,
                "conversation_manager_state": data.conversation_manager_state,
            },
            default=str,  # Handle non-serializable types gracefully
        )

        s3.put_object(
            Bucket=config.bucket,
            Key=key,
            Body=payload.encode("utf-8"),
            ContentType="application/json",
        )

        logger.info(f"Session saved: {len(data.messages)} messages")

    except Exception as e:
        logger.exception(f"Failed to save session: {e}")
        raise ApplicationError(
            f"Failed to save session to S3: {e}",
            type="SessionSaveError",
            non_retryable=False,
        ) from e
