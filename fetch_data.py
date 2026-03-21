"""
Data fetching utilities for bruteforcecreativity.
This is infrastructure — the autonomous agent should NOT modify this file.

Provides a DataFetcher class that wraps multiple data sources with caching.
All data is cached to ~/.cache/bruteforcecreativity/ to avoid redundant API calls.
"""

import logging
import os
import json
import hashlib
import pickle
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("bruteforce.data")

CACHE_DIR = Path.home() / ".cache" / "bruteforcecreativity"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Default backtest window: trailing 12 months
DEFAULT_LOOKBACK_DAYS = 365


def _cache_key(prefix: str, **kwargs) -> str:
    """Generate a deterministic cache key from arguments."""
    raw = json.dumps(kwargs, sort_keys=True, default=str)
    h = hashlib.md5(raw.encode()).hexdigest()[:12]
    return f"{prefix}_{h}"


def _load_cache(key: str, max_age_hours: int = 24):
    """Load from cache if exists and not expired."""
    path = CACHE_DIR / f"{key}.pkl"
    if path.exists():
        age = datetime.now().timestamp() - path.stat().st_mtime
        if age < max_age_hours * 3600:
            logger.debug("Cache HIT: %s (age %.0fs)", key, age)
            with open(path, "rb") as f:
                return pickle.load(f)
        else:
            logger.debug("Cache EXPIRED: %s (age %.0fs > %ds)", key, age, max_age_hours * 3600)
    return None


def _save_cache(key: str, data):
    """Save data to cache."""
    path = CACHE_DIR / f"{key}.pkl"
    with open(path, "wb") as f:
        pickle.dump(data, f)
    logger.debug("Cache SAVE: %s", key)


