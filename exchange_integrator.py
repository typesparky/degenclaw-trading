#!/usr/bin/env python3
"""
Exchange Integration System - Perp DEX Expansion
=================================================
Adds new perp DEX exchanges for cross-venue arbitrage.

New Exchanges to Add:
- variational (variational_io)
- extended (extendedapp)
- tradexyz (HIP-3 on Hyperliquid)
- Markets_xyz (HIP-3 on Hyperliquid)
- hibachi (hibachi_xyz)
- pacifica (pacifica_fi)
- 01Exchange (01Exchange)
- nado (nadoHQ)
- edgeX (edgeX_exchange)
- ostium (mentioned by user)

Data Collection Strategy:
1. Check if exchange has REST API for historical candles
2. If available, fetch historical 1-min candles
3. If not, use WebSocket for real-time and build historical cache
4. For HIP-3 exchanges, can piggyback on Hyperliquid data
5. Save to unified parquet format

Output:
- Unified data cache with all exchanges
- Exchange metadata (API endpoints, supported assets, fees, etc.)
"""

import requests
import json
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import time
import hashlib

BASE = Path("~/hermes-workspace/degenclaw-trading").expanduser()
CACHE = BASE / "data" / "cache"
METADATA_FILE = BASE / "exchange_metadata.json"

# Exchange configurations
EXCHANGE_CONFIGS = {
    # Existing
    "flx": {
        "name": "Hyperliquid",
        "type": "DEX",
        "api_base": "https://api.hyperliquid.xyz/info",
        "ws_base": "wss://api.hyperliquid.xyz/ws",
        "fetcher": "fetch_hyperliquid"
    },
    "xyz": {
        "name": "XYZ",
        "type": "DEX",
        "api_base": "https://api.xyz.io",
        "ws_base": "wss://ws.xyz.io",
        "fetcher": "fetch_xyz"
    },
    "km": {
        "name": "Kwenta",
        "type": "DEX",
        "api_base": "https://api.kwenta.io",
        "ws_base": "wss://ws.kwenta.io",
        "fetcher": "fetch_kwenta"
    },

    # NEW - Tier A
    "variational": {
        "name": "Variational",
        "type": "DEX",
        "api_base": "https://api.variational.io",
        "ws_base": "wss://ws.variational.io",
        "fetcher": "fetch_variational"
    },
    "extended": {
        "name": "Extended",
        "type": "DEX",
        "api_base": "https://api.extended.fi",
        "ws_base": "wss://ws.extended.fi",
        "fetcher": "fetch_extended"
    },
    "tradexyz": {
        "name": "TradeXYZ",
        "type": "DEX",
        "subtype": "HIP-3",
        "api_base": "https://api.tradexyz.io",
        "ws_base": "wss://ws.tradexyz.io",
        "fetcher": "fetch_hip3",  # Uses Hyperliquid HIP-3
        "base_exchange": "flx"  # Piggyback on Hyperliquid
    },
    "markets_xyz": {
        "name": "MarketsXYZ",
        "type": "DEX",
        "subtype": "HIP-3",
        "api_base": "https://api.markets.xyz",
        "ws_base": "wss://ws.markets.xyz",
        "fetcher": "fetch_hip3",  # Uses Hyperliquid HIP-3
        "base_exchange": "flx"  # Piggyback on Hyperliquid
    },

    # Tier B
    "hibachi": {
        "name": "Hibachi",
        "type": "DEX",
        "api_base": "https://api.hibachi.xyz",
        "ws_base": "wss://ws.hibachi.xyz",
        "fetcher": "fetch_hibachi"
    },
    "pacifica": {
        "name": "PacificFi",
        "type": "DEX",
        "api_base": "https://api.pacifica.fi",
        "ws_base": "wss://ws.pacifica.fi",
        "fetcher": "fetch_pacifica"
    },
    "01exchange": {
        "name": "01Exchange",
        "type": "DEX",
        "api_base": "https://api.01.exchange",
        "ws_base": "wss://ws.01.exchange",
        "fetcher": "fetch_01exchange"
    },
    "nado": {
        "name": "Nado",
        "type": "DEX",
        "api_base": "https://api.nadohq.com",
        "ws_base": "wss://ws.nadohq.com",
        "fetcher": "fetch_nado"
    },

    # Tier C
    "edgex": {
        "name": "EdgeX",
        "type": "DEX",
        "api_base": "https://api.edgex.exchange",
        "ws_base": "wss://ws.edgex.exchange",
        "fetcher": "fetch_edgex"
    },

    # Mentioned by user
    "ostium": {
        "name": "Ostium",
        "type": "DEX",
        "api_base": "https://api.ostium.trade",
        "ws_base": "wss://ws.ostium.trade",
        "fetcher": "fetch_ostium"
    },

    # CEX — Bitunix Futures
    "bitunix": {
        "name": "Bitunix",
        "type": "CEX",
        "api_base": "https://fapi.bitunix.com",
        "ws_base": "wss://fapi.bitunix.com/public/",
        "fetcher": "fetch_bitunix"
    }
}

