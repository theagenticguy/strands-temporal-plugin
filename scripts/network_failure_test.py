#!/usr/bin/env python3
"""Manual Network Failure Test for Strands Temporal Plugin.

This script tests the crash-proof capabilities of the strands-temporal-plugin
by simulating network failures to Bedrock during agent execution.

Prerequisites:
1. Running Temporal server (temporal server start-dev)
2. AWS credentials configured
3. sudo access for network manipulation

Usage:
    # Terminal 1: Start the worker
    python examples/basic_weather_agent/run_worker.py

    # Terminal 2: Run this test
    sudo python scripts/network_failure_test.py

What it does:
1. Starts a workflow that calls Bedrock
2. After N seconds, blocks network traffic to Bedrock
3. The activity should fail and start retrying
4. After M seconds, unblocks the network
5. The activity should succeed on retry
6. Verifies the workflow completed successfully
"""

import argparse
import asyncio
import logging
import os
import signal
import subprocess
import sys
from datetime import timedelta

# Add src to path for development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)


# =============================================================================
# macOS Network Blocking
# =============================================================================


class MacOSNetworkBlocker:
    """Block network traffic to specific hosts on macOS using pfctl.

    Uses the packet filter (pf) to block outgoing traffic to Bedrock endpoints.
    Requires sudo privileges.
    """

    BEDROCK_HOSTS = [
        "bedrock-runtime.us-east-1.amazonaws.com",
        "bedrock-agent-runtime.us-east-1.amazonaws.com",
        # Add other regions as needed
        "bedrock-runtime.us-west-2.amazonaws.com",
        "bedrock-agent-runtime.us-west-2.amazonaws.com",
    ]

    PF_RULES_FILE = "/tmp/strands_temporal_pf_rules.conf"
    PF_ANCHOR = "strands_temporal_test"

    def __init__(self):
        self._is_blocked = False
        self._original_pf_enabled = None

    def _check_sudo(self) -> bool:
        """Check if we have sudo privileges."""
        return os.geteuid() == 0

    def _get_host_ips(self, hostname: str) -> list[str]:
        """Resolve hostname to IP addresses."""
        import socket
        try:
            ips = socket.getaddrinfo(hostname, 443, socket.AF_INET)
            return list(set(ip[4][0] for ip in ips))
        except socket.gaierror:
            logger.warning(f"Could not resolve {hostname}")
            return []

    def _create_pf_rules(self) -> str:
        """Generate pf rules to block Bedrock traffic."""
        rules = []
        rules.append(f"# Strands Temporal Plugin - Network Failure Test Rules")
        rules.append(f"# Generated automatically - DO NOT EDIT")
        rules.append("")

        for host in self.BEDROCK_HOSTS:
            ips = self._get_host_ips(host)
            for ip in ips:
                # Block outgoing TCP to port 443 (HTTPS)
                rules.append(f"block drop out quick proto tcp to {ip} port 443")
            if ips:
                rules.append(f"# {host} -> {', '.join(ips)}")

        return "\n".join(rules)

    def block(self) -> bool:
        """Block traffic to Bedrock endpoints.

        Returns:
            True if blocking was successful, False otherwise.
        """
        if not self._check_sudo():
            logger.error("This script requires sudo privileges to manipulate network")
            return False

        if self._is_blocked:
            logger.warning("Network is already blocked")
            return True

        try:
            # Generate and write rules
            rules = self._create_pf_rules()
            with open(self.PF_RULES_FILE, "w") as f:
                f.write(rules)

            logger.info(f"Created pf rules at {self.PF_RULES_FILE}")
            logger.info("Rules:\n" + rules)

            # Check if pf is currently enabled
            result = subprocess.run(
                ["pfctl", "-s", "info"],
                capture_output=True,
                text=True
            )
            self._original_pf_enabled = "Status: Enabled" in result.stdout

            # Load and enable rules
            subprocess.run(
                ["pfctl", "-f", self.PF_RULES_FILE],
                check=True,
                capture_output=True
            )

            # Enable pf if not already enabled
            if not self._original_pf_enabled:
                subprocess.run(
                    ["pfctl", "-e"],
                    check=True,
                    capture_output=True
                )

            self._is_blocked = True
            logger.info("Network traffic to Bedrock is now BLOCKED")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to configure pf: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Failed to block network: {e}")
            return False

    def unblock(self) -> bool:
        """Remove Bedrock traffic blocking.

        Returns:
            True if unblocking was successful, False otherwise.
        """
        if not self._is_blocked:
            logger.warning("Network is not blocked")
            return True

        try:
            # Flush all rules
            subprocess.run(
                ["pfctl", "-F", "all"],
                check=True,
                capture_output=True
            )

            # Disable pf if it wasn't enabled before
            if self._original_pf_enabled is False:
                subprocess.run(
                    ["pfctl", "-d"],
                    check=True,
                    capture_output=True
                )

            # Clean up rules file
            if os.path.exists(self.PF_RULES_FILE):
                os.remove(self.PF_RULES_FILE)

            self._is_blocked = False
            logger.info("Network traffic to Bedrock is now UNBLOCKED")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to remove pf rules: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Failed to unblock network: {e}")
            return False

    def is_blocked(self) -> bool:
        """Check if blocking is currently active."""
        return self._is_blocked


