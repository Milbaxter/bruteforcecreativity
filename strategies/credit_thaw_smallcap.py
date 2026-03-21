"""
Credit Thaw Small Cap — buy IWM when high yield spreads narrow + small caps lagging.

Thesis: When high yield bond spreads narrow (BAMLH0A0HYM2 from FRED drops), it signals
improving credit conditions and risk appetite. Small caps benefit most from credit easing
(they rely more on bank/high-yield debt) but price this in with a lag vs large caps.
Combined with: IWM underperforming SPY (dislocation exists) + IWM above 20-day MA (not
in structural downtrend).

Eccentricity: Uses FRED credit spread data as a leading signal for small cap equities.
Institutional credit desks don't trade IWM; equity desks don't watch credit spreads at
this granularity. The cross-domain signal is the edge.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Credit Thaw Small Cap",
    "hypothesis": "Narrowing high yield spreads signal credit easing that benefits small caps most, but IWM lags the signal by days. Buy on spread compression + relative underperformance + trend confirmation.",
    "universe": ["IWM", "SPY"],
    "entry": "Buy IWM when HY spread 10-day change < -0.1 AND IWM 10d return < SPY 10d return AND IWM > 20d MA",
    "exit": "Sell after 7 days or +4%/-3% stop",
    "position_size": "80% of capital per trade",
    "eccentricity": "Credit market signal → equity sub-asset class trade. Cross-domain signal that no single desk monitors together.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch credit spread data from FRED
    # BAMLH0A0HYM2 = ICE BofA US High Yield Index Option-Adjusted Spread
    hy_spread = data_fetcher.get_fred_series("BAMLH0A0HYM2", start=start_date, end=end_date)

    iwm = data_fetcher.get_prices("IWM", start=start_date, end=end_date)
    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)

    if iwm.empty or spy.empty:
        return

    iwm_close = iwm["Close"].dropna()
    spy_close = spy["Close"].dropna()

    if hy_spread.empty:
        return

    # Align credit spread to trading days (forward fill since FRED is daily but may miss weekends)
    hy_spread.index = pd.to_datetime(hy_spread.index)
    iwm_close.index = pd.to_datetime(iwm_close.index)
    spy_close.index = pd.to_datetime(spy_close.index)

    # Reindex spread to trading days
    all_dates = iwm_close.index
    hy_aligned = hy_spread.reindex(all_dates, method="ffill")

    # Drop any NaN
    common = all_dates[hy_aligned.notna() & iwm_close.index.isin(spy_close.index)]
    if len(common) < 25:
        return

    hy_aligned = hy_aligned.loc[common]
    iwm_c = iwm_close.loc[common]
    spy_c = spy_close.reindex(common, method="ffill")

    # Signals
    lookback = 10
    hy_change = hy_aligned.diff(lookback)  # negative = spreads narrowing (bullish)
    iwm_ret_10d = iwm_c.pct_change(lookback)
    spy_ret_10d = spy_c.pct_change(lookback)
    iwm_ma20 = iwm_c.rolling(20).mean()

    in_trade = False
    entry_price = None
    days_held = 0

    for i in range(max(lookback, 20), len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        price = float(iwm_c.iloc[i])

        if in_trade:
            days_held += 1
            pnl_pct = (price - entry_price) / entry_price

            if days_held >= 7 or pnl_pct >= 0.04 or pnl_pct <= -0.03:
                portfolio.sell("IWM", all_shares=True, date=date_str)
                in_trade = False
                entry_price = None
                days_held = 0

        elif not in_trade:
            spread_chg = float(hy_change.iloc[i]) if pd.notna(hy_change.iloc[i]) else 0
            iwm_10d = float(iwm_ret_10d.iloc[i]) if pd.notna(iwm_ret_10d.iloc[i]) else 0
            spy_10d = float(spy_ret_10d.iloc[i]) if pd.notna(spy_ret_10d.iloc[i]) else 0
            ma20_val = float(iwm_ma20.iloc[i]) if pd.notna(iwm_ma20.iloc[i]) else 0

            # Entry: spreads narrowing + IWM lagging + above trend
            if spread_chg < -0.1 and iwm_10d < spy_10d and price > ma20_val:
                result = portfolio.buy("IWM", dollars=portfolio.cash * 0.8, date=date_str)
                if result:
                    in_trade = True
                    entry_price = price
                    days_held = 0

    # Close remaining position
    if in_trade:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell("IWM", all_shares=True, date=last_date)
