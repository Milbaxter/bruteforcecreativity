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

        # Try sources in order: fredapi (if key), FRED CSV (no key!), yfinance fallback
        data = pd.Series(dtype=float)

        # Source 1: fredapi with API key
        if self.fred_api_key:
            try:
                from fredapi import Fred
                fred = Fred(api_key=self.fred_api_key)
                data = fred.get_series(series_id, observation_start=start, observation_end=end)
                logger.info("FRED %s: %d observations via API key", series_id, len(data))
            except Exception as e:
                logger.warning("fredapi for %s failed: %s", series_id, e)

        # Source 2: FRED CSV endpoint (NO API KEY NEEDED)
        if data.empty:
            try:
                csv_url = (
                    f"https://fred.stlouisfed.org/graph/fredgraph.csv"
                    f"?id={series_id}&cosd={start}&coed={end}"
                )
                df = pd.read_csv(csv_url, parse_dates=["observation_date"], index_col="observation_date")
                col = df.columns[0]
                data = pd.to_numeric(df[col], errors="coerce").dropna()
                data.index.name = None
                logger.info("FRED %s: %d observations via CSV (no key needed)", series_id, len(data))
            except Exception as e:
                logger.warning("FRED CSV for %s failed: %s", series_id, e)

        # Source 3: yfinance fallback for a few common series
        if data.empty:
            fred_to_yf = {
                "DFF": "^IRX", "DTB3": "^IRX", "DGS10": "^TNX",
                "DGS2": "^FVX", "VIXCLS": "^VIX",
            }
            yf_ticker = fred_to_yf.get(series_id)
            if yf_ticker:
                try:
                    df = yf.download(yf_ticker, start=start, end=end, progress=False)
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    data = df["Close"].dropna()
                    logger.info("FRED %s: yfinance %s fallback (%d rows)", series_id, yf_ticker, len(data))
                except Exception as e:
                    logger.warning("yfinance fallback for %s failed: %s", series_id, e)

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

    # ── CoinGecko (crypto market data) ──────────────────────────────

    def get_coingecko_market_data(
        self, vs_currency: str = "usd", count: int = 100
    ) -> pd.DataFrame:
        """
        Fetch top crypto market data from CoinGecko (free, no key).
        Returns: coin, symbol, price, volume_24h, market_cap, change_24h, change_7d.
        """
        key = _cache_key("coingecko_markets", vs=vs_currency, count=count)
        cached = _load_cache(key, max_age_hours=6)
        if cached is not None:
            return cached

        try:
            url = "https://api.coingecko.com/api/v3/coins/markets"
            params = {
                "vs_currency": vs_currency,
                "order": "market_cap_desc",
                "per_page": min(count, 250),
                "page": 1,
                "sparkline": False,
                "price_change_percentage": "7d",
            }
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            rows = []
            for coin in data:
                rows.append({
                    "coin": coin.get("id", ""),
                    "symbol": coin.get("symbol", "").upper(),
                    "price": coin.get("current_price"),
                    "volume_24h": coin.get("total_volume"),
                    "market_cap": coin.get("market_cap"),
                    "change_24h_pct": coin.get("price_change_percentage_24h"),
                    "change_7d_pct": coin.get("price_change_percentage_7d_in_currency"),
                })
            df = pd.DataFrame(rows)
            logger.info("CoinGecko: fetched %d coins", len(df))
        except Exception as e:
            logger.warning("CoinGecko market data failed: %s", e)
            df = pd.DataFrame()

        _save_cache(key, df)
        return df

    def get_coingecko_history(
        self, coin_id: str, days: int = 365, vs_currency: str = "usd"
    ) -> pd.DataFrame:
        """
        Fetch historical daily prices for a crypto coin from CoinGecko.
        coin_id: e.g. 'bitcoin', 'ethereum', 'solana' (CoinGecko slug, not ticker)
        Returns DataFrame with date, price, volume, market_cap.
        """
        key = _cache_key("coingecko_hist", coin=coin_id, days=days, vs=vs_currency)
        cached = _load_cache(key, self.cache_hours)
        if cached is not None:
            return cached

        try:
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
            params = {"vs_currency": vs_currency, "days": days, "interval": "daily"}
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            prices = data.get("prices", [])
            volumes = data.get("total_volumes", [])
            mcaps = data.get("market_caps", [])

            df = pd.DataFrame(prices, columns=["timestamp", "price"])
            df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
            df = df.set_index("date").drop(columns=["timestamp"])

            if volumes:
                vol_df = pd.DataFrame(volumes, columns=["timestamp", "volume"])
                vol_df["date"] = pd.to_datetime(vol_df["timestamp"], unit="ms")
                df["volume"] = vol_df.set_index("date")["volume"]
            if mcaps:
                mc_df = pd.DataFrame(mcaps, columns=["timestamp", "market_cap"])
                mc_df["date"] = pd.to_datetime(mc_df["timestamp"], unit="ms")
                df["market_cap"] = mc_df.set_index("date")["market_cap"]

            logger.info("CoinGecko history for %s: %d days", coin_id, len(df))
        except Exception as e:
            logger.warning("CoinGecko history for %s failed: %s", coin_id, e)
            df = pd.DataFrame()

        _save_cache(key, df)
        return df

    # ── Earnings Calendar ────────────────────────────────────────────

    def get_earnings_calendar(self, tickers: list[str] | str) -> pd.DataFrame:
        """
        Fetch earnings dates and surprise data for given tickers via yfinance.
        Returns: ticker, date, eps_estimate, eps_actual, surprise_pct.
        """
        if isinstance(tickers, str):
            tickers = [tickers]

        key = _cache_key("earnings", tickers=sorted(tickers))
        cached = _load_cache(key, self.cache_hours)
        if cached is not None:
            return cached

        all_rows = []
        for ticker in tickers:
            try:
                t = yf.Ticker(ticker)
                cal = t.earnings_dates
                if cal is not None and not cal.empty:
                    for idx, row in cal.iterrows():
                        all_rows.append({
                            "ticker": ticker,
                            "date": idx,
                            "eps_estimate": row.get("EPS Estimate"),
                            "eps_actual": row.get("Reported EPS"),
                            "surprise_pct": row.get("Surprise(%)"),
                        })
            except Exception as e:
                logger.debug("Earnings for %s failed: %s", ticker, e)

        df = pd.DataFrame(all_rows) if all_rows else pd.DataFrame()
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            logger.info("Earnings calendar: %d entries across %d tickers", len(df), len(tickers))

        _save_cache(key, df)
        return df

    # ── Economic Calendar (FOMC, CPI, Jobs) ──────────────────────────

    def get_economic_calendar(self) -> pd.DataFrame:
        """
        Return key economic event dates for the backtest period.
        Includes FOMC meetings, CPI releases, jobs reports.
        These dates are public and fixed — we hardcode recent ones
        and supplement with scraping.
        """
        key = _cache_key("econ_calendar")
        cached = _load_cache(key, max_age_hours=168)  # Cache for a week
        if cached is not None:
            return cached

        # FOMC meeting dates (scheduled, public knowledge)
        # These are the announcement dates for 2025-2026
        fomc_dates = [
            "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
            "2025-07-30", "2025-09-17", "2025-11-05", "2025-12-17",
            "2026-01-28", "2026-03-18",
        ]

        # CPI release dates (typically mid-month)
        cpi_dates = [
            "2025-01-15", "2025-02-12", "2025-03-12", "2025-04-10",
            "2025-05-13", "2025-06-11", "2025-07-11", "2025-08-12",
            "2025-09-10", "2025-10-14", "2025-11-12", "2025-12-10",
            "2026-01-14", "2026-02-12", "2026-03-11",
        ]

        # Jobs report (first Friday of month)
        jobs_dates = [
            "2025-01-10", "2025-02-07", "2025-03-07", "2025-04-04",
            "2025-05-02", "2025-06-06", "2025-07-03", "2025-08-01",
            "2025-09-05", "2025-10-03", "2025-11-07", "2025-12-05",
            "2026-01-09", "2026-02-06", "2026-03-06",
        ]

        rows = []
        for d in fomc_dates:
            rows.append({"date": d, "event": "FOMC"})
        for d in cpi_dates:
            rows.append({"date": d, "event": "CPI"})
        for d in jobs_dates:
            rows.append({"date": d, "event": "JOBS"})

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        logger.info("Economic calendar: %d events", len(df))

        _save_cache(key, df)
        return df

    # ── Short Interest ───────────────────────────────────────────────

    def get_short_interest(self, tickers: list[str] | str) -> pd.DataFrame:
        """
        Fetch current short interest data for tickers via yfinance.
        Returns: ticker, short_pct_float, short_ratio, shares_short.
        """
        if isinstance(tickers, str):
            tickers = [tickers]

        key = _cache_key("short_interest", tickers=sorted(tickers))
        cached = _load_cache(key, self.cache_hours)
        if cached is not None:
            return cached

        rows = []
        for ticker in tickers:
            try:
                info = yf.Ticker(ticker).info
                rows.append({
                    "ticker": ticker,
                    "short_pct_float": info.get("shortPercentOfFloat"),
                    "short_ratio": info.get("shortRatio"),
                    "shares_short": info.get("sharesShort"),
                })
            except Exception as e:
                logger.debug("Short interest for %s failed: %s", ticker, e)

        df = pd.DataFrame(rows) if rows else pd.DataFrame()
        logger.info("Short interest: %d tickers", len(df))

        _save_cache(key, df)
        return df

    # ── Fear & Greed Proxy ───────────────────────────────────────────

    def get_fear_greed(
        self, start: str | None = None, end: str | None = None
    ) -> pd.Series:
        """
        Compute a daily Fear & Greed proxy score (0-100) from:
        - VIX level (inverted: high VIX = fear)
        - Market momentum (SPY 20-day vs 125-day MA)
        - Put/call proxy (VIX term structure)

        0 = extreme fear, 100 = extreme greed. Historical, backtestable.
        """
        key = _cache_key("fear_greed", start=start, end=end)
        cached = _load_cache(key, self.cache_hours)
        if cached is not None:
            return cached

        vix = self.get_vix(start=start, end=end).dropna()
        spy = self.get_prices("SPY", start=start, end=end)
        if isinstance(spy.columns, pd.MultiIndex):
            spy_close = spy[("Close", "SPY")]
        else:
            spy_close = spy["Close"]
        spy_close = spy_close.dropna()

        if vix.empty or spy_close.empty:
            return pd.Series(dtype=float)

        # VIX component: normalize 10-40 range to 100-0 (inverted)
        vix_score = ((40 - vix.clip(10, 40)) / 30 * 100).clip(0, 100)

        # Momentum component: SPY 20d MA vs 125d MA
        ma20 = spy_close.rolling(20).mean()
        ma125 = spy_close.rolling(125).mean()
        momentum = ((ma20 / ma125 - 1) * 1000).clip(-50, 50) + 50  # Center at 50

        # Combine (equal weight)
        common = vix_score.index.intersection(momentum.index)
        score = (vix_score.reindex(common) * 0.5 + momentum.reindex(common) * 0.5).dropna()
        score = score.clip(0, 100).round(1)
        logger.info("Fear/Greed proxy: %d days, current=%.1f", len(score),
                     score.iloc[-1] if not score.empty else 0)

        _save_cache(key, score)
        return score

    # ── Wikipedia Pageviews (public attention proxy) ────────────────

    def get_wikipedia_pageviews(
        self,
        article: str,
        start: str | None = None,
        end: str | None = None,
        granularity: str = "daily",
    ) -> pd.Series:
        """
        Fetch Wikipedia pageview counts for an article (public attention proxy).
        Uses Wikimedia REST API — free, no key, data back to July 2015.

        Args:
            article: Wikipedia article title (e.g. 'Tesla,_Inc.', 'Bitcoin', 'GameStop')
                     Use underscores for spaces, match exact Wikipedia title.
            start: start date 'YYYY-MM-DD' (default: 12 months ago)
            end: end date 'YYYY-MM-DD' (default: today)
            granularity: 'daily' or 'monthly'

        Returns:
            Series with date index and pageview counts.
        """
        if end is None:
            end = datetime.now().strftime("%Y-%m-%d")
        if start is None:
            start = (datetime.now() - timedelta(days=DEFAULT_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

        key = _cache_key("wiki_pageviews", article=article, start=start, end=end, gran=granularity)
        cached = _load_cache(key, self.cache_hours)
        if cached is not None:
            return cached

        try:
            start_fmt = start.replace("-", "") + "00"
            end_fmt = end.replace("-", "") + "00"
            url = (
                f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
                f"/en.wikipedia/all-access/all-agents/{article}/{granularity}/{start_fmt}/{end_fmt}"
            )
            resp = requests.get(url, headers={"User-Agent": "bruteforcecreativity/1.0"}, timeout=15)
            resp.raise_for_status()
            items = resp.json().get("items", [])

            dates = []
            views = []
            for item in items:
                ts = item["timestamp"]
                dates.append(pd.Timestamp(f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"))
                views.append(item["views"])

            data = pd.Series(views, index=dates, name=f"pageviews_{article}")
            logger.info("Wikipedia pageviews for %s: %d days", article, len(data))
        except Exception as e:
            logger.warning("Wikipedia pageviews for %s failed: %s", article, e)
            data = pd.Series(dtype=float)

        _save_cache(key, data)
        return data

    # ── Open-Meteo Weather (historical weather data) ─────────────────

    def get_weather_history(
        self,
        latitude: float,
        longitude: float,
        start: str | None = None,
        end: str | None = None,
        variables: list[str] | None = None,
    ) -> pd.DataFrame:
        """
        Fetch historical daily weather data from Open-Meteo (free, no key, data since 1940).

        Args:
            latitude: e.g. 40.71 (NYC), 29.76 (Houston), 41.88 (Chicago)
            longitude: e.g. -74.01 (NYC), -95.37 (Houston), -87.63 (Chicago)
            start: start date 'YYYY-MM-DD'
            end: end date 'YYYY-MM-DD'
            variables: daily weather variables to fetch. Defaults to
                       ['temperature_2m_max', 'temperature_2m_min', 'precipitation_sum',
                        'windspeed_10m_max', 'snowfall_sum']

        Returns:
            DataFrame with date index and weather variable columns.

        Common use cases for strategies:
            - Extreme cold/heat + energy stocks (XLE, UNG)
            - Hurricanes/storms + insurance stocks, utilities
            - Snowfall + retail/travel stocks
        """
        if end is None:
            end = datetime.now().strftime("%Y-%m-%d")
        if start is None:
            start = (datetime.now() - timedelta(days=DEFAULT_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
        if variables is None:
            variables = [
                "temperature_2m_max", "temperature_2m_min",
                "precipitation_sum", "windspeed_10m_max", "snowfall_sum",
            ]

        key = _cache_key("weather", lat=latitude, lon=longitude, start=start, end=end, vars=variables)
        cached = _load_cache(key, self.cache_hours)
        if cached is not None:
            return cached

        try:
            url = "https://archive-api.open-meteo.com/v1/archive"
            params = {
                "latitude": latitude,
                "longitude": longitude,
                "start_date": start,
                "end_date": end,
                "daily": ",".join(variables),
                "timezone": "America/New_York",
            }
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            daily = resp.json().get("daily", {})

            dates = daily.pop("time", [])
            df = pd.DataFrame(daily, index=pd.to_datetime(dates))
            df.index.name = None
            logger.info("Weather data (%.2f, %.2f): %d days, %d vars", latitude, longitude, len(df), len(df.columns))
        except Exception as e:
            logger.warning("Open-Meteo weather fetch failed: %s", e)
            df = pd.DataFrame()

        _save_cache(key, df)
        return df

    # ── Crypto Fear & Greed Index ────────────────────────────────────

    def get_crypto_fear_greed(self, days: int = 365) -> pd.Series:
        """
        Fetch the Crypto Fear & Greed Index from alternative.me (free, no key, daily since 2018).
        Score 0-100: 0 = Extreme Fear, 100 = Extreme Greed.

        Great for contrarian crypto entries: buy when crypto market is in extreme fear.
        """
        key = _cache_key("crypto_fng", days=days)
        cached = _load_cache(key, self.cache_hours)
        if cached is not None:
            return cached

        try:
            url = f"https://api.alternative.me/fng/?limit={days}&format=json"
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            items = resp.json().get("data", [])

            dates = []
            values = []
            for item in items:
                dates.append(pd.Timestamp.fromtimestamp(int(item["timestamp"])))
                values.append(int(item["value"]))

            data = pd.Series(values, index=dates, name="crypto_fear_greed")
            data = data.sort_index()
            logger.info("Crypto Fear & Greed: %d days, current=%d", len(data), data.iloc[-1] if not data.empty else 0)
        except Exception as e:
            logger.warning("Crypto Fear & Greed fetch failed: %s", e)
            data = pd.Series(dtype=float)

        _save_cache(key, data)
        return data

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

        print("  [1/10] SPY benchmark...")
        fetcher.get_spy_benchmark()

        print("  [2/10] VIX...")
        fetcher.get_vix()

        print("  [3/10] Major ETFs & commodities...")
        tickers = [
            "SPY", "QQQ", "IWM",                    # Indices
            "XLF", "XLE", "XLV", "XLK", "XLI",      # Sectors
            "XLP", "XLU", "XLB", "XLRE",
            "GLD", "SLV", "USO", "UNG", "WEAT",      # Commodities
            "TLT", "IEF", "HYG",                     # Bonds
            "BTC-USD", "ETH-USD", "SOL-USD",          # Crypto
            "EURUSD=X", "GBPUSD=X",                   # Forex
        ]
        fetcher.get_prices(tickers)

        print("  [4/10] FRED macro data...")
        for series in ["DFF", "DGS10", "DTB3", "VIXCLS"]:
            try:
                fetcher.get_fred_series(series)
                print(f"    {series} OK")
            except Exception as e:
                print(f"    {series} FAILED: {e}")

        print("  [5/10] Congressional trades...")
        try:
            df = fetcher.get_congressional_trades()
            print(f"    OK ({len(df)} trades)")
        except Exception as e:
            print(f"    FAILED: {e}")

        print("  [6/10] Google Trends...")
        try:
            fetcher.get_google_trends(["stock market", "recession", "bitcoin"])
            print("    OK")
        except Exception as e:
            print(f"    FAILED: {e}")

        print("  [7/10] CoinGecko top 100 crypto...")
        try:
            df = fetcher.get_coingecko_market_data()
            print(f"    OK ({len(df)} coins)")
        except Exception as e:
            print(f"    FAILED: {e}")

        print("  [8/10] Economic calendar...")
        try:
            df = fetcher.get_economic_calendar()
            print(f"    OK ({len(df)} events)")
        except Exception as e:
            print(f"    FAILED: {e}")

        print("  [9/10] Fear & Greed proxy...")
        try:
            s = fetcher.get_fear_greed()
            print(f"    OK ({len(s)} days, current={s.iloc[-1]:.1f})")
        except Exception as e:
            print(f"    FAILED: {e}")

        print("  [10/13] Short interest (top ETFs)...")
        try:
            df = fetcher.get_short_interest(["GME", "AMC", "TSLA", "AAPL", "NVDA"])
            print(f"    OK ({len(df)} tickers)")
        except Exception as e:
            print(f"    FAILED: {e}")

        print("  [11/13] Wikipedia pageviews...")
        try:
            for article in ["Tesla,_Inc.", "Bitcoin", "GameStop"]:
                s = fetcher.get_wikipedia_pageviews(article)
                print(f"    {article}: {len(s)} days")
        except Exception as e:
            print(f"    FAILED: {e}")

        print("  [12/13] Weather history (Houston for energy)...")
        try:
            df = fetcher.get_weather_history(29.76, -95.37)
            print(f"    OK ({len(df)} days, {len(df.columns)} vars)")
        except Exception as e:
            print(f"    FAILED: {e}")

        print("  [13/13] Crypto Fear & Greed Index...")
        try:
            s = fetcher.get_crypto_fear_greed()
            print(f"    OK ({len(s)} days, current={s.iloc[-1]})")
        except Exception as e:
            print(f"    FAILED: {e}")

        print(f"\nCache populated at {CACHE_DIR}")
    else:
        print(f"Usage: uv run fetch_data.py --refresh")
        print(f"Cache dir: {CACHE_DIR}")
