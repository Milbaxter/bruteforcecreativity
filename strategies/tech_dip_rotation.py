"""
Tech Dip Rotation: Same pullback-buying concept as Pullback Sniper, but
rotates between top tech stocks, always buying the most oversold one.

Thesis: Individual tech stocks have larger pullbacks than QQQ (which is
diversified). By rotating into the MOST oversold tech stock, we get
bigger bounces while still benefiting from the secular tech bull market.
"""

import pandas as pd

STRATEGY = {
    "name": "Tech Dip Rotation",
    "hypothesis": "Individual tech stocks pull back harder than QQQ but bounce back just as fast. Rotating into the most oversold tech name captures bigger dip-buying bounces.",
    "universe": [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
        "AMD", "NFLX", "CRM", "ADBE", "AVGO", "ORCL",
    ],
    "entry": "Buy the tech stock with the largest pullback from its 10-day high (>3% threshold)",
    "exit": "Sell when stock recovers to within 1% of 10-day high, or after 7 days, or -5% stop",
    "position_size": "80% of cash in one stock",
    "eccentricity": "Concentrated single-stock dip buying. No fund manager would put 80% into a single tech stock that just dropped. But in a tech bull market, these bounces are reliable.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    universe = STRATEGY["universe"]

    # Load price data
    all_prices = {}
    for ticker in universe:
        try:
            p = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
            if isinstance(p.columns, pd.MultiIndex):
                p.columns = p.columns.get_level_values(0)
            if not p.empty and "Close" in p.columns:
                all_prices[ticker] = p["Close"]
        except Exception:
            continue

    if len(all_prices) < 3:
        return

    # Use common trading days
    common_idx = None
    for series in all_prices.values():
        if common_idx is None:
            common_idx = set(series.index)
        else:
            common_idx &= set(series.index)

    trading_days = sorted(common_idx)
    if len(trading_days) < 15:
        return

    in_position = False
    current_ticker = None
    entry_price = None
    days_held = 0

    for i in range(10, len(trading_days)):
        day = trading_days[i]
        day_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]

        if in_position:
            days_held += 1
            current_price = float(all_prices[current_ticker].loc[day])
            pct_from_entry = (current_price - entry_price) / entry_price

            # Compute current 10-day high for held stock
            lookback = [float(all_prices[current_ticker].loc[trading_days[j]])
                        for j in range(max(0, i - 10), i + 1)]
            rolling_high = max(lookback)
            drawdown = (current_price - rolling_high) / rolling_high

            # Exit: recovered to within 1% of high, or 7 days, or -5% stop
            if drawdown > -0.01 or days_held >= 7 or pct_from_entry <= -0.05:
                portfolio.sell(current_ticker, all_shares=True, date=day_str)
                in_position = False
                current_ticker = None
                entry_price = None
                days_held = 0
        else:
            # Find the most oversold stock
            drawdowns = {}
            for ticker, series in all_prices.items():
                if day not in series.index:
                    continue
                current_price = float(series.loc[day])
                lookback = [float(series.loc[trading_days[j]])
                            for j in range(max(0, i - 10), i + 1)]
                rolling_high = max(lookback)
                dd = (current_price - rolling_high) / rolling_high
                if dd <= -0.03:  # At least 3% pullback
                    drawdowns[ticker] = dd

            if drawdowns:
                # Pick the most oversold
                best = min(drawdowns, key=drawdowns.get)
                result = portfolio.buy(best, dollars=portfolio.cash * 0.80, date=day_str)
                if result:
                    in_position = True
                    current_ticker = best
                    entry_price = float(all_prices[best].loc[day])
                    days_held = 0

    # Close remaining
    if in_position and trading_days:
        last = trading_days[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_ticker, all_shares=True, date=last)
