"""Example tools demonstrating the create_durable_agent pattern.

These tools showcase various use cases:
- Simple synchronous tools
- Tools with external API calls (I/O)
- Tools that might fail transiently

All tools are decorated with @tool and will be executed durably
via Temporal activities when used with create_durable_agent().
"""

import random
import time
from strands import tool


@tool
def get_weather(city: str) -> str:
    """Get current weather for a city.

    Args:
        city: Name of the city to get weather for

    Returns:
        Weather description for the city
    """
    # Simulated weather data
    weather_data = {
        "seattle": {"temp": 55, "condition": "Rainy", "humidity": 85},
        "new york": {"temp": 68, "condition": "Cloudy", "humidity": 60},
        "miami": {"temp": 82, "condition": "Sunny", "humidity": 75},
        "tokyo": {"temp": 78, "condition": "Humid", "humidity": 80},
        "london": {"temp": 50, "condition": "Foggy", "humidity": 90},
        "paris": {"temp": 65, "condition": "Clear", "humidity": 55},
    }

    city_lower = city.lower()
    if city_lower in weather_data:
        data = weather_data[city_lower]
        return (
            f"Weather in {city}: {data['condition']}, "
            f"{data['temp']}°F, Humidity: {data['humidity']}%"
        )
    else:
        # Simulate API call for unknown cities
        temp = random.randint(40, 90)
        return f"Weather in {city}: Partly cloudy, {temp}°F (estimated)"


@tool
def search_web(query: str, max_results: int = 3) -> str:
    """Search the web for information.

    This simulates a web search API call that might experience
    transient failures (rate limits, timeouts, etc.).

    Args:
        query: Search query string
        max_results: Maximum number of results to return

    Returns:
        Search results as formatted text
    """
    # Simulate potential transient failure (10% chance)
    if random.random() < 0.1:
        raise ConnectionError("Simulated search API timeout - will retry")

    # Simulated search results
    results = [
        f"Result 1: Information about '{query}' from Wikipedia",
        f"Result 2: News article discussing '{query}'",
        f"Result 3: Expert analysis of '{query}'",
        f"Result 4: Forum discussion about '{query}'",
        f"Result 5: Academic paper on '{query}'",
    ]

    return "\n".join(results[:max_results])


@tool
def calculate(expression: str) -> str:
    """Safely evaluate a mathematical expression.

    Args:
        expression: Mathematical expression to evaluate (e.g., "2 + 2 * 3")

    Returns:
        Result of the calculation
    """
    # Safe evaluation - only allow basic math operations
    allowed_chars = set("0123456789+-*/().% ")
    if not all(c in allowed_chars for c in expression):
        return f"Error: Expression contains invalid characters. Only numbers and +-*/().% are allowed."

    try:
        # Use eval with restricted globals for safety
        result = eval(expression, {"__builtins__": {}}, {})
        return f"Result: {expression} = {result}"
    except Exception as e:
        return f"Error calculating '{expression}': {str(e)}"


@tool
def get_stock_price(symbol: str) -> str:
    """Get current stock price for a symbol.

    This simulates a financial API call.

    Args:
        symbol: Stock ticker symbol (e.g., "AAPL", "GOOGL")

    Returns:
        Stock price information
    """
    # Simulated stock data
    stock_prices = {
        "AAPL": 178.50,
        "GOOGL": 141.25,
        "MSFT": 378.90,
        "AMZN": 178.75,
        "META": 505.25,
        "TSLA": 248.50,
        "NVDA": 875.30,
    }

    symbol_upper = symbol.upper()
    if symbol_upper in stock_prices:
        price = stock_prices[symbol_upper]
        # Add some random variation
        change = random.uniform(-2.0, 2.0)
        change_pct = (change / price) * 100
        direction = "+" if change > 0 else ""
        return (
            f"{symbol_upper}: ${price + change:.2f} "
            f"({direction}{change:.2f}, {direction}{change_pct:.2f}%)"
        )
    else:
        return f"Stock symbol '{symbol}' not found"


@tool
def send_notification(
    recipient: str,
    message: str,
    channel: str = "email"
) -> str:
    """Send a notification to a user.

    This simulates sending notifications via various channels.
    In a real app, this would call external notification services.

    Args:
        recipient: User to notify (email or username)
        message: Notification message
        channel: Notification channel (email, sms, slack)

    Returns:
        Confirmation of notification sent
    """
    # Simulate sending notification
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    if channel.lower() not in ["email", "sms", "slack"]:
        return f"Error: Unknown channel '{channel}'. Use email, sms, or slack."

    # Simulate potential failure (5% chance)
    if random.random() < 0.05:
        raise ConnectionError(f"Failed to send {channel} notification - will retry")

    return (
        f"Notification sent successfully!\n"
        f"  Channel: {channel}\n"
        f"  Recipient: {recipient}\n"
        f"  Message: {message[:50]}{'...' if len(message) > 50 else ''}\n"
        f"  Timestamp: {timestamp}"
    )


@tool
def get_user_info(user_id: str) -> str:
    """Get information about a user.

    This simulates a database or API lookup.

    Args:
        user_id: User ID or username to look up

    Returns:
        User information
    """
    # Simulated user database
    users = {
        "user123": {
            "name": "Alice Johnson",
            "email": "alice@example.com",
            "role": "Engineer",
            "department": "Engineering",
        },
        "user456": {
            "name": "Bob Smith",
            "email": "bob@example.com",
            "role": "Manager",
            "department": "Product",
        },
        "user789": {
            "name": "Carol Williams",
            "email": "carol@example.com",
            "role": "Designer",
            "department": "Design",
        },
    }

    if user_id in users:
        user = users[user_id]
        return (
            f"User: {user['name']}\n"
            f"  Email: {user['email']}\n"
            f"  Role: {user['role']}\n"
            f"  Department: {user['department']}"
        )
    else:
        return f"User '{user_id}' not found"
