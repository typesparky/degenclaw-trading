#!/usr/bin/env python3
"""
Polymarket Production Quoting Bot v3
======================================
Full order management with the official polymarket-client SDK.

Features:
  - Safe wide quoting (tiered by probability)
  - Real-time WebSocket monitoring (sports scores + market prices)
  - Order placement, cancellation, and replacement
  - Position tracking and P&L logging
  - Maker rebate tracking
  - Goal-based recalculation

Setup:
  pip install polymarket-client websockets requests

  export POLYMARKET_PRIVATE_KEY=0x...
  export POLYMARKET_WALLET_ADDRESS=0x...  (optional, uses deposit wallet by default)

Usage:
  python3 polymarket_bot_v3.py --dry-run --query "Belgium"
  python3 polymarket_bot_v3.py --live --query "Belgium"
  python3 polymarket_bot_v3.py --status  # Check positions and P&L
"""

import asyncio
import json
import os
import time
from decimal import Decimal
from typing import Dict, List, Tuple, Optional
from datetime import datetime

import websockets
import requests

# ── SDK IMPORT ────────────────────────────────────────────────────────────────
try:
    from polymarket import AsyncPublicClient, AsyncSecureClient
    from polymarket.streams import MarketSpec, UserSpec
    HAS_SDK = True
except ImportError:
    HAS_SDK = False
    print("[WARN] polymarket-client not installed. Run: pip install polymarket-client")


# ═══════════════════════════════════════════════════════════════════════════════
# PRICING ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def safe_price(p: float, bid_depth: float = 0, ask_depth: float = 0, capture_rebate: bool = True) -> Tuple[float, float]:
    """
    Dynamic pricing based on actual order book state -- no hardcoded thresholds.
    
    Args:
        p: Fair probability (0-1)
        bid_depth: Total bid depth on opposite side (shares). 0 = empty book.
        ask_depth: Total ask depth on our side (shares). 0 = empty book.
        capture_rebate: Whether to target rebate-eligible spreads.
    
    Logic:
        Empty book (depth=0): We are the only MM. Wide spreads.
        Thin book (depth < 100): Some competition. Moderate spreads.
        Deep book (depth >= 1000): Liquid. Tight spreads for rebates.
    """
    total_depth = bid_depth + ask_depth

    if total_depth == 0:
        base_spread = 0.12
    elif total_depth < 50:
        base_spread = 0.10
    elif total_depth < 200:
        base_spread = 0.08
    elif total_depth < 500:
        base_spread = 0.06
    elif total_depth < 1000:
        base_spread = 0.045
    else:
        base_spread = 0.015

    if capture_rebate:
        max_spread = 0.045
        if total_depth >= 1000:
            max_spread = 0.015
        base_spread = min(base_spread, max_spread)

    # Moonshot premium: low-prob outcomes are overpriced on PM
    if p < 0.05:
        base_spread += 0.05
    elif p < 0.10:
        base_spread += 0.03
    elif p < 0.15:
        base_spread += 0.02

    half_spread = base_spread / 2

    if p >= 0.15:
        bid = max(0.01, p - half_spread)
        ask = min(0.99, p + half_spread)
    else:
        # Moonshot: bid at absolute floor, ask captures premium
        if p >= 0.10:
            bid_floor = 0.04
        elif p >= 0.05:
            bid_floor = 0.03
        else:
            bid_floor = 0.02
        bid = bid_floor
        ask = min(0.99, p + half_spread + 0.02)

    return round(bid, 4), round(ask, 4)


def safe_size(p: float) -> int:
    if p >= 0.30: return 500
    if p >= 0.15: return 300
    if p >= 0.05: return 200
    return 100


def taker_fee(shares: int, price: float) -> float:
    """Polymarket fee curve: C * 0.03 * p * (1-p)"""
    return shares * 0.03 * price * (1 - price)


def maker_rebate(shares: int, price: float) -> float:
    """25% of taker fee rebated to maker."""
    return taker_fee(shares, price) * 0.25


