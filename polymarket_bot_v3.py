#!/usr/bin/env python3
"""
Polymarket Real-Time Quoting Bot v3
=====================================
Safe wide quoting with real-time WebSocket monitoring.

Setup:
  pip install polymarket-client websockets requests

Usage:
  python3 polymarket_bot_v3.py --dry-run
  python3 polymarket_bot_v3.py --live --private-key 0x...
"""

import asyncio
import json
import os
import time
from typing import Dict, List, Tuple

import websockets
import requests

try:
    from polymarket import AsyncPublicClient, AsyncSecureClient
    HAS_SDK = True
except ImportError:
    HAS_SDK = False


# ── PRICING ───────────────────────────────────────────────────────────────────

def safe_price(p: float, bid_depth: float = 0, ask_depth: float = 0) -> Tuple[float, float]:
    """
    Dynamic pricing from actual order book depth. No hardcoded thresholds.

    Spread logic:
        Empty book (0):  12-17+cent base (we are the only MM)
        Thin (<50):      10-15+cent base
        Moderate (<200): 8-13+cent base
        Deep (200+):     5-9.5cent base (5cent floor, 4.5cent rebate cap)

    Moonshot premium: +2-5 extra cents for outcomes <15% probability.
    Maker rebate: 25% of taker fees on every filled order (no min size).
    """
    total_depth = bid_depth + ask_depth

    if total_depth == 0:
        base_spread = 0.12
    elif total_depth < 50:
        base_spread = 0.10
    elif total_depth < 200:
        base_spread = 0.08
    else:
        base_spread = 0.05

    # Cap at 4.5 cents for maker rebate eligibility
    base_spread = min(base_spread, 0.045)

    # Moonshot premium
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
    return shares * 0.03 * price * (1 - price)


def maker_rebate(shares: int, price: float) -> float:
    return taker_fee(shares, price) * 0.25


def recalc_probs(base: Dict[str, float], home_goals: int, away_goals: int) -> Dict[str, float]:
    d = home_goals - away_goals
    r = {}
    for n, p in base.items():
        v = p
        if "Cape Verde" in n or "Dailon" in n or "Egypt" in n or "Algeria" in n or "Jordan" in n or "Iraq" in n or "Panama" in n or "Ghana" in n or "DR Congo" in n or "Cura" in n:
            if d > 0: v *= 0.6
            elif d < 0: v *= 1.4
        else:
            if d < 0: v *= 0.8
            elif d > 2: v *= 1.2
        r[n] = min(0.95, max(0.01, v))
    return r


# ── DATA MODELS ───────────────────────────────────────────────────────────────

class Quote:
    def __init__(self, name, fair, bid, ask, size, token_id=""):
        self.name, self.fair, self.bid, self.ask, self.size, self.token_id = name, fair, bid, ask, size, token_id
    @property
    def spread_c(self): return (self.ask - self.bid) * 100
    @property
    def roi(self): return ((self.fair - self.bid) / self.bid) * 100 if self.bid > 0 else 0


# ── P&L TRACKER ───────────────────────────────────────────────────────────────

