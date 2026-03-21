"""
Sector Dispersion Fade — buy the worst-performing sector when dispersion is high.

Thesis: When cross-sectional sector returns are highly dispersed (some sectors up big,
others down big), it signals a rotation event. The worst sector tends to mean-revert
within 3-7 days as the rotation unwinds or rebalancing flows kick in. This is especially
true when the underperformance is sharp (>3% gap from the mean) and VIX is moderate
(not a systemic crisis).

Three signals:
1. Cross-sector dispersion > 2% (std dev of 5-day sector returns)
2. Worst sector's 5-day return is > 2 std devs below the sector mean
3. VIX < 30 (not a systemic crisis — in a crisis, rotation is permanent, not temporary)

Universe: 9 sector SPDRs (XLF, XLK, XLE, XLV, XLI, XLC, XLY, XLP, XLU)
"""

import pandas as pd
import numpy as np

SECTORS = ["XLF", "XLK", "XLE", "XLV", "XLI", "XLC", "XLY", "XLP", "XLU"]

STRATEGY = {
    "name": "Sector Dispersion Fade",
    "hypothesis": "High cross-sector dispersion signals rotation events where the worst sector mean-reverts within 3-7 days. Buy the laggard when dispersion is elevated and VIX is moderate.",
    "universe": SECTORS + ["SPY"],
    "entry": "Buy worst sector when sector return std dev > 2% AND worst is > 2 std devs below mean AND VIX < 30",
    "exit": "Sell after 5 days or +3%/-2% stop",
    "position_size": "80% of capital per trade",
    "eccentricity": "Cross-sectional dispersion as a signal (not single-asset momentum). Exploits rotation rebalancing flows that institutional sector funds create but can't trade against.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    # Fetch all sector prices
    sector_prices = {}
    for sector in SECTORS:
        df = data_fetcher.get_prices(sector, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            sector_prices[sector] = df["Close"].dropna()

    if len(sector_prices) < 7 or vix.empty:
        return

    # Find common dates across all sectors and VIX
    common_dates = None
    for s, prices in sector_prices.items():
        prices.index = pd.to_datetime(prices.index)
        if common_dates is None:
            common_dates = prices.index
        else:
            common_dates = common_dates.intersection(prices.index)

    vix.index = pd.to_datetime(vix.index)
    common_dates = common_dates.intersection(vix.index)

    if len(common_dates) < 20:
        return

    common_dates = common_dates.sort_values()

    # Build aligned price matrix
    price_matrix = pd.DataFrame({s: sector_prices[s].loc[common_dates] for s in sector_prices})

    # 5-day sector returns
    ret_5d = price_matrix.pct_change(5)

    in_trade = False
    trade_ticker = None
    entry_price = None
    days_held = 0

    for i in range(10, len(common_dates)):
        date_str = common_dates[i].strftime("%Y-%m-%d")

        if in_trade:
            days_held += 1
            current_price = float(price_matrix[trade_ticker].iloc[i])
            pnl_pct = (current_price - entry_price) / entry_price

            if days_held >= 5 or pnl_pct >= 0.03 or pnl_pct <= -0.02:
                portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                in_trade = False
                trade_ticker = None
                entry_price = None
                days_held = 0

        elif not in_trade:
            # Get current 5-day returns for all sectors
            row = ret_5d.iloc[i].dropna()
            if len(row) < 5:
                continue

            sector_mean = row.mean()
            sector_std = row.std()
            vix_level = float(vix.loc[common_dates[i]])

            if sector_std < 0.005:  # not enough dispersion
                continue

            # Find worst sector
            worst_sector = row.idxmin()
            worst_ret = row[worst_sector]
            z_score = (worst_ret - sector_mean) / sector_std

            # Entry: high dispersion + worst sector is outlier + not crisis
            if sector_std > 0.02 and z_score < -2.0 and vix_level < 30:
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
