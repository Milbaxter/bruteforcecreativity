"""
Earnings Overreaction Reversal: Buy large-cap stocks that drop >5% on earnings day,
betting on a mean-reversion bounce within 3 trading days.

Thesis: Retail traders panic-sell on headline earnings misses. The initial drop
often overshoots fair value, especially in liquid large-caps where fundamentals
haven't actually changed that much. Institutional investors step in over the
next 1-3 days, creating a bounce.
"""

import pandas as pd
from datetime import datetime, timedelta

STRATEGY = {
    "name": "Earnings Overreaction Reversal",
    "hypothesis": "Large-cap stocks that drop >5% on earnings day are oversold by retail panic. They tend to bounce 1-3 days later as institutions buy the dip.",
    "universe": [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
        "JPM", "V", "JNJ", "UNH", "HD", "PG", "MA", "DIS",
        "NFLX", "CRM", "AMD", "INTC", "PYPL", "BA", "NKE",
        "COST", "WMT", "KO", "PEP", "MCD", "ADBE", "CSCO", "CMCSA",
    ],
    "entry": "Buy when stock drops >5% on earnings day (or next trading day after report)",
    "exit": "Sell 3 trading days after entry, or at +4% profit / -3% stop loss",
    "position_size": "20% of available cash per trade, max 3 concurrent positions",
    "eccentricity": "Exploits the speed gap: retail sells on headline, institutions take 1-3 days to analyze and buy. Too fast for most fund approval processes.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    universe = STRATEGY["universe"]

    # Fetch earnings calendar for all universe tickers
    earnings = data_fetcher.get_earnings_calendar(universe)

    if earnings.empty:
        return

    # Filter to our backtest period (normalize tz to avoid comparison errors)
    earnings["date"] = pd.to_datetime(earnings["date"], utc=True).dt.tz_localize(None)
    start_dt = pd.Timestamp(start_date)
    end_dt = pd.Timestamp(end_date)
    earnings = earnings[
        (earnings["date"] >= start_dt) & (earnings["date"] <= end_dt)
    ].copy()
    earnings = earnings.sort_values("date")

    # Track open positions
    open_positions = {}  # ticker -> {entry_date, entry_price, days_held}
    max_concurrent = 3

    # Get price data for all universe tickers (already preloaded by engine)
    # We need to iterate day by day
    all_prices = {}
    for ticker in universe:
        try:
            p = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
            if isinstance(p.columns, pd.MultiIndex):
                p.columns = p.columns.get_level_values(0)
            if not p.empty:
                all_prices[ticker] = p
        except Exception:
            continue

    if not all_prices:
        return

    # Collect all trading dates from SPY
    spy_prices = all_prices.get("AAPL", list(all_prices.values())[0])
    trading_days = sorted(spy_prices.index)

    # Build earnings date lookup: date -> list of tickers reporting
    earnings_by_date = {}
    for _, row in earnings.iterrows():
        d = row["date"]
        if hasattr(d, "date"):
            d = pd.Timestamp(d.date())
        ticker = row["ticker"]
        if d not in earnings_by_date:
            earnings_by_date[d] = []
        earnings_by_date[d].append(ticker)

    for i, date in enumerate(trading_days):
        if i < 1:
            continue

        date_str = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)[:10]
        prev_date = trading_days[i - 1]

        # Check and manage open positions
        tickers_to_close = []
        for ticker, pos in list(open_positions.items()):
            pos["days_held"] += 1

            if ticker in all_prices and date in all_prices[ticker].index:
                current_price = float(all_prices[ticker].loc[date, "Close"])
                pct_from_entry = (current_price - pos["entry_price"]) / pos["entry_price"]

                # Exit: 3 days held, or +4% take profit, or -3% stop loss
                if pos["days_held"] >= 3 or pct_from_entry >= 0.04 or pct_from_entry <= -0.03:
                    tickers_to_close.append(ticker)

        for ticker in tickers_to_close:
            portfolio.sell(ticker, all_shares=True, date=date_str)
            del open_positions[ticker]

        # Check for new earnings drops
        # Look at yesterday's and the day before's earnings dates
        for check_date in [prev_date, date]:
            normalized = pd.Timestamp(check_date.date()) if hasattr(check_date, "date") else pd.Timestamp(check_date)
            if normalized not in earnings_by_date:
                continue

            for ticker in earnings_by_date[normalized]:
                if ticker in open_positions:
                    continue
                if len(open_positions) >= max_concurrent:
                    continue
                if ticker not in all_prices:
                    continue

                prices_df = all_prices[ticker]
                if date not in prices_df.index or prev_date not in prices_df.index:
                    continue

                current_close = float(prices_df.loc[date, "Close"])
                prev_close = float(prices_df.loc[prev_date, "Close"])
                day_return = (current_close - prev_close) / prev_close

                # Entry: stock dropped >5% on/after earnings
                if day_return < -0.05:
                    cash_per_trade = portfolio.cash * 0.20
                    if cash_per_trade < 100:
                        continue

                    result = portfolio.buy(ticker, dollars=cash_per_trade, date=date_str)
                    if result:
                        open_positions[ticker] = {
                            "entry_date": date_str,
                            "entry_price": current_close,
                            "days_held": 0,
                        }

    # Close remaining positions
    if trading_days:
        last_date = trading_days[-1].strftime("%Y-%m-%d")
        for ticker in list(open_positions.keys()):
            portfolio.sell(ticker, all_shares=True, date=last_date)
