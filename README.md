# Trading System — Quick Start

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Polymarket Bot │     │  Bitunix Connector│     │ Cross-Venue Arb │
│  polymarket_    │     │  bitunix_        │     │ cross_venue_    │
│  bot_v3.py      │     │  connector.py    │     │ all.py          │
└────────┬────────┘     └────────┬─────────┘     └────────┬────────┘
         │                       │                        │
         └───────────┬───────────┘                        │
                     │                                    │
         ┌───────────▼───────────┐                        │
         │  Exchange Integrator  │◄───────────────────────┘
         │  exchange_integrator  │
         │  .py                  │
         └───────────┬───────────┘
                     │
         ┌───────────▼───────────┐
         │  Notifier             │
         │  notifier.py          │
         └───────────┬───────────┘
                     │
         ┌───────────▼───────────┐
         │  Hermes Gateway       │
         │  (Telegram bridge)    │
         └───────────────────────┘
```

## Setup

```bash
cd ~/hermes-workspace/degenclaw-trading
python3 -m venv .venv
source .venv/bin/activate
pip install polymarket-client websockets requests pandas pyarrow matplotlib
```

## Environment Variables

```bash
# Polymarket (for live trading)
export POLYMARKET_PRIVATE_KEY=0x...
export POLYMARKET_WALLET_ADDRESS=0x...  # Optional

# Bitunix (for live trading)
export BITUNIX_API_KEY=...
export BITUNIX_SECRET_KEY=...
```

## Usage

### Polymarket Bot

```bash
# Dry run — see quotes without placing orders
./start_bot.sh dry-run "Belgium"

# Live trading (places real orders)
POLYMARKET_PRIVATE_KEY=0x... ./start_bot.sh live "Spain"

# Check P&L status
./start_bot.sh status

# Scan for arb opportunities
./start_bot.sh scan
```

### Bitunix Connector

```bash
# Test connection
python3 bitunix_connector.py

# Fetch candles
python3 -c "
from bitunix_connector import fetch_bitunix_candles
df = fetch_bitunix_candles('BTCUSDT', interval='1m', limit=100)
print(df.tail())
"
```

### Cross-Venue Arb Scanner

```bash
python3 -c "
from cross_venue_all import load_all_series, plot_prices_and_spreads

# Compare BTC across venues
sources = [
    ('bitunix:BTCUSDT', 'cex_live', None, None),
    ('flx:BTC', 'dex', 'flx', ['flx:BTC']),
]
data = load_all_series('BTC', sources)
for v, df in data.items():
    print(f'{v}: {len(df)} candles, latest={df[\"close\"].iloc[-1]:.2f}')
"
```

### Notifications

```bash
# Send a quote alert
python3 notifier.py quote "BTC" 0.42 0.19 0.65 500 121.1

# Send a fill notification
python3 notifier.py fill "BTC" BUY 0.19 500 2.31 0.58

# Send a goal alert
python3 notifier.py goal "Spain vs Cape Verde" "1-0" "1H" "36:00"

# Check P&L
python3 notifier.py pnl
```

### Dashboard

```bash
# View the Bitunix backtest dashboard
open diagnostics_output/bitunix_backtest_dashboard.html
```

## File Reference

| File | Purpose |
|------|---------|
| `polymarket_bot_v3.py` | Main Polymarket quoting bot |
| `bitunix_connector.py` | Bitunix exchange REST + WebSocket client |
| `exchange_integrator.py` | Unified exchange data fetcher |
| `cross_venue_all.py` | Cross-venue arbitrage scanner |
| `notifier.py` | Notification formatter |
| `start_bot.sh` | Startup script |
| `polymarket_safe_pricing_v2.py` | Pricing calculator |
| `polymarket_ev_logic.py` | EV verification |
| `bitunix_backtest_dashboard.html` | Interactive dashboard |

## Pricing Strategy

The bot uses tiered safe pricing:

| Probability | Bid | Ask | Buffer |
|-------------|-----|-----|--------|
| ≥30% | fair × 0.50 − 2¢ | fair × 1.50 + 2¢ | 50% survival |
| 10-30% | fair × 0.60 − 3¢ | fair × 1.40 + 3¢ | 40% vol factor |
| 3-10% | min(fair − 5¢, fair × 0.50) | fair + 10¢ | Absolute 5¢ |
| <3% | min(fair − 10¢, fair × 0.30) | fair + 20¢ | Absolute 10¢ |

## Fee Structure

**Polymarket Sports:**
- Taker fee: 3% (fee curve: C × 0.03 × p × (1-p))
- Maker rebate: 25% of taker fee
- Min rebate size: $200 per trade
- Max rebate spread: 4.5¢ (our quotes are wider — we sacrifice rebate for safety)

**Bitunix:**
- Check `bitunix_connector.py` `get_fee_schedule()` for current rates

## Safety Notes

1. Always start with `--dry-run` to verify quotes
2. Start with small sizes ($100-$200 per quote)
3. The wide spreads mean low fill rate — this is by design
4. Monitor P&L with `./start_bot.sh status`
5. On goals, the bot cancels stale orders and recalculates
