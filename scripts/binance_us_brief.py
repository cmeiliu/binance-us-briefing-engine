#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


BASE_URL = "https://api.binance.us"
SKILL_VERSION = "0.2.0"
DEFAULT_CONFIG_PATH = Path.home() / ".openclaw" / "binance-us-briefing-engine.json"
DEFAULT_STATE_PATH = Path.home() / ".openclaw" / "binance-us-briefing-engine-state.json"
DEFAULT_QUOTE_ASSETS = ["USD", "USDT", "USDC", "BTC"]
DEFAULT_RECENT_DAYS = 30
DEFAULT_ALERT_THRESHOLD_PCT = 5.0
LIMITED_MODE_REASON = "Account credentials not found; running in limited market-only mode."
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
ASSET_SEARCH_TERMS = {
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "SOL": "Solana",
    "AVAX": "Avalanche crypto",
    "DOGE": "Dogecoin",
    "XRP": "XRP Ripple",
    "ADA": "Cardano ADA",
    "LINK": "Chainlink",
    "LTC": "Litecoin",
    "BCH": "Bitcoin Cash",
}
ASSET_ALIASES = {
    "BTC": ["Bitcoin", "BTC", "XBT"],
    "ETH": ["Ethereum", "ETH"],
    "SOL": ["Solana", "SOL"],
    "AVAX": ["Avalanche", "AVAX"],
    "DOGE": ["Dogecoin", "DOGE"],
    "XRP": ["XRP", "Ripple"],
    "ADA": ["Cardano", "ADA"],
    "LINK": ["Chainlink", "LINK"],
    "LTC": ["Litecoin", "LTC"],
    "BCH": ["Bitcoin Cash", "BCH"],
    "MATIC": ["Polygon", "MATIC", "POL"],
    "SUI": ["Sui", "SUI"],
    "APT": ["Aptos", "APT"],
    "HBAR": ["Hedera", "HBAR"],
    "SHIB": ["Shiba Inu", "SHIB"],
}
MARKET_CONTEXT_CACHE: Dict[str, Dict[str, Any]] = {}


class BinanceUSError(RuntimeError):
    pass


def now_ms() -> int:
    return int(time.time() * 1000)


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def trim_lines(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


def format_price(value: float) -> str:
    if value >= 1000:
        return f"${value:,.0f}"
    if value >= 1:
        return f"${value:,.2f}"
    if value >= 0.01:
        return f"${value:,.4f}"
    return f"${value:,.6f}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate personalized Binance.US briefings.")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init-config", help="Create a starter config file.")
    init_parser.add_argument("--force", action="store_true", help="Overwrite an existing config file.")

    parser.add_argument(
        "--mode",
        choices=[
            "daily_brief",
            "watchlist_brief",
            "opportunity_alert",
            "funding_nudge",
            "weekly_reset",
            "portfolio_brief",
        ],
        default="daily_brief",
    )
    parser.add_argument("--format", choices=["json", "text", "both"], default="both")
    parser.add_argument("--watchlist", default="", help="Comma-separated asset tickers, e.g. BTC,ETH,SOL")
    parser.add_argument(
        "--quote-assets",
        default=",".join(DEFAULT_QUOTE_ASSETS),
        help="Comma-separated preferred quote assets for pair selection.",
    )
    parser.add_argument("--recent-days", type=int, default=DEFAULT_RECENT_DAYS)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--alert-threshold-pct", type=float, default=DEFAULT_ALERT_THRESHOLD_PCT)
    parser.add_argument("--limit", type=int, default=5, help="Maximum highlights to include.")
    parser.add_argument("--news-limit", type=int, default=3, help="Maximum news headlines to include.")
    return parser.parse_args()


def write_default_config(path: Path, force: bool) -> None:
    if path.exists() and not force:
        raise BinanceUSError(f"Config already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    sample = {
        "watchlist": ["BTC", "ETH", "SOL", "AVAX"],
        "quote_assets": DEFAULT_QUOTE_ASSETS,
        "portfolio_currency": "USD",
        "recent_days": DEFAULT_RECENT_DAYS,
        "alert_threshold_pct": DEFAULT_ALERT_THRESHOLD_PCT,
        "news_limit": 3,
        "quiet_hours": {"start": "22:00", "end": "07:00"},
    }
    path.write_text(json.dumps(sample, indent=2) + "\n", encoding="utf-8")


def load_config(path_str: str) -> Dict[str, Any]:
    path = Path(os.path.expanduser(path_str))
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BinanceUSError(f"Invalid config JSON in {path}: {exc}") from exc


