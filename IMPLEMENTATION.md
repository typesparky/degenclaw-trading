# Implementation Checklist

## ✅ Done
- [x] Polymarket pricing engine (tiered safe pricing with moonshot premium)
- [x] Volume-aware spread adjustment (tight for high-vol, wide for low-vol)
- [x] Rebate-aware quoting (≤4.5¢ for maker rebate, ≤1.5¢ for liquidity rewards)
- [x] Market discovery (finds markets + token IDs from Polymarket API)
- [x] Cross-reference with ESPN betting odds
- [x] Bitunix connector (REST + WebSocket, all endpoints)
- [x] Cross-venue arb scanner (Bitunix vs DEX)
- [x] P&L tracking and logging
- [x] GitHub repo: https://github.com/typesparky/degenclaw-trading

## 🔄 To Do

### 1. Polymarket API Authentication (REQUIRED to place orders)
- [ ] Get Polymarket CLOB API key + secret + passphrase
- [ ] Set environment variables: `POLYMARKET_PRIVATE_KEY`, `POLYMARKET_API_KEY`, `POLYMARKET_API_SECRET`, `POLYMARKET_API_PASSPHRASE`
- [ ] Test order placement with small size ($10)
- [ ] Test order cancellation

### 2. Telegram Bot Setup (REQUIRED for notifications)
- [ ] Create Telegram bot via @BotFather (if not already done)
- [ ] Get bot token
- [ ] Start conversation with bot on Telegram
- [ ] Get chat ID
- [ ] Configure channel in Hermes gateway
- [ ] Test notification delivery

### 3. Bot Scheduling (REQUIRED for automation)
- [ ] Set up cron job or systemd service to run `start_bot.sh` every 6 hours
- [ ] Pre-match scan: 24h, 12h, 6h, 1h before each match
- [ ] Cancel all orders at kickoff
- [ ] Post-match: settle and log P&L

### 4. Live Sports Data (OPTIONAL - for in-play quoting)
- [ ] Polymarket Sports WebSocket already works (tested)
- [ ] ESPN scoreboard scraping for betting odds reference
- [ ] MLB Stats API for play-by-play (free, no key)
- [ ] Goal detection → cancel/replace quotes within 30s

### 5. Bitunix Live Trading (OPTIONAL - for CEX leg)
- [ ] Set Bitunix API keys: `BITUNIX_API_KEY`, `BITUNIX_SECRET_KEY`
- [ ] Test small market order (e.g., $10 BTC)
- [ ] Implement position management (stop-loss, take-profit)
- [ ] Wire into cross-venue arb scanner for automatic execution

### 6. Monitoring & Alerts
- [ ] P&L summary sent to Telegram daily
- [ ] Fill notifications in real-time
- [ ] Goal alerts during live matches
- [ ] Divergence alerts when spread > threshold

## Quick Start (Server)

```bash
# Clone
git clone git@github.com:typesparky/degenclaw-trading.git
cd degenclaw-trading

# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Dry run (see quotes without placing)
./start_bot.sh dry-run "France"

# Live (requires API keys)
export POLYMARKET_PRIVATE_KEY=0x...
./start_bot.sh live "France"

# Check P&L
./start_bot.sh status
```

## Environment Variables

```bash
# Polymarket (required for live trading)
POLYMARKET_PRIVATE_KEY=0x...
POLYMARKET_API_KEY=...
POLYMARKET_API_SECRET=...
POLYMARKET_API_PASSPHRASE=...

# Bitunix (required for CEX trading)
BITUNIX_API_KEY=...
BITUNIX_SECRET_KEY=...

# Telegram (required for notifications)
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## File Map

| File | Purpose |
|------|---------|
| `polymarket_bot_v3.py` | Main bot — pricing, quoting, WebSocket |
| `polymarket_safe_pricing_v2.py` | Standalone pricing calculator |
| `scan_polymarket.py` | Market scanner (CLI) |
| `notifier.py` | Notification formatter |
| `telegram_bridge.py` | Telegram delivery |
| `start_bot.sh` | Startup script |
| `bitunix_connector.py` | Bitunix exchange client |
| `exchange_integrator.py` | Unified data fetcher |
| `cross_venue_all.py` | Cross-venue arb scanner |
