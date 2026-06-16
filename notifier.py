#!/usr/bin/env python3
"""
Trading Bot Notifier
=====================
Sends notifications via the Hermes gateway using the irc tool.
This is a helper script that formats messages and outputs them
in a format that can be sent via the irc tool.

Usage:
  python3 notifier.py quote "BTC" 0.42 0.19 0.65 500 121.1
  python3 notifier.py fill "BTC" BUY 0.19 500 2.31 0.58
  python3 notifier.py goal "Spain vs Cape Verde" "1-0" "1H" "36:00"
  python3 notifier.py divergence "BTC" "Bitunix" 66423.9 "HL" 66512.3 0.15
  python3 notifier.py pnl
  python3 notifier.py status running 17 34

Output: JSON that can be sent via irc tool to Telegram.
"""

import json
import sys
from datetime import datetime


def format_quote(market, fair, bid, ask, size, roi):
    return (
        f"📊 Quote: {market}\n"
        f"Fair: {float(fair)*100:.1f}% | Bid: {bid} | Ask: {ask}\n"
        f"Size: {size} | ROI: {float(roi):+.1f}%\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
    )


def format_fill(market, side, price, size, fee, rebate):
    return (
        f"✅ Fill: {market}\n"
        f"Side: {side} | Price: {price} | Size: {size}\n"
        f"Fee: ${float(fee):.2f} | Rebate: ${float(rebate):.2f}\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
    )


def format_goal(match, score, period, elapsed):
    return (
        f"⚽ GOAL: {match}\n"
        f"Score: {score} | {period} {elapsed}\n"
        f"Recalculating quotes..."
    )


def format_divergence(market, venue_a, price_a, venue_b, price_b, diff):
    emoji = "🔴" if abs(float(diff)) > 0.2 else "🟡" if abs(float(diff)) > 0.1 else "🟢"
    return (
        f"{emoji} Divergence: {market}\n"
        f"{venue_a}: {price_a}\n"
        f"{venue_b}: {price_b}\n"
        f"Diff: {float(diff):+.3f}%\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
    )


def format_pnl(summary):
    return (
        f"📈 P&L Summary\n"
        f"Fills: {summary['total_fills']}\n"
        f"Fees: ${summary['total_fees']:.2f}\n"
        f"Rebates: ${summary['total_rebates']:.2f}\n"
        f"Net: ${summary['net_fees']:.2f}\n"
        f"Positions: {len(summary.get('positions', {}))}"
    )


def format_status(status, markets, orders):
    emoji = "🟢" if status == "running" else "🔴"
    return (
        f"{emoji} Bot Status: {status}\n"
        f"Markets: {markets} | Orders: {orders}\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
    )


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    output = {}

    if cmd == "quote" and len(sys.argv) >= 8:
        output["message"] = format_quote(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6], sys.argv[7])
    elif cmd == "fill" and len(sys.argv) >= 8:
        output["message"] = format_fill(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6], sys.argv[7])
    elif cmd == "goal" and len(sys.argv) >= 6:
        output["message"] = format_goal(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
    elif cmd == "divergence" and len(sys.argv) >= 8:
        output["message"] = format_divergence(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6], sys.argv[7])
    elif cmd == "pnl":
        # Read from PnL file
        try:
            with open("polymarket_pnl.json") as f:
                data = json.load(f)
            summary = {
                "total_fills": len(data.get("fills", [])),
                "total_fees": data.get("total_fees", 0),
                "total_rebates": data.get("total_rebates", 0),
                "net_fees": data.get("total_fees", 0) - data.get("total_rebates", 0),
                "positions": {k: v for k, v in data.get("positions", {}).items() if v.get("shares", 0) > 0},
            }
            output["message"] = format_pnl(summary)
        except:
            output["message"] = "📈 P&L: No data yet"
    elif cmd == "status" and len(sys.argv) >= 5:
        output["message"] = format_status(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        print(f"Unknown command or wrong args: {cmd}")
        print(__doc__)
        sys.exit(1)

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
