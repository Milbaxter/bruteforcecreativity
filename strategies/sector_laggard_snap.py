"""
Sector Laggard Snap — buy the worst 3-day sector when it's an outlier, sell in 3 days.

Thesis: Same as Sector Dispersion Fade but more aggressive. When any sector underperforms
the sector average by >1.5 std devs over 3 days, buy it for a quick 3-day mean reversion
snap. Looser filters to generate more trades. The edge is that sector rotation creates
temporary dislocations that snap back quickly as passive fund rebalancing and dip-buyers
step in.

Three signals:
1. Worst sector 3-day return is > 1.5 std devs below sector mean
2. Worst sector 3-day return < -1% (actually down, not just relatively lagging)
3. SPY 3-day return > -2% (market isn't in full meltdown)

Faster cadence: 3-day hold, tighter stops, more frequent rotation.
"""

import pandas as pd
import numpy as np

SECTORS = ["XLF", "XLK", "XLE", "XLV", "XLI", "XLC", "XLY", "XLP", "XLU", "XLRE"]

STRATEGY = {
    "name": "Sector Laggard Snap",
    "hypothesis": "Sector that underperforms peers by >1.5 std over 3 days snaps back within 3 days due to rebalancing and dip-buying flows.",
    "universe": SECTORS + ["SPY"],
    "entry": "Buy worst sector when 3d return is > 1.5 std devs below sector mean AND actually negative AND market not crashing",
    "exit": "Sell after 3 days or +2%/-1.5% stop",
    "position_size": "80% of capital per trade",
    "eccentricity": "Cross-sectional mean reversion with fast 3-day cycle. Captures rotation whipsaw that passive/index funds create.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)

    # Fetch all sector prices
    sector_prices = {}
    for sector in SECTORS:
        df = data_fetcher.get_prices(sector, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            sector_prices[sector] = df["Close"].dropna()

    if len(sector_prices) < 7 or spy.empty:
        return

    spy_close = spy["Close"].dropna()
    spy_close.index = pd.to_datetime(spy_close.index)

    # Find common dates
    common_dates = None
    for s, prices in sector_prices.items():
        prices.index = pd.to_datetime(prices.index)
        if common_dates is None:
            common_dates = prices.index
        else:
            common_dates = common_dates.intersection(prices.index)

    common_dates = common_dates.intersection(spy_close.index)
    if len(common_dates) < 15:
        return

    common_dates = common_dates.sort_values()

    # Build aligned price matrix
    price_matrix = pd.DataFrame({s: sector_prices[s].loc[common_dates] for s in sector_prices})
    spy_aligned = spy_close.loc[common_dates]

    # 3-day sector returns
    ret_3d = price_matrix.pct_change(3)
    spy_ret_3d = spy_aligned.pct_change(3)

    in_trade = False
    trade_ticker = None
    entry_price = None
    days_held = 0

    for i in range(5, len(common_dates)):
        date_str = common_dates[i].strftime("%Y-%m-%d")

        if in_trade:
            days_held += 1
            current_price = float(price_matrix[trade_ticker].iloc[i])
            pnl_pct = (current_price - entry_price) / entry_price

            if days_held >= 3 or pnl_pct >= 0.02 or pnl_pct <= -0.015:
                portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                in_trade = False
                trade_ticker = None
                entry_price = None
                days_held = 0

        elif not in_trade:
            row = ret_3d.iloc[i].dropna()
            if len(row) < 5:
                continue

            sector_mean = row.mean()
            sector_std = row.std()

            if sector_std < 0.003:
                continue

            worst_sector = row.idxmin()
            worst_ret = float(row[worst_sector])
            z_score = (worst_ret - sector_mean) / sector_std

            spy_3d = float(spy_ret_3d.iloc[i]) if pd.notna(spy_ret_3d.iloc[i]) else 0

            # Entry: sector outlier + actually down + market not crashing
            if z_score < -1.5 and worst_ret < -0.01 and spy_3d > -0.02:
                worst_price = float(price_matrix[worst_sector].iloc[i])
                result = portfolio.buy(worst_sector, dollars=portfolio.cash * 0.8, date=date_str)
                if result:
                    in_trade = True
                    trade_ticker = worst_sector
                    entry_price = worst_price
                    days_held = 0

    # Close remaining
    if in_trade:
        last_date = common_dates[-1].strftime("%Y-%m-%d")
        portfolio.sell(trade_ticker, all_shares=True, date=last_date)