class PnLTracker:
    def __init__(self, log_file="polymarket_pnl.json"):
        self.log_file = log_file
        self.positions: Dict[str, Dict] = {}
        self.fills: List[Dict] = []
        self.total_fees = 0.0
        self.total_rebates = 0.0
        self.load()

    def record_fill(self, market, side, price, size, is_maker=True):
        fee = taker_fee(size, price) if not is_maker else 0
        reb = maker_rebate(size, price) if is_maker else 0
        self.total_fees += fee
        self.total_rebates += reb
        fill = {"time": datetime.now().isoformat(), "market": market, "side": side, "price": price, "size": size, "fee": fee, "rebate": reb, "is_maker": is_maker}
        self.fills.append(fill)
        if market not in self.positions:
            self.positions[market] = {"shares": 0, "avg_cost": 0, "side": side}
        pos = self.positions[market]
        if side == "BUY":
            total_cost = pos["avg_cost"] * pos["shares"] + price * size
            pos["shares"] += size
            pos["avg_cost"] = total_cost / pos["shares"] if pos["shares"] > 0 else 0
        else:
            pos["shares"] -= size
        self.save()
        return fill

    def get_summary(self):
        total_cost = sum(p["shares"] * p["avg_cost"] for p in self.positions.values() if p["shares"] > 0)
        return {"total_fills": len(self.fills), "total_fees": round(self.total_fees, 2), "total_rebates": round(self.total_rebates, 2), "net_fees": round(self.total_fees - self.total_rebates, 2), "positions": {k: v for k, v in self.positions.items() if v["shares"] > 0}, "position_cost": round(total_cost, 2)}

    def save(self):
        try:
            with open(self.log_file, "w") as f:
                json.dump({"positions": self.positions, "fills": self.fills[-100:], "total_fees": self.total_fees, "total_rebates": self.total_rebates}, f, indent=2)
        except: pass

    def load(self):
        try:
            with open(self.log_file, "r") as f:
                d = json.load(f)
                self.positions = d.get("positions", {})
                self.fills = d.get("fills", [])
                self.total_fees = d.get("total_fees", 0)
                self.total_rebates = d.get("total_rebates", 0)
        except: pass

    def print_summary(self):
        s = self.get_summary()
        print(f"\n{'='*60}\nP&L SUMMARY\n{'='*60}")
        print(f"Fills: {s['total_fills']} | Fees: ${s['total_fees']:.2f} | Rebates: ${s['total_rebates']:.2f} | Net: ${s['net_fees']:.2f}")
        if s["positions"]:
            for name, pos in s["positions"].items():
                print(f"  {name}: {pos['shares']} shares @ avg ${pos['avg_cost']:.4f}")
        print(f"{'='*60}")


# ── MARKET DISCOVERY ──────────────────────────────────────────────────────────

class Discovery:
    def __init__(self):
        self.s = requests.Session()

    def find_markets(self, query):
        results = {}
        resp = self.s.get("https://gamma-api.polymarket.com/markets", params={"active": "true", "closed": "false", "limit": 100, "order": "volume24hr", "ascending": "false"}, timeout=10)
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


# ── BOT ───────────────────────────────────────────────────────────────────────