def load_state(path: Path = DEFAULT_STATE_PATH) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_state(state: Dict[str, Any], path: Path = DEFAULT_STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def load_secret_from_env_or_files() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    key_names = ["BINANCE_US_API_KEY"]
    secret_names = ["BINANCE_US_SECRET_KEY"]

    api_key = next((os.environ.get(name) for name in key_names if os.environ.get(name)), None)
    secret_key = next((os.environ.get(name) for name in secret_names if os.environ.get(name)), None)
    if api_key and secret_key:
        return api_key.strip(), secret_key.strip(), "environment"

    env_files = [
        Path.home() / ".openclaw" / "secrets.env",
        Path.home() / ".env",
        Path.cwd() / ".env",
    ]

    for env_file in env_files:
        if not env_file.exists():
            continue
        content = env_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        values: Dict[str, str] = {}
        for line in content:
            if "=" not in line or line.strip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")

        api_key = next((values.get(name) for name in key_names if values.get(name)), None)
        secret_key = next((values.get(name) for name in secret_names if values.get(name)), None)
        if api_key and secret_key:
            return api_key, secret_key, str(env_file)

    return None, None, None


def http_get(path: str, params: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Any:
    query = urllib.parse.urlencode([(k, v) for k, v in params.items() if v is not None], doseq=True)
    url = f"{BASE_URL}{path}"
    if query:
        url = f"{url}?{query}"
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise BinanceUSError(f"HTTP {exc.code} calling {path}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise BinanceUSError(f"Network error calling {path}: {exc}") from exc


def signed_get(path: str, params: Dict[str, Any], api_key: str, secret_key: str) -> Any:
    payload = dict(params)
    payload["timestamp"] = now_ms()
    query = urllib.parse.urlencode([(k, v) for k, v in payload.items() if v is not None], doseq=True)
    signature = hmac.new(secret_key.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
    payload["signature"] = signature
    headers = {"X-MBX-APIKEY": api_key}
    return http_get(path, payload, headers=headers)


def public_get(path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    return http_get(path, params or {})


def http_get_text(url: str, headers: Optional[Dict[str, str]] = None) -> str:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise BinanceUSError(f"HTTP {exc.code} loading {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise BinanceUSError(f"Network error loading {url}: {exc}") from exc


def normalize_watchlist(cli_watchlist: str, config: Dict[str, Any]) -> List[str]:
    combined: List[str] = []
    for source in [config.get("watchlist", []), cli_watchlist.split(",") if cli_watchlist else []]:
        for asset in source:
            asset = str(asset).strip().upper()
            if asset and asset not in combined:
                combined.append(asset)
    return combined


def parse_quote_assets(cli_quote_assets: str, config: Dict[str, Any]) -> List[str]:
    values = config.get("quote_assets") or cli_quote_assets.split(",")
    return [str(item).strip().upper() for item in values if str(item).strip()]


def build_symbol_maps(exchange_info: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    by_symbol: Dict[str, Dict[str, Any]] = {}
    by_base: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for entry in exchange_info.get("symbols", []):
        if entry.get("status") != "TRADING":
            continue
        symbol = entry["symbol"]
        by_symbol[symbol] = entry
        by_base[entry["baseAsset"]].append(entry)
    return by_symbol, by_base


def choose_symbol_for_asset(asset: str, by_base: Dict[str, List[Dict[str, Any]]], quote_assets: List[str]) -> Optional[str]:
    candidates = by_base.get(asset, [])
    if not candidates:
        return None
    for quote in quote_assets:
        for entry in candidates:
            if entry.get("quoteAsset") == quote:
                return entry["symbol"]
    return candidates[0]["symbol"]


def ticker_map() -> Dict[str, Dict[str, Any]]:
    data = public_get("/api/v3/ticker/24hr")
    return {entry["symbol"]: entry for entry in data}


def fetch_klines(symbol: str, interval: str = "1h", limit: int = 24) -> List[List[Any]]:
    return public_get("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})


def infer_volume_ratio(symbol: str) -> Optional[float]:
    try:
        klines = fetch_klines(symbol, interval="1h", limit=16)
    except BinanceUSError:
        return None
    if len(klines) < 4:
        return None
    volumes = [safe_float(item[5]) for item in klines[:-1]]
    latest = safe_float(klines[-1][5])
    median_volume = statistics.median(v for v in volumes if v > 0) if any(v > 0 for v in volumes) else 0
    if median_volume <= 0:
        return None
    return latest / median_volume


def seven_day_change_pct(symbol: str) -> Optional[float]:
    try:
        klines = fetch_klines(symbol, interval="1d", limit=8)
    except BinanceUSError:
        return None
    if len(klines) < 2:
        return None
    start = safe_float(klines[0][1])
    end = safe_float(klines[-1][4])
    if start <= 0:
        return None
    return ((end - start) / start) * 100.0


def market_context(symbol: Optional[str]) -> Dict[str, Any]:
    if not symbol:
        return {}
    if symbol in MARKET_CONTEXT_CACHE:
        return MARKET_CONTEXT_CACHE[symbol]
    try:
        klines = fetch_klines(symbol, interval="1d", limit=31)
    except BinanceUSError:
        MARKET_CONTEXT_CACHE[symbol] = {}
        return {}
    if len(klines) < 8:
        MARKET_CONTEXT_CACHE[symbol] = {}
        return {}
    closes = [safe_float(item[4]) for item in klines]
    current = closes[-1]
    week_ago = closes[-8] if len(closes) >= 8 else 0.0
    prior_week_close = closes[-15] if len(closes) >= 15 else 0.0
    month_high = max(closes[-30:]) if len(closes) >= 30 else max(closes)
    month_low = min(closes[-30:]) if len(closes) >= 30 else min(closes)
    current_7d = ((current - week_ago) / week_ago) * 100.0 if week_ago > 0 else None
    prior_7d = ((week_ago - prior_week_close) / prior_week_close) * 100.0 if prior_week_close > 0 else None
    high_distance_pct = ((current - month_high) / month_high) * 100.0 if month_high > 0 else None
    low_distance_pct = ((current - month_low) / month_low) * 100.0 if month_low > 0 else None
    context = {
        "change_pct_7d": current_7d,
        "change_pct_prior_7d": prior_7d,
        "month_high": month_high,
        "month_low": month_low,
        "is_30d_high": month_high > 0 and abs(current - month_high) / month_high < 0.005,
        "high_distance_pct": high_distance_pct,
        "low_distance_pct": low_distance_pct,
    }
    MARKET_CONTEXT_CACHE[symbol] = context
    return context


def format_price_quantity(amount: float, asset: str) -> str:
    if asset == "BTC":
        return f"{amount:.4f} BTC"
    if amount >= 1000:
        return f"{amount:,.0f} {asset}"
    if amount >= 1:
        return f"{amount:,.2f} {asset}"
    return f"{amount:,.4f} {asset}"


def dedupe_lines(lines: List[str]) -> List[str]:
    seen = set()
    deduped = []
    for line in lines:
        key = " ".join(line.split()).lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(line)
    return deduped


def asset_search_term(asset: str) -> str:
    return ASSET_SEARCH_TERMS.get(asset, f"{asset} crypto")


def news_queries_for_asset(asset: str) -> List[str]:
    aliases = ASSET_ALIASES.get(asset, [asset_search_term(asset), asset])
    queries = [
        f"{aliases[0]} crypto when:2d",
        f"{asset} crypto market when:2d",
    ]
    if len(aliases) > 1:
        queries.append(f"{aliases[0]} OR {aliases[1]} crypto when:2d")
    return queries


def normalize_story_title(title: str) -> str:
    lowered = title.lower()
    for delimiter in (" - ", " | ", ":", "—"):
        if delimiter in lowered:
            lowered = lowered.split(delimiter, 1)[0]
    return " ".join(lowered.split())


def fetch_asset_news(asset: str, limit: int = 3) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen_titles = set()
    for query in news_queries_for_asset(asset):
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
        url = f"{GOOGLE_NEWS_RSS}?{urllib.parse.urlencode(params)}"
        xml_text = http_get_text(url, headers={"User-Agent": "Mozilla/5.0"})
        root = ET.fromstring(xml_text)
        for item in root.findall("./channel/item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            source = ""
            source_node = item.find("source")
            if source_node is not None and source_node.text:
                source = source_node.text.strip()
            published_at = None
            if pub_date:
                try:
                    published_at = parsedate_to_datetime(pub_date).astimezone().isoformat(timespec="seconds")
                except (TypeError, ValueError, OverflowError):
                    published_at = None
            if not title:
                continue
            title_key = normalize_story_title(title)
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            items.append(
                {
                    "asset": asset,
                    "title": title,
                    "link": link,
                    "source": source or "Google News",
                    "published_at": published_at,
                }
            )
            if len(items) >= limit:
                return items
    return items[:limit]


def fetch_account_context(
    api_key: Optional[str],
    secret_key: Optional[str],
    watchlist: List[str],
    by_base: Dict[str, List[Dict[str, Any]]],
    quote_assets: List[str],
    recent_days: int,
) -> Dict[str, Any]:
    context: Dict[str, Any] = {"limited_mode": not (api_key and secret_key), "credentials_source": None, "balances": [], "recent_trades": {}, "fiat_deposits": [], "staking_balances": []}
    if not (api_key and secret_key):
        return context

    account = signed_get("/api/v3/account", {}, api_key, secret_key)
    balances = []
    for item in account.get("balances", []):
        free = safe_float(item.get("free"))
        locked = safe_float(item.get("locked"))
        total = free + locked
        if total > 0:
            balances.append({"asset": item["asset"], "free": free, "locked": locked, "total": total})
    context["balances"] = balances

    relevant_assets = [entry["asset"] for entry in balances]
    for asset in watchlist:
        if asset not in relevant_assets:
            relevant_assets.append(asset)

    trade_symbols: List[str] = []
    for asset in relevant_assets:
        symbol = choose_symbol_for_asset(asset, by_base, quote_assets)
        if symbol and symbol not in trade_symbols:
            trade_symbols.append(symbol)

    start_ms = int((datetime.now(timezone.utc) - timedelta(days=recent_days)).timestamp() * 1000)
    recent_trades: Dict[str, List[Dict[str, Any]]] = {}
    for symbol in trade_symbols[:10]:
        try:
            trades = signed_get("/api/v3/myTrades", {"symbol": symbol, "startTime": start_ms, "limit": 50}, api_key, secret_key)
        except BinanceUSError:
            continue
        if trades:
            recent_trades[symbol] = trades
    context["recent_trades"] = recent_trades

    try:
        fiat_history = signed_get("/sapi/v1/fiatpayment/query/deposit/history", {"transactionType": 0, "beginTime": start_ms, "endTime": now_ms()}, api_key, secret_key)
        context["fiat_deposits"] = fiat_history.get("data", []) if isinstance(fiat_history, dict) else fiat_history
    except BinanceUSError:
        pass

    try:
        staking = signed_get("/sapi/v1/staking/stakingBalance", {}, api_key, secret_key)
        if isinstance(staking, list):
            context["staking_balances"] = staking
    except BinanceUSError:
        pass

    return context


def portfolio_snapshot(balances: List[Dict[str, Any]], by_base: Dict[str, List[Dict[str, Any]]], tickers: Dict[str, Dict[str, Any]], quote_assets: List[str]) -> Dict[str, Any]:
    holdings: List[Dict[str, Any]] = []
    total_value = 0.0
    cash_value = 0.0
    week_change_value = 0.0

    for balance in balances:
        asset = balance["asset"]
        total = balance["total"]
        price = 1.0 if asset in {"USD", "USDT", "USDC"} else 0.0
        symbol = None
        if asset not in {"USD", "USDT", "USDC"}:
            symbol = choose_symbol_for_asset(asset, by_base, quote_assets)
            if symbol and symbol in tickers:
                price = safe_float(tickers[symbol].get("lastPrice"))
        usd_value = total * price
        change_pct = safe_float(tickers[symbol].get("priceChangePercent")) if symbol and symbol in tickers else 0.0
        context = market_context(symbol)
        week_change_pct = context.get("change_pct_7d")
        prior_week_change_pct = context.get("change_pct_prior_7d")
        contribution = usd_value * (change_pct / 100.0)
        week_contribution = usd_value * ((week_change_pct or 0.0) / 100.0)
        holdings.append(
            {
                "asset": asset,
                "symbol": symbol,
                "amount": total,
                "price": price,
                "usd_value": usd_value,
                "change_pct_24h": change_pct,
                "change_pct_7d": week_change_pct,
                "change_pct_prior_7d": prior_week_change_pct,
                "contribution_24h": contribution,
                "contribution_7d": week_contribution,
                "is_30d_high": context.get("is_30d_high", False),
                "high_distance_pct": context.get("high_distance_pct"),
            }
        )
        total_value += usd_value
        week_change_value += week_contribution
        if asset in {"USD", "USDT", "USDC"}:
            cash_value += usd_value

    holdings.sort(key=lambda item: item["usd_value"], reverse=True)
    top_asset = holdings[0] if holdings else None
    concentration = (top_asset["usd_value"] / total_value) if top_asset and total_value > 0 else 0.0
    return {
        "holdings": holdings,
        "total_value": total_value,
        "cash_value": cash_value,
        "cash_ratio": (cash_value / total_value) if total_value > 0 else 0.0,
        "top_asset": top_asset,
        "concentration": concentration,
        "week_change_value": week_change_value,
        "week_change_pct": ((week_change_value / total_value) * 100.0) if total_value > 0 else 0.0,
    }


def recent_trade_summary(recent_trades: Dict[str, List[Dict[str, Any]]], by_symbol: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    asset_events: Dict[str, Any] = {}
    for symbol, trades in recent_trades.items():
        if symbol not in by_symbol or not trades:
            continue
        base_asset = by_symbol[symbol]["baseAsset"]
        last_trade = sorted(trades, key=lambda t: t.get("time", 0))[-1]
        side = "BUY" if last_trade.get("isBuyer") else "SELL"
        asset_events[base_asset] = {"symbol": symbol, "side": side, "time": last_trade.get("time"), "price": safe_float(last_trade.get("price")), "qty": safe_float(last_trade.get("qty"))}
    return asset_events


def market_tone(tickers: Dict[str, Dict[str, Any]], watch_symbols: List[str]) -> str:
    symbols = watch_symbols[:]
    for candidate in ["BTCUSD", "BTCUSDT", "ETHUSD", "ETHUSDT", "SOLUSD", "SOLUSDT"]:
        if candidate in tickers and candidate not in symbols:
            symbols.append(candidate)
    changes = [safe_float(tickers[s]["priceChangePercent"]) for s in symbols if s in tickers]
    if not changes:
        return "mixed"
    avg = statistics.mean(changes)
    if avg >= 1.5:
        return "risk_on"
    if avg <= -1.5:
        return "risk_off"
    return "mixed"


def top_market_movers(tickers: Dict[str, Dict[str, Any]], quote_assets: List[str], limit: int) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for symbol, ticker in tickers.items():
        if not any(symbol.endswith(q) for q in quote_assets):
            continue
        quote_volume = safe_float(ticker.get("quoteVolume"))
        if quote_volume <= 50000:
            continue
        candidates.append({"symbol": symbol, "change_pct": safe_float(ticker.get("priceChangePercent")), "quote_volume": quote_volume})
    candidates.sort(key=lambda item: (abs(item["change_pct"]), item["quote_volume"]), reverse=True)
    return candidates[:limit]


def find_watchlist_insights(watchlist: List[str], by_base: Dict[str, List[Dict[str, Any]]], tickers: Dict[str, Dict[str, Any]], quote_assets: List[str]) -> List[Dict[str, Any]]:
    insights: List[Dict[str, Any]] = []
    for asset in watchlist:
        symbol = choose_symbol_for_asset(asset, by_base, quote_assets)
        if not symbol or symbol not in tickers:
            continue
        change = safe_float(tickers[symbol].get("priceChangePercent"))
        price = safe_float(tickers[symbol].get("lastPrice"))
        context = market_context(symbol)
        week_change = context.get("change_pct_7d")
        prior_week_change = context.get("change_pct_prior_7d")
        ratio = infer_volume_ratio(symbol)
        summary = f"{asset} {format_price(price)} ({change:+.1f}% 24h"
        if week_change is not None:
            summary += f", {week_change:+.1f}% vs 7d"
        summary += ")."
        if context.get("is_30d_high"):
            summary += " It is pressing a 30-day high."
        if ratio and ratio >= 1.8:
            summary += f" Hourly volume is {ratio:.1f}x baseline."
        insights.append(
            {
                "asset": asset,
                "symbol": symbol,
                "change_pct": change,
                "change_pct_7d": week_change,
                "change_pct_prior_7d": prior_week_change,
                "price": price,
                "volume_ratio": ratio,
                "is_30d_high": context.get("is_30d_high", False),
                "high_distance_pct": context.get("high_distance_pct"),
                "summary": summary,
            }
        )
    insights.sort(key=lambda item: (abs(item["change_pct"]), abs(item.get("change_pct_7d") or 0.0), item["volume_ratio"] or 0.0), reverse=True)
    return insights


def latest_fiat_deposit_age_days(fiat_deposits: List[Dict[str, Any]]) -> Optional[int]:
    if not fiat_deposits:
        return None
    timestamps: List[int] = []
    for item in fiat_deposits:
        for key in ("createTime", "insertTime", "time", "updateTime"):
            value = item.get(key)
            if value:
                timestamps.append(int(value))
                break
    if not timestamps:
        return None
    latest = max(timestamps)
    age = datetime.now(timezone.utc) - datetime.fromtimestamp(latest / 1000.0, tz=timezone.utc)
    return max(0, age.days)


def score_news_item(story: Dict[str, Any], snapshot: Dict[str, Any], trade_summary: Dict[str, Any], watchlist: List[str]) -> float:
    score = 0.0
    asset = story["asset"]
    if snapshot.get("top_asset") and snapshot["top_asset"]["asset"] == asset:
        score += 4.0
    if asset in trade_summary:
        score += 3.0
    if asset in watchlist:
        score += 2.0
    title = story["title"].lower()
    if any(word in title for word in ["hack", "etf", "security", "lawsuit", "approval", "launch", "surge", "upgrade"]):
        score += 1.5
    if any(word in title for word in ["price of", "current price", "forecast", "prediction"]):
        score -= 1.5
    source = (story.get("source") or "").lower()
    if source in {"fortune", "bloomberg", "reuters", "coindesk", "cointelegraph", "the block", "mashable"}:
        score += 0.5
    published_at = story.get("published_at")
    if published_at:
        try:
            age_hours = (datetime.now().astimezone() - datetime.fromisoformat(published_at)).total_seconds() / 3600.0
            if age_hours <= 12:
                score += 0.5
        except ValueError:
            pass
    return score


def explain_news_item(story: Dict[str, Any], snapshot: Dict[str, Any], trade_summary: Dict[str, Any], watchlist: List[str]) -> str:
    asset = story["asset"]
    title = story["title"]
    title_lower = title.lower()
    if snapshot.get("top_asset") and snapshot["top_asset"]["asset"] == asset:
        prefix = f"{asset} is your largest position, so this is worth scanning."
    elif asset in trade_summary:
        action = "bought" if trade_summary[asset]["side"] == "BUY" else "sold"
        prefix = f"You recently {action.lower()} {asset}, so this is relevant context."
    elif asset in watchlist:
        prefix = f"{asset} is on your watchlist, so this could matter if momentum persists."
    else:
        prefix = f"{asset} is relevant to your current market focus."

    if any(word in title_lower for word in ["hack", "security", "exploit"]):
        suffix = "Treat this as risk-sensitive news, not routine market chatter."
    elif any(word in title_lower for word in ["launch", "approval", "upgrade", "rolls out", "partnership"]):
        suffix = "This reads like a real catalyst, not just a price recap."
    elif any(word in title_lower for word in ["price of", "current price", "forecast", "prediction"]):
        suffix = "This looks more like recap content than a fresh catalyst."
    else:
        suffix = "Check whether the story changes your thesis or is just noise."
    return f"{prefix} {suffix}"


def relevant_assets_for_news(snapshot: Dict[str, Any], trade_summary: Dict[str, Any], watchlist: List[str], limit: int) -> List[str]:
    ordered: List[str] = []
    if snapshot.get("top_asset"):
        ordered.append(snapshot["top_asset"]["asset"])
    for holding in snapshot.get("holdings", [])[: max(limit, 3)]:
        asset = holding.get("asset")
        if asset and asset not in ordered and asset not in {"USD", "USDT", "USDC"}:
            ordered.append(asset)
    for asset in trade_summary:
        if asset not in ordered:
            ordered.append(asset)
    for asset in watchlist:
        if asset not in ordered:
            ordered.append(asset)
    return [asset for asset in ordered if asset not in {"USD", "USDT", "USDC"}][:limit]


def fetch_news_context(snapshot: Dict[str, Any], trade_summary: Dict[str, Any], watchlist: List[str], news_limit: int) -> List[Dict[str, Any]]:
    assets = relevant_assets_for_news(snapshot, trade_summary, watchlist, news_limit)
    stories: List[Dict[str, Any]] = []
    for asset in assets:
        try:
            stories.extend(fetch_asset_news(asset, limit=1))
        except (BinanceUSError, ET.ParseError):
            continue
    scored = []
    for story in stories:
        story["news_score"] = score_news_item(story, snapshot, trade_summary, watchlist)
        story["why_this_matters"] = explain_news_item(story, snapshot, trade_summary, watchlist)
        scored.append(story)
    scored.sort(key=lambda item: item.get("news_score", 0.0), reverse=True)
    return scored[:news_limit]


def held_assets(snapshot: Dict[str, Any]) -> List[str]:
    return [item["asset"] for item in snapshot.get("holdings", []) if item.get("usd_value", 0.0) > 1 and item["asset"] not in {"USD", "USDT", "USDC"}]


def watchlist_gap_insights(snapshot: Dict[str, Any], watch_insights: List[Dict[str, Any]]) -> List[str]:
    held = set(held_assets(snapshot))
    prompts = []
    for insight in watch_insights:
        if insight["asset"] in held:
            continue
        if insight["change_pct"] >= 4 or (insight.get("change_pct_7d") or 0) >= 8 or insight.get("is_30d_high"):
            week = f" and {insight['change_pct_7d']:+.1f}% this week" if insight.get("change_pct_7d") is not None else ""
            prompts.append(f"{insight['asset']} is up {insight['change_pct']:+.1f}% today{week}, and you have none. Worth a look?")
    return prompts[:1]


def idle_cash_story(snapshot: Dict[str, Any], watch_insights: List[Dict[str, Any]]) -> Optional[str]:
    if snapshot["cash_ratio"] < 0.2 or snapshot["cash_value"] <= 0:
        return None
    if not watch_insights:
        return f"You have about {format_price(snapshot['cash_value'])} sitting idle in cash-like balances."
    anchor = watch_insights[0]
    units = snapshot["cash_value"] / anchor["price"] if anchor.get("price") else 0.0
    return (
        f"You have about {format_price(snapshot['cash_value'])} sitting idle. At {anchor['asset']}'s current price, "
        f"that is roughly {format_price_quantity(units, anchor['asset'])}."
    )


def first_run_hook(snapshot: Dict[str, Any], watch_insights: List[Dict[str, Any]], state: Dict[str, Any], limited_mode: bool) -> Optional[str]:
    if state.get("has_run"):
        return None
    anchor = watch_insights[0] if watch_insights else snapshot.get("top_asset")
    if not anchor:
        return None
    asset = anchor["asset"]
    day_move = anchor.get("change_pct", anchor.get("change_pct_24h", 0.0))
    cash_story = idle_cash_story(snapshot, watch_insights)
    if cash_story:
        return f"First look: yesterday {asset} moved {day_move:+.1f}% while your cash sat on the sidelines. {cash_story}"
    if limited_mode:
        return f"First look: yesterday {asset} moved {day_move:+.1f}%. This brief exists to make sure you do not miss the next move blind."
    return f"First look: yesterday {asset} moved {day_move:+.1f}%. This is the kind of move this brief is supposed to catch early."


def build_portfolio_sections(snapshot: Dict[str, Any], trade_summary: Dict[str, Any], watch_insights: List[Dict[str, Any]], news_items: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    matters: List[str] = []
    news: List[str] = []
    ignore: List[str] = []

    holdings = [h for h in snapshot.get("holdings", []) if h["usd_value"] > 0]
    if holdings:
        best = max(holdings, key=lambda item: item["contribution_24h"])
        best_week = f", {best['change_pct_7d']:+.1f}% vs 7d" if best.get("change_pct_7d") is not None else ""
        matters.append(f"{best['asset']} is doing the most work in your account at {format_price(best['price'])} ({best['change_pct_24h']:+.1f}% 24h{best_week}).")
        worst = min(holdings, key=lambda item: item["contribution_24h"])
        if worst["asset"] != best["asset"]:
            worst_week = f", {worst['change_pct_7d']:+.1f}% vs 7d" if worst.get("change_pct_7d") is not None else ""
            matters.append(f"{worst['asset']} is your weakest contributor today at {format_price(worst['price'])} ({worst['change_pct_24h']:+.1f}% 24h{worst_week}).")

    cash_story = idle_cash_story(snapshot, watch_insights)
    if cash_story:
        matters.append(cash_story)
    if snapshot["concentration"] >= 0.55 and snapshot["top_asset"]:
        matters.append(f"{snapshot['top_asset']['asset']} is roughly {snapshot['concentration'] * 100:.0f}% of your account, so concentration risk is elevated.")

    for asset, event in list(trade_summary.items())[:2]:
        matters.append(f"You recently {event['side'].lower()} {asset}, so today's move is worth checking against that decision.")

    for insight in watch_insights[:2]:
        if insight["volume_ratio"] and insight["volume_ratio"] >= 1.8:
            matters.append(f"{insight['asset']} has real participation behind the move at {format_price(insight['price'])} with {insight['volume_ratio']:.1f}x hourly volume.")
        else:
            week = f", {insight['change_pct_7d']:+.1f}% vs 7d" if insight.get("change_pct_7d") is not None else ""
            high_note = " It is at a 30-day high." if insight.get("is_30d_high") else ""
            matters.append(f"{insight['asset']} is one of the strongest names on your watchlist at {format_price(insight['price'])} ({insight['change_pct']:+.1f}% 24h{week}).{high_note}")

    matters.extend(watchlist_gap_insights(snapshot, watch_insights))

    for story in news_items[:2]:
        news.append(f"{story['asset']}: {story['title']} {story['why_this_matters']}")
        if "price recap" in story["why_this_matters"].lower() or "noise" in story["why_this_matters"].lower():
            ignore.append(f"{story['asset']}: the current headline looks informational, not thesis-changing.")

    if not ignore and news_items:
        ignore.append("Ignore duplicate price-recap headlines unless they point to a real catalyst.")
    return {
        "what_matters": dedupe_lines(matters)[:5],
        "news_that_matters": dedupe_lines(news)[:2],
        "probably_ignore": dedupe_lines(ignore)[:2],
    }


def choose_suggested_action(snapshot: Dict[str, Any], trade_summary: Dict[str, Any], watch_insights: List[Dict[str, Any]], latest_deposit_age: Optional[int], limited_mode: bool) -> Dict[str, Any]:
    if snapshot["concentration"] >= 0.6 and snapshot["top_asset"]:
        asset = snapshot["top_asset"]["asset"]
        return {
            "label": f"{asset} now drives most of your risk. Open Binance.US and decide whether you still want that much riding on one name.",
            "intent": "open_portfolio_risk",
            "params": {"asset": asset, "url": "https://www.binance.us/"},
        }
    if snapshot["cash_ratio"] >= 0.2:
        for insight in watch_insights:
            if insight.get("change_pct_7d") is not None and insight["change_pct"] > 0 and insight["change_pct_7d"] > 5:
                return {
                    "label": f"You have {format_price(snapshot['cash_value'])} in cash. {insight['asset']} is pressing the tape here, so this is the moment to decide whether you want in.",
                    "intent": "open_asset",
                    "params": {"asset": insight["asset"], "url": "https://www.binance.us/"},
                }
        return {
            "label": f"You have {format_price(snapshot['cash_value'])} idle. Open Binance.US and decide whether to deploy it or keep waiting on purpose.",
            "intent": "open_convert_or_spot",
            "params": {"url": "https://www.binance.us/"},
        }
    for insight in watch_insights:
        if insight.get("is_30d_high"):
            return {
                "label": f"{insight['asset']} is at a 30-day high. Open Binance.US and check whether your limit orders still make sense.",
                "intent": "open_asset",
                "params": {"asset": insight["asset"], "url": "https://www.binance.us/"},
            }
        if insight["volume_ratio"] and insight["volume_ratio"] >= 1.8:
            return {
                "label": f"{insight['asset']} is moving on real volume. Open Binance.US and decide whether this setup still deserves your attention.",
                "intent": "open_asset",
                "params": {"asset": insight["asset"], "url": "https://www.binance.us/"},
            }
    if limited_mode and watch_insights:
        return {
            "label": f"Open Binance.US and compare {watch_insights[0]['asset']} with its 7-day trend before this move gets away from you.",
            "intent": "open_asset",
            "params": {"asset": watch_insights[0]["asset"], "url": "https://www.binance.us/"},
        }
    if trade_summary:
        asset = next(iter(trade_summary.keys()))
        return {
            "label": f"Open Binance.US and check whether {asset} still fits the reason you traded it in the first place.",
            "intent": "open_asset",
            "params": {"asset": asset, "url": "https://www.binance.us/"},
        }
    if latest_deposit_age is None:
        return {"label": "Open Binance.US and review funding options before the next move finds you unprepared.", "intent": "open_funding", "params": {"url": "https://www.binance.us/"}}
    return {"label": "Open Binance.US and make one intentional decision instead of waiting passively.", "intent": "open_account_overview", "params": {"url": "https://www.binance.us/"}}


def find_asset_context(asset: Optional[str], snapshot: Dict[str, Any], watch_insights: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not asset:
        return None
    for item in snapshot.get("holdings", []):
        if item.get("asset") == asset:
            return item
    for item in watch_insights:
        if item.get("asset") == asset:
            return item
    return None


def event_type_from_title(title: str) -> str:
    lowered = title.lower()
    if any(word in lowered for word in ["hack", "exploit", "breach", "security threat", "security"]):
        return "security_risk"
    if any(word in lowered for word in ["approval", "etf", "greenlight", "license"]):
        return "approval"
    if any(word in lowered for word in ["launch", "rolls out", "rollout", "release", "upgrade", "mainnet"]):
        return "product_launch"
    if any(word in lowered for word in ["partnership", "integrates", "integration", "adoption", "joins"]):
        return "adoption"
    if any(word in lowered for word in ["lawsuit", "probe", "investigation", "sec", "charges"]):
        return "regulatory_risk"
    if any(word in lowered for word in ["price of", "current price", "forecast", "prediction", "better hold"]):
        return "narrative_only"
    return "general_news"


def story_for_asset(asset: Optional[str], news_items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if asset:
        for item in news_items:
            if item.get("asset") == asset:
                return item
    return news_items[0] if news_items else None


def event_outcome_frame(asset: str, story: Optional[Dict[str, Any]], asset_ctx: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    if not story:
        price_ref = f" at {format_price(asset_ctx['price'])}" if asset_ctx and asset_ctx.get("price") else ""
        return (
            f"If the setup keeps improving, {asset}{price_ref} can still justify attention, especially if the market keeps confirming the move.",
            "Patience makes sense if the move is not tied to a concrete catalyst yet and you want one more session of confirmation.",
        )

    event_type = event_type_from_title(story["title"])
    title = story["title"]
    price_ref = f" at {format_price(asset_ctx['price'])}" if asset_ctx and asset_ctx.get("price") else ""

    if event_type == "approval":
        return (
            f"The bull case is that `{title}` signals a real adoption or access unlock for {asset}{price_ref}, which could keep flows and attention elevated.",
            f"The patient case is that approval-style headlines often get priced in quickly, so waiting to see whether {asset} holds the move is defensible.",
        )
    if event_type == "product_launch":
        return (
            f"The bull case is that `{title}` points to a real product or network improvement for {asset}{price_ref}, which can strengthen the story if users care.",
            f"The patient case is that launch headlines do not always translate into demand right away, so waiting for follow-through is reasonable.",
        )
    if event_type == "adoption":
        return (
            f"The bull case is that `{title}` could expand real usage or distribution for {asset}{price_ref}, which is the kind of event that can matter beyond one day.",
            f"The patient case is that partnership and adoption headlines are often vague, so it is fair to wait for evidence that the market treats it as meaningful.",
        )
    if event_type == "security_risk":
        return (
            f"The bull case is limited here: if `{title}` proves contained, {asset}{price_ref} could stabilize once the fear clears.",
            f"The patient case is stronger because security-driven headlines can keep repricing risk for longer than people expect.",
        )
    if event_type == "regulatory_risk":
        return (
            f"The bull case is that `{title}` turns out to be less damaging than feared and {asset}{price_ref} shrugs it off.",
            f"The patient case is that regulatory headlines can stay messy for a while, so waiting for clarity is usually the cleaner choice.",
        )
    if event_type == "narrative_only":
        return (
            f"The bull case is mostly sentiment-driven: `{title}` can keep {asset}{price_ref} in the conversation if traders lean into the narrative.",
            f"The patient case is that this looks more like commentary than a catalyst, so waiting for a real event is the safer interpretation.",
        )
    return (
        f"The bull case is that `{title}` changes how the market is thinking about {asset}{price_ref}, and the move keeps building.",
        f"The patient case is that the headline may fade quickly, so waiting for price and volume to confirm the story is valid.",
    )


def build_decision_frame(
    suggested_action: Dict[str, Any],
    snapshot: Dict[str, Any],
    watch_insights: List[Dict[str, Any]],
    latest_deposit_age: Optional[int],
    news_items: List[Dict[str, Any]],
) -> Optional[Dict[str, str]]:
    intent = suggested_action.get("intent")
    asset = suggested_action.get("params", {}).get("asset")
    asset_ctx = find_asset_context(asset, snapshot, watch_insights)
    related_story = story_for_asset(asset, news_items)

    if intent == "open_portfolio_risk" and asset_ctx:
        bull_case, patient_case = event_outcome_frame(asset_ctx["asset"], related_story, asset_ctx)
        return {
            "title": f"What should you do about {asset_ctx['asset']}?",
            "bull_case": bull_case,
            "patient_case": f"{patient_case} If you would be uncomfortable with one name driving this much risk, decide your max position size first.",
        }
    if intent in {"open_asset", "open_watchlist"} and asset_ctx:
        bull_line, patient_line = event_outcome_frame(asset_ctx["asset"], related_story, asset_ctx)
        return {
            "title": f"What should you do about {asset_ctx['asset']}?",
            "bull_case": bull_line,
            "patient_case": patient_line,
        }
    if intent in {"open_convert_or_spot", "open_funding"}:
        cash_line = f"You have about {format_price(snapshot['cash_value'])} available." if snapshot.get("cash_value", 0.0) > 0 else "You have room to get prepared."
        if latest_deposit_age is not None:
            cash_line = cash_line[:-1] + f", and your last deposit was about {latest_deposit_age} day(s) ago."
        story = news_items[0] if news_items else None
        catalyst_line = f" Today's key event is `{story['title']}`." if story else ""
        return {
            "title": "What should you do about your cash?",
            "bull_case": f"{cash_line}{catalyst_line} If that event strengthens a setup you already believe in, acting now gives the cash a reason to exist.",
            "patient_case": "Patience makes sense if the headline is only noise, or if the likely outcome still does not improve any asset on your list.",
        }
    return {
        "title": "What should you do about this?",
        "bull_case": "If the setup still matches your thesis, acting now may be better than drifting back into passive waiting.",
        "patient_case": "If the case is still blurry, patience is valid. Let the market prove more before you commit.",
    }


def choose_headline(snapshot: Dict[str, Any], trade_summary: Dict[str, Any], watch_insights: List[Dict[str, Any]], tone: str, limited_mode: bool) -> str:
    if snapshot["top_asset"] and watch_insights:
        return f"{snapshot['top_asset']['asset']} is driving your account, while {watch_insights[0]['asset']} is the setup worth checking next."
    if snapshot["top_asset"]:
        return f"{snapshot['top_asset']['asset']} is the main driver of your account at {format_price(snapshot['top_asset']['price'])}."
    if trade_summary:
        asset = next(iter(trade_summary.keys()))
        return f"{asset} is the asset to revisit first because it overlaps with your recent trading history."
    if watch_insights:
        lead = watch_insights[0]
        if lead["volume_ratio"] and lead["volume_ratio"] >= 1.8:
            return f"{lead['asset']} is the most actionable name on your watchlist at {format_price(lead['price'])}, with {lead['change_pct']:+.1f}% 24h and {lead['volume_ratio']:.1f}x volume."
        return f"{lead['asset']} is the most actionable name on your watchlist at {format_price(lead['price'])} ({lead['change_pct']:+.1f}% 24h)."
    if limited_mode:
        return "This is a limited market-only brief. It becomes much more useful once account context is connected."
    return f"Market tone is {tone.replace('_', ' ')}, but your account context is too thin to rank what matters."


def compose_personalized_highlights(snapshot: Dict[str, Any], trade_summary: Dict[str, Any], watch_insights: List[Dict[str, Any]], news_items: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    highlights: List[Dict[str, Any]] = []
    holdings = snapshot["holdings"]
    if holdings:
        best = max(holdings, key=lambda item: item["contribution_24h"])
        worst = min(holdings, key=lambda item: item["contribution_24h"])
        if best["usd_value"] > 0:
            week = f", {best['change_pct_7d']:+.1f}% vs 7d" if best.get("change_pct_7d") is not None else ""
            highlights.append({"type": "holding_impact", "asset": best["asset"], "summary": f"{best['asset']} is your strongest contributor at {format_price(best['price'])} ({best['change_pct_24h']:+.1f}% 24h{week})."})
        if worst["usd_value"] > 0 and worst["asset"] != best["asset"]:
            week = f", {worst['change_pct_7d']:+.1f}% vs 7d" if worst.get("change_pct_7d") is not None else ""
            highlights.append({"type": "risk_note", "asset": worst["asset"], "summary": f"{worst['asset']} is your weakest contributor at {format_price(worst['price'])} ({worst['change_pct_24h']:+.1f}% 24h{week})."})
    if snapshot["cash_ratio"] >= 0.2:
        highlights.append({"type": "idle_cash", "summary": f"Roughly {snapshot['cash_ratio'] * 100:.0f}% of your portfolio is sitting in cash or cash-like balances."})
    if snapshot["concentration"] >= 0.6 and snapshot["top_asset"]:
        highlights.append({"type": "concentration", "asset": snapshot["top_asset"]["asset"], "summary": f"{snapshot['top_asset']['asset']} is about {snapshot['concentration'] * 100:.0f}% of your account value."})
    for asset, event in trade_summary.items():
        highlights.append({"type": "recent_trade", "asset": asset, "summary": f"Your most recent {asset} trade was a {event['side']} in the last {DEFAULT_RECENT_DAYS} days."})
    for insight in watch_insights[:2]:
        highlights.append({"type": "watchlist", "asset": insight["asset"], "summary": insight["summary"]})
    for story in news_items[:2]:
        highlights.append({"type": "news_context", "asset": story["asset"], "summary": f"{story['title']} {story['why_this_matters']}", "link": story["link"], "source": story["source"]})
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in highlights:
        key = (item.get("type"), item.get("asset"), item.get("summary"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:limit]


def weekly_reset_sections(snapshot: Dict[str, Any], watch_insights: List[Dict[str, Any]], news_items: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    matters: List[str] = []
    news: List[str] = []
    ignore: List[str] = []

    holdings = [h for h in snapshot.get("holdings", []) if h["usd_value"] > 0 and h.get("change_pct_7d") is not None]
    if holdings:
        best = max(holdings, key=lambda item: item.get("contribution_7d", 0.0))
        worst = min(holdings, key=lambda item: item.get("contribution_7d", 0.0))
        delta_text = ""
        if best.get("change_pct_prior_7d") is not None:
            delta = best["change_pct_7d"] - best["change_pct_prior_7d"]
            delta_text = f" That is {delta:+.1f} points versus the prior week."
        matters.append(
            f"Your account is roughly {snapshot['week_change_pct']:+.1f}% vs 7d, with {best['asset']} contributing the most at {format_price(best['price'])} ({best['change_pct_7d']:+.1f}% vs 7d).{delta_text}"
        )
        if worst["asset"] != best["asset"]:
            matters.append(
                f"{worst['asset']} was the biggest weekly drag at {format_price(worst['price'])} ({worst['change_pct_7d']:+.1f}% vs 7d)."
            )
        if snapshot["week_change_value"]:
            matters.append(f"Week over week, your book moved about {format_price(snapshot['week_change_value'])}.")
    if snapshot["cash_ratio"] >= 0.2:
        matters.append(f"You still have about {snapshot['cash_ratio'] * 100:.0f}% in cash-like balances, which leaves room to act without selling.")
    for insight in watch_insights[:1]:
        if insight.get("change_pct_7d") is not None:
            prior = insight.get("change_pct_prior_7d")
            compare = f" versus {prior:+.1f}% last week" if prior is not None else ""
            matters.append(f"{insight['asset']} is the watchlist name with the strongest weekly follow-through at {insight['change_pct_7d']:+.1f}% vs 7d{compare}.")

    for story in news_items[:2]:
        news.append(f"{story['asset']}: {story['title']} {story['why_this_matters']}")
        if "price recap" in story["why_this_matters"].lower() or "noise" in story["why_this_matters"].lower():
            ignore.append(f"{story['asset']}: weekly recap headlines are less useful unless they point to a catalyst you still believe in.")

    if not ignore:
        ignore.append("Ignore weekly leaderboard chatter that does not change your thesis or your position sizing.")

    return {
        "what_matters": dedupe_lines(matters)[:5],
        "news_that_matters": dedupe_lines(news)[:2],
        "probably_ignore": dedupe_lines(ignore)[:2],
    }


def render_text(payload: Dict[str, Any]) -> str:
    lines = [f"**{payload['title']}**", "", payload["headline"], ""]
    if payload.get("first_run_hook"):
        lines.append(f"_Heads up: {payload['first_run_hook']}_")
        lines.append("")
    if payload.get("limited_mode"):
        lines.append("_Quick note: account credentials were not available, so this version is market-only._")
        lines.append("")

    sections = payload.get("sections", {})
    if sections.get("what_matters"):
        lines.append("**What jumps out**")
        for item in sections["what_matters"]:
            lines.append(f"- {item}")
        lines.append("")
    if sections.get("news_that_matters"):
        lines.append("**Why it matters today**")
        for item in sections["news_that_matters"]:
            lines.append(f"- {item}")
        lines.append("")
    if sections.get("probably_ignore"):
        lines.append("**Ignore this noise**")
        for item in sections["probably_ignore"]:
            lines.append(f"- {item}")
        lines.append("")
    if not sections:
        for item in payload.get("highlights", []):
            label = item.get("asset") or item.get("symbol") or item.get("type", "highlight")
            lines.append(f"- {label}: {item['summary']}")
        lines.append("")
    if payload.get("risk_note"):
        lines.append(f"**One risk to watch**  {payload['risk_note']}")
        lines.append("")
    if payload.get("suggested_action"):
        lines.append(f"**What I would do next**  {payload['suggested_action']['label']}")
        lines.append("")
    if payload.get("decision_frame"):
        frame = payload["decision_frame"]
        lines.append(f"**{frame['title']}**")
        lines.append(f"- Bull case: {frame['bull_case']}")
        lines.append(f"- Case for patience: {frame['patient_case']}")
        lines.append("")
    if payload.get("version"):
        lines.append(f"_Skill v{payload['version']}. If you installed from GitHub or with `--copy`, run `npx skills update` to refresh._")
        lines.append("")
    lines.append("_Market information only. Not financial advice._")
    return trim_lines("\n".join(lines))


def build_brief(args: argparse.Namespace, config: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    watchlist = normalize_watchlist(args.watchlist, config)
    quote_assets = parse_quote_assets(args.quote_assets, config)
    recent_days = int(config.get("recent_days", args.recent_days))
    alert_threshold_pct = float(config.get("alert_threshold_pct", args.alert_threshold_pct))
    news_limit = int(config.get("news_limit", args.news_limit))

    exchange_info = public_get("/api/v3/exchangeInfo")
    by_symbol, by_base = build_symbol_maps(exchange_info)
    tickers = ticker_map()
    mover_list = top_market_movers(tickers, quote_assets, args.limit)

    api_key, secret_key, credentials_source = load_secret_from_env_or_files()
    context = fetch_account_context(api_key, secret_key, watchlist, by_base, quote_assets, recent_days)
    context["credentials_source"] = credentials_source

    snapshot = portfolio_snapshot(context["balances"], by_base, tickers, quote_assets)
    trade_summary = recent_trade_summary(context["recent_trades"], by_symbol)
    watch_insights = find_watchlist_insights(watchlist, by_base, tickers, quote_assets)
    news_items = fetch_news_context(snapshot, trade_summary, watchlist, news_limit)

    watch_symbols = [item["symbol"] for item in watch_insights if item.get("symbol")]
    tone = market_tone(tickers, watch_symbols)
    limited_mode = context["limited_mode"]
    title_map = {
        "daily_brief": "Binance.US Morning Brief",
        "watchlist_brief": "Your Watchlist Brief",
        "opportunity_alert": "Opportunity Alert",
        "funding_nudge": "Funding Nudge",
        "weekly_reset": "Weekly Reset",
        "portfolio_brief": "Your Portfolio Brief",
    }

    highlights = compose_personalized_highlights(snapshot, trade_summary, watch_insights, news_items, args.limit)
    if limited_mode and not highlights:
        for mover in mover_list[: min(3, args.limit)]:
            highlights.append({"type": "market_mover", "symbol": mover["symbol"], "summary": f"{mover['symbol']} is {mover['change_pct']:+.1f}% with strong quote volume."})

    risk_note = None
    if snapshot["concentration"] >= 0.6 and snapshot["top_asset"]:
        risk_note = f"Your account is heavily concentrated in {snapshot['top_asset']['asset']}."
    elif trade_summary:
        asset, event = next(iter(trade_summary.items()))
        symbol = event["symbol"]
        change = safe_float(tickers.get(symbol, {}).get("priceChangePercent"))
        direction = "down" if change < 0 else "up"
        risk_note = f"{asset} is {direction} {abs(change):.1f}% since your recent trade signal was recorded."

    latest_deposit_age = latest_fiat_deposit_age_days(context["fiat_deposits"])
    suggested_action = choose_suggested_action(snapshot, trade_summary, watch_insights, latest_deposit_age, limited_mode)
    hook = first_run_hook(snapshot, watch_insights, state, limited_mode)

    if args.mode == "watchlist_brief":
        headline = f"Your watchlist is {tone.replace('_', ' ')}, with {watch_insights[0]['asset']} leading." if watch_insights else "Your watchlist has no active configured insights."
        suggested_action = {"label": "Open Binance.US and decide whether your watchlist leader deserves a spot in the portfolio.", "intent": "open_watchlist", "params": {"url": "https://www.binance.us/"}}
        highlights = watch_insights[: args.limit] or highlights
    elif args.mode == "opportunity_alert":
        triggered = next((item for item in watch_insights if abs(item["change_pct"]) >= alert_threshold_pct or (item["volume_ratio"] and item["volume_ratio"] >= 1.8)), None)
        if triggered:
            headline = f"{triggered['asset']} just forced its way onto the screen at {format_price(triggered['price'])}."
            highlights = [{"type": "triggered_asset", "asset": triggered["asset"], "symbol": triggered["symbol"], "summary": triggered["summary"]}]
            for story in news_items:
                if story["asset"] == triggered["asset"]:
                    highlights.append({"type": "news_context", "asset": story["asset"], "summary": f"Recent headline: {story['title']} {story['why_this_matters']}", "link": story["link"]})
                    break
            suggested_action = {
                "label": f"{triggered['asset']} crossed your attention threshold. Open Binance.US (https://www.binance.us/) and check your limit orders now.",
                "intent": "open_asset",
                "params": {"asset": triggered["asset"], "url": "https://www.binance.us/"},
            }
        else:
            headline = "No owned, watched, or recently traded asset crossed the configured alert threshold."
            suggested_action = {"label": "Review watchlist thresholds", "intent": "open_watchlist_settings"}
    elif args.mode == "funding_nudge":
        dip_candidate = next((item for item in watch_insights if item["change_pct"] <= -5 or (item.get("change_pct_7d") or 0.0) <= -8), None)
        if latest_deposit_age is None:
            headline = "You do not appear to have a recent completed fiat deposit."
        else:
            headline = f"Your last completed fiat deposit appears to be about {latest_deposit_age} day(s) ago."
        if snapshot["cash_ratio"] >= 0.2:
            highlights.insert(0, {"type": "cash_status", "summary": f"You already have about {snapshot['cash_ratio'] * 100:.0f}% of your account in cash or cash-like balances."})
            suggested_action = {"label": f"You already have cash ready. Open Binance.US and decide whether to put it to work.", "intent": "open_convert_or_spot", "params": {"url": "https://www.binance.us/"}}
        elif dip_candidate and (latest_deposit_age is None or latest_deposit_age >= 14):
            headline = f"You have not deposited in {latest_deposit_age or 14}+ days, and {dip_candidate['asset']} is down {dip_candidate['change_pct']:+.1f}% today."
            highlights.insert(0, {"type": "dip_nudge", "summary": f"{dip_candidate['asset']} is off {dip_candidate['change_pct']:+.1f}% today and {dip_candidate.get('change_pct_7d', 0.0):+.1f}% over 7d. This is when being ready matters."})
            suggested_action = {
                "label": f"Open Binance.US (https://www.binance.us/) and decide whether this dip deserves fresh capital.",
                "intent": "open_funding",
                "params": {"url": "https://www.binance.us/", "asset": dip_candidate["asset"]},
            }
        else:
            suggested_action = {"label": "Open Binance.US and review funding options before the next setup appears.", "intent": "open_funding", "params": {"url": "https://www.binance.us/"}}
    elif args.mode == "weekly_reset":
        if snapshot["top_asset"]:
            headline = f"Over the last week, your account moved about {snapshot['week_change_pct']:+.1f}%, with {snapshot['top_asset']['asset']} still setting the tone."
        elif watch_insights and watch_insights[0].get("change_pct_7d") is not None:
            headline = f"Over the last week, {watch_insights[0]['asset']} had the strongest follow-through in your watchlist at {watch_insights[0]['change_pct_7d']:+.1f}% vs 7d."
        else:
            best = mover_list[0]["symbol"] if mover_list else "BTCUSD"
            headline = f"Weekly reset: {best} led recent momentum while the broader tape stayed {tone.replace('_', ' ')}."
        if snapshot["cash_ratio"] >= 0.2 and watch_insights:
            suggested_action = {
                "label": f"You still have {snapshot['cash_ratio'] * 100:.0f}% cash. Revisit {watch_insights[0]['asset']} before the next week starts.",
                "intent": "open_asset",
                "params": {"asset": watch_insights[0]["asset"]},
            }
        elif watch_insights and watch_insights[0].get("change_pct_7d") is not None:
            suggested_action = {
                "label": f"Recheck whether {watch_insights[0]['asset']} still deserves attention after a {watch_insights[0]['change_pct_7d']:+.1f}% week.",
                "intent": "open_asset",
                "params": {"asset": watch_insights[0]["asset"]},
            }
        else:
            suggested_action = {"label": "Open the weekly recap and resize any stale positions.", "intent": "open_market_summary"}
    elif args.mode == "portfolio_brief":
        if snapshot["top_asset"]:
            headline = f"{snapshot['top_asset']['asset']} is your largest position, and cash represents about {snapshot['cash_ratio'] * 100:.0f}% of your account."
        else:
            headline = "Portfolio brief unavailable because no non-zero balances were found."
        suggested_action = {"label": "Open Binance.US and make one deliberate portfolio decision now, not later.", "intent": "open_portfolio_actions", "params": {"url": "https://www.binance.us/"}}
    else:
        headline = choose_headline(snapshot, trade_summary, watch_insights, tone, limited_mode)

    decision_frame = build_decision_frame(suggested_action, snapshot, watch_insights, latest_deposit_age, news_items)

    personalization = {"based_on": [], "user_angle": None}
    if context["balances"]:
        personalization["based_on"].append("balances")
    if context["recent_trades"]:
        personalization["based_on"].append("recent_trades")
    if watchlist:
        personalization["based_on"].append("watchlist")
    if snapshot["cash_ratio"] >= 0.2:
        personalization["based_on"].append("idle_cash")
    if snapshot["top_asset"]:
        personalization["user_angle"] = f"{snapshot['top_asset']['asset']} is currently your largest position."
    elif limited_mode:
        personalization["user_angle"] = LIMITED_MODE_REASON

    sections = build_portfolio_sections(snapshot, trade_summary, watch_insights, news_items)
    if args.mode == "watchlist_brief":
        sections["what_matters"] = [item["summary"] for item in watch_insights[:4]]
    elif args.mode == "opportunity_alert" and highlights:
        sections["what_matters"] = [item["summary"] for item in highlights if item["type"] != "news_context"][:2]
        sections["news_that_matters"] = [item["summary"] for item in highlights if item["type"] == "news_context"][:1]
    elif args.mode == "weekly_reset":
        sections = weekly_reset_sections(snapshot, watch_insights, news_items)

    return {
        "mode": args.mode,
        "generated_at": iso_now(),
        "version": SKILL_VERSION,
        "title": title_map[args.mode],
        "headline": headline,
        "market_tone": tone,
        "limited_mode": limited_mode,
        "credentials_source": credentials_source,
        "personalization": personalization,
        "portfolio_summary": {
            "total_estimated_value": round(snapshot["total_value"], 2),
            "cash_estimated_value": round(snapshot["cash_value"], 2),
            "cash_ratio": round(snapshot["cash_ratio"], 4),
            "largest_position": snapshot["top_asset"]["asset"] if snapshot["top_asset"] else None,
            "concentration_ratio": round(snapshot["concentration"], 4),
            "week_change_pct": round(snapshot["week_change_pct"], 2),
        },
        "sections": sections,
        "highlights": highlights[: args.limit],
        "first_run_hook": hook,
        "risk_note": risk_note,
        "suggested_action": suggested_action,
        "decision_frame": decision_frame,
        "watchlist": watchlist,
        "news": news_items,
        "disclaimer": "Market information only. Not financial advice.",
    }


def main() -> int:
    args = parse_args()
    if args.command == "init-config":
        path = Path(os.path.expanduser(getattr(args, "config", str(DEFAULT_CONFIG_PATH))))
        write_default_config(path, force=args.force)
        print(f"Created config: {path}")
        return 0

    config = load_config(args.config)
    state = load_state()
    payload = build_brief(args, config, state)
    rendered = render_text(payload)
    state["has_run"] = True
    state["last_generated_at"] = payload["generated_at"]
    state["last_mode"] = payload["mode"]
    state["last_watchlist"] = payload.get("watchlist", [])
    save_state(state)

    if args.format == "json":
        print(json.dumps(payload, indent=2))
    elif args.format == "text":
        print(rendered)
    else:
        print(json.dumps(payload, indent=2))
        print("\n---\n")
        print(rendered)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BinanceUSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
