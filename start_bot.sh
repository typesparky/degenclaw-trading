#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Trading Bot Startup Script
# Starts the Polymarket quoting bot with Telegram notifications
# ═══════════════════════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual environment
source .venv/bin/activate

# Check dependencies
echo "Checking dependencies..."
python3 -c "import polymarket; import websockets; import requests; import pandas; print('✓ All dependencies OK')"

# Parse arguments
MODE="${1:-dry-run}"
QUERY="${2:-Belgium}"
PRIVATE_KEY="${POLYMARKET_PRIVATE_KEY:-}"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Trading Bot Starting"
echo "  Mode: $MODE"
echo "  Query: $QUERY"
echo "  Key: ${PRIVATE_KEY:+set}"
echo "═══════════════════════════════════════════════════════════════"
echo ""

if [ "$MODE" == "live" ]; then
    if [ -z "$PRIVATE_KEY" ]; then
        echo "ERROR: POLYMARKET_PRIVATE_KEY not set"
        echo "Usage: POLYMARKET_PRIVATE_KEY=0x... ./start_bot.sh live 'Belgium'"
        exit 1
    fi
    python3 polymarket_bot_v3.py --live --query "$QUERY"
elif [ "$MODE" == "status" ]; then
    python3 polymarket_bot_v3.py --dry-run --query "" 2>/dev/null
    echo ""
    python3 notifier.py pnl
elif [ "$MODE" == "scan" ]; then
    echo "Running cross-venue scan..."
    python3 -c "
from exchange_integrator import fetch_bitunix_candles
import pandas as pd

# Scan Bitunix for low-volume coins with wide spreads
from bitunix_connector import BitunixRestClient
client = BitunixRestClient()
tickers = client.get_tickers()
active = sorted([t for t in tickers if t.turnover_24h > 1000], key=lambda x: x.turnover_24h)

print(f'Active coins: {len(active)}')
print()
for t in active[:20]:
    try:
        ob = client.get_depth(t.symbol, limit='5')
        if ob.best_bid and ob.best_ask:
            spread_bps = ob.spread_bps or 0
            print(f'{t.symbol:<18} Price: {t.last_price:>10.4f}  Spread: {spread_bps:>6.2f}bps  Vol24h: ${t.turnover_24h:>12.0f}')
    except:
        pass
"
else
    # Dry run (default)
    python3 polymarket_bot_v3.py --dry-run --query "$QUERY"
fi
