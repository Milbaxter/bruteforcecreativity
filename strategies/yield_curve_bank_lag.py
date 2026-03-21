"""
Yield Curve Bank Lag — buy XLF when the yield curve steepens but banks haven't moved.

Thesis: When the 10Y-2Y Treasury spread (T10Y2Y from FRED) steepens rapidly, bank
profitability improves (banks borrow short, lend long). But bank stocks (XLF) often
lag the yield curve move by 2-5 days because: (1) yield curve traders are in the bond
market, not equities, (2) banks' earnings sensitivity to curve steepening takes time
to flow through analyst models.

Three signals:
1. T10Y2Y 10-day change > +0.1 (curve steepening)
2. XLF 5-day return < +1% (hasn't priced it in yet)
3. XLF > 20-day MA (not in structural downtrend)

Buy XLF, hold 5-7 days for catch-up.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Yield Curve Bank Lag",
    "hypothesis": "Yield curve steepening (T10Y2Y rising) boosts bank profitability but XLF lags by 2-5 days. Buy on steepening + XLF lagging + above trend.",
    "universe": ["XLF", "SPY"],
    "entry": "Buy XLF when T10Y2Y 10d change > +0.1 AND XLF 5d return < 1% AND XLF > 20d MA",
    "exit": "Sell after 7 days or +3%/-2% stop",
    "position_size": "80% of capital per trade",
    "eccentricity": "FRED yield curve data as leading indicator for bank equity timing. Bond traders don't trade XLF; equity traders don't watch T10Y2Y closely.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch yield curve spread
    t10y2y = data_fetcher.get_fred_series("T10Y2Y", start=start_date, end=end_date)
    xlf = data_fetcher.get_prices("XLF", start=start_date, end=end_date)

    if xlf.empty or t10y2y.empty:
        return

    xlf_close = xlf["Close"].dropna()
    xlf_close.index = pd.to_datetime(xlf_close.index)
    t10y2y.index = pd.to_datetime(t10y2y.index)

    # Align yield curve to trading days
    all_dates = xlf_close.index
    t10y2y_aligned = t10y2y.reindex(all_dates, method="ffill")

    common = all_dates[t10y2y_aligned.notna()]
    if len(common) < 25:
        return

    xlf_c = xlf_close.loc[common]
    yc = t10y2y_aligned.loc[common]

    # Signals
    yc_change10 = yc.diff(10)
    xlf_ret5 = xlf_c.pct_change(5)
    xlf_ma20 = xlf_c.rolling(20).mean()

    in_trade = False
    entry_price = None
    days_held = 0

    for i in range(25, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        price = float(xlf_c.iloc[i])

        if in_trade:
            days_held += 1
            pnl_pct = (price - entry_price) / entry_price

            if days_held >= 7 or pnl_pct >= 0.03 or pnl_pct <= -0.02:
                portfolio.sell("XLF", all_shares=True, date=date_str)
                in_trade = False
                entry_price = None
                days_held = 0

        elif not in_trade:
            yc_chg = float(yc_change10.iloc[i]) if pd.notna(yc_change10.iloc[i]) else 0
            xlf_r = float(xlf_ret5.iloc[i]) if pd.notna(xlf_ret5.iloc[i]) else 0
            ma20 = float(xlf_ma20.iloc[i]) if pd.notna(xlf_ma20.iloc[i]) else 0

            # Yield curve steepening + XLF hasn't moved + above trend
            if yc_chg > 0.1 and xlf_r < 0.01 and price > ma20:
                result = portfolio.buy("XLF", dollars=portfolio.cash * 0.8, date=date_str)
                if result:
                    in_trade = True
                    entry_price = price
                    days_held = 0

    if in_trade:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell("XLF", all_shares=True, date=last_date)