def recalc_probs(base: Dict[str, float], home_goals: int, away_goals: int,
                 home_team: str = "Spain", away_team: str = "Cape Verde") -> Dict[str, float]:
    """Adjust fair values based on match score."""
    d = home_goals - away_goals
    r = {}
    for name, p in base.items():
        v = p
        # Determine which team the player belongs to
        is_away = any(kw in name.lower() for kw in ["cape verde", "dailon", "egypt", "opponent"])
        if is_away:
            if d > 0: v *= 0.6   # Opponent scored → less likely
            elif d < 0: v *= 1.4  # They scored → more likely
        else:
            if d < 0: v *= 0.8   # Home team conceded → slight decrease
            elif d > 2: v *= 1.2  # Dominating → more likely
        r[name] = min(0.95, max(0.01, v))
    return r


# ═══════════════════════════════════════════════════════════════════════════════
# P&L TRACKER
# ═══════════════════════════════════════════════════════════════════════════════

class PnLTracker:
    """Track positions, fills, fees, and rebates."""

    def __init__(self, log_file: str = "polymarket_pnl.json"):
        self.log_file = log_file
        self.positions: Dict[str, Dict] = {}  # market_name -> {shares, avg_cost, side}
        self.fills: List[Dict] = []
        self.total_fees = 0.0
        self.total_rebates = 0.0
        self.load()

    def record_fill(self, market: str, side: str, price: float, size: int, is_maker: bool):
        """Record a fill."""
        fee = taker_fee(size, price) if not is_maker else 0
        reb = maker_rebate(size, price) if is_maker else 0
        self.total_fees += fee
        self.total_rebates += reb

        fill = {
            "time": datetime.now().isoformat(),
            "market": market,
            "side": side,
            "price": price,
            "size": size,
            "fee": fee,
            "rebate": reb,
            "is_maker": is_maker,
        }
        self.fills.append(fill)

        # Update position
        if market not in self.positions:
            self.positions[market] = {"shares": 0, "avg_cost": 0, "side": side}

        pos = self.positions[market]
        if side == "BUY":
            total_cost = pos["avg_cost"] * pos["shares"] + price * size
            pos["shares"] += size
            pos["avg_cost"] = total_cost / pos["shares"] if pos["shares"] > 0 else 0
        else:  # SELL
            pos["shares"] -= size

        self.save()
        return fill

    def get_summary(self) -> Dict:
        """Get P&L summary."""
        total_position_value = 0
        for name, pos in self.positions.items():
            if pos["shares"] > 0:
                total_position_value += pos["shares"] * pos["avg_cost"]

        return {
            "total_fills": len(self.fills),
            "total_fees": round(self.total_fees, 2),
            "total_rebates": round(self.total_rebates, 2),
            "net_fees": round(self.total_fees - self.total_rebates, 2),
            "positions": {k: v for k, v in self.positions.items() if v["shares"] > 0},
            "position_cost": round(total_position_value, 2),
        }

    def save(self):
        data = {
            "positions": self.positions,
            "fills": self.fills[-100:],  # Keep last 100 fills
            "total_fees": self.total_fees,
            "total_rebates": self.total_rebates,
        }
        try:
            with open(self.log_file, "w") as f:
                json.dump(data, f, indent=2)
        except:
            pass

    def load(self):
        try:
            with open(self.log_file, "r") as f:
                data = json.load(f)
                self.positions = data.get("positions", {})
                self.fills = data.get("fills", [])
                self.total_fees = data.get("total_fees", 0)
                self.total_rebates = data.get("total_rebates", 0)
        except:
            pass

    def print_summary(self):
        s = self.get_summary()
        print(f"\n{'=' * 60}")
        print("P&L SUMMARY")
        print(f"{'=' * 60}")
        print(f"Total fills:    {s['total_fills']}")
        print(f"Total fees:     ${s['total_fees']:.2f}")
        print(f"Total rebates:  ${s['total_rebates']:.2f}")
        print(f"Net fees:       ${s['net_fees']:.2f}")
        print(f"Position cost:  ${s['position_cost']:.2f}")
        if s["positions"]:
            print(f"\nOpen positions:")
            for name, pos in s["positions"].items():
                print(f"  {name}: {pos['shares']} shares @ avg ${pos['avg_cost']:.4f}")
        print(f"{'=' * 60}")


# ═══════════════════════════════════════════════════════════════════════════════
# MARKET DISCOVERY
# ═══════════════════════════════════════════════════════════════════════════════

