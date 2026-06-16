#!/usr/bin/env python3
"""
Polymarket Market Scanner
==========================
Scans all live sports markets, finds thin order books,
and outputs a formatted report for Telegram.

Usage:
  python3 scan_polymarket.py
  python3 scan_polymarket.py --min-vol 10000
  python3 scan_polymarket.py --event "Spain"
"""

import requests
import json
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional


def get_events(limit=100):
    """Get all active events."""
    resp = requests.get('https://gamma-api.polymarket.com/events', params={
        'active': 'true', 'closed': 'false', 'limit': limit,
        'order': 'volume24hr', 'ascending': 'false',
    }, timeout=15)
    return resp.json()


def get_orderbook(condition_id: str) -> Optional[Dict]:
    """Get order book depth for a market."""
    try:
        resp = requests.get(
            f'https://clob.polymarket.com/markets/{condition_id}',
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return None


def is_sports_event(title: str, slug: str) -> bool:
    """Filter for sports events only."""
    keywords = [
        'vs', 'cup', 'fifa', 'world cup', 'match', 'game',
        'fc', 'united', 'city', 'real', 'barcelona', 'liverpool',
        'arsenal', 'chelsea', 'manchester', 'bayern', 'psg',
        'juventus', 'milan', 'inter', 'roma', 'napoli', 'atletico',
        'tottenham', 'dortmund', 'leipzig', 'sevilla', 'valencia',
        'villarreal', 'athletic', 'real sociedad', 'celta', 'betis',
        'lyon', 'marseille', 'lille', 'monaco', 'porto', 'benfica',
        'sporting', 'ajax', 'psv', 'feyenoord', 'club brugge',
        'anderlecht', 'celtic', 'rangers', 'galatasaray', 'fenerbahce',
        'besiktas', 'olympiacos', 'panathinaikos', 'aek', 'paok',
        'copenhagen', 'malmo', 'rosenborg', 'salzburg', 'rapid',
        'legia', 'lech', 'sporting cp', 'braga', 'guimaraes',
        'boavista', 'estoril', 'moreirense', 'farense', 'arouca',
        'estoril', 'vitoria', 'famalicao', 'gil vicente', 'penafiel',
        'estoril praia', 'cd nacional', 'cf os belenenses', 'sc farense',
        'rio ave', 'fc vilafranquense', 'cd trofense', 'sc covilha',
        'ud oliveirense', 'cd mafra', 'fc penafiel', 'leixoes sc',
        'sc espinho', 'fc felgueiras', 'ad sanjoanense', 'cd cinfães',
        'gondomar sc', 'uscs porto', 'sc salgueiros', 'rebordosa ac',
        'amarante fc', 'pedras salgadas', 'sc vianense', 'cd riva',
        'merelinense fc', 'ad fafe', 'mondinense fc', 'torreense',
        'caldas sc', 'cd fatima', 'sc praiense', 'lusitania fc',
        'oriental dragon', 'real sc', 'cova da piedade', 'atletico cp',
        'casa pia', 'estrela amadora', 'benfica b', 'sporting b',
        'porto b', 'braga b', 'vitoria guimaraes b', 'rio ave b',
        'boavista b', 'famalicao b', 'gil vicente b', 'estoril b',
        'penafiel b', 'trofense b', 'felgueiras b', 'sanjoanense b',
        'riva b', 'merelinense b', 'fafe b', 'mondinense b', 'torreense b',
        'caldas b', 'fatima b', 'praiense b', 'lusitania b', 'oriental b',
        'real b', 'cova b', 'atletico b', 'casa pia b', 'estrela b',
        'nfl', 'nba', 'mlb', 'nhl', 'ufc', 'mma', 'boxing', 'tennis',
        'golf', 'cricket', 'rugby', 'formula 1', 'f1', 'nascar',
        'esports', 'lol', 'dota', 'cs:go', 'cs2', 'valorant', 'overwatch',
        'rocket league', 'fortnite', 'apex legends', 'call of duty',
        'rainbow six', 'pubg', 'hearthstone', 'starcraft', 'warcraft',
        'counter-strike', 'natus', 'g2', 'navi', 'faze', 'astralis',
        'vitality', 'liquid', 'cloud9', 'fnatic', 'ence', 'heroic',
        'gambit', 'spirit', 'virtus.pro', 'forze', 'og', 'evil geniuses',
        '100 thieves', 'sentinels', 'cloud 9', 'team liquid', 'fnatic',
        'ence', 'heroic', 'gambit', 'spirit', 'virtus pro', 'forze',
        'og', 'evil geniuses', '100 thieves', 'sentinels',
        'basketball', 'football', 'soccer', 'hockey', 'baseball',
        'volleyball', 'handball', 'water polo', 'badminton', 'squash',
        'table tennis', 'cycling', 'swimming', 'athletics', 'gymnastics',
        'wrestling', 'judo', 'karate', 'taekwondo', 'fencing', 'archery',
        'shooting', 'weightlifting', 'rowing', 'sailing', 'surfing',
        'skateboarding', 'climbing', 'breaking', 'parkour',
    ]
    text = (title + ' ' + slug).lower()
    return any(kw in text for kw in keywords)


def scan_markets(min_volume=0, event_filter=None):
    """Scan all sports markets and return structured data."""
    events = get_events()
    
    results = []
    for e in events:
        title = e.get('title', '')
        slug = e.get('slug', '')
        start = e.get('startDate', '')
        
        if not is_sports_event(title, slug):
            continue
        if event_filter and event_filter.lower() not in title.lower():
            continue
            
        markets = e.get('markets', [])
        for m in markets:
            q = m.get('question', '')
            prices_raw = m.get('outcomePrices', '[]')
            prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
            outcomes_raw = m.get('outcomes', '[]')
            outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw
            vol = float(m.get('volume', 0) or 0)
            cid = m.get('conditionId', '')
            
            if vol < min_volume:
                continue
                
            # Parse start time
            start_str = ''
            started = False
            try:
                if start:
                    start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                    now = datetime.now(timezone.utc)
                    diff = (now - start_dt).total_seconds()
                    started = diff > 0
                    if started:
                        hours_ago = diff / 3600
                        if hours_ago < 1:
                            start_str = f"{int(diff/60)}m ago"
                        elif hours_ago < 24:
                            start_str = f"{int(hours_ago)}h ago"
                        else:
                            start_str = f"{int(hours_ago/24)}d ago"
                    else:
                        hours_to = -diff / 3600
                        if hours_to < 1:
                            start_str = f"in {int(-diff/60)}m"
                        elif hours_to < 24:
                            start_str = f"in {int(hours_to)}h"
                        else:
                            start_str = f"in {int(hours_to/24)}d"
            except:
                start_str = start[:10] if start else '?'
            
            results.append({
                'event': title[:60],
                'question': q[:80],
                'outcomes': outcomes,
                'prices': prices,
                'volume': vol,
                'start': start_str,
                'started': started,
                'condition_id': cid,
            })
    
    return results


def format_telegram_report(markets: List[Dict]) -> str:
    """Format market scan results for Telegram."""
    
    # Group by event
    events = {}
    for m in markets:
        event = m['event']
        if event not in events:
            events[event] = []
        events[event].append(m)
    
    # Sort events by total volume
    event_vols = {}
    for event, ms in events.items():
        event_vols[event] = sum(m['volume'] for m in ms)
    
    lines = []
    lines.append("📊 <b>Polymarket Sports Markets</b>")
    lines.append(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC")
    lines.append(f"📈 {len(markets)} markets across {len(events)} events")
    lines.append("")
    
    # Live events first
    live_events = []
    upcoming_events = []
    for event, ms in events.items():
        is_live = any(m['started'] for m in ms)
        if is_live:
            live_events.append((event, ms))
        else:
            upcoming_events.append((event, ms))
    
    if live_events:
        lines.append("🔴 <b>LIVE EVENTS</b>")
        lines.append("─" * 30)
        for event, ms in sorted(live_events, key=lambda x: -event_vols[x[0]]):
            total_vol = sum(m['volume'] for m in ms)
            lines.append(f"\n⚽ <b>{event}</b>")
            lines.append(f"   Vol: ${total_vol:,.0f} | Markets: {len(ms)}")
            
            # Show top 5 markets by volume
            top_markets = sorted(ms, key=lambda x: -x['volume'])[:5]
            for m in top_markets:
                prices = m['prices']
                outcomes = m['outcomes']
                price_str = " | ".join(
                    f"{o}: {float(p)*100:.1f}¢" 
                    for o, p in zip(outcomes, prices)
                ) if prices and outcomes else "N/A"
                
                vol_str = f"${m['volume']:,.0f}" if m['volume'] > 0 else "$0"
                status = "🟢" if m['volume'] > 10000 else "🟡" if m['volume'] > 1000 else "🔴"
                
                lines.append(f"   {status} {m['question'][:50]}")
                lines.append(f"      {price_str} | Vol: {vol_str}")
    
    if upcoming_events:
        lines.append(f"\n📅 <b>UPCOMING EVENTS</b>")
        lines.append("─" * 30)
        for event, ms in sorted(upcoming_events, key=lambda x: -event_vols[x[0]])[:10]:
            total_vol = sum(m['volume'] for m in ms)
            start_str = ms[0]['start'] if ms[0]['start'] else '?'
            lines.append(f"\n⚽ <b>{event}</b>")
            lines.append(f"   Start: {start_str} | Vol: ${total_vol:,.0f} | Markets: {len(ms)}")
            
            # Show top 3 markets
            top_markets = sorted(ms, key=lambda x: -x['volume'])[:3]
            for m in top_markets:
                prices = m['prices']
                outcomes = m['outcomes']
                price_str = " | ".join(
                    f"{o}: {float(p)*100:.1f}¢" 
                    for o, p in zip(outcomes, prices)
                ) if prices and outcomes else "N/A"
                lines.append(f"   • {m['question'][:50]}")
                lines.append(f"     {price_str}")
    
    # Recommended markets for spread trading
    lines.append(f"\n🎯 <b>RECOMMENDED FOR SPREAD TRADING</b>")
    lines.append("─" * 30)
    
    # Find markets with moderate volume (not too thin, not too thick)
    # and reasonable price ranges (not near 0 or 1)
    recommended = []
    for m in markets:
        prices = [float(p) for p in m['prices']] if m['prices'] else []
        vol = m['volume']
        
        # Good spread markets: price between 10-90%, volume $1K-$100K
        if prices:
            max_price = max(prices)
            min_price = min(prices)
            if (0.10 <= max_price <= 0.90 and 
                0.10 <= min_price <= 0.90 and
                1000 <= vol <= 100000):
                recommended.append(m)
    
    # Sort by volume (prefer moderate volume)
    recommended.sort(key=lambda x: -x['volume'])
    
    for m in recommended[:15]:
        prices = m['prices']
        outcomes = m['outcomes']
        price_str = " | ".join(
            f"{o}: {float(p)*100:.1f}¢" 
            for o, p in zip(outcomes, prices)
        ) if prices and outcomes else "N/A"
        
        lines.append(f"\n📌 {m['question'][:60]}")
        lines.append(f"   {price_str}")
        lines.append(f"   Vol: ${m['volume']:,.0f} | {m['event'][:30]}")
        
        # Suggest spread
        if prices and len(prices) >= 2:
            p1, p2 = float(prices[0]), float(prices[1])
            spread = abs(p1 - p2)
            mid = (p1 + p2) / 2
            suggested_bid = max(0.01, mid - spread * 0.3)
            suggested_ask = min(0.99, mid + spread * 0.3)
            lines.append(f"   💡 Suggest: bid {suggested_bid:.2f} / ask {suggested_ask:.2f}")
    
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Polymarket Market Scanner")
    parser.add_argument("--min-vol", type=float, default=0, help="Minimum volume filter")
    parser.add_argument("--event", type=str, default=None, help="Filter by event name")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()
    
    print("Scanning Polymarket markets...")
    markets = scan_markets(min_volume=args.min_vol, event_filter=args.event)
    print(f"Found {len(markets)} markets")
    
    if args.json:
        print(json.dumps(markets, indent=2))
    else:
        report = format_telegram_report(markets)
        print(report)


if __name__ == "__main__":
    main()
