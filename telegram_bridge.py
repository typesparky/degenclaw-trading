#!/usr/bin/env python3
"""
Telegram Bridge for Trading Bots
==================================
Sends notifications to Telegram via the Hermes gateway.
Connects to the gateway's local API and routes messages to configured channels.

Usage:
  python3 telegram_bridge.py --send "BTC divergence: BX 0.15% below HL"
  python3 telegram_bridge.py --status
  python3 telegram_bridge.py --configure-channel <channel_id>
"""

import json
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

GATEWAY_HOST = "localhost"
GATEWAY_PORT = 3000
PROFILES_DIR = Path("~/.hermes/profiles").expanduser()
QUANT_PROFILE = PROFILES_DIR / "quant"
CHANNEL_DIR = QUANT_PROFILE / "channel_directory.json"
SESSIONS_DIR = QUANT_PROFILE / "sessions"


# ═══════════════════════════════════════════════════════════════════════════════
# GATEWAY CLIENT
# ═══════════════════════════════════════════════════════════════════════════════

class HermesGateway:
    """Client for the Hermes gateway local API."""

    def __init__(self, host=GATEWAY_HOST, port=GATEWAY_PORT):
        self.base_url = f"http://{host}:{port}"
        self._session = None

    @property
    def session(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
        return self._session

    def health(self) -> dict:
        """Check gateway health."""
        try:
            r = self.session.get(f"{self.base_url}/health", timeout=5)
            return r.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_channels(self) -> dict:
        """Get configured channels."""
        try:
            r = self.session.get(f"{self.base_url}/api/channels", timeout=5)
            return r.json()
        except Exception as e:
            return {"error": str(e)}

    def send_message(self, channel: str, message: str, platform: str = "telegram") -> dict:
        """Send a message to a specific channel."""
        try:
            r = self.session.post(
                f"{self.base_url}/api/send",
                json={
                    "platform": platform,
                    "channel": channel,
                    "message": message,
                },
                timeout=10,
            )
            return r.json()
        except Exception as e:
            return {"error": str(e)}

    def get_sessions(self) -> list:
        """Get active sessions."""
        try:
            r = self.session.get(f"{self.base_url}/api/sessions", timeout=5)
            return r.json()
        except Exception as e:
            return []


# ═══════════════════════════════════════════════════════════════════════════════
# NOTIFICATION FORMATTERS
# ═══════════════════════════════════════════════════════════════════════════════

class NotificationFormatter:
    """Format trading notifications for Telegram."""

    @staticmethod
    def quote_alert(market: str, fair: float, bid: float, ask: float, size: int, roi: float) -> str:
        return (
            f"📊 <b>Quote Alert</b>\n"
            f"Market: <code>{market}</code>\n"
            f"Fair: {fair*100:.1f}% | Bid: {bid:.2f} | Ask: {ask:.2f}\n"
            f"Size: {size} | ROI: {roi:+.1f}%\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )

    @staticmethod
    def fill_alert(market: str, side: str, price: float, size: int, fee: float, rebate: float) -> str:
        return (
            f"✅ <b>Fill</b>\n"
            f"Market: <code>{market}</code>\n"
            f"Side: {side} | Price: {price:.4f} | Size: {size}\n"
            f"Fee: ${fee:.2f} | Rebate: ${rebate:.2f}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )

    @staticmethod
    def goal_alert(match: str, score: str, period: str, elapsed: str) -> str:
        return (
            f"⚽ <b>GOAL!</b>\n"
            f"Match: {match}\n"
            f"Score: {score} | {period} {elapsed}\n"
            f"Recalculating quotes..."
        )

    @staticmethod
    def divergence_alert(market: str, venue_a: str, price_a: float,
                         venue_b: str, price_b: float, diff_pct: float) -> str:
        emoji = "🔴" if abs(diff_pct) > 0.2 else "🟡" if abs(diff_pct) > 0.1 else "🟢"
        return (
            f"{emoji} <b>Divergence</b>\n"
            f"Market: <code>{market}</code>\n"
            f"{venue_a}: {price_a:.4f}\n"
            f"{venue_b}: {price_b:.4f}\n"
            f"Diff: {diff_pct:+.3f}%\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )

    @staticmethod
    def pnl_summary(summary: dict) -> str:
        return (
            f"📈 <b>P&L Summary</b>\n"
            f"Fills: {summary['total_fills']}\n"
            f"Fees: ${summary['total_fees']:.2f}\n"
            f"Rebates: ${summary['total_rebates']:.2f}\n"
            f"Net: ${summary['net_fees']:.2f}\n"
            f"Positions: {len(summary.get('positions', {}))}"
        )

    @staticmethod
    def bot_status(status: str, markets: int, orders: int) -> str:
        emoji = "🟢" if status == "running" else "🔴"
        return (
            f"{emoji} <b>Bot Status</b>\n"
            f"Status: {status}\n"
            f"Markets: {markets}\n"
            f"Active orders: {orders}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CHANNEL CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

def load_channels() -> dict:
    """Load channel directory."""
    try:
        with open(CHANNEL_DIR) as f:
            return json.load(f)
    except:
        return {"platforms": {"telegram": []}}

def save_channels(channels: dict):
    """Save channel directory."""
    with open(CHANNEL_DIR, "w") as f:
        json.dump(channels, f, indent=2)

def add_telegram_channel(channel_id: str, name: str = "trading-alerts"):
    """Add a Telegram channel to the directory."""
    channels = load_channels()
    telegram_channels = channels.get("platforms", {}).get("telegram", [])
    entry = {"id": channel_id, "name": name, "enabled": True}
    if entry not in telegram_channels:
        telegram_channels.append(entry)
    channels.setdefault("platforms", {})["telegram"] = telegram_channels
    save_channels(channels)
    print(f"✓ Added Telegram channel: {channel_id} ({name})")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Telegram Bridge for Trading Bots")
    parser.add_argument("--send", type=str, help="Send a message")
    parser.add_argument("--channel", type=str, default=None, help="Target channel ID")
    parser.add_argument("--status", action="store_true", help="Check gateway status")
    parser.add_argument("--channels", action="store_true", help="List configured channels")
    parser.add_argument("--configure-channel", type=str, help="Add a Telegram channel ID")
    parser.add_argument("--platform", type=str, default="telegram", help="Platform (default: telegram)")
    args = parser.parse_args()

    gateway = HermesGateway()

    if args.status:
        health = gateway.health()
        print(f"Gateway: {health.get('status', 'unknown')}")
        channels = gateway.get_channels()
        print(f"Channels: {json.dumps(channels, indent=2)[:500]}")
        return

    if args.channels:
        channels = load_channels()
        telegram = channels.get("platforms", {}).get("telegram", [])
        print(f"Telegram channels: {len(telegram)}")
        for ch in telegram:
            print(f"  - {ch.get('id', '?')} ({ch.get('name', 'unknown')})")
        return

    if args.configure_channel:
        add_telegram_channel(args.configure_channel)
        return

    if args.send:
        channel = args.channel
        if not channel:
            # Try to find first configured Telegram channel
            channels = load_channels()
            telegram = channels.get("platforms", {}).get("telegram", [])
            if telegram:
                channel = telegram[0].get("id")
            else:
                print("ERROR: No Telegram channel configured. Use --configure-channel <id>")
                sys.exit(1)

        result = gateway.send_message(channel, args.send, args.platform)
        if "error" in result:
            print(f"ERROR: {result['error']}")
            sys.exit(1)
        else:
            print(f"✓ Message sent to {args.platform}/{channel}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
