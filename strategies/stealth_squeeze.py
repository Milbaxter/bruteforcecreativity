"""
Stealth Squeeze — buy stocks with low attention + rising price + potential squeeze.

Thesis: When a stock's Wikipedia pageviews are declining/flat (low retail attention) but
the price is rising steadily, it's a "stealth rally" — institutional buying without retail
awareness. These rallies tend to accelerate when retail finally notices, and any short
interest adds fuel via forced covering.

Instead of looking at individual stocks (which requires knowing tickers in advance),
scan sector ETFs that represent heavily-shorted sectors. When a sector ETF shows:
1. Price rising (5d return > 1%)
2. Low/declining Google Trends attention (proxy for retail attention)
3. Above 20-day MA (uptrend confirmed)

Buy it for the continuation + eventual attention catalyst.

Universe: XBI (biotech - often heavily shorted), IWM (small caps - high short interest),
ARKK (innovation - retail favorite that can squeeze), XRT (retail - high short interest)
"""

import pandas as pd
import numpy as np

SCAN_ETFS = ["XBI", "IWM", "ARKK", "XRT"]

STRATEGY = {
    "name": "Stealth Squeeze",
    "hypothesis": "ETFs with rising prices but low/declining Google Trends attention are in stealth rallies that accelerate when attention comes. Buy the strongest stealth rally.",
    "universe": SCAN_ETFS + ["SPY"],
    "entry": "Buy ETF with 5d return > 1% AND declining Google Trends AND above 20d MA. Best 5d return wins.",
    "exit": "Sell after 5 days or +4%/-2% stop",
    "position_size": "80% of capital per trade",
    "eccentricity": "Combines price momentum with INVERSE attention signal (buy when nobody is watching). Opposite of typical attention-buying strategies.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch prices for all ETFs
    all_prices = {}
    for ticker in SCAN_ETFS:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            all_prices[ticker] = s

    if len(all_prices) < 3:
        return

    # Fetch Google Trends for related terms (batch to avoid rate limits)
    try:
        trends = data_fetcher.get_google_trends(["biotech", "small cap stocks", "ARK invest", "retail stocks"])
    except Exception:
        trends = pd.DataFrame()

    # If no trends, fall back to price-only stealth detection
    has_trends = not trends.empty

    # Map ETF to trend keyword
    ticker_to_trend = {"XBI": "biotech", "IWM": "small cap stocks", "ARKK": "ARK invest", "XRT": "retail stocks"}

    # Find common dates
    common = None
    for s in all_prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 25:
        return
    common = common.sort_values()

    pm = pd.DataFrame({t: all_prices[t].loc[common] for t in all_prices})
    ret5 = pm.pct_change(5)
    ma20 = pm.rolling(20).mean()

    in_trade = False
    trade_ticker = None
    entry_price = None
    days_held = 0

    for i in range(25, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")

        if in_trade:
            days_held += 1
            curr = float(pm[trade_ticker].iloc[i])
            pnl_pct = (curr - entry_price) / entry_price

            if days_held >= 5 or pnl_pct >= 0.04 or pnl_pct <= -0.02:
                portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                in_trade = False
                trade_ticker = None
                entry_price = None
                days_held = 0

        elif not in_trade:
            best_ticker = None
            best_ret = 0

            for ticker in all_prices:
                price = float(pm[ticker].iloc[i])
                r5 = float(ret5[ticker].iloc[i]) if pd.notna(ret5[ticker].iloc[i]) else 0
                ma = float(ma20[ticker].iloc[i]) if pd.notna(ma20[ticker].iloc[i]) else price

                # Price rising + above trend
                if r5 > 0.01 and price > ma:
                    # Check if attention is low/declining (if trends available)
                    attention_low = True
                    if has_trends and ticker in ticker_to_trend:
                        keyword = ticker_to_trend[ticker]
                        if keyword in trends.columns:
                            recent_trend = trends[keyword].iloc[-4:]  # last 4 weeks
                            if len(recent_trend) >= 2:
                                # Attention declining or flat
                                attention_low = float(recent_trend.iloc[-1]) <= float(recent_trend.iloc[-2]) * 1.1

                    if attention_low and r5 > best_ret:
                        best_ret = r5
                        best_ticker = ticker

            if best_ticker:
                price = float(pm[best_ticker].iloc[i])
                result = portfolio.buy(best_ticker, dollars=portfolio.cash * 0.8, date=date_str)
                if result:
                    in_trade = True
                    trade_ticker = best_ticker
                    entry_price = price
                    days_held = 0

    if in_trade:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(trade_ticker, all_shares=True, date=last_date)
