"""Tools with controllable failure modes for resilience testing.

Each tool simulates a real-world failure pattern:
- Transient network errors (succeed after N retries)
- Slow external APIs (configurable latency)
- Permanent failures (always fail)

Temporal's retry policies and heartbeat timeouts handle all of these
automatically — no retry logic needed in the tool code.
"""

import os
import time

from strands import tool

# Global counters track attempts across retries (reset per workflow via env var)
_attempt_counts: dict[str, int] = {}


def _get_attempts(tool_name: str) -> int:
    """Get and increment attempt counter for a tool."""
    _attempt_counts[tool_name] = _attempt_counts.get(tool_name, 0) + 1
    return _attempt_counts[tool_name]


def reset_counters():
    """Reset all attempt counters (called at start of each workflow)."""
    _attempt_counts.clear()


@tool
def flaky_api_call(query: str) -> str:
    """Call an external API that fails transiently before succeeding.

    Simulates a real-world API with intermittent 503 errors.
    Fails on the first 2 attempts, succeeds on the 3rd.
    Temporal's retry policy handles this automatically.

    Args:
        query: The search query to send to the API

    Returns:
        API response text
    """
    attempt = _get_attempts("flaky_api_call")
    failures_before_success = int(os.environ.get("FLAKY_FAILURES", "2"))

    print(f"  [flaky_api_call] Attempt {attempt} for query: {query!r}")

    if attempt <= failures_before_success:
        print(f"  [flaky_api_call] Simulating 503 Service Unavailable (attempt {attempt}/{failures_before_success})")
        raise ConnectionError(
            f"503 Service Unavailable - API temporarily overloaded (attempt {attempt})"
        )

    print(f"  [flaky_api_call] Success on attempt {attempt}")
    return f"API results for '{query}': Found 3 relevant documents about {query}."


@tool
def slow_database_query(table: str) -> str:
    """Query a slow database that takes a long time to respond.

    Simulates a database query with configurable latency.
    If it takes longer than the heartbeat timeout, Temporal
    detects it as stuck and retries on another worker.

    Args:
        table: The database table to query

    Returns:
        Query results
    """
    delay = int(os.environ.get("SLOW_DB_SECONDS", "5"))
    print(f"  [slow_database_query] Querying table '{table}', estimated time: {delay}s")

    # Sleep in chunks so heartbeats can fire
    for i in range(delay):
        time.sleep(1)
        print(f"  [slow_database_query] Processing... {i + 1}/{delay}s")

    return f"Query results from '{table}': 42 rows returned, avg processing time 2.3ms"


@tool
def unreliable_webhook(url: str, payload: str) -> str:
    """Send a webhook that fails permanently after exhausting retries.

    Simulates a downstream service that is completely down.
    Temporal will retry up to the configured max_attempts,
    then the activity fails and the agent sees the error.

    Args:
        url: Webhook endpoint URL
        payload: JSON payload to send

    Returns:
        Webhook delivery confirmation
    """
    attempt = _get_attempts("unreliable_webhook")
    print(f"  [unreliable_webhook] Attempt {attempt}: POST {url}")
    raise ConnectionError(
        f"Connection refused: {url} - service is down (attempt {attempt})"
    )


@tool
def reliable_calculator(expression: str) -> str:
    """A tool that always works — for contrast with the failing tools.

    Args:
        expression: Math expression to evaluate

    Returns:
        Calculation result
    """
    allowed_chars = set("0123456789+-*/().% ")
    if not all(c in allowed_chars for c in expression):
        return "Error: Invalid characters in expression"

    try:
        result = eval(expression, {"__builtins__": {}}, {})
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error: {e}"
