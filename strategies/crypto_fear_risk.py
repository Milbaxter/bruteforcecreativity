"""
Crypto Fear Risk Indicator
Use crypto fear/greed index as a LEADING indicator for traditional asset rotation.
Crypto sentiment often leads broader risk appetite.
Don't trade crypto — just use its sentiment to time GLD/QQQ/XLE.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Crypto Fear Risk Indicator",
    "hypothesis": "Crypto fear/greed index leads broader risk appetite by 1-3 days. When crypto is fearful, traditional safe havens (GLD) outperform. When crypto is greedy, risk assets (QQQ/XLE) outperform. Using crypto sentiment as a cross-market regime indicator.",
    "universe": ["GLD", "QQQ", "XLE"],
    "entry": "Crypto F&G < 30 → GLD. F&G > 55 → best of QQQ/XLE by 7d momentum. Neutral → best of all 3.",
    "exit": "Rotate every 3 trading days, -3% stop loss",
    "position_size": "90% of capital in selected ETF",
    "eccentricity": "Uses crypto-market sentiment (alternative data) as a cross-domain leading indicator for traditional equity/commodity rotation — no institution would use Bitcoin fear to trade gold miners",
}


def run(data_fetcher, portfolio, start_date, end_date):
    prices_gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)
    prices_qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    prices_xle = data_fetcher.get_prices("XLE", start=start_date, end=end_date)

    for df in [prices_gld, prices_qqq, prices_xle]:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

    # Fetch crypto fear/greed (alternative data source)
    crypto_fg = data_fetcher.get_crypto_fear_greed(days=400)

    if prices_gld.empty or prices_qqq.empty or prices_xle.empty:
        return

    gld_close = prices_gld["Close"]
    qqq_close = prices_qqq["Close"]
    xle_close = prices_xle["Close"]

    # 7-day momentum
    gld_ret7 = gld_close.pct_change(7)
    qqq_ret7 = qqq_close.pct_change(7)
    xle_ret7 = xle_close.pct_change(7)

    trading_days = qqq_close.index.tolist()

    # Align crypto fear/greed
    if isinstance(crypto_fg, pd.Series):
        fg_aligned = crypto_fg.reindex(pd.DatetimeIndex(trading_days), method="ffill")
    else:
        fg_aligned = pd.Series(50, index=pd.DatetimeIndex(trading_days))

    current_holding = None
    entry_price = None
    last_rotation = -999

    for i in range(10, len(trading_days)):
        date = trading_days[i]
        date_str = date.strftime("%Y-%m-%d")

        # Stop loss
        if current_holding is not None and entry_price is not None:
            if current_holding == "GLD":
                current = float(gld_close.loc[date])
            elif current_holding == "QQQ":
                current = float(qqq_close.loc[date])
            else:
                current = float(xle_close.loc[date])

            pct = (current - entry_price) / entry_price
            if pct <= -0.03:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
                current_holding = None
                entry_price = None
                last_rotation = i
                continue

        # Rotate every 3 days
        if i - last_rotation < 3:
            continue

        # Crypto fear/greed value
        fg_val = float(fg_aligned.loc[date]) if date in fg_aligned.index and not pd.isna(fg_aligned.loc[date]) else 50

        # Momentum values
        gld_mom = float(gld_ret7.loc[date]) if date in gld_ret7.index and not pd.isna(gld_ret7.loc[date]) else 0
        qqq_mom = float(qqq_ret7.loc[date]) if date in qqq_ret7.index and not pd.isna(qqq_ret7.loc[date]) else 0
        xle_mom = float(xle_ret7.loc[date]) if date in xle_ret7.index and not pd.isna(xle_ret7.loc[date]) else 0

        # Regime-based selection
        if fg_val < 30:
            # Crypto fear → risk-off → GLD (safe haven)
            target = "GLD"
        elif fg_val > 55:
            # Crypto greed → risk-on → best of QQQ/XLE
            target = "QQQ" if qqq_mom > xle_mom else "XLE"
        else:
            # Neutral → pure momentum across all 3
            moms = {"GLD": gld_mom, "QQQ": qqq_mom, "XLE": xle_mom}
            target = max(moms, key=moms.get)

        if target != current_holding:
            if current_holding is not None:
                portfolio.sell(current_holding, all_shares=True, date=date_str)

            dollars = portfolio.cash * 0.90
            result = portfolio.buy(target, dollars=dollars, date=date_str)
            if result:
                current_holding = target
                entry_price = result["exec_price"]

        last_rotation = i
