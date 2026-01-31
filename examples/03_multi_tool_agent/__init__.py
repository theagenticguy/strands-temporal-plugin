"""Durable Agent Example Package.

This package demonstrates the create_durable_agent() factory for building
crash-proof AI agents with Temporal.

Usage:
    # Start worker
    python run_worker.py

    # Run examples
    python run_client.py weather
    python run_client.py all
"""

from .tools import (
    calculate,
    get_stock_price,
    get_user_info,
    get_weather,
    search_web,
    send_notification,
)
from .workflows import (
    ConversationalAssistant,
    FinanceAssistant,
    GeneralAssistant,
    NotificationAgent,
    ResearchAssistant,
    WeatherAssistant,
)

__all__ = [
    # Tools
    "get_weather",
    "search_web",
    "calculate",
    "get_stock_price",
    "get_user_info",
    "send_notification",
    # Workflows
    "WeatherAssistant",
    "ResearchAssistant",
    "NotificationAgent",
    "FinanceAssistant",
    "GeneralAssistant",
    "ConversationalAssistant",
]
