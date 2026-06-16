#!/usr/bin/env python3
"""
Bitunix Futures Exchange Connector
===================================
REST + WebSocket client for Bitunix futures trading.
Supports market data, order management, and account queries.

API docs: https://www.bitunix.com/api-docs/futures/common/introduction.html
Endpoints: https://fapi.bitunix.com
WebSocket: wss://fapi.bitunix.com/public/ (public) | wss://fapi.bitunix.com/private/ (private)

Auth: Double SHA256 — sign = SHA256(SHA256(nonce + timestamp + apiKey + queryParams + body) + secretKey)

Bitunix response format notes:
  Ticker: {symbol, markPrice, lastPrice, open, last, quoteVol, baseVol, high, low}
  Kline:  {open, high, low, close, baseVol, quoteVol, time}  (dict, NOT array)
  Depth:  {asks: [[price, qty], ...], bids: [[price, qty], ...]}
"""

import hashlib
import json
import time
import uuid
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import requests
import pandas as pd

try:
    import websocket
    HAS_WS = True
except ImportError:
    HAS_WS = False


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

BASE_URL = "https://fapi.bitunix.com"
WS_PUBLIC_URL = "wss://fapi.bitunix.com/public/"
WS_PRIVATE_URL = "wss://fapi.bitunix.com/private/"

RATE_LIMIT_PUBLIC = 10
RATE_LIMIT_PRIVATE = 6


# ═══════════════════════════════════════════════════════════════════════════════
# DATA TYPES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class BitunixTicker:
    symbol: str
    last_price: float
    mark_price: float
    high_24h: float
    low_24h: float
    volume_24h: float        # base volume
    turnover_24h: float      # quote volume
    open_24h: float
    price_change_pct_24h: float
    raw: Dict = field(default_factory=dict)


@dataclass
class BitunixOrderBook:
    symbol: str
    bids: List[Tuple[float, float]]
    asks: List[Tuple[float, float]]
    timestamp: int
    raw: Dict = field(default_factory=dict)

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0][0] if self.asks else None

    @property
    def mid_price(self) -> Optional[float]:
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return None

    @property
    def spread(self) -> Optional[float]:
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None

    @property
    def spread_bps(self) -> Optional[float]:
        mid = self.mid_price
        if mid and self.spread:
            return (self.spread / mid) * 10000
        return None


@dataclass
class BitunixKline:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float


@dataclass
class BitunixOrderResult:
    order_id: str
    client_id: str
    symbol: str
    side: str
    order_type: str
    price: float
    qty: float
    status: str
    raw: Dict = field(default_factory=dict)


@dataclass
class BitunixAccount:
    margin_coin: str
    available_balance: float
    frozen_balance: float
    unrealized_pnl: float
    realized_pnl: float
    margin_ratio: float
    raw: Dict = field(default_factory=dict)


@dataclass
class BitunixPosition:
    symbol: str
    side: str
    qty: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    leverage: int
    liquidation_price: float
    margin: float
    raw: Dict = field(default_factory=dict)


class BitunixAPIError(Exception):
    def __init__(self, code: int, msg: str, raw: Dict = None):
        self.code = code
        self.msg = msg
        self.raw = raw or {}
        super().__init__(f"Bitunix API Error {code}: {msg}")


# ═══════════════════════════════════════════════════════════════════════════════
# SIGNING
# ═══════════════════════════════════════════════════════════════════════════════

def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _generate_nonce() -> str:
    return uuid.uuid4().hex


def _generate_timestamp() -> str:
    return str(int(time.time() * 1000))


def _sort_params(params: Dict[str, str]) -> str:
    if not params:
        return ""
    return "".join(k + params[k] for k in sorted(params.keys()))


def generate_signature(
    api_key: str, secret_key: str, nonce: str,
    timestamp: str, query_params: str, body: str,
) -> str:
    digest_input = nonce + timestamp + api_key + query_params + body
    digest = _sha256_hex(digest_input)
    sign_input = digest + secret_key
    return _sha256_hex(sign_input)


