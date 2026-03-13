#!/usr/bin/env python3
"""Structured Output Client

Connects to Temporal and executes structured output workflows.

Usage:
    # Make sure the worker is running first, then:
    cd examples/06_structured_output

    # Weather analysis (default)
    uv run python run_client.py weather

    # Movie review
    uv run python run_client.py movie

    # Custom prompt
    uv run python run_client.py weather --prompt "Analyze the weather in Tokyo"
"""

import argparse
import asyncio
import json
import uuid

from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client
from workflow import MovieReviewWorkflow, WeatherAnalysisWorkflow


async def main():
    """Execute a structured output workflow."""
    parser = argparse.ArgumentParser(description="Structured Output Client")
    parser.add_argument(
        "type",
        choices=["weather", "movie"],
        default="weather",
        nargs="?",
        help="Type of structured output (default: weather)",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="Custom prompt (overrides default)",
    )
    args = parser.parse_args()

    # Default prompts
    defaults = {
        "weather": "Analyze the weather in San Francisco assuming it's a typical foggy summer day with 62°F temperature",
        "movie": "Review the movie Inception",
    }
    prompt = args.prompt or defaults[args.type]

    print()
    print("=" * 50)
    print("  Strands Temporal - Structured Output Client")
    print("=" * 50)
    print()

    # Connect to Temporal
    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )
    print("[OK] Connected to Temporal")
    print()

    print(f"Type: {args.type}")
    print(f"Prompt: {prompt}")
    print("Processing...")
    print()

    # Select workflow based on type
    if args.type == "weather":
        workflow_run = WeatherAnalysisWorkflow.run
        workflow_id = f"weather-analysis-{uuid.uuid4().hex[:8]}"
    else:
        workflow_run = MovieReviewWorkflow.run
        workflow_id = f"movie-review-{uuid.uuid4().hex[:8]}"

    # Execute the workflow
    result = await client.execute_workflow(
        workflow_run,
        prompt,
        id=workflow_id,
        task_queue="strands-structured-output",
    )

    print("-" * 50)
    print("Structured Output:")
    print("-" * 50)
    print(json.dumps(result, indent=2))
    print("-" * 50)
    print()
    print("View workflow in Temporal UI: http://localhost:8233")


if __name__ == "__main__":
    asyncio.run(main())
