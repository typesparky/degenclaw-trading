#!/usr/bin/env python3
"""
Multi-venue price comparison: DEX (Hydromancer) + CEX (MEXC, Bitget)
Plots raw prices overlaid, spreads, and stats for all matching assets.
Includes Volume and HL-Spread metrics for liquidity ranking.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, matplotlib.pyplot as plt, matplotlib.dates as mdates
import json
from pathlib import Path
from decimal import Decimal

BASE = Path("~/hermes-workspace/degenclaw-trading").expanduser()
DATA = BASE / "data"
CEX = DATA / "cex_candles"
OUT = BASE / "plots"
OUT.mkdir(exist_ok=True)

plt.style.use("dark_background")
plt.rcParams.update({
    "figure.facecolor": "#0a0a0a",
    "axes.facecolor": "#111111",
    "axes.grid": True,
    "grid.alpha": 0.2,
    "font.size": 10,
    "axes.titlesize": 13,
    "axes.labelsize": 10,
})

def to_float(v): return float(v) if isinstance(v, Decimal) else float(v)

# ── Asset groupings ──────────────────────────────────────────────────
ASSETS = {
    "OIL (WTI)": [
        ("flx:OIL", "dex", "flx", ["flx:OIL"]),
        ("xyz:CL", "dex", "xyz", ["xyz:CL"]),
        ("cash:WTI", "dex", "cash", ["cash:WTI"]),
        ("km:USOIL", "dex", "km", ["km:USOIL"]),
        ("mexc:USOIL", "cex", CEX / "mexc_usoil.parquet", None),
    ],
    "OIL (Brent)": [
        ("xyz:BRENTOIL", "dex", "xyz", ["xyz:BRENTOIL"]),
        ("mexc:UKOIL", "cex", CEX / "mexc_ukoil.parquet", None),
    ],
    "NatGas": [
        ("flx:GAS", "dex", "flx", ["flx:GAS"]),
        ("xyz:NATGAS", "dex", "xyz", ["xyz:NATGAS"]),
        ("mexc:NGAS", "cex", CEX / "mexc_ngas.parquet", None),
        ("bitget:NATGAS", "cex", CEX / "bitget_natgas.parquet", None),
    ],
    "BTC": [
        ("flx:BTC", "dex", "flx", ["flx:BTC"]),
        ("bitunix:BTCUSDT", "cex_live", None, None),
    ],
    "ETH": [
        ("flx:ETH", "dex", "flx", ["flx:ETH"]),
        ("bitunix:ETHUSDT", "cex_live", None, None),
    ],
    "SOL": [
        ("flx:SOL", "dex", "flx", ["flx:SOL"]),
        ("bitunix:SOLUSDT", "cex_live", None, None),
    ],
    "Gold": [
        ("flx:GOLD", "dex", "flx", ["flx:GOLD"]),
        ("xyz:GOLD", "dex", "xyz", ["xyz:GOLD"]),
        ("cash:GOLD", "dex", "cash", ["cash:GOLD"]),
        ("km:GOLD", "dex", "km", ["km:GOLD"]),
        ("mexc:XAUT", "cex", CEX / "mexc_xaut.parquet", None),
        ("bitget:XAU", "cex", CEX / "bitget_xau.parquet", None),
    ],
    "Silver": [
        ("flx:SILVER", "dex", "flx", ["flx:SILVER"]),
        ("xyz:SILVER", "dex", "xyz", ["xyz:SILVER"]),
        ("cash:SILVER", "dex", "cash", ["cash:SILVER"]),
        ("km:SILVER", "dex", "km", ["km:SILVER"]),
        ("mexc:SILVER", "cex", CEX / "mexc_silver.parquet", None),
        ("bitget:XAG", "cex", CEX / "bitget_xag.parquet", None),
    ],
    "NVDA": [
        ("flx:NVDA", "dex", "flx", ["flx:NVDA"]),
        ("xyz:NVDA", "dex", "xyz", ["xyz:NVDA"]),
        ("cash:NVDA", "dex", "cash", ["cash:NVDA"]),
        ("km:NVDA", "dex", "km", ["km:NVDA"]),
        ("bitget:NVDA", "cex", CEX / "bitget_nvda.parquet", None),
    ],
    "SPX500": [
        ("flx:USA500", "dex", "flx", ["flx:USA500"]),
        ("xyz:SP500", "dex", "xyz", ["xyz:SP500"]),
        ("cash:USA500", "dex", "cash", ["cash:USA500"]),
        ("km:US500", "dex", "km", ["km:US500"]),
        ("mexc:SPX500", "cex", CEX / "mexc_spx500.parquet", None),
    ],
    "Copper": [
        ("flx:COPPER", "dex", "flx", ["flx:COPPER"]),
        ("xyz:COPPER", "dex", "xyz", ["xyz:COPPER"]),
        ("bitget:COPPER", "cex", CEX / "bitget_copper.parquet", None),
    ],
    "TSLA": [
        ("flx:TSLA", "dex", "flx", ["flx:TSLA"]),
        ("xyz:TSLA", "dex", "xyz", ["xyz:TSLA"]),
        ("cash:TSLA", "dex", "cash", ["cash:TSLA"]),
        ("km:TSLA", "dex", "km", ["km:TSLA"]),
    ],
    "NAS100": [
        ("flx:USA100", "dex", "flx", ["flx:USA100"]),
        ("xyz:XYZ100", "dex", "xyz", ["xyz:XYZ100"]),
        ("km:USTECH", "dex", "km", ["km:USTECH"]),
        ("mexc:NAS100", "cex", CEX / "mexc_nas100.parquet", None),
    ],
    "Macro Oil (WTI-Brent)": [
        ("xyz:CL", "dex", "xyz", ["xyz:CL"]),
        ("xyz:BRENTOIL", "dex", "xyz", ["xyz:BRENTOIL"]),
        ("mexc:USOIL", "cex", CEX / "mexc_usoil.parquet", None),
        ("mexc:UKOIL", "cex", CEX / "mexc_ukoil.parquet", None),
    ],
    "Macro Metals (Gold-Silver)": [
        ("mexc:XAUT", "cex", CEX / "mexc_xaut.parquet", None),
        ("mexc:SILVER", "cex", CEX / "mexc_silver.parquet", None),
    ],
}

COLORS = [
    "#00d4ff", "#ff6b35", "#7cff01", "#ff35c5",
    "#ffd700", "#ff4444", "#aa66ff", "#66ffcc",
    "#ff9966", "#3399ff",
]

CACHE = DATA / "cache"
CACHE.mkdir(exist_ok=True)

def load_dex_1min(dex, coins):
    """Load DEX 1s candles, aggregate to 1min close, volume, and hl_spread with local caching."""
    cache_file = CACHE / f"{dex}_1min_aggregated.parquet"
    
    # Try to load from cache first
    if cache_file.exists():
        try:
            df_cache = pd.read_parquet(cache_file)
            df_cache["minute"] = pd.to_datetime(df_cache["minute"], utc=True)
            results = {}
            for coin in coins:
                sub = df_cache[df_cache["coin"] == coin].set_index("minute")
                if not sub.empty:
                    results[coin] = sub[["close", "volume", "hl_spread"]]
            if results:
                print(f"  Loaded {dex} from cache.")
                return results
        except Exception as e:
            print(f"  Cache read failed for {dex}: {e}")

    # Fallback to raw processing
    print(f"  Processing raw {dex} data (Aggregating to 1min)...")
    frames = []
    raw_dir = DATA / "raw_candles" / dex
    cols_wanted = ["coin", "timestamp", "close", "high", "low", "volume", "volume_quote"]
    
    if raw_dir.exists():
        files = sorted(raw_dir.glob("*.parquet"))
        for f in files:
            try:
                # Optimized read: get schema first
                sample = pd.read_parquet(f, engine='pyarrow').head(0)
                available = [c for c in cols_wanted if c in sample.columns]
                df = pd.read_parquet(f, columns=available)
                df = df[df["coin"].isin(coins)]
                if len(df) > 0: frames.append(df)
            except: pass
            
    if not frames: return {}
    
    df = pd.concat(frames, ignore_index=True)
    for col in ["close", "high", "low", "volume", "volume_quote"]:
        if col in df.columns:
            df[col] = df[col].apply(to_float)
    
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["minute"] = df["timestamp"].dt.floor("1min")
    
    # Global aggregation for the cache
    vol_col = "volume_quote" if "volume_quote" in df.columns else "volume"
    agg_df = df.groupby(["coin", "minute"]).agg(
        close=("close", "last"),
        volume=(vol_col, "sum"),
        high=("high", "max"),
        low=("low", "min")
    ).reset_index()
    
    agg_df["hl_spread"] = (agg_df["high"] - agg_df["low"]) / agg_df["close"] * 100
    
    # Save cache
    agg_df.to_parquet(cache_file)
    print(f"  Saved {dex} aggregation to cache.")
    
    # Return split by coin
    results = {}
    for coin in coins:
        sub = agg_df[agg_df["coin"] == coin].set_index("minute")
        if not sub.empty:
            results[coin] = sub[["close", "volume", "hl_spread"]]
    return results


def load_cex_1min(filepath):
    """Load CEX 1min candle parquet with local caching."""
    cache_file = CACHE / f"cex_{filepath.stem}_1min.parquet"
    if cache_file.exists():
        try:
            return pd.read_parquet(cache_file).set_index("minute")
        except: pass

    df = pd.read_parquet(filepath)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["minute"] = df["timestamp"].dt.floor("1min")
    
    m_grouped = df.groupby("minute")
    close = m_grouped["close"].last()
    volume = m_grouped["volume"].sum()
    high = m_grouped["high"].max()
    low = m_grouped["low"].min()
    
    res = pd.DataFrame({
        "close": close,
        "volume": volume,
        "hl_spread": (high - low) / close * 100
    })
    res.to_parquet(cache_file, index=True) # Ensure 'minute' index is saved
    return res

def load_all_series(asset_name, sources):
    all_data = {}
    for label, kind, arg3, arg4 in sources:
        df_sub = pd.DataFrame()
        if kind == "dex":
            coin_map = load_dex_1min(arg3, arg4)
            for coin_name, sub in coin_map.items():
                df_sub = sub
        elif kind == "cex":
            if arg3.exists():
                df_sub = load_cex_1min(arg3)
        elif kind == "cex_live":
            # Live fetch from Bitunix REST API
            try:
                from bitunix_connector import fetch_bitunix_candles
                symbol = label.split(":")[1] if ":" in label else label
                df_sub = fetch_bitunix_candles(symbol, interval="1m", limit=1000)
            except Exception as e:
                print(f"  Warning: live fetch failed for {label}: {e}")
        if not df_sub.empty:
            if label == "km:US500": df_sub["close"] *= 10
            if label == "km:USTECH": df_sub["close"] *= 40
            if label == "km:USOIL": df_sub["close"] *= 0.75
            all_data[label] = df_sub
    return all_data

def plot_prices_and_spreads(asset_name, all_data, skip_plots=False):
    stats_list = []
    if len(all_data) < 2: return stats_list

    # --- Calculate venue metrics first to determine baseline ---
    venue_metrics = {}
    for label, df in all_data.items():
        venue_metrics[label] = {
            "avg_volume": float(df["volume"].mean()),
            "total_volume": float(df["volume"].sum()),
            "avg_hl_spread": float(df["hl_spread"].mean()),
        }

    # Baseline selection: Highest total volume
    sorted_venues = sorted(venue_metrics.items(), key=lambda x: x[1]['total_volume'], reverse=True)
    ref_label = sorted_venues[0][0]
    
    print(f"  Asset: {asset_name} | Baseline: {ref_label} (Vol: {venue_metrics[ref_label]['total_volume']:.2f})")

    prices = pd.DataFrame({l: df["close"] for l, df in all_data.items()})
    prices = prices.dropna(how="all")
    if len(prices) < 100: return stats_list

    if ref_label not in prices.columns:
        ref_label = prices.columns[0]

    if not skip_plots:
        fig, axes = plt.subplots(3, 1, figsize=(18, 14), height_ratios=[3, 2, 1], gridspec_kw={"hspace": 0.25})
        fig.suptitle(f"{asset_name} — Cross-Venue Comparison (Ref: {ref_label})", fontsize=15, fontweight="bold")
        
        ax1 = axes[0]
        for i, col in enumerate(prices.columns):
            ax1.plot(prices.index, prices[col], label=col, color=COLORS[i % len(COLORS)], linewidth=0.8)
        ax1.legend(loc="upper left", fontsize=8, ncol=2)
        ax1.set_title("Raw Close Prices (1-min)")
        
        ax2 = axes[1]
        for i, col in enumerate(prices.columns):
            if col == ref_label: continue
            spread_pct = (prices[col] - prices[ref_label]) / prices[ref_label] * 100
            ax2.plot(prices.index, spread_pct, label=f"{col} - {ref_label}", color=COLORS[i % len(COLORS)], linewidth=0.5)
            ax2.axhline(spread_pct.mean(), color=COLORS[i % len(COLORS)], linestyle="--", linewidth=0.8, alpha=0.5)
        ax2.set_title(f"Spread vs {ref_label} (%)")
        
        ax3 = axes[2]
        for i, col in enumerate(prices.columns):
            if col == ref_label: continue
            spread_pct = ((prices[col] - prices[ref_label]) / prices[ref_label] * 100).dropna()
            ax3.hist(spread_pct, bins=100, alpha=0.5, color=COLORS[i % len(COLORS)], label=col)
        ax3.set_title("Spread Distribution")
        
        safe_name = asset_name.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_")
        fig.savefig(OUT / f"{safe_name}_cross_venue.png", dpi=150, bbox_inches="tight")
        plt.close(fig)

    for col in prices.columns:
        if col == ref_label: continue
        both = prices[[ref_label, col]].dropna()
        if len(both) < 100: continue
        spread = (both[col] - both[ref_label]) / both[ref_label] * 100
        corr = both[ref_label].corr(both[col])
        pct_above = (spread.abs() > 0.25).mean() * 100
        
        stats_list.append({
            "pair": f"{col} vs {ref_label}",
            "mean": float(spread.mean()),
            "std": float(spread.std()),
            "pct_above_025": float(pct_above),
            "corr": float(corr),
            "venue_a": col,
            "venue_b": ref_label,
            "venue_a_metrics": venue_metrics[col],
            "venue_b_metrics": venue_metrics[ref_label]
        })
    return stats_list

if __name__ == "__main__":
    stats_path = OUT / "stats.json"
    
    if stats_path.exists():
        try:
            with open(stats_path, "r") as f:
                all_stats = json.load(f)
        except:
            all_stats = {}
    else:
        all_stats = {}
    
    print("Loading data and generating stats (with caching)...\n")
    
    print("Resuming data generation for remaining and macro assets...\n")
    
    # Targeting specific macro and missing assets
    priority = ["Macro Oil (WTI-Brent)", "Macro Metals (Gold-Silver)", "SPX500", "NAS100"]
    for asset_name in priority:
        if asset_name not in ASSETS: continue
        sources = ASSETS[asset_name]
        print(f"Processing {asset_name}...")
        all_data = load_all_series(asset_name, sources)
        if all_data:
            all_stats[asset_name] = plot_prices_and_spreads(asset_name, all_data, skip_plots=True)
            with open(stats_path, "w") as f:
                json.dump(all_stats, f, indent=2)
    
    # Also ensure everything else is present
    for asset_name, sources in ASSETS.items():
        if asset_name not in all_stats:
            print(f"Processing {asset_name}...")
            all_data = load_all_series(asset_name, sources)
            if all_data:
                all_stats[asset_name] = plot_prices_and_spreads(asset_name, all_data, skip_plots=True)
                with open(stats_path, "w") as f:
                    json.dump(all_stats, f, indent=2)
    
    print(f"\nStats saved to {stats_path}")
    print("Done!")