class Discovery:
    def __init__(self):
        self.s = requests.Session()

    def find_markets(self, query: str) -> Dict[str, Dict]:
        """Find markets by text. Returns {question: {tokens, prices}}."""
        results = {}
        resp = self.s.get(f"{GAMMA_API}/markets", params={
            "active": "true", "closed": "false", "limit": 100,
            "order": "volume24hr", "ascending": "false",
        }, timeout=10)
        for m in resp.json():
            q = m.get("question", "")
            if query.lower() in q.lower():
                tokens = json.loads(m.get("clobTokenIds", "[]"))
                outcomes = json.loads(m.get("outcomes", "[]"))
                prices = [float(p) for p in json.loads(m.get("outcomePrices", "[]"))]
                if tokens and outcomes:
                    tok_map = {outcomes[i]: tokens[i] for i in range(min(len(outcomes), len(tokens)))}
                    results[q] = {"tokens": tok_map, "prices": prices}
        return results


GAMMA_API = "https://gamma-api.polymarket.com"


# ═══════════════════════════════════════════════════════════════════════════════
# QUOTE
# ═══════════════════════════════════════════════════════════════════════════════

class Quote:
    def __init__(self, name, fair, bid, ask, size, token_id=""):
        self.name, self.fair, self.bid, self.ask, self.size, self.token_id = name, fair, bid, ask, size, token_id

    @property
    def spread_c(self):
        return (self.ask - self.bid) * 100

    @property
    def roi(self):
        return ((self.fair - self.bid) / self.bid) * 100 if self.bid > 0 else 0


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN BOT
# ═══════════════════════════════════════════════════════════════════════════════

