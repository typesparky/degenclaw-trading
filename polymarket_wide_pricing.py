#!/usr/bin/env python3
"""
Polymarket Super-Wide Pricing for Thin Markets
===============================================
Goal: Quote so wide that you almost never get picked off,
but when you do, the edge is large enough to overcome fees
and still be +EV even if the market moves against you.

Key insight: In a thin market with no sharp reference price,
the "fair value" is a wide range, not a point estimate.
We quote at the edges of that range.
"""

# ═══════════════════════════════════════════════════════════════════════════════
# FEE STRUCTURE
# ═══════════════════════════════════════════════════════════════════════════════
TAKER_FEE = 0.03          # 3%
REBATE_RATE = 0.25        # 25% of taker fee rebated to maker
NET_TAKER_COST = TAKER_FEE * (1 - REBATE_RATE)  # 2.25%
MAKER_REBATE = TAKER_FEE * REBATE_RATE           # 0.75% per fill

# Reward eligibility
REBATE_MIN_SIZE = 200     # $ minimum per trade
REBATE_MAX_SPREAD = 4.5   # cents — BUT we're intentionally wider than this
                          # We sacrifice the rebate for safety

# ═══════════════════════════════════════════════════════════════════════════════
# SUPER-WIDE PRICING MODEL
# ═══════════════════════════════════════════════════════════════════════════════
# For each market, we calculate:
#   - "Safe bid": Price so low that even if fair value drops 30%, we're still OK
#   - "Safe ask": Price so high that even if fair value rises 30%, we're still OK
#   - "Disaster check": What happens if we get filled and the market moves 50% against us?

def super_wide_price(fair_prob, volatility_factor=0.30):
    """
    Returns (bid, ask) that are wide enough to survive adverse selection.
    
    volatility_factor: How much fair value could move in the next few minutes.
    For live sports with 3s delay, 30-50% moves are common on goals/red cards.
    """
    # The fair value itself is uncertain — it's a range, not a point
    # For a player prop, "40% chance of scoring" could easily be 25-55%
    # depending on game state, substitutions, etc.
    
    # Safe bid: We want to buy YES only if it's a steal
    # = fair_prob - volatility - margin_of_safety
    safe_bid = max(0.01, fair_prob * (1 - volatility_factor) - 0.05)
    
    # Safe ask: We want to sell YES only if it's expensive
    # = fair_prob + volatility + margin_of_safety  
    safe_ask = min(0.99, fair_prob * (1 + volatility_factor) + 0.05)
    
    return round(safe_bid, 4), round(safe_ask, 4)


def edge_analysis(fair_prob, bid, ask, size_dollars=200):
    """
    Calculate the edge for a round-trip (buy YES + sell NO).
    Accounts for fees and potential adverse selection.
    """
    # Cost to buy YES at our bid
    cost_buy_yes = bid * size_dollars
    
    # Cost to buy NO at our NO-bid (= 1 - our YES-ask)
    cost_buy_no = (1 - ask) * size_dollars
    
    # Total round-trip cost
    total_cost = cost_buy_yes + cost_buy_no
    
    # Guaranteed payout at resolution
    payout = 1.00 * size_dollars
    
    # Gross profit
    gross_profit = payout - total_cost
    
    # Fees (taker on both sides, since we're hitting the book)
    fees = NET_TAKER_COST * size_dollars * 2
    
    # Net profit
    net_profit = gross_profit - fees
    
    # Return on capital
    roi = net_profit / total_cost * 100 if total_cost > 0 else 0
    
    return {
        'total_cost': total_cost,
        'gross_profit': gross_profit,
        'fees': fees,
        'net_profit': net_profit,
        'roi_pct': roi,
        'breakeven_prob': bid / (bid + (1 - ask)) if (bid + (1 - ask)) > 0 else 0,
    }


