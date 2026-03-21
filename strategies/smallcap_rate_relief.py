"""
Small Cap Rate Relief — buy IWM when yields drop fast but small caps haven't caught up yet.

Thesis: When the 10Y yield drops sharply (TLT surges >2% in 5 days), small caps benefit
disproportionately due to variable-rate debt sensitivity and discount rate effects. But
institutional money flows to large caps first, creating a 1-5 day lag in IWM. The VIX
filter ensures we're buying during actual stress (not calm), and the relative underperformance
filter (IWM lagging SPY) confirms the dislocation hasn't been priced in yet.

Eccentricity: Combines bond market signal + equity relative value + volatility regime.
No fund would trade IWM based on TLT momentum — they'd trade the yield curve directly.
At small scale ($10-100K), IWM is perfectly liquid and the edge is in the lag.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Small Cap Rate Relief",
    "hypothesis": "When yields drop fast (TLT surges), small caps lag large caps by 1-5 days due to institutional flow patterns. Buy IWM on TLT surge + IWM-SPY underperformance + elevated VIX.",
    "universe": ["IWM", "TLT", "SPY"],
    "entry": "Buy IWM when TLT 5-day return > 2% AND IWM 5-day return lags SPY by > 1% AND VIX > 18",
    "exit": "Sell after 5 trading days or at +3%/-2% stop",
    "position_size": "80% of capital per trade",
    "eccentricity": "Cross-asset signal (bonds → small caps) with relative value filter. Funds trade yield curve directly; this exploits the lag in equity sub-asset-class repricing at retail scale.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch all needed data
    tlt = data_fetcher.get_prices("TLT", start=start_date, end=end_date)
    iwm = data_fetcher.get_prices("IWM", start=start_date, end=end_date)
    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)
    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    if tlt.empty or iwm.empty or spy.empty or vix.empty:
        return

    # Get close prices
    tlt_close = tlt["Close"].dropna()
    iwm_close = iwm["Close"].dropna()
    spy_close = spy["Close"].dropna()

    # Align all series to common dates
    common = tlt_close.index.intersection(iwm_close.index).intersection(spy_close.index).intersection(vix.index)
    if len(common) < 10:
        return

    tlt_close = tlt_close.loc[common]
    iwm_close = iwm_close.loc[common]
    spy_close = spy_close.loc[common]
    vix_vals = vix.loc[common]

    # Compute signals
    lookback = 5
    tlt_ret = tlt_close.pct_change(lookback)
    iwm_ret = iwm_close.pct_change(lookback)
    spy_ret = spy_close.pct_change(lookback)
    relative_ret = iwm_ret - spy_ret  # negative means IWM lagging

    in_trade = False
    entry_date = None
    entry_price = None
    days_held = 0

    for i in range(lookback, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        current_price = float(iwm_close.iloc[i])

        if in_trade:
            days_held += 1
            # Check exit conditions
            pnl_pct = (current_price - entry_price) / entry_price

            if days_held >= 5 or pnl_pct >= 0.03 or pnl_pct <= -0.02:
                portfolio.sell("IWM", all_shares=True, date=date_str)
                in_trade = False
                entry_date = None
                entry_price = None
                days_held = 0

        elif not in_trade:
            # Entry conditions
            tlt_5d = float(tlt_ret.iloc[i])
            iwm_spy_diff = float(relative_ret.iloc[i])
            vix_level = float(vix_vals.iloc[i])

            if tlt_5d > 0.02 and iwm_spy_diff < -0.01 and vix_level > 18:
                result = portfolio.buy("IWM", dollars=portfolio.cash * 0.8, date=date_str)
                if result:
                    in_trade = True
                    entry_date = date_str
                    entry_price = current_price
                    days_held = 0

    # Close any remaining position on last day
    if in_trade:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell("IWM", all_shares=True, date=last_date)
