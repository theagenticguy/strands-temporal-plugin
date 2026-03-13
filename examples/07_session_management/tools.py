"""Memory tools for the session management example.

Simple tools that work with in-memory state for the workflow turn.
Cross-turn persistence is handled by TemporalSessionManager (S3).
"""

from strands import tool

_facts: list[str] = []


@tool
def remember_fact(fact: str) -> str:
    """Remember a fact for later recall.

    Args:
        fact: The fact to remember

    Returns:
        Confirmation message
    """
    _facts.append(fact)
    return f"Remembered: {fact}"


@tool
def recall_facts() -> str:
    """Recall all remembered facts.

    Returns:
        All remembered facts or a message if none exist
    """
    if not _facts:
        return "No facts remembered yet."
    return "Remembered facts:\n" + "\n".join(f"- {f}" for f in _facts)
