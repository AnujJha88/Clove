#!/bin/bash
#
# CloveOS YC Demo Runner
#
# This script runs the full agentic demo with a sample query.
#
# Usage:
#   ./run_demo.sh                    # Default query
#   ./run_demo.sh "Your query here"  # Custom query
#   ./run_demo.sh --chaos            # With chaos injection
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLOVE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║           CloveOS - YC Agentic Demo                       ║"
echo "║   'Reliable Control for Agentic/ML Systems'               ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check if kernel is running
if ! [ -S /tmp/clove.sock ]; then
    echo -e "${RED}Error: CloveOS kernel not running${NC}"
    echo ""
    echo "Start the kernel first:"
    echo "  cd $CLOVE_ROOT/build && ./clove_kernel"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓ Kernel detected${NC}"

# Default query
QUERY="${1:-What are the latest breakthroughs in protein folding and structure prediction?}"

# Check for flags
CHAOS_FLAG=""
SCOUTS=2

for arg in "$@"; do
    case $arg in
        --chaos)
            CHAOS_FLAG="--chaos"
            echo -e "${YELLOW}⚡ Chaos mode enabled${NC}"
            ;;
        --scouts=*)
            SCOUTS="${arg#*=}"
            ;;
    esac
done

echo ""
echo -e "${CYAN}Query:${NC} $QUERY"
echo -e "${CYAN}Scouts:${NC} $SCOUTS"
echo ""

# Run the mission
cd "$SCRIPT_DIR"
python3 mission_control.py "$QUERY" --scouts "$SCOUTS" $CHAOS_FLAG

echo ""
echo -e "${GREEN}Demo complete!${NC}"
echo ""
echo "Generated files in: $SCRIPT_DIR/outputs/"
