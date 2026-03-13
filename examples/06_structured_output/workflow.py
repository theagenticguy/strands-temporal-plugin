"""Structured Output Workflows

Demonstrates using TemporalModelStub.structured_output() to get validated
Pydantic model responses from the LLM via Temporal activities.
"""

import logging

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from strands_temporal_plugin import BedrockProviderConfig, TemporalModelStub

    from models import MovieReview, WeatherAnalysis

logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()],
)


@workflow.defn
class WeatherAnalysisWorkflow:
    """Workflow that returns structured weather analysis.

    Uses TemporalModelStub.structured_output() to get a validated
    WeatherAnalysis Pydantic model from the LLM.

    Example usage:
        result = await client.execute_workflow(
            WeatherAnalysisWorkflow.run,
            "Analyze the current weather in San Francisco",
            id="weather-analysis-1",
            task_queue="strands-structured-output",
        )
    """

    @workflow.run
    async def run(self, prompt: str) -> dict:
        """Run weather analysis with structured output.

        Args:
            prompt: Weather analysis request

        Returns:
            Dict representation of WeatherAnalysis model
        """
        model = TemporalModelStub(
            BedrockProviderConfig(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            )
        )

        result = await model.structured_output(WeatherAnalysis, prompt)
        return result.model_dump()


@workflow.defn
class MovieReviewWorkflow:
    """Workflow that returns structured movie reviews.

    Uses TemporalModelStub.structured_output() to get a validated
    MovieReview Pydantic model from the LLM.

    Example usage:
        result = await client.execute_workflow(
            MovieReviewWorkflow.run,
            "Review the movie Inception",
            id="movie-review-1",
            task_queue="strands-structured-output",
        )
    """

    @workflow.run
    async def run(self, prompt: str) -> dict:
        """Run movie review with structured output.

        Args:
            prompt: Movie review request

        Returns:
            Dict representation of MovieReview model
        """
        model = TemporalModelStub(
            BedrockProviderConfig(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            )
        )

        result = await model.structured_output(MovieReview, prompt)
        return result.model_dump()