# Asset mapping across exchanges
ASSET_MAPPINGS = {
    "OIL (WTI)": {
        "flx": "OIL",
        "xyz": "CL",
        "cash": "WTI",
        "km": "USOIL",
        "mexc": "USOIL",
        "variational": "OIL",
        "extended": "OIL",
        "tradexyz": "OIL",
        "markets_xyz": "OIL",
        "hibachi": "OIL",
        "pacifica": "OIL",
        "01exchange": "OIL",
        "nado": "OIL",
        "edgex": "OIL",
        "ostium": "OIL",
        "bitunix": "OILUSDT"
    },
    "BTC": {
        "bitunix": "BTCUSDT"
    },
    "ETH": {
        "bitunix": "ETHUSDT"
    },
    "SOL": {
        "bitunix": "SOLUSDT"
    },
    "NatGas": {
        "flx": "GAS",
        "xyz": "NATGAS",
        "mexc": "NGAS",
        "bitget": "NATGAS",
        "variational": "GAS",
        "extended": "GAS",
        "hibachi": "GAS",
        "pacifica": "GAS",
        "ostium": "GAS"
    },
    "Gold": {
        "flx": "GOLD",
        "xyz": "GOLD",
        "cash": "GOLD",
        "km": "GOLD",
        "mexc": "XAUT",
        "bitget": "XAU",
        "variational": "GOLD",
        "extended": "GOLD",
        "tradexyz": "GOLD",
        "markets_xyz": "GOLD",
        "hibachi": "GOLD",
        "pacifica": "GOLD",
        "nado": "GOLD",
        "edgex": "GOLD",
        "ostium": "GOLD"
    },
    "Silver": {
        "flx": "SILVER",
        "xyz": "SILVER",
        "cash": "SILVER",
        "km": "SILVER",
        "mexc": "SILVER",
        "bitget": "XAG",
        "variational": "SILVER",
        "extended": "SILVER",
        "tradexyz": "SILVER",
        "markets_xyz": "SILVER",
        "hibachi": "SILVER",
        "pacifica": "SILVER",
        "nado": "SILVER",
        "edgex": "SILVER",
        "ostium": "SILVER"
    },
    "NVDA": {
        "flx": "NVDA",
        "xyz": "NVDA",
        "cash": "NVDA",
        "km": "NVDA",
        "bitget": "NVDA",
        "variational": "NVDA",
        "extended": "NVDA",
        "tradexyz": "NVDA",
        "markets_xyz": "NVDA",
        "hibachi": "NVDA",
        "nado": "NVDA",
        "edgex": "NVDA"
    },
    "SPX500": {
        "flx": "USA500",
        "xyz": "SP500",
        "cash": "USA500",
        "km": "US500",
        "mexc": "SPX500",
        "variational": "SP500",
        "extended": "SP500",
        "tradexyz": "SP500",
        "markets_xyz": "SP500",
        "hibachi": "SP500",
        "pacifica": "SP500",
        "nado": "SP500",
        "edgex": "SP500",
        "ostium": "SP500"
    },
    "Copper": {
        "flx": "COPPER",
        "xyz": "COPPER",
        "bitget": "COPPER",
        "variational": "COPPER",
        "extended": "COPPER",
        "hibachi": "COPPER",
        "nado": "COPPER",
        "edgex": "COPPER"
    },
    "TSLA": {
        "flx": "TSLA",
        "xyz": "TSLA",
        "cash": "TSLA",
        "km": "TSLA",
        "variational": "TSLA",
        "extended": "TSLA",
        "tradexyz": "TSLA",
        "markets_xyz": "TSLA",
        "hibachi": "TSLA",
        "nado": "TSLA",
        "edgex": "TSLA"
    },
    "NAS100": {
        "flx": "USA100",
        "xyz": "XYZ100",
        "km": "USTECH",
        "mexc": "NAS100",
        "variational": "USA100",
        "extended": "USA100",
        "tradexyz": "USA100",
        "markets_xyz": "USA100",
        "hibachi": "USA100",
        "nado": "USA100",
        "edgex": "USA100"
    }
}

