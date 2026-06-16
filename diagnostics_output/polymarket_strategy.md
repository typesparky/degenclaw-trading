# Polymarket Sports Market Making — Complete Strategy

## Data Sources (All Free)

### 1. ESPN Scoreboard (Primary)
- URL: `https://www.espn.com/soccer/scoreboard/_/date/YYYYMMDD`
- Provides: Live scores, betting odds (moneyline, spread, O/U from DraftKings)
- Format: HTML (parseable)
- Coverage: Soccer, MLB, NBA, NFL, NHL, Tennis, etc.

### 2. MLB Stats API (Live play-by-play)
- URL: `https://statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live`
- Provides: Real-time play-by-play, scores, stats
- Format: JSON
- Coverage: MLB only

### 3. Polymarket Sports WebSocket
- URL: `wss://sports-api.polymarket.com/ws`
- Provides: Live scores for all Polymarket-tracked games
- Format: JSON push
- Coverage: All sports on Polymarket

### 4. Polymarket Gamma API (Market discovery)
- URL: `https://gamma-api.polymarket.com/events`
- Provides: All markets, prices, volumes, start times
- Format: JSON
- Coverage: All markets

## Strategy A: Pre-Match (No Live Data Needed)

### Timeline:
- **T-24h to T-6h:** Place wide spreads. Books are thin but not empty. Other MMs are still quoting.
- **T-6h to T-1h:** Tighten spreads as more MMs arrive. Best edge is in the 6-12h window.
- **T-1h to kickoff:** Books are liquid. Edge is smaller but still exists in less popular markets.
- **Kickoff:** STOP. Don't touch during live play unless you have real-time data.

### Pricing:
1. Get ESPN betting odds for the match
2. Convert to implied probabilities
3. Place Polymarket quotes 5-10¢ wide around those probabilities
4. Size: $200-$500 per quote

### Example: France vs Senegal (June 16, 7PM ET)
ESPN odds: France -215 (implied ~68%), Senegal +375 (implied ~21%), Draw ~11%

Polymarket pricing:
- France win: bid 0.63 / ask 0.73 (mid ~0.68)
- Senegal win: bid 0.16 / ask 0.26 (mid ~0.21)  
- Draw: bid 0.06 / ask 0.16 (mid ~0.11)

## Strategy B: Live Game (Requires Real-Time Data)

### Data Pipeline:
1. Connect to Polymarket Sports WebSocket → get live scores
2. Parse ESPN scoreboard every 30 seconds → get betting odds updates
3. When a goal/event happens:
   a. Wait 30 seconds for market to settle
   b. Recalculate fair values based on new game state
   c. Cancel stale orders
   d. Place new wide quotes

### Live Pricing:
- **Widen spreads to 15-20¢** during live play (from 5-10¢ pre-match)
- **Only quote markets where both outcomes have >10% probability**
- **Max $200 per quote** during live play
- **Stop quoting entirely in the last 10 minutes** of a close game (too volatile)

### Example: Saudi Arabia vs Uruguay (1-1, 2H 80')
Current Polymarket prices (stale): Saudi 52.5%, Draw 33.5%, Uruguay 13.5%

Recommended live quotes (wide):
- Saudi win: bid 0.40 / ask 0.60 (20¢ spread)
- Draw: bid 0.25 / ask 0.45 (20¢ spread)
- Uruguay win: bid 0.05 / ask 0.20 (15¢ spread)

## Strategy C: Post-Goal Mean Reversion

When a goal happens:
1. Polymarket prices jump (often overshooting)
2. Other MMs pull quotes (fear of adverse selection)
3. You can place counter-trend quotes at better prices

Example: Saudi scores to make it 2-1
- Saudi win price jumps from 52.5% → 85%
- Place SELL at 0.80 (overpriced) and BUY at 0.60 (underpriced)
- When the market settles, you capture the mean reversion

## Upcoming Matches to Watch

### June 16 (Today):
- **France vs Senegal** — 7PM ET (World Cup)
  - ESPN: France -215, O/U 2.5
  - Polymarket markets: 33+ (match result, spreads, player props)
  
- **Iraq vs Norway** — 10PM ET (World Cup)
  - ESPN: Norway -475, O/U 2.5
  - Polymarket markets: 33+

- **Argentina vs Algeria** — 1AM ET (World Cup)
  - ESPN: Argentina -225, O/U 2.5
  - Polymarket markets: 33+

### June 17-18:
- More World Cup group stage matches
- Check ESPN schedule for exact times

## Implementation

### Pre-Match Bot:
```
1. Every 6 hours, scan Polymarket for upcoming matches (next 24h)
2. For each match, get ESPN betting odds
3. Calculate fair values and recommended spreads
4. Place limit orders on Polymarket
5. Monitor and adjust until kickoff
6. Cancel all orders at kickoff
```

### Live Bot (when ready):
```
1. Connect to Polymarket Sports WebSocket
2. Parse ESPN scoreboard every 30s
3. On goal/event: wait 30s, recalculate, cancel/replace
4. On match end: settle positions
```

## Risk Management

- **Max $500 per quote** pre-match
- **Max $200 per quote** during live play
- **Max $2,000 total exposure** per match
- **Stop quoting** if a market moves >20% against you
- **Always hold to resolution** — don't panic sell
