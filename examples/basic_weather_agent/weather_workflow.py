"""Clean Strands Weather Agent Workflow

Following the OpenAI Agents pattern for simple, clean workflow definitions.
"""

from temporalio import workflow
from strands import Agent, tool
from strands.models import BedrockModel

from strands_temporal_plugin.runner import TemporalModelStub


# Define the weather tool (same as before)
@tool
def get_weather(city: str) -> str:
    """Get current weather for a city.

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
    }

    city_lower = city.lower()
    if city_lower in weather_conditions:
        return f"The weather in {city} is: {weather_conditions[city_lower]}"
    else:
        return f"Weather data for {city} is not available. Assuming pleasant conditions!"


@workflow.defn
class StrandsWeatherAgent:
    """Simple weather agent workflow using normal Strands Agent API."""

    @workflow.run
    async def run(self, prompt: str) -> str:
        """Run the weather agent with durable execution.

        Args:
            prompt: User's weather question

        Returns:
            Weather information response
        """
        # Just create a normal Strands Agent - plugin handles durability automatically!
        # Use model string ID to avoid BedrockModel creation in workflow (which violates sandbox)
        agent = Agent(
            model=TemporalModelStub("us.anthropic.claude-sonnet-4-20250514-v1:0"),  # Plugin will create BedrockModel in activity
            tools=[get_weather],
            system_prompt=(
                "You are a helpful weather assistant. "
                "You can get current weather information for cities using your weather tool. "
                "Always use the get_weather tool when users ask about weather conditions. "
                "Provide friendly, informative responses about the weather."
            ),
            callback_handler=None,
        )

        # This call is automatically routed to Temporal activities by the plugin!
        result = await agent.invoke_async(prompt)

        return str(result)