def get_auth_headers(
    api_key: str, secret_key: str,
    query_params: str = "", body: str = "",
) -> Dict[str, str]:
    nonce = _generate_nonce()
    timestamp = _generate_timestamp()
    sign = generate_signature(api_key, secret_key, nonce, timestamp, query_params, body)
    return {
        "api-key": api_key,
        "sign": sign,
        "nonce": nonce,
        "timestamp": timestamp,
        "Content-Type": "application/json",
        "language": "en-US",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# REST CLIENT
# ═══════════════════════════════════════════════════════════════════════════════

class BitunixRestClient:
    """Bitunix Futures REST client — public + private endpoints."""

    def __init__(self, api_key: str = "", secret_key: str = "", base_url: str = BASE_URL):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self._last_public_call = 0.0
        self._last_private_call = 0.0

    def _throttle(self, limit: int):
        now = time.time()
        min_interval = 1.0 / limit
        if limit == RATE_LIMIT_PUBLIC:
            elapsed = now - self._last_public_call
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            self._last_public_call = time.time()
        else:
            elapsed = now - self._last_private_call
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            self._last_private_call = time.time()

    def _request(self, method: str, path: str, params: Dict = None,
                 body: Dict = None, auth: bool = False) -> Any:
        url = self.base_url + path
        query_str = ""
        body_str = ""

        if params:
            url += "?" + urlencode(sorted(params.items()))

        if body:
            body_str = json.dumps(body, separators=(",", ":"))

        if auth:
            if not self.api_key or not self.secret_key:
                raise ValueError("API key and secret required for private endpoints")
            self._throttle(RATE_LIMIT_PRIVATE)
            headers = get_auth_headers(self.api_key, self.secret_key, query_str, body_str)
        else:
            self._throttle(RATE_LIMIT_PUBLIC)
            headers = {"Content-Type": "application/json"}

        resp = self.session.request(method, url, headers=headers,
                                     data=body_str if body_str else None, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code", 0) != 0:
            raise BitunixAPIError(data.get("code"), data.get("msg", "Unknown error"), data)

        return data.get("data", data)

    # ── Public endpoints ───────────────────────────────────────────────

    def get_trading_pairs(self) -> List[Dict]:
        return self._request("GET", "/api/v1/futures/market/trading_pairs")

    def get_tickers(self, symbol: str = "") -> List[BitunixTicker]:
        params = {}
        if symbol:
            params["symbols"] = symbol
        raw = self._request("GET", "/api/v1/futures/market/tickers", params=params or None)
        return [_parse_ticker(t) for t in raw]

    def get_ticker(self, symbol: str) -> BitunixTicker:
        tickers = self.get_tickers(symbol)
        if not tickers:
            raise ValueError(f"No ticker found for {symbol}")
        return tickers[0]

    def get_depth(self, symbol: str, limit: str = "50") -> BitunixOrderBook:
        """limit: 1 / 5 / 15 / 50 / max"""
        params = {"symbol": symbol, "limit": limit}
        raw = self._request("GET", "/api/v1/futures/market/depth", params=params)
        return _parse_orderbook(symbol, raw)

    def get_klines(
        self, symbol: str, interval: str = "1m", limit: int = 500,
        start_time: int = None, end_time: int = None, kline_type: str = "LAST_PRICE",
    ) -> List[BitunixKline]:
        """interval: 1m 5m 15m 30m 1h 2h 4h 6h 8h 12h 1d 3d 1w 1M"""
        params = {
            "symbol": symbol, "interval": interval,
            "limit": str(limit), "type": kline_type,
        }
        if start_time:
            params["startTime"] = str(start_time)
        if end_time:
            params["endTime"] = str(end_time)
        raw = self._request("GET", "/api/v1/futures/market/kline", params=params)
        return [_parse_kline(k) for k in raw]

    def get_klines_df(
        self, symbol: str, interval: str = "1m", limit: int = 500,
        start_time: int = None, end_time: int = None,
    ) -> pd.DataFrame:
        klines = self.get_klines(symbol, interval, limit, start_time, end_time)
        if not klines:
            return pd.DataFrame()
        df = pd.DataFrame([{
            "time": pd.to_datetime(k.timestamp, unit="ms"),
            "open": k.open, "high": k.high, "low": k.low,
            "close": k.close, "volume": k.volume, "turnover": k.turnover,
        } for k in klines])
        df = df.set_index("time")
        return df

    def get_funding_rate(self, symbol: str) -> Dict:
        return self._request("GET", "/api/v1/futures/market/funding_rate",
                             params={"symbol": symbol})

    def get_batch_funding_rates(self) -> List[Dict]:
        return self._request("GET", "/api/v1/futures/market/funding_rate/batch")

    # ── Private endpoints ──────────────────────────────────────────────

    def get_account(self, margin_coin: str = "USDT") -> BitunixAccount:
        raw = self._request("GET", "/api/v1/futures/account",
                            params={"margin_coin": margin_coin}, auth=True)
        return _parse_account(raw)

    def get_positions(self, symbol: str = "") -> List[BitunixPosition]:
        params = {}
        if symbol:
            params["symbol"] = symbol
        raw = self._request("GET", "/api/v1/futures/position/get_pending_positions",
                            params=params or None, auth=True)
        return [_parse_position(p) for p in raw] if raw else []

    def get_history_positions(self, symbol: str = "") -> List[Dict]:
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/api/v1/futures/position/get_history_positions",
                             params=params or None, auth=True)

    def place_order(
        self, symbol: str, side: str, order_type: str, qty: str,
        price: str = "0", trade_side: str = "OPEN", effect: str = "GTC",
        reduce_only: bool = False, client_id: str = "",
        tp_price: str = "", tp_stop_type: str = "MARK",
        tp_order_type: str = "LIMIT", tp_order_price: str = "",
        sl_price: str = "", sl_stop_type: str = "MARK",
        sl_order_type: str = "MARKET",
    ) -> BitunixOrderResult:
        body: Dict[str, Any] = {
            "symbol": symbol, "side": side, "orderType": order_type,
            "qty": qty, "price": price, "tradeSide": trade_side,
            "effect": effect, "reduceOnly": reduce_only,
        }
        if client_id:
            body["clientId"] = client_id
        if tp_price:
            body["tpPrice"] = tp_price
            body["tpStopType"] = tp_stop_type
            body["tpOrderType"] = tp_order_type
            if tp_order_price:
                body["tpOrderPrice"] = tp_order_price
        if sl_price:
            body["slPrice"] = sl_price
            body["slStopType"] = sl_stop_type
            body["slOrderType"] = sl_order_type

        raw = self._request("POST", "/api/v1/futures/trade/place_order",
                            body=body, auth=True)
        return _parse_order_result(raw)

    def cancel_orders(self, symbol: str, order_ids: List[str]) -> Dict:
        order_list = [{"orderId": oid} for oid in order_ids]
        body = {"symbol": symbol, "orderList": order_list}
        return self._request("POST", "/api/v1/futures/trade/cancel_orders",
                             body=body, auth=True)

    def cancel_all_orders(self, symbol: str) -> Dict:
        return self._request("POST", "/api/v1/futures/trade/cancel_all_orders",
                             body={"symbol": symbol}, auth=True)

    def get_pending_orders(self, symbol: str = "") -> List[Dict]:
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/api/v1/futures/trade/get_pending_orders",
                             params=params or None, auth=True)

    def get_history_orders(self, symbol: str = "") -> List[Dict]:
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/api/v1/futures/trade/get_history_orders",
                             params=params or None, auth=True)

    def get_order_detail(self, symbol: str, order_id: str) -> Dict:
        params = {"symbol": symbol, "orderId": order_id}
        return self._request("GET", "/api/v1/futures/trade/get_order_detail",
                             params=params, auth=True)

    def change_leverage(self, symbol: str, leverage: int) -> Dict:
        body = {"symbol": symbol, "leverage": leverage}
        return self._request("POST", "/api/v1/futures/trade/change_leverage",
                             body=body, auth=True)

    def change_margin_mode(self, symbol: str, margin_mode: str) -> Dict:
        body = {"symbol": symbol, "marginMode": margin_mode}
        return self._request("POST", "/api/v1/futures/trade/change_margin_mode",
                             body=body, auth=True)

    def close_all_positions(self) -> Dict:
        return self._request("POST", "/api/v1/futures/trade/close_all_positions",
                             body={}, auth=True)