def fetch_hyperliquid_candles(symbol, interval='1m', limit=1000):
    """Fetch candles from Hyperliquid API."""
    try:
        url = "https://api.hyperliquid.xyz/info"
        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin": symbol,
                "interval": interval,
                "startTime": int((datetime.now() - timedelta(days=30)).timestamp() * 1000),
                "endTime": int(datetime.now().timestamp() * 1000)
            }
        }

        response = requests.post(url, json=payload, timeout=10)
        data = response.json()

        if data and len(data) > 0:
            df = pd.DataFrame(data)
            df['time'] = pd.to_datetime(df['t'], unit='ms')
            df = df.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'})
            df = df.set_index('time')
            return df[['open', 'high', 'low', 'close', 'volume']]
    except Exception as e:
        print(f"Error fetching from Hyperliquid: {e}")

    return None


def fetch_bitunix_candles(symbol, interval='1m', limit=1000):
    """Fetch candles from Bitunix Futures API."""
    try:
        base_url = "https://fapi.bitunix.com"
        end_ms = int(datetime.now().timestamp() * 1000)
        start_ms = int((datetime.now() - timedelta(days=30)).timestamp() * 1000)

        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": str(limit),
            "type": "LAST_PRICE",
            "startTime": str(start_ms),
            "endTime": str(end_ms),
        }

        query_string = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        url = f"{base_url}/api/v1/futures/market/kline?{query_string}"

        response = requests.get(url, timeout=10, headers={"Content-Type": "application/json"})
        data = response.json()

        if data.get("code", 0) != 0:
            print(f"Bitunix API error: {data.get('msg', 'unknown')}")
            return None

        klines = data.get("data", [])
        if not klines:
            return None

        # Bitunix kline format: dict with keys open, high, low, close, baseVol, quoteVol, time
        rows = []
        for k in klines:
            if isinstance(k, dict):
                rows.append({
                    "time": pd.to_datetime(int(k.get("time", 0)), unit="ms"),
                    "open": float(k.get("open", 0)),
                    "high": float(k.get("high", 0)),
                    "low": float(k.get("low", 0)),
                    "close": float(k.get("close", 0)),
                    "volume": float(k.get("baseVol", 0) or k.get("volume", 0)),
                })
            elif isinstance(k, list) and len(k) >= 6:
                rows.append({
                    "time": pd.to_datetime(int(k[0]), unit="ms"),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                })

        if not rows:
            return None

        df = pd.DataFrame(rows)
        df = df.set_index("time")
        return df[["open", "high", "low", "close", "volume"]]
    except Exception as e:
        print(f"Error fetching from Bitunix: {e}")
        return None

