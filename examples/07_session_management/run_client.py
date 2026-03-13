#!/usr/bin/env python3
"""Session Management Client

Connects to Temporal and executes the session management workflow.

Usage:
    # Make sure the worker is running first, then:
    cd examples/07_session_management

    # Single turn
    uv run python run_client.py --prompt "Remember that my favorite color is blue"

    # Multi-turn demo (2 sequential workflow executions with same session)
    uv run python run_client.py --multi-turn

    # Custom session ID
    uv run python run_client.py --session-id user-123 --prompt "Hello!"

    # With LocalStack
    AWS_ENDPOINT_URL=http://localhost:4566 uv run python run_client.py --multi-turn
"""

import argparse
import asyncio
import uuid

from strands_temporal_plugin import StrandsTemporalPlugin
from temporalio.client import Client
from workflow import SessionWorkflow


async def main():
    """Execute the session management workflow."""
    parser = argparse.ArgumentParser(description="Session Management Client")
    parser.add_argument(
        "--session-id",
        type=str,
        default="demo",
        help="Session identifier (default: demo)",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="Prompt to send to the agent",
    )
    parser.add_argument(
        "--bucket",
        type=str,
        default="agent-sessions",
        help="S3 bucket for session storage (default: agent-sessions)",
    )
    parser.add_argument(
        "--region",
        type=str,
        default="us-east-1",
        help="AWS region (default: us-east-1)",
    )
    parser.add_argument(
        "--multi-turn",
        action="store_true",
        help="Run a multi-turn demo with 2 sequential workflow executions",
    )
    args = parser.parse_args()

    print()
    print("=" * 50)
    print("  Strands Temporal - Session Management Client")
    print("=" * 50)
    print()

    # Connect to Temporal
    client = await Client.connect(
        "localhost:7233",
        plugins=[StrandsTemporalPlugin()],
    )
    print("[OK] Connected to Temporal")
    print()

    if args.multi_turn:
        # Multi-turn demo: 2 sequential executions with the same session
        session_id = args.session_id
        turns = [
            "Remember that my favorite color is blue and I have a meeting at 3pm.",
            "What did I tell you to remember?",
        ]

        for i, prompt in enumerate(turns, 1):
            print(f"--- Turn {i} ---")
            print(f"Session: {session_id}")
            print(f"Prompt: {prompt}")
            print("Processing...")
            print()

            input_data = {
                "prompt": prompt,
                "session_id": session_id,
                "bucket": args.bucket,
                "region_name": args.region,
            }

            result = await client.execute_workflow(
                SessionWorkflow.run,
                input_data,
                id=f"session-{session_id}-{uuid.uuid4().hex[:8]}",
                task_queue="strands-session",
            )

            print("Response:")
            print(result)
            print()

        print("=" * 50)
        print("Multi-turn demo complete!")
        print("The agent remembered facts from Turn 1 and recalled them in Turn 2.")
        print("Session state was persisted to S3 between workflow executions.")
    else:
        # Single turn
        prompt = args.prompt or "Remember that my favorite color is blue."

        print(f"Session: {args.session_id}")
        print(f"Prompt: {prompt}")
        print("Processing...")
        print()

        input_data = {
            "prompt": prompt,
            "session_id": args.session_id,
            "bucket": args.bucket,
            "region_name": args.region,
        }

        result = await client.execute_workflow(
            SessionWorkflow.run,
            input_data,
            id=f"session-{args.session_id}-{uuid.uuid4().hex[:8]}",
            task_queue="strands-session",
        )

        print("-" * 50)
        print("Response:")
        print("-" * 50)
        print(result)
        print("-" * 50)

    print()
    print("View workflow in Temporal UI: http://localhost:8233")


if __name__ == "__main__":
    asyncio.run(main())
