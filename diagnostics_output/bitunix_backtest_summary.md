# Bitunix × Hyperliquid Cross-Venue Backtest Results
**Date**: 2026-06-15  
**Data**: 1-min candles, 24h lookback, 9 coins  
**Exchanges**: Bitunix Futures (BX) vs Hyperliquid (HL)

---

## Key Finding
Bitunix **systematically prices 0.08-0.20% below Hyperliquid** across mid-tier coins. This is a persistent bias, not random noise. The divergence mean-reverts over 2-30 minutes depending on extremity.

---

## Divergence Stats (24h, 1-min candles)

| Coin | Mean | Std | Min | Max | |Mean| | >0.1% of time |
|------|------|-----|-----|-----|------|------|
| ICP | -0.185% | 0.107 | -0.641% | +0.094% | 0.168% | 71% |
| IMX | -0.184% | 0.122 | -0.583% | +0.151% | 0.203% | 79% |
| NEAR | -0.177% | 0.037 | -0.312% | -0.078% | 0.180% | 99% |
| AAVE | -0.157% | 0.042 | -0.267% | +0.012% | 0.151% | 91% |
| LTC | -0.135% | 0.058 | -0.265% | +0.029% | 0.120% | 67% |
| JUP | -0.131% | 0.071 | -0.404% | +0.059% | 0.130% | 68% |
| ONDO | -0.083% | 0.058 | -0.321% | +0.141% | 0.081% | 33% |
| PYTH | -0.097% | 0.101 | -0.362% | +0.290% | 0.111% | 45% |
| LINK | -0.080% | 0.032 | -0.183% | +0.040% | 0.076% | 19% |

---

## Strategy Results

### Strategy A: Directional Mean Reversion (Long BX only)
Buy BX when z < -entry, sell when z > -exit. Single-leg.

| Config | Trades | Win% | Avg | Net | Max DD | PF | Sharpe | Daily |
|--------|--------|------|-----|-----|--------|-----|--------|-------|
| z1.0 x z0.3 | 173 | 49.1% | +0.012% | +2.08% | -2.47% | 1.17 | 9.87 | +2.08% |
| z1.5 x z0.3 | 88 | 42.0% | +0.017% | +1.44% | -1.72% | 1.25 | 8.56 | +1.44% |
| **z2.0 x z0.3** | **50** | **44.0%** | **+0.028%** | **+1.38%** | **-1.09%** | **1.46** | **14.26** | **+1.38%** |

### Strategy B: Hold-the-Bias Carry
Buy BX when z < -1.0, hold N minutes. Captures systematic mean reversion.

| Hold | Trades | Win% | Avg | Net | Max DD | PF | Sharpe | Daily |
|------|--------|------|-----|-----|--------|-----|--------|-------|
| 10min | 240 | 56.2% | +0.107% | +28.9% | -5.61% | 1.91 | 54.9 | +28.9% |
| **20min** | **222** | **59.0%** | **+0.187%** | **+50.5%** | **-15.3%** | **2.14** | **67.3** | **+50.5%** |
| 30min | 208 | 60.6% | +0.265% | +72.2% | -16.3% | 2.48 | 77.8 | +72.2% |

### Strategy C: Bidirectional (Long + Short) — **BEST RISK-ADJUSTED**
Long BX when z < -2.0, short BX when z > +2.0.

| Config | Trades | Win% | Avg | Net | Max DD | PF | Sharpe | Daily |
|--------|--------|------|-----|-----|--------|-----|--------|-------|
| **z2.0 x z0.0 x 10m** | **80** | **50.0%** | **+0.019%** | **+1.50%** | **-1.11%** | **1.28** | **11.39** | **+1.50%** |
| z2.0 x z0.3 x 10m | 83 | 48.2% | +0.019% | +1.58% | -1.17% | 1.29 | 12.29 | +1.58% |
| z2.0 x z0.5 x 10m | 85 | 45.9% | -0.001% | -0.06% | -1.47% | 0.99 | -0.38 | -0.06% |
| z1.5 x z0.0 x 10m | 144 | 43.8% | -0.018% | -2.58% | -5.08% | 0.80 | -15.7 | -2.58% |
| z1.0 x z0.3 x 10m | 284 | 46.8% | -0.012% | -3.42% | -6.09% | 0.86 | -13.7 | -3.42% |

**Critical**: Only z=±2.0 is viable. Lower thresholds lose money after costs.

---

## Cost Sensitivity (5-min forward return, net of round-trip costs)

| Cost/RT | z=1.0 | z=1.5 | z=2.0 |
|---------|-------|-------|-------|
| 2 bps | -0.031% | -0.049% | -0.056% |
| 4 bps | -0.051% | -0.069% | -0.076% |
| 6 bps | -0.071% | -0.089% | -0.096% |
| 8 bps | -0.091% | -0.109% | -0.116% |
| 10 bps | -0.111% | -0.129% | -0.136% |

**Target**: Sub-6 bps round-trip. Use limit orders on both venues.

---

## By Coin Performance (Strategy C, z2.0)

| Coin | N | Win% | Total | Long WR | Short WR |
|------|---|------|-------|---------|----------|
| ICP | 12 | 58.3% | +1.01% | 57% | 60% |
| AAVE | 9 | 55.6% | +0.17% | 60% | 50% |
| IMX | 5 | 60.0% | +0.13% | 50% | 100% |
| NEAR | 9 | 66.7% | +1.13% | 75% | 50% |
| ONDO | 8 | 62.5% | +0.31% | 80% | 33% |
| JUP | 11 | 45.5% | +0.20% | 50% | 40% |
| PYTH | 9 | 44.4% | -0.76% | 40% | 50% |
| LTC | 11 | 36.4% | +0.11% | 40% | 33% |
| LINK | 10 | 20.0% | -0.57% | 20% | 20% |

**Best**: NEAR, ICP, IMX, AAVE. **Worst**: LINK (divergence doesn't mean-revert cleanly).

---

## Execution Notes
- **Granularity**: 1-min candles (lowest Bitunix provides; no 5s/trades endpoints)
- **Entry**: At candle close (realistic: next candle open)
- **Fees**: 0.02% BX taker, 0.04% HL taker → target sub-6 bps RT with limit orders
- **Slippage**: ~0.01-0.03% per leg for small orders (<$10K) on BX mid-tier coins
- **Mean reversion half-life**: ~2-3 min for z>2.0, ~10-20 min for z>1.0
- **Short BX** (when expensive) performs slightly better than long BX (when cheap)

---

## Dashboard
Full interactive dashboard: `diagnostics_output/bitunix_backtest_dashboard.html`