def fetch_generic_exchange(exchange_code, symbol):
    """
    Generic fetcher for new exchanges.
    In production, each exchange would have its own implementation.
    For now, this is a template that shows the structure.
    """
    exchange = EXCHANGE_CONFIGS.get(exchange_code)
    if not exchange:
        return None

    # Check if it's a HIP-3 exchange (uses Hyperliquid data)
    if exchange.get('subtype') == 'HIP-3':
        return fetch_hyperliquid_candles(symbol)

    # For other exchanges, would implement specific API calls
    # This is a placeholder - actual implementation depends on exchange API
    try:
        # Example structure (would be customized per exchange)
        url = f"{exchange['api_base']}/candles"
        params = {
            'symbol': symbol,
            'interval': '1m',
            'limit': 1000
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        # Parse response based on exchange format
        # This would be customized per exchange
        if data and 'data' in data:
            df = pd.DataFrame(data['data'])
            # Standardize column names
            df['time'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = df.rename(columns={'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close', 'vol': 'volume'})
            df = df.set_index('time')
            return df[['open', 'high', 'low', 'close', 'volume']]
    except Exception as e:
        print(f"Error fetching from {exchange['name']}: {e}")

    return None

def discover_exchange_assets(exchange_code):
    """
    Discover which assets are available on an exchange.
    """
    exchange = EXCHANGE_CONFIGS.get(exchange_code)
    if not exchange:
        return []

    available_assets = []

    # For HIP-3 exchanges, assets are same as Hyperliquid
    if exchange.get('subtype') == 'HIP-3':
        return list(ASSET_MAPPINGS.keys())

    # For other exchanges, would query exchange's asset list
    # This is a placeholder
    try:
        url = f"{exchange['api_base']}/markets"
        response = requests.get(url, timeout=10)
        data = response.json()

        # Parse and map assets
        # This would be customized per exchange
        if data and 'markets' in data:
            for market in data['markets']:
                # Map to our asset names
                for asset_name, mappings in ASSET_MAPPINGS.items():
                    if exchange_code in mappings and market['symbol'] == mappings[exchange_code]:
                        available_assets.append(asset_name)
    except Exception as e:
        print(f"Error discovering assets for {exchange['name']}: {e}")

    return available_assets

def fetch_all_exchange_data(exchange_code, assets=None):
    """
    Fetch data for all assets from a specific exchange.
    """
    if assets is None:
        assets = discover_exchange_assets(exchange_code)

    exchange = EXCHANGE_CONFIGS.get(exchange_code)
    if not exchange:
        print(f"Unknown exchange: {exchange_code}")
        return {}

    print(f"Fetching data from {exchange['name']}...")

    results = {}

    for asset in assets:
        symbol = ASSET_MAPPINGS.get(asset, {}).get(exchange_code)
        if not symbol:
            continue

        print(f"  - {asset} ({symbol})...")

        # Fetch data using appropriate method
        if exchange.get('subtype') == 'HIP-3':
            df = fetch_hyperliquid_candles(symbol)
        elif exchange_code == 'bitunix':
            df = fetch_bitunix_candles(symbol)
        else:
            df = fetch_generic_exchange(exchange_code, symbol)

        if df is not None and len(df) > 0:
            results[asset] = df
            print(f"    ✓ {len(df)} candles")
        else:
            print(f"    ✗ No data")

    return results

def save_exchange_data(exchange_code, data):
    """
    Save fetched data to parquet format.
    """
    if not data:
        return

    exchange = EXCHANGE_CONFIGS.get(exchange_code)
    exchange_name = exchange['name'].lower().replace(' ', '_')

    all_data = []

    for asset, df in data.items():
        df = df.copy()
        df['asset'] = asset
        df['venue'] = exchange_code
        all_data.append(df)

    if all_data:
        combined = pd.concat(all_data)
        output_file = CACHE / f"{exchange_code}_1min_aggregated.parquet"
        combined.to_parquet(output_file)
        print(f"✓ Saved to {output_file} ({len(combined)} rows)")

def generate_exchange_metadata():
    """
    Generate metadata file with all exchange information.
    """
    metadata = {
        "last_updated": datetime.now().isoformat(),
        "exchanges": {},
        "total_exchanges": len(EXCHANGE_CONFIGS),
        "supported_assets": list(ASSET_MAPPINGS.keys())
    }

    for code, config in EXCHANGE_CONFIGS.items():
        metadata["exchanges"][code] = {
            "name": config["name"],
            "type": config["type"],
            "subtype": config.get("subtype", "native"),
            "api_base": config["api_base"],
            "ws_base": config["ws_base"],
            "supported_assets": [asset for asset, mappings in ASSET_MAPPINGS.items() if code in mappings]
        }

    with open(METADATA_FILE, 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"✓ Exchange metadata saved to {METADATA_FILE}")

def main():
    print("=" * 60)
    print("Exchange Integration System - Perp DEX Expansion")
    print("=" * 60)

    # New exchanges to add
    new_exchanges = [
        "variational", "extended", "tradexyz", "markets_xyz",
        "hibachi", "pacifica", "01exchange", "nado", "edgex", "ostium",
        "bitunix"
    ]

    print(f"\nExchanges to add: {len(new_exchanges)}")
    for exchange in new_exchanges:
        config = EXCHANGE_CONFIGS.get(exchange)
        print(f"  - {config['name']} ({exchange})")
        print(f"    Type: {config['type']} {config.get('subtype', '')}")

    print("\n" + "=" * 60)
    print("Fetching data from new exchanges...")
    print("=" * 60 + "\n")

    for exchange_code in new_exchanges:
        print(f"\n{'=' * 60}")
        print(f"Processing: {EXCHANGE_CONFIGS[exchange_code]['name']}")
        print(f"{'=' * 60}")

        # Discover assets
        assets = discover_exchange_assets(exchange_code)
        print(f"\nAvailable assets: {len(assets)}")
        for asset in assets:
            symbol = ASSET_MAPPINGS[asset].get(exchange_code, 'N/A')
            print(f"  - {asset} → {symbol}")

        # Fetch data
        data = fetch_all_exchange_data(exchange_code, assets)

        # Save data
        if data:
            save_exchange_data(exchange_code, data)

        # Rate limiting
        time.sleep(1)

    # Generate metadata
    print("\n" + "=" * 60)
    print("Generating exchange metadata...")
    print("=" * 60)
    generate_exchange_metadata()

    print("\n" + "=" * 60)
    print("✓ Exchange integration complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
