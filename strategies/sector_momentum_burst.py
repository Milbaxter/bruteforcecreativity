"""
Sector Momentum Burst: Each week, buy the sector ETF with the strongest
5-day momentum. Hold for 3 trading days, then rotate.

Thesis: Short-term sector momentum is self-reinforcing. When money flows into
a sector, it attracts more flow (news coverage, analyst upgrades, retail FOMO).
This creates 3-5 day momentum bursts before the rotation exhausts.

The eccentric angle: we're combining 11 sector ETFs with a weekly rotation
frequency that's too fast for most sector funds (which rebalance monthly/quarterly).
"""

import pandas as pd

STRATEGY = {
    "name": "Sector Momentum Burst",
    "hypothesis": "The best-performing sector over 5 days tends to continue outperforming for 3 more days due to flow momentum and narrative reinforcement.",
    "universe": [
        "XLF", "XLE", "XLV", "XLK", "XLI", "XLP", "XLU", "XLB", "XLRE", "XLC", "XLY",
    ],
    "entry": "Buy the sector ETF with highest 5-day return every 3 trading days",
    "exit": "Sell after 3 trading days and rotate to new leader",
    "position_size": "90% of cash into the winning sector",
    "eccentricity": "Weekly sector rotation is too fast for institutional sector funds. They rebalance monthly or quarterly. This captures the 3-5 day momentum burst they miss.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    universe = STRATEGY["universe"]

    # Load prices for all sector ETFs
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
    common_index = None
    for ticker, series in all_prices.items():
        if common_index is None:
            common_index = set(series.index)
        else:
            common_index &= set(series.index)

    trading_days = sorted(common_index)
    if len(trading_days) < 10:
        return

    current_holding = None
    hold_days = 0
    rotation_interval = 3  # Rotate every 3 days

    for i in range(5, len(trading_days)):  # Start after 5 days for lookback
        day = trading_days[i]
        day_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]

        if current_holding:
            hold_days += 1

        # Time to rotate?
        if hold_days >= rotation_interval or current_holding is None:
            # Compute 5-day momentum for each sector
            lookback_day = trading_days[i - 5]
            momentum = {}
            for ticker, series in all_prices.items():
                if day in series.index and lookback_day in series.index:
                    current = float(series.loc[day])
                    past = float(series.loc[lookback_day])
                    if past > 0:
                        momentum[ticker] = (current - past) / past

            if not momentum:
                continue

            # Pick the winner
            best_ticker = max(momentum, key=momentum.get)
            best_momentum = momentum[best_ticker]

            # Only enter if momentum is positive
            if best_momentum <= 0:
                # Sell current if held and no positive momentum anywhere
                if current_holding:
                    portfolio.sell(current_holding, all_shares=True, date=day_str)
                    current_holding = None
                    hold_days = 0
                continue

            # Sell current holding if different from new winner
            if current_holding and current_holding != best_ticker:
                portfolio.sell(current_holding, all_shares=True, date=day_str)
                current_holding = None

            # Buy new winner
            if current_holding != best_ticker:
                result = portfolio.buy(best_ticker, dollars=portfolio.cash * 0.90, date=day_str)
                if result:
                    current_holding = best_ticker
                    hold_days = 0

    # Close remaining
    if current_holding and trading_days:
        last = trading_days[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last)