def adverse_selection_check(fair_prob, bid, ask, max_move=0.50):
    """
    What happens if we get filled and the market moves max_move against us?
    E.g., we buy YES at 0.15, then fair value drops 50% to 0.075.
    """
    # Scenario: We buy YES at bid, then fair value drops
    new_fair = fair_prob * (1 - max_move)
    our_position_value = new_fair  # Our YES token is now worth new_fair
    loss = bid - new_fair  # We paid bid, it's now worth new_fair
    
    # Scenario: We sell YES at ask, then fair value rises
    new_fair_up = fair_prob * (1 + max_move)
    loss_if_sold = new_fair_up - ask  # We sold at ask, it's now worth more
    
    return {
        'buy_yes_then_drops': {'new_fair': new_fair, 'loss_per_share': max(0, loss)},
        'sell_yes_then_rises': {'new_fair': new_fair_up, 'loss_per_share': max(0, loss_if_sold)},
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PRICING TABLES
# ═══════════════════════════════════════════════════════════════════════════════

players = [
    # (name, fair_prob_over_0.5, volume, notes)
    ("Lamine Yamal",    0.42, 43300, "Highest volume prop"),
    ("Dani Olmo",       0.38,  7800, ""),
    ("Ferrán Torres",   0.35, 27200, ""),
    ("Fabián Ruiz",    0.28,  9400, ""),
    ("Alex Baena",     0.25,  1200, "Thin — wide quotes"),
    ("Gavi Paez",      0.22, 13700, ""),
    ("Borja Iglesias",  0.30,   596, "Very thin"),
    ("Cucurella",      0.08,   490, "Extremely thin — quote very wide"),
    ("Eric García",    0.05,   203, "Extremely thin"),
    ("Marc Pubill",    0.04,   212, "Extremely thin"),
    ("Dailon Livramento", 0.06, 2300, "Thin"),
]

print("=" * 120)
print("POLYMARKET SUPER-WIDE PRICING — Spain vs Cape Verde (LIVE)")
print("=" * 120)
print()
print("Strategy: Quote so wide that you only get filled on mispricings.")
print("When you do get filled, the edge is large enough to survive adverse selection.")
print()
print(f"Fee: {TAKER_FEE*100:.1f}% taker | {NET_TAKER_COST*100:.2f}% net after rebate")
print(f"Rebate eligibility: ≤{REBATE_MAX_SPREAD}¢ spread AND ≥${REBATE_MIN_SIZE} size")
print(f"NOTE: Our spreads are intentionally WIDER than {REBATE_MAX_SPREAD}¢ — we sacrifice rebate for safety")
print()

# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 1: Super-wide pricing with 30% volatility factor
# ═══════════════════════════════════════════════════════════════════════════════

print("=" * 120)
print("TABLE 1: SUPER-WIDE PRICING (30% volatility factor)")
print("=" * 120)
print()
print(f"{'Player':<20} {'Fair%':>6} {'Bid':>6} {'Ask':>6} {'Sprd':>6} {'Cost':>6} {'Gross$':>7} {'Net$':>7} {'ROI%':>7} {'Rebate?':<12}")
print("-" * 120)

for name, fair_prob, vol, notes in players:
    bid, ask = super_wide_price(fair_prob, volatility_factor=0.30)
    spread_cents = (ask - bid) * 100
    
    # Edge analysis for $200 round-trip
    edge = edge_analysis(fair_prob, bid, ask, size_dollars=200)
    
    # Rebate check
    qualifies = spread_cents <= REBATE_MAX_SPREAD and 200 >= REBATE_MIN_SIZE
    rebate_str = f"✓ ({spread_cents:.1f}¢)" if qualifies else f"✗ {spread_cents:.1f}¢"
    
    print(f"{name:<20} {fair_prob*100:>5.1f}% {bid:>6.2f} {ask:>6.2f} {spread_cents:>5.1f}¢ ${edge['total_cost']:>5.0f} ${edge['gross_profit']:>+6.2f} ${edge['net_profit']:>+6.2f} {edge['roi_pct']:>+6.1f}% {rebate_str:<12}")

print()
print("Interpretation:")
print("  - Cost = total $ to buy YES at bid + buy NO at (1-ask)")
print("  - Gross$ = $1.00 payout - cost (before fees)")
print("  - Net$ = Gross$ - taker fees on both sides")
print("  - ROI% = Net$ / Cost")
print()

# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 2: Adverse selection check
# ═══════════════════════════════════════════════════════════════════════════════

print("=" * 120)
print("TABLE 2: ADVERSE SELECTION CHECK (What if market moves 50% against us?)")
print("=" * 120)
print()
print(f"{'Player':<20} {'Fair%':>6} {'Bid':>6} {'Ask':>6} {'If buy YES & drops 50%':>25} {'If sell YES & rises 50%':>25}")
print("-" * 120)

for name, fair_prob, vol, notes in players:
    bid, ask = super_wide_price(fair_prob, volatility_factor=0.30)
    adverse = adverse_selection_check(fair_prob, bid, ask, max_move=0.50)
    
    buy_risk = adverse['buy_yes_then_drops']
    sell_risk = adverse['sell_yes_then_rises']
    
    buy_str = f"fair→{buy_risk['new_fair']:.2f}, loss=${buy_risk['loss_per_share']:.2f}/shr"
    sell_str = f"fair→{sell_risk['new_fair']:.2f}, loss=${sell_risk['loss_per_share']:.2f}/shr"
    
    print(f"{name:<20} {fair_prob*100:>5.1f}% {bid:>6.2f} {ask:>6.2f} {buy_str:<25} {sell_str:<25}")

print()
print("Key: Even if fair value moves 50% against you after getting filled,")
print("your loss per share is limited because you bought at such extreme prices.")
print()

# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 3: Recommended quote sizes
# ═══════════════════════════════════════════════════════════════════════════════

print("=" * 120)
print("TABLE 3: RECOMMENDED QUOTE SIZES")
print("=" * 120)
print()
print(f"{'Player':<20} {'Bid':>6} {'Ask':>6} {'Bid Size':>10} {'Ask Size':>10} {'Max Risk':>10}")
print("-" * 120)

for name, fair_prob, vol, notes in players:
    bid, ask = super_wide_price(fair_prob, volatility_factor=0.30)
    
    # Size inversely proportional to volume
    # Thin markets: smaller size to limit exposure
    if vol < 500:
        bid_size = 100
        ask_size = 100
    elif vol < 2000:
        bid_size = 200
        ask_size = 200
    elif vol < 10000:
        bid_size = 300
        ask_size = 300
    else:
        bid_size = 500
        ask_size = 500
    
    # Max risk = worst case if we get filled and market moves against us
    adverse = adverse_selection_check(fair_prob, bid, ask, max_move=0.50)
    max_loss_per_share = max(adverse['buy_yes_then_drops']['loss_per_share'], 
                              adverse['sell_yes_then_rises']['loss_per_share'])
    max_risk = max_loss_per_share * max(bid_size, ask_size)
    
    print(f"{name:<20} {bid:>6.2f} {ask:>6.2f} ${bid_size:>9} ${ask_size:>9} ${max_risk:>9.2f}")

print()
print("Max Risk = worst-case loss if market moves 50% against you after fill")
print()

# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 4: Scenario analysis
# ═══════════════════════════════════════════════════════════════════════════════

print("=" * 120)
print("TABLE 4: SCENARIO ANALYSIS — What happens in different game states?")
print("=" * 120)
print()
print("Current: 36', 0-0. What if Spain scores? What if Cape Verde scores?")
print()

scenarios = {
    "Spain scores (1-0)": {
        "Lamine Yamal": 0.55, "Dani Olmo": 0.50, "Ferrán Torres": 0.48,
        "Fabián Ruiz": 0.35, "Alex Baena": 0.32, "Gavi Paez": 0.28,
        "Borja Iglesias": 0.40, "Cucurella": 0.10, "Eric García": 0.06,
        "Marc Pubill": 0.05, "Dailon Livramento": 0.04,
    },
    "Cape Verde scores (0-1)": {
        "Lamine Yamal": 0.35, "Dani Olmo": 0.30, "Ferrán Torres": 0.28,
        "Fabián Ruiz": 0.22, "Alex Baena": 0.18, "Gavi Paez": 0.15,
        "Borja Iglesias": 0.22, "Cucurella": 0.06, "Eric García": 0.04,
        "Marc Pubill": 0.03, "Dailon Livramento": 0.15,
    },
    "Spain scores again (2-0)": {
        "Lamine Yamal": 0.65, "Dani Olmo": 0.60, "Ferrán Torres": 0.55,
        "Fabián Ruiz": 0.42, "Alex Baena": 0.38, "Gavi Paez": 0.35,
        "Borja Iglesias": 0.50, "Cucurella": 0.12, "Eric García": 0.08,
        "Marc Pubill": 0.06, "Dailon Livramento": 0.03,
    },
}

for scenario, probs in scenarios.items():
    print(f"  {scenario}:")
    for name, new_fair in probs.items():
        # Find original fair prob
        orig_fair = next((p[1] for p in players if p[0] == name), None)
        if orig_fair:
            bid, ask = super_wide_price(orig_fair, volatility_factor=0.30)
            # Would our quote still be good?
            if new_fair > ask:
                status = f"ASK TOO LOW — would have sold YES at {ask:.2f} but now worth {new_fair:.2f}"
            elif new_fair < bid:
                status = f"BID TOO HIGH — would have bought YES at {bid:.2f} but now worth {new_fair:.2f}"
            else:
                status = f"OK — new fair {new_fair:.2f} still within our [{bid:.2f}, {ask:.2f}] range"
            print(f"    {name:<20} {status}")
    print()

# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════

print("=" * 120)
print("SUMMARY & RECOMMENDATIONS")
print("=" * 120)
print()
print("""
1. PRICING PHILOSOPHY:
   - Quote at prices where you'd be happy to hold to resolution
   - If someone hits your bid, you're getting a bargain
   - If someone lifts your ask, you're selling at a premium
   - You're not trying to make markets — you're fishing for mispricings

2. SPREAD WIDTH:
   - 30% volatility factor means spreads of 15-30¢ on most markets
   - This is WIDE — you won't get filled often
   - But when you do, the edge is 15-50% ROI per round-trip
   - You sacrifice the 0.75% maker rebate (spread too wide) but gain safety

3. SIZE:
   - $100-$500 per quote depending on market thickness
   - Thin markets (<$500 vol): $100
   - Medium markets ($1K-$10K vol): $200-$300
   - Liquid markets (>$10K vol): $500

4. RISK MANAGEMENT:
   - If you get filled on one side only, you have a directional position
   - Set a mental stop: if fair value moves 30% against you, accept the loss
   - The wide pricing means even a 50% adverse move is survivable
   - Max risk per trade: ~$50-$150 depending on size

5. WHEN TO ADJUST:
   - After a goal: immediately widen further (volatility spikes)
   - After a red card: recalculate fair values entirely
   - At halftime: tighten slightly (less time for variance)
   - In stoppage time: only quote if the outcome is nearly certain

6. EXPECTED FILL RATE:
   - At these wide spreads, expect 1-5 fills per match per market
   - That's fine — each fill should be +15-50% ROI
   - 5 fills × $200 × 25% avg ROI = $250 profit per match
   - Scale up as you learn which markets get hit

7. THE EDGE:
   - No sharp bookmaker prices exist for these markets (OddsPortal empty)
   - Polymarket crowd is pricing based on gut feel, not models
   - Your edge is knowing the approximate fair value from pre-match lines
   - The crowd overreacts to match events — you fade the overreaction
""")
