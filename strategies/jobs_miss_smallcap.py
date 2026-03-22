"""
Jobs Miss Small Cap Bounce

Hypothesis: After jobs report days, if SPY drops >0.5% (suggesting a bad or confusing
report), IWM (small caps) tends to overreact to the downside because small caps are
more rate-sensitive. But weak jobs = future rate cuts = actually good for small caps.
Combined with crypto fear/greed as a broader risk sentiment check.

Signals:
1. WHY: Jobs report day (from economic calendar) AND SPY drops > 0.5% that day
2. WHEN: IWM pulls back > 0.8% on the jobs day (overreaction)
3. WHEN NOT: VIX > 35 (genuine crisis, not just jobs noise)

Eccentricity: Exploiting the behavioral overreaction pattern in small caps around
employment data releases. Too mechanical and frequent for institutional discretionary
funds who would overthink each report.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Jobs Miss Small Cap Bounce",
    "hypothesis": "Small caps overreact to bad jobs reports; weak employment = rate cuts = good for IWM. Buy the overreaction.",
    "universe": ["IWM", "SPY"],
    "entry": "Buy IWM day after jobs report when SPY dropped >0.5% AND IWM dropped >0.8% on report day",
    "exit": "Sell after 3 trading days or +2.5% gain or -2% stop loss",
    "position_size": "60% of capital per trade",
    "eccentricity": "Behavioral overreaction arbitrage on specific economic calendar dates for small caps.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    iwm = data_fetcher.get_prices("IWM", start=start_date, end=end_date)
    if isinstance(iwm.columns, pd.MultiIndex):
        iwm.columns = iwm.columns.get_level_values(0)
    iwm_close = iwm["Close"].dropna()
    iwm_open = iwm["Open"].dropna() if "Open" in iwm.columns else iwm_close

    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
    spy_close = spy["Close"].dropna()
    spy_open = spy["Open"].dropna() if "Open" in spy.columns else spy_close

    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    # Economic calendar - get jobs report dates
    econ_cal = data_fetcher.get_economic_calendar()
    if econ_cal.empty:
        return
    jobs_dates = econ_cal[econ_cal["event"] == "JOBS"]["date"]
    jobs_dates_str = set(jobs_dates.dt.strftime("%Y-%m-%d"))

    # Also add CPI dates as another catalyst
    cpi_dates = econ_cal[econ_cal["event"] == "CPI"]["date"]
    cpi_dates_str = set(cpi_dates.dt.strftime("%Y-%m-%d"))
    all_event_dates = jobs_dates_str | cpi_dates_str

    if iwm_close.empty or spy_close.empty:
        return

    trading_days = iwm_close.index.strftime("%Y-%m-%d").tolist()
    in_trade = False
    entry_date = None
    entry_price = None

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)
        price = iwm_close.iloc[i]

        # Exit
        if in_trade:
            days_held = (date_ts - pd.Timestamp(entry_date)).days
            pct_change = (price - entry_price) / entry_price * 100
            if days_held >= 3 or pct_change >= 2.5 or pct_change <= -2.0:
                portfolio.sell("IWM", all_shares=True, date=date_str)
                in_trade = False
                entry_date = None
                entry_price = None
                continue

        # Entry: check if previous trading day was an event day with a selloff
        if not in_trade and i >= 2:
            prev_date = trading_days[i-1]

            if prev_date not in all_event_dates:
                continue

            # SPY dropped > 0.5% on event day
            spy_prev_mask = spy_close.index <= pd.Timestamp(prev_date)
            if not spy_prev_mask.any():
                continue
            spy_prev_idx = spy_close.index.get_indexer([pd.Timestamp(prev_date)], method="pad")
            if spy_prev_idx[0] < 1:
                continue
            spy_event_close = spy_close.iloc[spy_prev_idx[0]]
            spy_prior_close = spy_close.iloc[spy_prev_idx[0] - 1]
            spy_ret = (spy_event_close - spy_prior_close) / spy_prior_close * 100
            if spy_ret > -0.5:
                continue

            # IWM dropped > 0.8% on event day
            iwm_prev_idx = iwm_close.index.get_indexer([pd.Timestamp(prev_date)], method="pad")
            if iwm_prev_idx[0] < 1:
                continue
            iwm_event_close = iwm_close.iloc[iwm_prev_idx[0]]
            iwm_prior_close = iwm_close.iloc[iwm_prev_idx[0] - 1]
            iwm_ret = (iwm_event_close - iwm_prior_close) / iwm_prior_close * 100
            if iwm_ret > -0.8:
                continue

            # VIX not in crisis
            vix_mask = vix.index <= date_ts
            if vix_mask.any():
                current_vix = vix[vix_mask].iloc[-1]
                if current_vix > 35:
                    continue

            dollars = portfolio.cash * 0.6
            if dollars > 100:
                result = portfolio.buy("IWM", dollars=dollars, date=date_str)
                if result:
                    in_trade = True
                    entry_date = date_str
                    entry_price = price

    if in_trade:
        portfolio.sell("IWM", all_shares=True, date=trading_days[-1])