# ═══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET CLIENT
# ═══════════════════════════════════════════════════════════════════════════════

class BitunixWsClient:
    """Bitunix Futures WebSocket client."""

    CH_TICKER = "ticker"
    CH_DEPTH = "depth_book1"
    CH_TRADE = "trade"
    CH_KLINE = "kline"
    CH_ORDERS = "orders"
    CH_POSITIONS = "positions"

    def __init__(
        self, api_key: str = "", secret_key: str = "",
        on_ticker: Optional[Callable] = None,
        on_depth: Optional[Callable] = None,
        on_trade: Optional[Callable] = None,
        on_order: Optional[Callable] = None,
        on_position: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
    ):
        if not HAS_WS:
            raise ImportError("websocket-client package required: pip install websocket-client")
        self.api_key = api_key
        self.secret_key = secret_key
        self.on_ticker = on_ticker
        self.on_depth = on_depth
        self.on_trade = on_trade
        self.on_order = on_order
        self.on_position = on_position
        self.on_error = on_error
        self._ws = None
        self._thread = None
        self._running = False
        self._authenticated = False

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._ws:
            self._ws.close()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self):
        while self._running:
            try:
                url = WS_PRIVATE_URL if self.api_key else WS_PUBLIC_URL
                self._ws = websocket.WebSocketApp(
                    url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self._ws.run_forever(ping_interval=15, ping_timeout=10)
            except Exception as e:
                if self.on_error:
                    self.on_error(e)
            if self._running:
                time.sleep(5)

    def _on_open(self, ws):
        if self.api_key and self.secret_key:
            self._authenticate(ws)
        self._authenticated = True

    def _authenticate(self, ws):
        nonce = _generate_nonce()
        timestamp = str(int(time.time()))
        digest = _sha256_hex(nonce + timestamp + self.api_key)
        sign = _sha256_hex(digest + self.secret_key)
        auth_msg = {
            "op": "login",
            "params": {
                "apiKey": self.api_key,
                "timestamp": int(timestamp),
                "nonce": nonce,
                "sign": sign,
            },
        }
        ws.send(json.dumps(auth_msg))

    def subscribe(self, channels: List[Dict[str, str]]):
        if self._ws and self._authenticated:
            self._ws.send(json.dumps({"op": "subscribe", "args": channels}))

    def subscribe_ticker(self, symbol: str):
        self.subscribe([{"ch": self.CH_TICKER, "symbol": symbol}])

    def subscribe_depth(self, symbol: str):
        self.subscribe([{"ch": self.CH_DEPTH, "symbol": symbol}])

    def subscribe_trades(self, symbol: str):
        self.subscribe([{"ch": self.CH_TRADE, "symbol": symbol}])

    def subscribe_kline(self, symbol: str, interval: str = "1m"):
        self.subscribe([{"ch": self.CH_KLINE, "symbol": symbol, "interval": interval}])

    def subscribe_private(self):
        self.subscribe([{"ch": self.CH_ORDERS}, {"ch": self.CH_POSITIONS}])

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return
        if data.get("op") == "pong":
            return
        if data.get("op") == "login":
            if data.get("code") == 0:
                self.subscribe_private()
            return

        ch = data.get("ch", "")
        channel_data = data.get("data", {})

        if ch == self.CH_TICKER and self.on_ticker:
            self.on_ticker(channel_data)
        elif ch == self.CH_DEPTH and self.on_depth:
            self.on_depth(channel_data)
        elif ch == self.CH_TRADE and self.on_trade:
            self.on_trade(channel_data)
        elif ch == self.CH_ORDERS and self.on_order:
            self.on_order(channel_data)
        elif ch == self.CH_POSITIONS and self.on_position:
            self.on_position(channel_data)

    def _on_error(self, ws, error):
        if self.on_error:
            self.on_error(error)

    def _on_close(self, ws, close_status, close_msg):
        self._authenticated = False


# ═══════════════════════════════════════════════════════════════════════════════
# HIGH-LEVEL CONNECTOR
# ═══════════════════════════════════════════════════════════════════════════════

class BitunixConnector:
    """Unified Bitunix connector — REST + WebSocket."""

    def __init__(self, api_key: str = "", secret_key: str = ""):
        self.rest = BitunixRestClient(api_key, secret_key)
        self.ws = None
        self._api_key = api_key
        self._secret_key = secret_key

    def enable_websocket(self, **callbacks):
        self.ws = BitunixWsClient(api_key=self._api_key, secret_key=self._secret_key, **callbacks)
        self.ws.start()

    def disable_websocket(self):
        if self.ws:
            self.ws.stop()
            self.ws = None

    def get_best_bid_ask(self, symbol: str) -> Tuple[Optional[float], Optional[float]]:
        try:
            ob = self.rest.get_depth(symbol, limit="5")
            return ob.best_bid, ob.best_ask
        except Exception:
            return None, None

    def get_mid_price(self, symbol: str) -> Optional[float]:
        bid, ask = self.get_best_bid_ask(symbol)
        if bid and ask:
            return (bid + ask) / 2
        return None

    def get_candles_df(self, symbol: str, interval: str = "1m",
                       lookback_days: int = 7) -> pd.DataFrame:
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - (lookback_days * 86400 * 1000)
        return self.rest.get_klines_df(symbol, interval, limit=1000,
                                        start_time=start_ms, end_time=end_ms)

    def get_standardized_candles(self, symbol: str, interval: str = "1m",
                                  lookback_days: int = 7) -> pd.DataFrame:
        df = self.get_candles_df(symbol, interval, lookback_days)
        if df.empty:
            return df
        return df[["open", "high", "low", "close", "volume"]]

    def place_market_buy(self, symbol: str, qty: str) -> BitunixOrderResult:
        return self.rest.place_order(symbol, side="BUY", order_type="MARKET", qty=qty)

    def place_market_sell(self, symbol: str, qty: str) -> BitunixOrderResult:
        return self.rest.place_order(symbol, side="SELL", order_type="MARKET", qty=qty)

    def place_limit_buy(self, symbol: str, qty: str, price: str) -> BitunixOrderResult:
        return self.rest.place_order(symbol, side="BUY", order_type="LIMIT", qty=qty, price=price)

    def place_limit_sell(self, symbol: str, qty: str, price: str) -> BitunixOrderResult:
        return self.rest.place_order(symbol, side="SELL", order_type="LIMIT", qty=qty, price=price)


# ═══════════════════════════════════════════════════════════════════════════════
# PARSERS (Bitunix-specific field names)
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_ticker(raw: Dict) -> BitunixTicker:
    # Bitunix ticker fields: symbol, markPrice, lastPrice, open, last, quoteVol, baseVol, high, low
    last_price = float(raw.get("lastPrice", 0) or raw.get("last", 0) or 0)
    open_price = float(raw.get("open", 0) or 0)
    high = float(raw.get("high", 0) or 0)
    low = float(raw.get("low", 0) or 0)
    # Price change %
    if open_price > 0:
        change_pct = ((last_price - open_price) / open_price) * 100
    else:
        change_pct = 0.0
    return BitunixTicker(
        symbol=raw.get("symbol", ""),
        last_price=last_price,
        mark_price=float(raw.get("markPrice", 0) or 0),
        high_24h=high,
        low_24h=low,
        volume_24h=float(raw.get("baseVol", 0) or 0),
        turnover_24h=float(raw.get("quoteVol", 0) or 0),
        open_24h=open_price,
        price_change_pct_24h=change_pct,
        raw=raw,
    )


def _parse_orderbook(symbol: str, raw: Dict) -> BitunixOrderBook:
    bids = [(float(p), float(q)) for p, q in raw.get("bids", [])]
    asks = [(float(p), float(q)) for p, q in raw.get("asks", [])]
    bids.sort(key=lambda x: -x[0])
    asks.sort(key=lambda x: x[0])
    return BitunixOrderBook(
        symbol=symbol, bids=bids, asks=asks,
        timestamp=int(raw.get("t", 0) or time.time() * 1000),
        raw=raw,
    )


def _parse_kline(raw: Dict) -> BitunixKline:
    # Bitunix kline: {open, high, low, close, baseVol, quoteVol, time}
    return BitunixKline(
        timestamp=int(raw.get("time", 0)),
        open=float(raw.get("open", 0)),
        high=float(raw.get("high", 0)),
        low=float(raw.get("low", 0)),
        close=float(raw.get("close", 0)),
        volume=float(raw.get("baseVol", 0) or 0),
        turnover=float(raw.get("quoteVol", 0) or 0),
    )


def _parse_order_result(raw: Dict) -> BitunixOrderResult:
    return BitunixOrderResult(
        order_id=str(raw.get("orderId", "")),
        client_id=str(raw.get("clientId", "")),
        symbol=raw.get("symbol", ""),
        side=raw.get("side", ""),
        order_type=raw.get("orderType", ""),
        price=float(raw.get("price", 0)),
        qty=float(raw.get("qty", 0)),
        status=raw.get("status", ""),
        raw=raw,
    )


def _parse_account(raw: Dict) -> BitunixAccount:
    return BitunixAccount(
        margin_coin=raw.get("marginCoin", "USDT"),
        available_balance=float(raw.get("availableBalance", 0) or 0),
        frozen_balance=float(raw.get("frozenBalance", 0) or 0),
        unrealized_pnl=float(raw.get("unrealizedPNL", 0) or 0),
        realized_pnl=float(raw.get("realizedPNL", 0) or 0),
        margin_ratio=float(raw.get("marginRatio", 0) or 0),
        raw=raw,
    )


def _parse_position(raw: Dict) -> BitunixPosition:
    return BitunixPosition(
        symbol=raw.get("symbol", ""),
        side=raw.get("side", ""),
        qty=float(raw.get("qty", 0) or 0),
        entry_price=float(raw.get("entryPrice", 0) or 0),
        mark_price=float(raw.get("markPrice", 0) or 0),
        unrealized_pnl=float(raw.get("unrealizedPNL", 0) or 0),
        leverage=int(raw.get("leverage", 0) or 0),
        liquidation_price=float(raw.get("liquidationPrice", 0) or 0),
        margin=float(raw.get("margin", 0) or 0),
        raw=raw,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# STANDALONE FETCHER (for exchange_integrator.py pattern)
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_bitunix_candles(symbol: str, interval: str = "1m", limit: int = 1000) -> Optional[pd.DataFrame]:
    """
    Fetch candles from Bitunix — follows the same pattern as fetch_hyperliquid_candles().
    Returns DataFrame with [open, high, low, close, volume] and datetime index.
    """
    try:
        client = BitunixRestClient()
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - (30 * 86400 * 1000)

        klines = client.get_klines(symbol, interval=interval, limit=limit,
                                    start_time=start_ms, end_time=end_ms)
        if not klines:
            return None

        df = pd.DataFrame([{
            "time": pd.to_datetime(k.timestamp, unit="ms"),
            "open": k.open, "high": k.high, "low": k.low,
            "close": k.close, "volume": k.volume,
        } for k in klines])
        df = df.set_index("time")
        return df[["open", "high", "low", "close", "volume"]]
    except Exception as e:
        print(f"Error fetching from Bitunix: {e}")
        return None


def fetch_bitunix_ticker(symbol: str = "") -> Optional[Dict]:
    try:
        client = BitunixRestClient()
        tickers = client.get_tickers(symbol)
        return tickers[0].raw if tickers else None
    except Exception as e:
        print(f"Error fetching ticker from Bitunix: {e}")
        return None


def fetch_bitunix_depth(symbol: str, limit: str = "50") -> Optional[Dict]:
    try:
        client = BitunixRestClient()
        ob = client.get_depth(symbol, limit)
        return {
            "symbol": ob.symbol, "bids": ob.bids, "asks": ob.asks,
            "best_bid": ob.best_bid, "best_ask": ob.best_ask,
            "mid_price": ob.mid_price, "spread": ob.spread,
            "spread_bps": ob.spread_bps, "timestamp": ob.timestamp,
        }
    except Exception as e:
        print(f"Error fetching depth from Bitunix: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# CLI / TEST
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("Bitunix Exchange Connector — Test")
    print("=" * 60)

    client = BitunixRestClient()

    # 1. Trading pairs
    print("\n[1] Trading pairs:")
    pairs = client.get_trading_pairs()
    if pairs:
        for p in pairs[:5]:
            print(f"  {p.get('symbol', '?')} — {p.get('baseCoin', '?')}/{p.get('quoteCoin', '?')}")
        print(f"  ... {len(pairs)} total pairs")

    # 2. Ticker
    print("\n[2] BTCUSDT Ticker:")
    try:
        t = client.get_ticker("BTCUSDT")
        print(f"  Last: {t.last_price}")
        print(f"  Mark: {t.mark_price}")
        print(f"  24h High: {t.high_24h}")
        print(f"  24h Low: {t.low_24h}")
        print(f"  24h Volume: {t.volume_24h}")
        print(f"  24h Turnover: {t.turnover_24h}")
        print(f"  Change%: {t.price_change_pct_24h:.2f}%")
    except Exception as e:
        print(f"  Error: {e}")

    # 3. Order book
    print("\n[3] BTCUSDT Order Book (top 5):")
    try:
        ob = client.get_depth("BTCUSDT", limit="5")
        print(f"  Best Bid: {ob.best_bid}")
        print(f"  Best Ask: {ob.best_ask}")
        print(f"  Mid: {ob.mid_price}")
        print(f"  Spread: {ob.spread} ({ob.spread_bps:.2f} bps)")
    except Exception as e:
        print(f"  Error: {e}")

    # 4. Klines
    print("\n[4] BTCUSDT 1m Klines (last 5):")
    try:
        df = client.get_klines_df("BTCUSDT", interval="1m", limit=5)
        if not df.empty:
            print(f"  {len(df)} candles")
            print(df.tail())
    except Exception as e:
        print(f"  Error: {e}")

    # 5. Funding rates
    print("\n[5] Batch Funding Rates (first 3):")
    try:
        rates = client.get_batch_funding_rates()
        for r in rates[:3]:
            print(f"  {r.get('symbol', '?')}: {r.get('fundingRate', '?')}")
    except Exception as e:
        print(f"  Error: {e}")

    print("\n" + "=" * 60)
    print("✓ Bitunix connector test complete")
    print("=" * 60)
