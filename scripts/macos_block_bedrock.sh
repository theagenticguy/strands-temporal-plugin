#!/bin/bash
#
# macOS Network Blocker for Bedrock Endpoints
#
# This script blocks/unblocks network traffic to AWS Bedrock endpoints
# using macOS's packet filter (pf). Used for testing crash-proof capabilities
# of the strands-temporal-plugin.
#
# Usage:
#   sudo ./macos_block_bedrock.sh block    # Block Bedrock traffic
#   sudo ./macos_block_bedrock.sh unblock  # Unblock Bedrock traffic
#   sudo ./macos_block_bedrock.sh status   # Check if blocking is active
#
# Requires: sudo privileges
#

set -e

# Bedrock endpoints to block
BEDROCK_HOSTS=(
    "bedrock-runtime.us-east-1.amazonaws.com"
    "bedrock-agent-runtime.us-east-1.amazonaws.com"
    "bedrock-runtime.us-west-2.amazonaws.com"
    "bedrock-agent-runtime.us-west-2.amazonaws.com"
)

PF_RULES_FILE="/tmp/strands_bedrock_block.conf"
MARKER_FILE="/tmp/.strands_bedrock_blocked"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

resolve_host() {
    local host=$1
    # Get all IPv4 addresses for the host
    dig +short "$host" A 2>/dev/null | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' || true
}

generate_rules() {
    echo "# Strands Temporal Plugin - Bedrock Blocking Rules"
    echo "# Generated: $(date)"
    echo ""

    for host in "${BEDROCK_HOSTS[@]}"; do
        ips=$(resolve_host "$host")
        if [[ -n "$ips" ]]; then
            echo "# $host"
            for ip in $ips; do
                echo "block drop out quick proto tcp to $ip port 443"
            done
            echo ""
        else
            echo "# WARNING: Could not resolve $host"
        fi
    done
}

do_block() {
    check_root

    if [[ -f "$MARKER_FILE" ]]; then
        log_warn "Bedrock traffic is already blocked"
        return 0
    fi

    log_info "Resolving Bedrock endpoints..."
    generate_rules > "$PF_RULES_FILE"

    log_info "Generated rules:"
    cat "$PF_RULES_FILE"

    log_info "Loading pf rules..."
    pfctl -f "$PF_RULES_FILE" 2>/dev/null

    log_info "Enabling pf..."
    pfctl -e 2>/dev/null || true

    # Create marker file
    touch "$MARKER_FILE"

    log_info "Bedrock traffic is now BLOCKED"
    echo ""
    log_warn "Don't forget to run: sudo $0 unblock"
}

do_unblock() {
    check_root

    if [[ ! -f "$MARKER_FILE" ]]; then
        log_warn "Bedrock traffic is not currently blocked"
        return 0
    fi

    log_info "Flushing pf rules..."
    pfctl -F all 2>/dev/null || true

    log_info "Disabling pf..."
    pfctl -d 2>/dev/null || true

    # Clean up files
    rm -f "$PF_RULES_FILE"
    rm -f "$MARKER_FILE"

    log_info "Bedrock traffic is now UNBLOCKED"
}

do_status() {
    if [[ -f "$MARKER_FILE" ]]; then
        log_info "Bedrock traffic is currently BLOCKED"
        if [[ -f "$PF_RULES_FILE" ]]; then
            echo ""
            echo "Active rules in $PF_RULES_FILE:"
            cat "$PF_RULES_FILE"
        fi
    else
        log_info "Bedrock traffic is NOT blocked"
    fi

    echo ""
    echo "pf status:"
    pfctl -s info 2>/dev/null | head -5 || echo "Could not get pf status (not root?)"
}

do_test_connectivity() {
    log_info "Testing connectivity to Bedrock endpoints..."
    echo ""

    for host in "${BEDROCK_HOSTS[@]}"; do
        echo -n "  $host: "
        if curl -s --connect-timeout 3 "https://$host" >/dev/null 2>&1; then
            echo -e "${GREEN}REACHABLE${NC}"
        else
            echo -e "${RED}BLOCKED/UNREACHABLE${NC}"
        fi
    done
}

usage() {
    echo "Usage: sudo $0 {block|unblock|status|test}"
    echo ""
    echo "Commands:"
    echo "  block    - Block traffic to Bedrock endpoints"
    echo "  unblock  - Unblock traffic to Bedrock endpoints"
    echo "  status   - Show current blocking status"
    echo "  test     - Test connectivity to Bedrock endpoints"
    echo ""
    echo "Example workflow for testing crash-proof capabilities:"
    echo "  1. Start Temporal: temporal server start-dev"
    echo "  2. Start worker: python examples/basic_weather_agent/run_worker.py"
    echo "  3. Start a workflow: python examples/basic_weather_agent/run_client.py"
    echo "  4. Block network: sudo $0 block"
    echo "  5. Observe activity retries in Temporal UI (http://localhost:8233)"
    echo "  6. Unblock network: sudo $0 unblock"
    echo "  7. Observe workflow completion"
}

case "$1" in
    block)
        do_block
        ;;
    unblock)
        do_unblock
        ;;
    status)
        do_status
        ;;
    test)
        do_test_connectivity
        ;;
    *)
        usage
        exit 1
        ;;
esac
