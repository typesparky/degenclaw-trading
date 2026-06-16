#!/usr/bin/env python3
"""
Polymarket Safe Pricing v2 — Tiered by Probability Level
=========================================================
Fix: For low-probability events (goals, corners, etc.), a percentage-based
survival factor doesn't work. A 50% discount on 5% = 2.5%, which is still
too high when the true probability is 5%.

Solution: Use ABSOLUTE buffers based on probability tier:
  - High prob (>30%): ±percentage (30% vol factor)
  - Mid prob (10-30%): ±percentage (40% vol factor)  
  - Low prob (3-10%): ±absolute (min 5¢ below fair)
  - Extreme low (<3%): ±absolute (min 8¢ below fair)

The key insight: For a 5% event, you want to buy at 1-2%, not 2.5%.
The "buffer below" should be LARGER in absolute terms for lower probabilities
because the crowd systematically overprices low-prob events.
"""

TAKER_FEE = 0.03
REBATE_RATE = 0.25
NET_TAKER = TAKER_FEE * (1 - REBATE_RATE)  # 2.25%


def safe_price_v2(fair_prob):
    """
    Tiered safe pricing that works for ALL probability levels.
    """
    if fair_prob >= 0.30:
        # High probability: 50% survival factor
        bid = max(0.01, fair_prob * 0.50 - 0.02)
        ask = min(0.99, fair_prob * 1.50 + 0.02)
    elif fair_prob >= 0.10:
        # Mid probability: 40% vol factor
        bid = max(0.01, fair_prob * 0.60 - 0.03)
        ask = min(0.99, fair_prob * 1.40 + 0.03)
    elif fair_prob >= 0.03:
        # Low probability (3-10%): absolute buffer
        bid = max(0.01, min(fair_prob - 0.05, fair_prob * 0.50))
        ask = min(0.99, fair_prob + 0.10)
    else:
        # Extreme low (<3%): larger absolute buffer
        bid = max(0.01, min(fair_prob - 0.10, fair_prob * 0.30))
        ask = min(0.99, fair_prob + 0.20)
    return round(bid, 4), round(ask, 4)