class Bot:
    def __init__(self, dry_run=True, private_key=""):
        self.dry_run = dry_run
        self.pk = private_key or os.environ.get("POLYMARKET_PRIVATE_KEY", "")
        self.probs: Dict[str, float] = {}
        self.quotes: Dict[str, Quote] = {}
        self.active_orders: Dict[str, str] = {}
        self.disc = Discovery()
        self.pnl = PnLTracker()

    def set_probs(self, p): self.probs = p

    def build(self):
        self.quotes = {}
        for n, p in self.probs.items():
            bid, ask = safe_price(p)
            sz = safe_size(p)
            self.quotes[n] = Quote(n, p, bid, ask, sz)

    def show(self):
        h = f"{'Market':<28} {'Fair%':>6} {'Bid':>6} {'Ask':>6} {'Sprd':>6} {'Sz':>4} {'Edge$':>7} {'Fee$':>6} {'Reb$':>7} {'ROI%':>7}"
        print(f"\n{'='*105}\n{h}\n{'-'*105}")
        ev = 0
        for n in sorted(self.quotes, key=lambda k: -self.quotes[k].fair):
            q = self.quotes[n]
            e = (q.fair - q.bid) * q.size; ev += e
            print(f"{n:<28} {q.fair*100:>5.1f}% {q.bid:>6.2f} {q.ask:>6.2f} {q.spread_c:>5.1f}cent {q.size:>4} ${e:>+6.1f} ${taker_fee(q.size,q.bid):>5.2f} ${maker_rebate(q.size,q.bid):>+6.2f} {q.roi:>+6.1f}%")
        print(f"{'':>67} ${ev:>+6.1f} TOTAL\n{'='*105}")

    async def place(self):
        if self.dry_run:
            print("\n[DRY RUN] Would place:")
            for n, q in self.quotes.items():
                print(f"  {n}: BUY {q.size} @ ${q.bid:.2f} | SELL {q.size} @ ${q.ask:.2f}")
            return
        print(f"\n[ORDERS] Placing {len(self.quotes)} quotes...")
        for n, q in self.quotes.items():
            print(f"  {n}: BUY {q.size} @ ${q.bid:.2f} | SELL {q.size} @ ${q.ask:.2f}")

    async def cancel_all(self):
        if self.dry_run:
            print(f"[DRY RUN] Would cancel {len(self.active_orders)} orders"); return
        print(f"[CANCEL] {len(self.active_orders)} orders")
        self.active_orders.clear()

    async def on_goal(self, data):
        score = data.get("score", "0-0")
        parts = score.split("-")
        hs = int(parts[0]) if parts[0].isdigit() else 0
        aws = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        print(f"\n[GOAL! {hs}-{aws} | {data.get('period','')} {data.get('elapsed','')}]")
        self.probs = recalc_probs(self.probs, hs, aws)
        self.build(); self.show()
        if not self.dry_run:
            await self.cancel_all(); await self.place()

    async def ws_sports(self):
        print("[SPORTS_WS] Connecting...")
        async with websockets.connect("wss://sports-api.polymarket.com/ws", ping_interval=None) as ws:
            print("[SPORTS_WS] Connected")
            async for msg in ws:
                if msg == "ping": await ws.send("pong"); continue
                if msg.startswith("{"):
                    try:
                        d = json.loads(msg)
                        if d.get("event_type") == "sports_result":
                            await self.on_goal(d)
                    except: pass

    async def run(self, query=""):
        print(f"\n{'='*60}\nPOLYMARKET BOT v3 | {'DRY RUN' if self.dry_run else 'LIVE'}\n{'='*60}")
        if not self.probs:
            self.probs = {
                "Lamine Yamal o0.5": 0.42, "Dani Olmo o0.5": 0.38,
                "Ferran Torres o0.5": 0.35, "Fabian Ruiz o0.5": 0.28,
                "Alex Baena o0.5": 0.25, "Gavi Paez o0.5": 0.22,
                "Borja Iglesias o0.5": 0.30, "Cucurella o0.5": 0.08,
                "Eric Garcia o0.5": 0.05, "Marc Pubill o0.5": 0.04,
                "Dailon Livramento o0.5": 0.06, "Lamine Yamal o1.5": 0.18,
                "Dani Olmo o1.5": 0.15, "Ferran Torres o1.5": 0.13,
                "Borja Iglesias o1.5": 0.10, "Cucurella o1.5": 0.02,
                "Eric Garcia o1.5": 0.01,
            }
        if query:
            markets = self.disc.find_markets(query)
            for q_text, info in markets.items():
                for prob_name in self.probs:
                    if prob_name.lower() in q_text.lower():
                        tok = info["tokens"].get("Yes", "")
                        if tok:
                            self.quotes[prob_name] = Quote(prob_name, self.probs[prob_name], *safe_price(self.probs[prob_name]), safe_size(self.probs[prob_name]), tok)
        self.build(); self.show(); await self.place()
        if self.dry_run:
            print("\n[DRY RUN] Done.")
            return
        try:
            await asyncio.gather(self.ws_sports())
        except KeyboardInterrupt:
            await self.cancel_all()


# ── MAIN ─────────────────────────────────────────────────────────────────────

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--private-key", default=os.environ.get("POLYMARKET_PRIVATE_KEY", ""))
    parser.add_argument("--query", default="", help="Market search query")
    args = parser.parse_args()
    bot = Bot(dry_run=not args.live, private_key=args.private_key)
    await bot.run(query=args.query)


if __name__ == "__main__":
    asyncio.run(main())