class PolymarketBot:
    def __init__(self, dry_run: bool = True, private_key: str = "", wallet: str = ""):
        self.dry_run = dry_run
        self.pk = private_key or os.environ.get("POLYMARKET_PRIVATE_KEY", "")
        self.wallet = wallet or os.environ.get("POLYMARKET_WALLET_ADDRESS", "")
        self.probs: Dict[str, float] = {}
        self.quotes: Dict[str, Quote] = {}
        self.active_orders: Dict[str, str] = {}  # "name_BUY"/"name_SELL" -> order_id
        self.disc = Discovery()
        self.pnl = PnLTracker()
        self.secure_client: Optional[AsyncSecureClient] = None

    def set_probs(self, p: Dict[str, float]):
        self.probs = p

    def build_quotes(self, orderbooks: Dict[str, Dict] = None):
        """Build quotes using actual order book depth for spread calculation."""
        self.quotes = {}
        for n, p in self.probs.items():
            # Get order book depth if available
            ob = (orderbooks or {}).get(n, {})
            bid_depth = ob.get("bid_depth", 0)
            ask_depth = ob.get("ask_depth", 0)
            bid, ask = safe_price(p, bid_depth=bid_depth, ask_depth=ask_depth)
            sz = safe_size(p)
            self.quotes[n] = Quote(n, p, bid, ask, sz)

    def show_quotes(self):
        h = f"{'Market':<28} {'Fair%':>6} {'Bid':>6} {'Ask':>6} {'Sprd':>6} {'Sz':>4} {'Edge$':>7} {'Fee$':>6} {'Reb$':>7} {'ROI%':>7}"
        print(f"\n{'=' * 105}\n{h}\n{'-' * 105}")
        ev = 0
        for n in sorted(self.quotes, key=lambda k: -self.quotes[k].fair):
            q = self.quotes[n]
            e = (q.fair - q.bid) * q.size
            ev += e
            print(f"{n:<28} {q.fair*100:>5.1f}% {q.bid:>6.2f} {q.ask:>6.2f} {q.spread_c:>5.1f}\u00a2 {q.size:>4} ${e:>+6.1f} ${taker_fee(q.size,q.bid):>5.2f} ${maker_rebate(q.size,q.bid):>+6.2f} {q.roi:>+6.1f}%")
        print(f"{'':>67} ${ev:>+6.1f} TOTAL\n{'=' * 105}")

    async def discover(self, query: str):
        print(f"\n[DISCOVERY] Searching: {query}")
        markets = self.disc.find_markets(query)
        print(f"[DISCOVERY] Found {len(markets)} markets")
        for q, info in list(markets.items())[:5]:
            print(f"  {q[:60]}")
            print(f"    Prices: {info['prices']}")
            for o, tid in list(info["tokens"].items())[:2]:
                print(f"    {o}: {tid[:30]}...")
        return markets

    async def place_quotes(self):
        """Place all quotes on Polymarket."""
        if self.dry_run:
            print("\n[DRY RUN] Would place:")
            for n, q in self.quotes.items():
                print(f"  {n}: BUY {q.size} @ ${q.bid:.2f} | SELL {q.size} @ ${q.ask:.2f}")
            return

        if not self.secure_client:
            print("[ERROR] No secure client")
            return

        print(f"\n[ORDERS] Placing {len(self.quotes)} quotes...")
        for name, q in self.quotes.items():
            if not q.token_id:
                print(f"  [SKIP] {name}: no token ID")
                continue
            try:
                # Place BUY limit for YES at bid
                resp = await self.secure_client.place_limit_order(
                    token_id=q.token_id, side="BUY", price=str(q.bid), size=str(q.size)
                )
                if resp.ok:
                    self.active_orders[f"{name}_BUY"] = resp.order_id
                    print(f"  [BUY]  {name} @ ${q.bid:.2f} x {q.size} -> {resp.order_id[:16]}...")
                else:
                    print(f"  [FAIL] {name} BUY: {resp.message}")

                # Place SELL limit for YES at ask
                resp2 = await self.secure_client.place_limit_order(
                    token_id=q.token_id, side="SELL", price=str(q.ask), size=str(q.size)
                )
                if resp2.ok:
                    self.active_orders[f"{name}_SELL"] = resp2.order_id
                    print(f"  [SELL] {name} @ ${q.ask:.2f} x {q.size} -> {resp2.order_id[:16]}...")
                else:
                    print(f"  [FAIL] {name} SELL: {resp2.message}")

                await asyncio.sleep(0.3)  # Rate limit
            except Exception as e:
                print(f"  [ERROR] {name}: {e}")

    async def cancel_all_orders(self):
        """Cancel all active orders."""
        if self.dry_run:
            print(f"[DRY RUN] Would cancel {len(self.active_orders)} orders")
            return
        if not self.secure_client:
            return

        print(f"\n[CANCEL] Cancelling {len(self.active_orders)} orders...")
        for key, oid in list(self.active_orders.items()):
            try:
                resp = await self.secure_client.cancel_order(order_id=oid)
                if resp.canceled:
                    print(f"  [CANCEL] {key}: {resp.canceled[0][:16]}...")
                del self.active_orders[key]
            except Exception as e:
                print(f"  [ERROR] {key}: {e}")

    async def on_goal(self, data: dict):
        """Handle live goal — recalculate and replace quotes."""
        score = data.get("score", "0-0")
        parts = score.split("-")
        hs = int(parts[0]) if parts[0].isdigit() else 0
        aws = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        print(f"\n[⚽ GOAL! {hs}-{aws} | {data.get('period','')} {data.get('elapsed','')}]")

        self.probs = recalc_probs(self.probs, hs, aws)
        self.build_quotes()
        self.show_quotes()

        if not self.dry_run:
            await self.cancel_all_orders()
            await self.place_quotes()

    async def ws_sports(self):
        """Connect to Sports WebSocket for live scores."""
        print("[SPORTS_WS] Connecting...")
        async with websockets.connect("wss://sports-api.polymarket.com/ws", ping_interval=None) as ws:
            print("[SPORTS_WS] Connected — listening for live scores")
            async for msg in ws:
                if msg == "ping":
                    await ws.send("pong")
                elif msg.startswith("{"):
                    try:
                        d = json.loads(msg)
                        if d.get("event_type") == "sports_result":
                            await self.on_goal(d)
                    except json.JSONDecodeError:
                        pass

    async def ws_user(self):
        """Connect to User WebSocket for fill notifications."""
        if not self.secure_client or self.dry_run:
            return
        try:
            stream = await self.secure_client.subscribe(UserSpec())
            async with stream:
                print("[USER_WS] Connected — listening for fills")
                async for event in stream:
                    if hasattr(event, "order_side"):  # UserOrderEvent
                        side = event.order_side
                        price = float(event.price) if hasattr(event, "price") else 0
                        size = float(event.original_size) if hasattr(event, "original_size") else 0
                        market = event.market if hasattr(event, "market") else "unknown"
                        print(f"  [FILL] {side} {size} @ ${price:.4f} ({market[:30]}...)")
                        # Record in P&L
                        for name, q in self.quotes.items():
                            if q.token_id == event.asset_id:
                                self.pnl.record_fill(
                                    market=name, side=side, price=price,
                                    size=int(size), is_maker=True
                                )
                                break
        except Exception as e:
            print(f"[USER_WS] Error: {e}")

    async def show_status(self):
        """Show current positions and P&L."""
        self.pnl.print_summary()
        if self.active_orders:
            print(f"\nActive orders: {len(self.active_orders)}")
            for key, oid in list(self.active_orders.items())[:10]:
                print(f"  {key}: {oid[:20]}...")

    async def run(self, query: str = "", show_status_only: bool = False):
        """Main run loop."""
        print(f"\n{'=' * 60}")
        print(f"POLYMARKET BOT v3 | {'DRY RUN' if self.dry_run else 'LIVE'}")
        print(f"SDK: {'Available' if HAS_SDK else 'NOT INSTALLED'}")
        print(f"{'=' * 60}")

        if show_status_only:
            await self.show_status()
            return

        # Initialize secure client for live mode
        if not self.dry_run and self.pk and HAS_SDK:
            self.secure_client = await AsyncSecureClient.create(
                private_key=self.pk,
                wallet=self.wallet if self.wallet else None,
            )
            print("[AUTH] Secure client initialized")

        # Default probabilities
        if not self.probs:
            self.probs = {
                "Lamine Yamal o0.5": 0.42, "Dani Olmo o0.5": 0.38,
                "Ferrán Torres o0.5": 0.35, "Fabián Ruiz o0.5": 0.28,
                "Alex Baena o0.5": 0.25, "Gavi Paez o0.5": 0.22,
                "Borja Iglesias o0.5": 0.30, "Cucurella o0.5": 0.08,
                "Eric García o0.5": 0.05, "Marc Pubill o0.5": 0.04,
                "Dailon Livramento o0.5": 0.06, "Lamine Yamal o1.5": 0.18,
                "Dani Olmo o1.5": 0.15, "Ferrán Torres o1.5": 0.13,
                "Borja Iglesias o1.5": 0.10, "Cucurella o1.5": 0.02,
                "Eric García o1.5": 0.01,
            }

        # Discover markets
        if query:
            markets = await self.discover(query)
            for q_text, info in markets.items():
                for prob_name in self.probs:
                    if prob_name.lower() in q_text.lower():
                        tok = info["tokens"].get("Yes", "")
                        if tok:
                            self.quotes[prob_name] = Quote(
                                prob_name, self.probs[prob_name],
                                *safe_price(self.probs[prob_name]),
                                safe_size(self.probs[prob_name]), tok
                            )

        self.build_quotes()
        self.show_quotes()
        await self.place_quotes()

        if self.dry_run:
            print("\n[DRY RUN] Done.")
            return

        # Live monitoring
        print("\n[BOT] Starting live monitoring...")
        try:
            await asyncio.gather(
                self.ws_sports(),
                self.ws_user(),
            )
        except KeyboardInterrupt:
            print("\n[BOT] Stopping...")
            await self.cancel_all_orders()
            self.pnl.print_summary()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Polymarket Quoting Bot v3")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--private-key", default=os.environ.get("POLYMARKET_PRIVATE_KEY", ""))
    parser.add_argument("--wallet", default=os.environ.get("POLYMARKET_WALLET_ADDRESS", ""))
    parser.add_argument("--query", default="", help="Market search query")
    parser.add_argument("--status", action="store_true", help="Show positions and P&L")
    args = parser.parse_args()

    bot = PolymarketBot(
        dry_run=not args.live,
        private_key=args.private_key,
        wallet=args.wallet,
    )
    await bot.run(query=args.query, show_status_only=args.status)


if __name__ == "__main__":
    asyncio.run(main())