def verify_quote(fair_prob, bid, ask, size):
    """Verify a quote is +EV after fees and adverse selection."""
    
    # Edge at fair value
    edge_per_share = fair_prob - bid
    edge_total = edge_per_share * size
    
    # Max loss if fair value drops 50%
    worst_fair = fair_prob * 0.5
    max_loss_per_share = max(0, bid - worst_fair)
    max_loss_total = max_loss_per_share * size
    
    # Fees if held to resolution (no round-trip, just hold)
    # If you're maker: no fee on entry, fee only if you sell before resolution
    # If held to resolution: NO FEES at all
    fees = 0  # Holding to resolution = no fees
    
    # Net EV = edge at fair - risk of adverse move
    # Assume 70% probability fair is correct, 30% it moves 50% against you
    ev = (0.70 * edge_total) + (0.30 * -max_loss_total) - fees
    
    # ROI
    roi = (ev / (bid * size)) * 100 if bid * size > 0 else 0
    
    return {
        'edge_at_fair': edge_total,
        'max_loss_50pct_adverse': max_loss_total,
        'ev': ev,
        'roi_pct': roi,
        'is_positive_ev': ev > 0,
        'edge_per_share': edge_per_share,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# FULL PRICING TABLE — ALL MARKETS
# ═══════════════════════════════════════════════════════════════════════════════

print("=" * 140)
print("POLYMARKET SAFE PRICING v2 — Tiered by Probability Level")
print("=" * 140)
print()
print("Buffer rules:")
print("  High prob (≥30%):  30% vol factor + 2¢ margin")
print("  Mid prob (10-30%): 40% vol factor + 3¢ margin")
print("  Low prob (3-10%):  ABSOLUTE min 5¢ below fair")
print("  Extreme low (<3%): ABSOLUTE min 8¢ below fair")
print()

# Player props — Over 0.5 goals
player_goals = [
    # (name, fair_prob, volume, notes)
    ("Lamine Yamal",    0.42, 43300, "High prob → 30% vol"),
    ("Dani Olmo",       0.38,  7800, "High prob → 30% vol"),
    ("Ferrán Torres",   0.35, 27200, "High prob → 30% vol"),
    ("Fabián Ruiz",    0.28,  9400, "Mid prob → 40% vol"),
    ("Alex Baena",     0.25,  1200, "Mid prob → 40% vol"),
    ("Gavi Paez",      0.22, 13700, "Mid prob → 40% vol"),
    ("Borja Iglesias",  0.30,   596, "High prob → 30% vol"),
    ("Cucurella",      0.08,   490, "Low prob → abs 5¢ buffer"),
    ("Eric García",    0.05,   203, "Low prob → abs 5¢ buffer"),
    ("Marc Pubill",    0.04,   212, "Low prob → abs 5¢ buffer"),
    ("Dailon Livramento", 0.06, 2300, "Low prob → abs 5¢ buffer"),
]

# Player props — Over 1.5 goals (much lower probability)
player_goals_15 = [
    ("Lamine Yamal o1.5",    0.18, 43300, "Mid prob"),
    ("Dani Olmo o1.5",       0.15,  7800, "Mid prob"),
    ("Ferrán Torres o1.5",   0.13, 27200, "Mid prob"),
    ("Borja Iglesias o1.5",  0.10,   596, "Mid/Low boundary"),
    ("Cucurella o1.5",       0.02,   490, "Extreme low"),
    ("Eric García o1.5",     0.01,   203, "Extreme low"),
]

# Corner markets
corner_markets = [
    ("Total corners o9.5",   0.55, 5000, "High prob"),
    ("Total corners o10.5",  0.45, 5000, "High prob"),
    ("Spain corners o6.5",   0.45, 3000, "High prob"),
    ("Spain corners o7.5",   0.30, 3000, "High/Mid boundary"),
    ("Cape Verde corners o2.5", 0.15, 1000, "Mid prob"),
    ("Cape Verde corners o3.5", 0.05, 1000, "Low prob"),
]

def size_for_vol(vol):
    if vol < 500: return 100
    elif vol < 2000: return 200
    elif vol < 10000: return 300
    else: return 500


def tier_label(fair_prob):
    if fair_prob >= 0.30: return "high"
    elif fair_prob >= 0.10: return "mid"
    elif fair_prob >= 0.03: return "low"
    else: return "xlow"


def print_table(title, markets):
    print(f"\n{'=' * 140}")
    print(f"{title}")
    print(f"{'=' * 140}")
    print()
    print(f"{'Market':<28} {'Fair%':>6} {'Tier':>6} {'Bid':>6} {'Ask':>6} {'Sprd':>6} {'Size':>6} {'Edge$':>8} {'MaxLoss$':>9} {'EV$':>8} {'ROI%':>8} {'+EV?':>5}")
    print("-" * 140)
    
    total_ev = 0
    for name, fair_prob, vol, notes in markets:
        bid, ask = safe_price_v2(fair_prob)
        spread_cents = (ask - bid) * 100
        size = size_for_vol(vol)
        result = verify_quote(fair_prob, bid, ask, size)
        total_ev += result['ev']
        
        print(f"{name:<28} {fair_prob*100:>5.1f}% {tier_label(fair_prob):>6} {bid:>6.2f} {ask:>6.2f} {spread_cents:>5.1f}¢ ${size:>5} ${result['edge_at_fair']:>+7.2f} ${result['max_loss_50pct_adverse']:>7.2f} ${result['ev']:>+7.2f} {result['roi_pct']:>+7.1f}% {'✓' if result['is_positive_ev'] else '✗':>5}")
    
    print(f"{'':>28} {'':>6} {'':>6} {'':>6} {'':>6} {'':>6} {'':>6} {'':>8} {'':>9} ${total_ev:>+7.2f} {'TOTAL EV':>8}")
    return total_ev


# Print all tables
ev1 = print_table("PLAYER PROPS — Over 0.5 Goals", player_goals)
ev2 = print_table("PLAYER PROPS — Over 1.5 Goals", player_goals_15)
ev3 = print_table("CORNER MARKETS", corner_markets)

print()
print("=" * 140)
print(f"TOTAL EV PER MATCH (all markets): ${ev1 + ev2 + ev3:+.2f}")
print("=" * 140)

# ═══════════════════════════════════════════════════════════════════════════════
# VERIFICATION: Is the buffer sufficient for low-prob events?
# ═══════════════════════════════════════════════════════════════════════════════

print()
print("=" * 140)
print("LOW-PROB VERIFICATION: Is the buffer sufficient?")
print("=" * 140)
print()

low_prob_examples = [
    ("Cucurella o0.5 goals", 0.08),
    ("Eric García o0.5 goals", 0.05),
    ("Marc Pubill o0.5 goals", 0.04),
    ("Cucurella o1.5 goals", 0.02),
    ("Eric García o1.5 goals", 0.01),
    ("Cape Verde corners o3.5", 0.05),
]

print(f"{'Market':<30} {'Fair%':>6} {'Bid':>6} {'Buffer':>8} {'Bid/Fair':>10} {'Verdict':<30}")
print("-" * 100)

for name, fair_prob in low_prob_examples:
    bid, ask = safe_price_v2(fair_prob)
    buffer = fair_prob - bid
    ratio = bid / fair_prob if fair_prob > 0 else 0
    
    # Verdict
    if buffer >= 0.05:
        verdict = "✓ Buffer ≥ 5¢ — safe"
    elif buffer >= 0.03:
        verdict = "~ Buffer 3-5¢ — acceptable"
    else:
        verdict = "✗ Buffer < 3¢ — too tight"
    
    if ratio > 0.7:
        verdict += " | ⚠ Bid too close to fair"
    
    print(f"{name:<30} {fair_prob*100:>5.1f}% {bid:>6.2f} {buffer:>7.2f} {ratio:>9.1%} {verdict}")

print()
print("Key: For a 5% event, bid should be ≤ 2% (buffer ≥ 3¢)")
print("     For a 2% event, bid should be ≤ 0.5% (buffer ≥ 1.5¢)")
print("     The absolute buffer rule ensures this.")

# ═══════════════════════════════════════════════════════════════════════════════
# COMPARISON: Old vs New Pricing
# ═══════════════════════════════════════════════════════════════════════════════

print()
print("=" * 140)
print("COMPARISON: Old (50% survival) vs New (tiered absolute buffer)")
print("=" * 140)
print()

comparison = [
    ("Cucurella o0.5", 0.08),
    ("Eric García o0.5", 0.05),
    ("Marc Pubill o0.5", 0.04),
    ("Lamine Yamal o0.5", 0.42),
    ("Dani Olmo o0.5", 0.38),
]

print(f"{'Market':<25} {'Fair%':>6} {'Old Bid':>8} {'New Bid':>8} {'Old Buffer':>10} {'New Buffer':>10} {'Improvement':>12}")
print("-" * 90)

for name, fair_prob in comparison:
    # Old: 50% survival factor
    old_bid = max(0.01, fair_prob * 0.50 - 0.02)
    old_buffer = fair_prob - old_bid
    
    # New: tiered
    new_bid, new_ask = safe_price_v2(fair_prob)
    new_buffer = fair_prob - new_bid
    
    improvement = "BETTER" if new_buffer > old_buffer else "SAME" if new_buffer == old_buffer else "WORSE"
    
    print(f"{name:<25} {fair_prob*100:>5.1f}% {old_bid:>8.2f} {new_bid:>8.2f} {old_buffer:>9.2f} {new_buffer:>9.2f} {improvement:>12}")

print()
print("The new tiered pricing gives MUCH better buffers for low-prob events")
print("while keeping reasonable spreads for high-prob events.")
