"""Weather tool for the weather agent example.

This tool is decorated with @tool and will be executed durably
via Temporal activities when used with create_durable_agent().
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
    # Mock weather data - replace with real API call in production
    weather_conditions = {
        "seattle": "Rainy and 55F",
        "new york": "Cloudy and 68F",
        "miami": "Sunny and 82F",
        "chicago": "Windy and 45F",
        "los angeles": "Sunny and 75F",
        "london": "Foggy and 50F",
        "paris": "Clear and 65F",
        "tokyo": "Humid and 78F",
        "san francisco": "Foggy and 60F",
        "denver": "Clear and 55F",
    }

    city_lower = city.lower()
    if city_lower in weather_conditions:
        return f"The weather in {city} is: {weather_conditions[city_lower]}"
    else:
        return f"Weather data for {city} is not available. Assuming pleasant conditions around 70F."
