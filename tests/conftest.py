"""Pytest configuration and fixtures for strands-temporal-plugin tests."""

import pytest


@pytest.fixture
def sample_messages():
    """Sample Strands messages for testing."""
    return [
        {
            "role": "user",
            "content": [{"text": "Hello, how are you?"}],
        }
    ]


@pytest.fixture
def sample_tool_spec():
    """Sample tool specification for testing.

    Note: Bedrock Converse API requires inputSchema to be wrapped in {"json": ...}
    """
    return {
        "name": "get_weather",
        "description": "Get the current weather for a city",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "The city name",
                    }
                },
                "required": ["city"],
            }
        },
    }


@pytest.fixture
def sample_stream_events():
    """Sample stream events from model inference."""
    return [
        {
            "messageStart": {
                "role": "assistant",
            }
        },
        {
            "contentBlockStart": {
                "contentBlockIndex": 0,
                "start": {},
            }
        },
        {
            "contentBlockDelta": {
                "contentBlockIndex": 0,
                "delta": {
                    "text": "Hello! ",
                },
            }
        },
        {
            "contentBlockDelta": {
                "contentBlockIndex": 0,
                "delta": {
                    "text": "How can I help you today?",
                },
            }
        },
        {
            "contentBlockStop": {
                "contentBlockIndex": 0,
            }
        },
        {
            "messageStop": {
                "stopReason": "end_turn",
            }
        },
        {
            "metadata": {
                "usage": {
                    "inputTokens": 10,
                    "outputTokens": 15,
                },
            }
        },
    ]


@pytest.fixture
def sample_tool_use_events():
    """Sample stream events with tool use."""
    return [
        {
            "messageStart": {
                "role": "assistant",
            }
        },
        {
            "contentBlockStart": {
                "contentBlockIndex": 0,
                "start": {
                    "toolUse": {
                        "toolUseId": "tool_123",
                        "name": "get_weather",
                    }
                },
            }
        },
        {
            "contentBlockDelta": {
                "contentBlockIndex": 0,
                "delta": {
                    "toolUse": {
                        "input": '{"city": "Seattle"}',
                    }
                },
            }
        },
        {
            "contentBlockStop": {
                "contentBlockIndex": 0,
            }
        },
        {
            "messageStop": {
                "stopReason": "tool_use",
            }
        },
        {
            "metadata": {
                "usage": {
                    "inputTokens": 20,
                    "outputTokens": 25,
                },
            }
        },
    ]
