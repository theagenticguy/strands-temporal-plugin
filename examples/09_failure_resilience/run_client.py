#!/usr/bin/env python3
"""Failure Resilience Client

Run different failure scenarios to observe Temporal's recovery behavior.

Prerequisites:
    1. Temporal server running: temporal server start-dev
    2. Worker running: python run_worker.py

Usage:
    cd examples/09_failure_resilience

    # Scenario 1: Transient failures with automatic retry
    uv run python run_client.py transient

    # Scenario 2: Slow tool with heartbeat timeout
    uv run python run_client.py timeout

    # Scenario 3: Permanent failure with graceful degradation
    uv run python run_client.py degradation

    # Run all scenarios
    uv run python run_client.py all
"""

import argparse
import asyncio
import uuid

from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client
from workflow import (
    GracefulDegradationWorkflow,
    TimeoutRecoveryWorkflow,
    TransientFailureWorkflow,
)

SCENARIOS = {
    "transient": {
        "workflow": TransientFailureWorkflow,
        "prompt": "Search for information about Temporal workflow engines and calculate 256 * 3.",
        "description": (
            "The flaky_api_call tool fails with ConnectionError on attempts 1 and 2,\n"
            "  then succeeds on attempt 3. Temporal retries automatically.\n"
            "  Watch the worker logs to see the retry attempts."
        ),
    },
    "timeout": {
        "workflow": TimeoutRecoveryWorkflow,
        "prompt": "Query the 'metrics' database table and calculate the average of 10, 20, 30, 40, 50.",
        "description": (
            "The slow_database_query tool takes 5 seconds (configurable via SLOW_DB_SECONDS).\n"
            "  Heartbeat timeout is set to 10s, so it completes normally.\n"
            "  Set SLOW_DB_SECONDS=15 to trigger a heartbeat timeout."
        ),
    },
    "degradation": {
        "workflow": GracefulDegradationWorkflow,
        "prompt": "Send a webhook to https://example.com/hook with payload 'test' AND calculate 100 / 7.",
        "description": (
            "The unreliable_webhook tool always fails (simulates a down service).\n"
            "  After 3 retry attempts, the error reaches the agent.\n"
            "  The agent reports the webhook failure but still completes the calculation."
        ),
    },
}


async def run_scenario(client: Client, name: str, scenario: dict) -> None:
    """Run a single failure scenario."""
    print(f"Scenario: {name}")
    print(f"  {scenario['description']}")
    print()
    print(f"  Prompt: {scenario['prompt']}")
    print("  Processing...")
    print()

    try:
        result = await client.execute_workflow(
            scenario["workflow"].run,
            scenario["prompt"],
            id=f"resilience-{name}-{uuid.uuid4().hex[:8]}",
            task_queue="strands-resilience",
        )

        print("  " + "-" * 50)
        print("  Result:")
        print("  " + "-" * 50)
        for line in str(result).split("\n"):
            print(f"  {line}")
        print("  " + "-" * 50)

    except Exception as e:
        print(f"  ERROR: {e}")

    print()


async def main():
    parser = argparse.ArgumentParser(
        description="Run failure resilience scenarios",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Scenarios:
  transient    - Flaky API retried automatically (succeeds on 3rd attempt)
  timeout      - Slow database query with heartbeat monitoring
  degradation  - Permanent webhook failure handled gracefully by agent

Environment variables:
  FLAKY_FAILURES=N     Number of failures before success (default: 2)
  SLOW_DB_SECONDS=N    Database query delay in seconds (default: 5)
        """,
    )
    parser.add_argument(
        "scenario",
        choices=["transient", "timeout", "degradation", "all"],
        help="Which failure scenario to run",
    )

    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  Strands Temporal - Failure Resilience Client")
    print("=" * 60)
    print()

    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )
    print("[OK] Connected to Temporal")
    print()

    if args.scenario == "all":
        scenarios_to_run = ["transient", "timeout", "degradation"]
    else:
        scenarios_to_run = [args.scenario]

    for name in scenarios_to_run:
        print("-" * 60)
        await run_scenario(client, name, SCENARIOS[name])

    print("=" * 60)
    print("Done! View workflow history in Temporal UI: http://localhost:8233")
    print()
    print("What to look for in the UI:")
    print("  - transient: Activity retries visible in event history")
    print("  - timeout:   Heartbeat details on slow_database_query activity")
    print("  - degradation: Failed activity + successful workflow completion")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