class LinuxNetworkBlocker:
    """Block network traffic on Linux using iptables."""

    BEDROCK_HOSTS = MacOSNetworkBlocker.BEDROCK_HOSTS

    def __init__(self):
        self._is_blocked = False
        self._blocked_ips: set[str] = set()

    def _get_host_ips(self, hostname: str) -> list[str]:
        """Resolve hostname to IP addresses."""
        import socket
        try:
            ips = socket.getaddrinfo(hostname, 443, socket.AF_INET)
            return list(set(ip[4][0] for ip in ips))
        except socket.gaierror:
            return []

    def block(self) -> bool:
        """Block traffic using iptables."""
        if os.geteuid() != 0:
            logger.error("Requires root privileges")
            return False

        try:
            for host in self.BEDROCK_HOSTS:
                for ip in self._get_host_ips(host):
                    subprocess.run(
                        ["iptables", "-A", "OUTPUT", "-d", ip, "-p", "tcp",
                         "--dport", "443", "-j", "DROP"],
                        check=True
                    )
                    self._blocked_ips.add(ip)

            self._is_blocked = True
            logger.info("Network blocked via iptables")
            return True
        except Exception as e:
            logger.error(f"Failed to block: {e}")
            return False

    def unblock(self) -> bool:
        """Remove iptables rules."""
        try:
            for ip in self._blocked_ips:
                subprocess.run(
                    ["iptables", "-D", "OUTPUT", "-d", ip, "-p", "tcp",
                     "--dport", "443", "-j", "DROP"],
                    check=False  # Don't fail if rule doesn't exist
                )
            self._blocked_ips.clear()
            self._is_blocked = False
            logger.info("Network unblocked")
            return True
        except Exception as e:
            logger.error(f"Failed to unblock: {e}")
            return False

    def is_blocked(self) -> bool:
        return self._is_blocked


def get_network_blocker():
    """Get the appropriate network blocker for the current platform."""
    import platform
    system = platform.system()

    if system == "Darwin":
        return MacOSNetworkBlocker()
    elif system == "Linux":
        return LinuxNetworkBlocker()
    else:
        raise NotImplementedError(f"Network blocking not implemented for {system}")


# =============================================================================
# Temporal Client Helpers
# =============================================================================


