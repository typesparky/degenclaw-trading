# Polymarket Live Market Scan — June 16, 2026

## KEY FINDING: All live markets have EMPTY order books

During live matches, market makers completely pull their quotes. Every single live market outcome shows:
- **Bid size: 0**
- **Ask size: 0**  
- **Spread: 20,000 bps (infinite)**

This means you can place **wide but consistent spreads** at prices near the pre-match / betting market odds, and you'll be the ONLY one providing liquidity. When the game ends, the market resolves and you collect the spread.

---

## 🔴 LIVE MATCHES (6 events, ~168 markets)

### 1. Saudi Arabia vs Uruguay — 2H 80' (1-1)
**3 main markets, all with empty books:**

| Market | Current Price | Pre-Match Fair | Recommended Bid/Ask |
|--------|--------------|----------------|-------------------|
| Saudi Arabia win | 52.5¢ | ~45% | bid 0.38 / ask 0.52 |
| Draw | 33.5¢ | ~25% | bid 0.20 / ask 0.30 |
| Uruguay win | 13.5¢ | ~30% | bid 0.25 / ask 0.35 |

**Strategy:** Place all 3 sides. The match is 1-1 in the 80th minute. Saudi Arabia is more likely to score again (they're pressing). Draw is also likely. Uruguay win is less likely but still possible. With empty books, any retail flow will hit your quotes.

### 2. Miami Marlins vs Philadelphia Phillies — Top 4th (0-3)
**26 markets, all empty books. Phillies dominating.**

Key markets:
- Phillies moneyline: 79.5¢ (near certain) → bid 0.75 / ask 0.85
- Phillies -1.5 spread: 58.5¢ → bid 0.50 / ask 0.60
- O/U 7.5: Over 42.5¢ → bid 0.35 / ask 0.50

### 3. Kansas City Royals vs Washington Nationals — Bot 4th (1-2)
**26 markets, all empty books. Nationals leading.**

Key markets:
- Nationals moneyline: 77.5¢ → bid 0.72 / ask 0.82
- Nationals -1.5 spread: 58.5¢ → bid 0.50 / ask 0.60
- O/U 8.5: Over 43.5¢ → bid 0.35 / ask 0.50

### 4. New York Mets vs Cincinnati Reds — Bot 2nd (0-3)
**26 markets, all empty books. Reds dominating early.**

Key markets:
- Reds moneyline: 82.5¢ → bid 0.78 / ask 0.88
- Reds -1.5 spread: 67.5¢ → bid 0.60 / ask 0.70
- O/U 8.5: Over 72.5¢ → bid 0.65 / ask 0.75

### 5. HSBC Tennis: Perricard vs Moutet — Set 3 (7-6, 4-6, 1-2)
**15 markets, all empty books. Close match.**

Key markets:
- Perricard moneyline: 52.5¢ → bid 0.45 / ask 0.55
- Moutet moneyline: 47.5¢ → bid 0.40 / ask 0.50
- Match O/U 22.5: Over 74.6¢ → bid 0.68 / ask 0.78

### 6. Saudi Arabia vs Uruguay — Halftime Result
**3 markets, empty books. Already 1-1 at halftime.**

---

## 📊 RECOMMENDED SPREAD STRATEGY

### For each live market:
1. **Look at the current Polymarket price** (this is the "stale" pre-match price)
2. **Set bid 5-10¢ below the current price**
3. **Set ask 5-10¢ above the current price**
4. **Size: $100-$500 per quote** (start small)

### Why this works:
- **Empty books = no competition.** You're the only one providing liquidity.
- **Prices are stale.** The current prices reflect pre-match odds, not the live game state. But they're the best reference point.
- **When the game ends, the market resolves.** If you've been filled on both sides, you've captured the spread. If only one side fills, you hold to resolution.
- **The 3-second delay works in YOUR favor.** You're not trying to market-make in real-time. You're placing limit orders and waiting.

### Risk management:
- **Max $500 per quote** during live play
- **Only quote markets where both outcomes have >5% probability** (avoid near-resolved markets)
- **Don't chase.** If the price moves against you, let it go. There will be more opportunities.

---

## 🎯 TOP 10 MARKETS TO QUOTE RIGHT NOW

1. **Saudi Arabia win** — 52.5¢ → bid 0.45 / ask 0.55 (match is 1-1, could go either way)
2. **Saudi Arabia draw** — 33.5¢ → bid 0.28 / ask 0.38 (draw is very possible at 1-1)
3. **Uruguay win** — 13.5¢ → bid 0.10 / ask 0.20 (less likely but still possible)
4. **Phillies moneyline** — 79.5¢ → bid 0.75 / ask 0.85 (Phillies leading 0-3)
5. **Phillies -1.5** — 58.5¢ → bid 0.52 / ask 0.62
6. **Nationals moneyline** — 77.5¢ → bid 0.72 / ask 0.82 (Nationals leading 1-2)
7. **Reds moneyline** — 82.5¢ → bid 0.78 / ask 0.88 (Reds leading 0-3)
8. **Perricard moneyline** — 52.5¢ → bid 0.45 / ask 0.55 (close tennis match)
9. **Moutet moneyline** — 47.5¢ → bid 0.40 / ask 0.50
10. **O/U 7.5 Marlins/Phillies** — Over 42.5¢ → bid 0.35 / ask 0.50

---

## 📱 TELEGRAM SETUP

To receive these scans on Telegram:
1. Start a conversation with your Telegram bot
2. Send `/start`
3. Get your chat ID
4. Run: `python3 telegram_bridge.py --configure-channel <chat_id>`
5. Then: `python3 scan_polymarket.py --send-telegram`

---

*Generated: 2026-06-16 01:42 UTC*
