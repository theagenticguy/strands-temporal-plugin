"""Weather tools for the example agent.

These tools are decorated with @tool and used directly by Strands Agent.
The tool execution happens within the Strands Agent event loop.

For the DurableAgent pattern (alternative), see tools_durable.py.
"""

from strands import tool


@tool
def get_weather(city: str) -> str:
    """Get current weather for a city.

    This is a simple mock implementation. In a real application,
    this would call a weather API.

    Args:
        city: Name of the city to get weather for

    Returns:
        Weather description for the city
    """
    # Mock weather data
    weather_conditions = {
        "seattle": "Rainy and 55°F",
        "new york": "Cloudy and 68°F",
        "miami": "Sunny and 82°F",
        "chicago": "Windy and 45°F",
        "los angeles": "Sunny and 75°F",
        "london": "Foggy and 50°F",
        "paris": "Clear and 65°F",
        "tokyo": "Humid and 78°F",
    }

    city_lower = city.lower()
    if city_lower in weather_conditions:
        return f"The weather in {city} is: {weather_conditions[city_lower]}"
    else:
        return f"Weather data for {city} is not available. Assuming pleasant conditions around 70°F."