async def run_workflow_with_failure(
    block_after_seconds: float = 2.0,
    unblock_after_seconds: float = 5.0,
    prompt: str = "What's the weather in Seattle?",
    task_queue: str = "strands-agents",
) -> dict:
    """Run a workflow and inject network failure mid-execution.

    Args:
        block_after_seconds: Time to wait before blocking network
        unblock_after_seconds: Time to wait before unblocking (from start)
        prompt: The prompt to send to the agent
        task_queue: Temporal task queue name

    Returns:
        Dictionary with test results
    """
    from temporalio.client import Client

    # Import the workflow
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples", "basic_weather_agent"))
    from workflows import FullyDurableWeatherAgent

    blocker = get_network_blocker()
    results = {
        "success": False,
        "workflow_result": None,
        "error": None,
        "network_blocked_at": None,
        "network_unblocked_at": None,
    }

    # Setup signal handler for cleanup
    def cleanup_handler(signum, frame):
        logger.info("Received signal, cleaning up...")
        blocker.unblock()
        sys.exit(1)

    signal.signal(signal.SIGINT, cleanup_handler)
    signal.signal(signal.SIGTERM, cleanup_handler)

    try:
        # Connect to Temporal
        client = await Client.connect("localhost:7233")
        logger.info("Connected to Temporal server")

        # Start the workflow
        logger.info(f"Starting workflow with prompt: {prompt}")
        handle = await client.start_workflow(
            FullyDurableWeatherAgent.run,
            prompt,
            id=f"network-failure-test-{int(asyncio.get_event_loop().time())}",
            task_queue=task_queue,
        )
        logger.info(f"Workflow started: {handle.id}")

        # Schedule network blocking
        async def block_network():
            await asyncio.sleep(block_after_seconds)
            logger.info(f"Blocking network after {block_after_seconds}s")
            blocker.block()
            results["network_blocked_at"] = asyncio.get_event_loop().time()

        async def unblock_network():
            await asyncio.sleep(unblock_after_seconds)
            logger.info(f"Unblocking network after {unblock_after_seconds}s")
            blocker.unblock()
            results["network_unblocked_at"] = asyncio.get_event_loop().time()

        # Run workflow with network manipulation
        block_task = asyncio.create_task(block_network())
        unblock_task = asyncio.create_task(unblock_network())

        try:
            # Wait for workflow completion with timeout
            result = await asyncio.wait_for(
                handle.result(),
                timeout=120.0  # 2 minute timeout
            )
            results["success"] = True
            results["workflow_result"] = result
            logger.info(f"Workflow completed successfully: {result[:100]}...")

        except asyncio.TimeoutError:
            results["error"] = "Workflow timed out"
            logger.error("Workflow timed out")

        except Exception as e:
            results["error"] = str(e)
            logger.error(f"Workflow failed: {e}")

        # Cancel any pending tasks
        block_task.cancel()
        unblock_task.cancel()

    except Exception as e:
        results["error"] = str(e)
        logger.exception(f"Test failed: {e}")

    finally:
        # Always cleanup
        blocker.unblock()

    return results


# =============================================================================
# CLI Interface
# =============================================================================


async def main():
    parser = argparse.ArgumentParser(
        description="Test strands-temporal-plugin crash-proof capabilities"
    )
    parser.add_argument(
        "--block-after",
        type=float,
        default=2.0,
        help="Seconds to wait before blocking network (default: 2.0)"
    )
    parser.add_argument(
        "--unblock-after",
        type=float,
        default=8.0,
        help="Seconds to wait before unblocking network (default: 8.0)"
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="What's the weather in Seattle and Tokyo?",
        help="Prompt to send to the agent"
    )
    parser.add_argument(
        "--task-queue",
        type=str,
        default="strands-agents",
        help="Temporal task queue name (default: strands-agents)"
    )
    parser.add_argument(
        "--block-only",
        action="store_true",
        help="Only block network (for manual testing)"
    )
    parser.add_argument(
        "--unblock-only",
        action="store_true",
        help="Only unblock network (cleanup)"
    )

    args = parser.parse_args()

    if args.block_only:
        blocker = get_network_blocker()
        if blocker.block():
            logger.info("Network blocked. Run with --unblock-only to restore.")
        return

    if args.unblock_only:
        blocker = get_network_blocker()
        blocker.unblock()
        logger.info("Network unblocked.")
        return

    # Run the full test
    results = await run_workflow_with_failure(
        block_after_seconds=args.block_after,
        unblock_after_seconds=args.unblock_after,
        prompt=args.prompt,
        task_queue=args.task_queue,
    )

    # Print results
    print("\n" + "=" * 60)
    print("TEST RESULTS")
    print("=" * 60)
    print(f"Success: {results['success']}")
    if results['workflow_result']:
        print(f"Result: {results['workflow_result'][:200]}...")
    if results['error']:
        print(f"Error: {results['error']}")
    print("=" * 60)

    return 0 if results['success'] else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