class DataFetcher:
    """
    Unified data fetcher with caching. Strategies receive an instance of this
    and use it to pull whatever data they need.
    """

    def __init__(self, cache_hours: int = 24):
        self.cache_hours = cache_hours
        self.fred_api_key = os.getenv("FRED_API_KEY")

    # ── Core Market Data ─────────────────────────────────────────────

    def get_prices(
        self,
        tickers: list[str] | str,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """
        Fetch OHLCV price data via yfinance.

        Args:
            tickers: single ticker or list of tickers
            start: start date (default: 12 months ago)
            end: end date (default: today)
            interval: '1d', '1h', '5m', etc.

        Returns:
            DataFrame with MultiIndex columns (ticker, OHLCV) if multiple tickers,
            or simple OHLCV columns if single ticker.
        """
        if isinstance(tickers, str):
            tickers = [tickers]

        if end is None:
            end = datetime.now().strftime("%Y-%m-%d")
        if start is None:
            start = (datetime.now() - timedelta(days=DEFAULT_LOOKBACK_DAYS)).strftime(
                "%Y-%m-%d"
            )

        key = _cache_key("prices", tickers=tickers, start=start, end=end, interval=interval)
        cached = _load_cache(key, self.cache_hours)
        if cached is not None:
            return cached

        df = yf.download(tickers, start=start, end=end, interval=interval, progress=False)

        # Flatten multi-level columns for single ticker
        if len(tickers) == 1 and isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        _save_cache(key, df)
        return df

    def get_fundamentals(self, ticker: str) -> dict:
        """Fetch fundamental data (PE, market cap, sector, etc.) for a ticker."""
        key = _cache_key("fundamentals", ticker=ticker)
        cached = _load_cache(key, self.cache_hours)
        if cached is not None:
            return cached

        info = yf.Ticker(ticker).info
        _save_cache(key, info)
        return info

    def get_options_chain(self, ticker: str, expiry: str | None = None) -> dict:
        """Fetch options chain data. Returns dict with 'calls' and 'puts' DataFrames."""
        key = _cache_key("options", ticker=ticker, expiry=expiry)
        cached = _load_cache(key, self.cache_hours)
        if cached is not None:
            return cached

        t = yf.Ticker(ticker)
        if expiry is None:
            expiry = t.options[0] if t.options else None
        if expiry is None:
            return {"calls": pd.DataFrame(), "puts": pd.DataFrame()}

        chain = t.option_chain(expiry)
        result = {"calls": chain.calls, "puts": chain.puts, "expiry": expiry}
        _save_cache(key, result)
        return result

    # ── FRED Macroeconomic Data ──────────────────────────────────────

    def get_fred_series(
        self,
        series_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.Series:
        """
        Fetch a FRED time series (e.g. 'DFF' for fed funds rate, 'CPIAUCSL' for CPI).

        Common series IDs:
            DFF     - Federal funds effective rate
            DGS10   - 10-year Treasury yield
            CPIAUCSL - Consumer Price Index
            UNRATE  - Unemployment rate
            GDP     - Gross Domestic Product
            VIXCLS  - VIX close
            T10Y2Y  - 10Y-2Y Treasury spread
            BAMLH0A0HYM2 - High yield spread
        """
        if end is None:
            end = datetime.now().strftime("%Y-%m-%d")
        if start is None:
            start = (datetime.now() - timedelta(days=DEFAULT_LOOKBACK_DAYS)).strftime(
                "%Y-%m-%d"
            )

        key = _cache_key("fred", series_id=series_id, start=start, end=end)
        cached = _load_cache(key, self.cache_hours)
        if cached is not None:
            return cached

        if self.fred_api_key:
            from fredapi import Fred

            fred = Fred(api_key=self.fred_api_key)
            data = fred.get_series(series_id, observation_start=start, observation_end=end)
            logger.info("FRED %s: %d observations via API key", series_id, len(data))
        else:
            # No API key — try yfinance as fallback for common series
            # FRED DEMO_KEY does not work; a real key is needed for direct FRED access
            logger.warning("No FRED_API_KEY set. Using yfinance fallback for %s. "
                          "Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html",
                          series_id)

            # Map common FRED series to yfinance tickers
            fred_to_yf = {
                "DFF": "^IRX",        # 13-week T-bill as proxy for fed funds
                "DTB3": "^IRX",       # 3-month T-bill rate
                "DGS10": "^TNX",      # 10-year Treasury yield
                "DGS2": "^FVX",       # 5-year Treasury as proxy for 2-year
                "VIXCLS": "^VIX",     # VIX
            }

            yf_ticker = fred_to_yf.get(series_id)
            if yf_ticker:
                try:
                    df = yf.download(yf_ticker, start=start, end=end, progress=False)
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    data = df["Close"].dropna()
                    logger.info("FRED %s: used yfinance %s fallback (%d rows)",
                               series_id, yf_ticker, len(data))
                except Exception as e:
                    logger.warning("yfinance fallback for %s failed: %s", series_id, e)
                    data = pd.Series(dtype=float)
            else:
                logger.warning("No yfinance fallback for FRED series %s — returning empty. "
                              "Set FRED_API_KEY in .env for full macro data access.", series_id)
                data = pd.Series(dtype=float)

        _save_cache(key, data)
        return data

    # ── Google Trends ────────────────────────────────────────────────

    def get_google_trends(
        self,
        keywords: list[str],
        timeframe: str = "today 12-m",
        geo: str = "",
    ) -> pd.DataFrame:
        """
        Fetch Google Trends interest-over-time data.

        Args:
            keywords: up to 5 search terms
            timeframe: e.g. 'today 12-m', 'today 3-m', '2024-01-01 2024-12-31'
            geo: country code, e.g. 'US' (empty = worldwide)
        """
        key = _cache_key("gtrends", keywords=keywords, timeframe=timeframe, geo=geo)
        cached = _load_cache(key, self.cache_hours)
        if cached is not None:
            return cached

        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="en-US", tz=360)
        pytrends.build_payload(keywords, cat=0, timeframe=timeframe, geo=geo)
        data = pytrends.interest_over_time()
        if "isPartial" in data.columns:
            data = data.drop(columns=["isPartial"])

        _save_cache(key, data)
        return data

    # ── Congressional Trading ────────────────────────────────────────

    def get_congressional_trades(self, days_back: int = 365) -> pd.DataFrame:
        """
        Fetch recent congressional stock trades from public APIs.
        Tries multiple sources in order of reliability.
        Returns DataFrame with columns: date, representative, ticker, type, amount.
        """
        key = _cache_key("congress", days_back=days_back)
        cached = _load_cache(key, self.cache_hours)
        if cached is not None:
            return cached

        df = pd.DataFrame()

        # Source 1: CapitolTrades HTML scraping (public, no key needed)
        try:
            logger.info("Fetching congressional trades from CapitolTrades...")
            from bs4 import BeautifulSoup
            import re

            # Scrape multiple pages
            all_rows = []
            for page in range(1, 6):  # First 5 pages
                url = f"https://www.capitoltrades.com/trades?page={page}"
                resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                table_rows = soup.select("tr")[1:]  # Skip header

                if not table_rows:
                    break

                for row in table_rows:
                    cells = row.find_all("td")
                    if len(cells) >= 8:
                        texts = [c.get_text(strip=True) for c in cells]
                        # Parse: Politician, Ticker, Published, Traded, Filed After, Owner, Type, Size
                        politician = texts[0]
                        asset_text = texts[1]
                        traded_date = texts[3]
                        trade_type = texts[6]
                        size = texts[7]

                        # Extract ticker from asset text (format: "Company NameTICKER:US")
                        ticker_match = re.search(r'([A-Z]{1,5}):[A-Z]{2}', asset_text)
                        ticker = ticker_match.group(1) if ticker_match else ""

                        # Parse date (format: "1 Mar2026")
                        date_match = re.search(r'(\d{1,2}\s+\w{3})(\d{4})', traded_date)
                        if date_match:
                            date_str = f"{date_match.group(1)} {date_match.group(2)}"
                        else:
                            date_str = traded_date

                        all_rows.append({
                            "date": date_str,
                            "representative": politician,
                            "ticker": ticker,
                            "type": trade_type,
                            "amount": size,
                        })

            if all_rows:
                df = pd.DataFrame(all_rows)
                df["date"] = pd.to_datetime(df["date"], format="mixed", errors="coerce")
                cutoff = datetime.now() - timedelta(days=days_back)
                df = df[df["date"] >= cutoff]
                df = df[df["ticker"] != ""]  # Drop entries with no ticker
                logger.info("Got %d congressional trades from CapitolTrades", len(df))
        except Exception as e:
            logger.warning("CapitolTrades scraping failed: %s", e)

        if df.empty:
            logger.warning("All congressional trade sources failed — returning empty DataFrame")

        _save_cache(key, df)
        return df

    # ── Insider Trading ──────────────────────────────────────────────

    def get_insider_trades(self, ticker: str | None = None) -> pd.DataFrame:
        """
        Fetch insider trading data from SEC EDGAR / OpenInsider.
        If ticker is None, returns recent cluster buys across all stocks.
        """
        key = _cache_key("insider", ticker=ticker or "all")
        cached = _load_cache(key, self.cache_hours)
        if cached is not None:
            return cached

        if ticker:
            url = f"http://openinsider.com/screener?s={ticker}&o=&pl=&ph=&st=0&lt=1&lk=&cnt=100&oc=&sortcol=0&cnt=100&page=1"
        else:
            # Cluster buys in last 30 days
            url = "http://openinsider.com/screener?s=&o=&pl=&ph=&st=0&lt=1&lk=&cnt=100&oc=&sortcol=0&cnt=100&page=1"

        try:
            resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table", {"class": "tinytable"})
            if table:
                df = pd.read_html(str(table))[0]
            else:
                df = pd.DataFrame()
        except Exception:
            df = pd.DataFrame()

        _save_cache(key, df)
        return df

    # ── Fear & Greed / Sentiment ─────────────────────────────────────

    def get_vix(
        self, start: str | None = None, end: str | None = None
    ) -> pd.Series:
        """Fetch VIX (CBOE Volatility Index) historical data."""
        df = self.get_prices("^VIX", start=start, end=end)
        if "Close" in df.columns:
            return df["Close"]
        return pd.Series(dtype=float)

    # ── Crypto ───────────────────────────────────────────────────────

    def get_crypto_prices(
        self,
        symbols: list[str] | str,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """
        Fetch crypto prices via yfinance. Use Yahoo-format tickers like 'BTC-USD', 'ETH-USD'.
        """
        if isinstance(symbols, str):
            symbols = [symbols]
        return self.get_prices(symbols, start=start, end=end)

    # ── Polymarket ───────────────────────────────────────────────────

    def get_polymarket_markets(self, query: str = "", limit: int = 50) -> list[dict]:
        """
        Fetch active Polymarket markets.

        Args:
            query: search term (e.g. 'election', 'fed', 'recession')
            limit: max results

        Returns:
            List of market dicts with keys: id, question, slug, outcomes, prices, volume, etc.
        """
        key = _cache_key("polymarket", query=query, limit=limit)
        cached = _load_cache(key, max_age_hours=1)  # Short cache for prediction markets
        if cached is not None:
            return cached

        url = "https://gamma-api.polymarket.com/markets"
        params = {"limit": limit, "active": True, "closed": False}
        if query:
            params["tag"] = query

        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            markets = resp.json()
        except Exception:
            markets = []

        _save_cache(key, markets)
        return markets

    # ── Utility Methods ──────────────────────────────────────────────

    def get_risk_free_rate(self) -> float:
        """Get current risk-free rate (3-month T-bill rate)."""
        try:
            series = self.get_fred_series("DTB3")
            if not series.empty:
                rate = series.dropna().iloc[-1] / 100  # Convert from percent
                logger.info("Risk-free rate: %.4f (from DTB3)", rate)
                return rate
        except Exception as e:
            logger.warning("Failed to get DTB3: %s", e)

        # Direct yfinance fallback
        try:
            df = yf.download("^IRX", period="5d", progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if not df.empty and "Close" in df.columns:
                rate = df["Close"].dropna().iloc[-1] / 100
                logger.info("Risk-free rate: %.4f (from ^IRX yfinance)", rate)
                return rate
        except Exception as e:
            logger.warning("^IRX fallback failed: %s", e)

        logger.warning("Using hardcoded 5%% risk-free rate fallback")
        return 0.05

    def get_spy_benchmark(
        self, start: str | None = None, end: str | None = None
    ) -> pd.DataFrame:
        """Get SPY prices for the benchmark period."""
        return self.get_prices("SPY", start=start, end=end)


# ── CLI: Refresh the cache ───────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if "--refresh" in sys.argv:
        print("Refreshing data cache...")
        fetcher = DataFetcher(cache_hours=0)  # Force fresh fetch

        # Pre-fetch commonly needed data
        print("  Fetching SPY benchmark...")
        fetcher.get_spy_benchmark()

        print("  Fetching VIX...")
        fetcher.get_vix()

        print("  Fetching major ETFs...")
        etfs = ["SPY", "QQQ", "IWM", "XLF", "XLE", "XLV", "XLK", "XLI", "XLP", "XLU", "GLD", "TLT"]
        fetcher.get_prices(etfs)

        print("  Fetching FRED macro data...")
        for series in ["DFF", "DGS10", "CPIAUCSL", "UNRATE", "T10Y2Y", "VIXCLS"]:
            try:
                fetcher.get_fred_series(series)
                print(f"    {series} OK")
            except Exception as e:
                print(f"    {series} FAILED: {e}")

        print("  Fetching congressional trades...")
        try:
            fetcher.get_congressional_trades()
            print("    OK")
        except Exception as e:
            print(f"    FAILED: {e}")

        print("  Fetching Google Trends for market terms...")
        try:
            fetcher.get_google_trends(["stock market", "recession", "inflation"])
            print("    OK")
        except Exception as e:
            print(f"    FAILED: {e}")

        print(f"\nCache populated at {CACHE_DIR}")
    else:
        print(f"Usage: uv run fetch_data.py --refresh")
        print(f"Cache dir: {CACHE_DIR}")
