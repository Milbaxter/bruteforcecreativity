"""
Crypto Sentiment Rotation
3-asset rotation (BITO/QQQ/XLU) with crypto fear/greed index as regime filter.
Extreme fear → force into BITO (contrarian). Extreme greed → avoid BITO.
Neutral → momentum-based rotation.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Crypto Sentiment Rotation",
    "hypothesis": "Crypto fear/greed extremes predict BTC ETF reversals. Combined with momentum rotation across BITO/QQQ/XLU, captures crypto rebounds while protecting with defensive rotation.",
    "universe": ["BITO", "QQQ", "XLU"],
    "entry": "Crypto F&G < 30 → BITO. F&G > 70 → best of QQQ/XLU by 7d momentum. Neutral → best of all 3 by 7d momentum.",
    "exit": "Rotate every 3 trading days, -4% stop loss per position",
    "position_size": "90% of capital in selected ETF",
    "eccentricity": "Uses crypto-specific sentiment index (alternative data) as a regime filter for a cross-asset rotation — blends crypto behavioral signals with traditional equity/defensive ETFs",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch price data
    prices_bito = data_fetcher.get_prices("BITO", start=start_date, end=end_date)
    prices_qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    prices_xlu = data_fetcher.get_prices("XLU", start=start_date, end=end_date)

    for df in [prices_bito, prices_qqq, prices_xlu]:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

    # Fetch crypto fear/greed index (alternative data)
    crypto_fg = data_fetcher.get_crypto_fear_greed(days=400)

    if prices_bito.empty or prices_qqq.empty or prices_xlu.empty:
        return

    bito_close = prices_bito["Close"]
    qqq_close = prices_qqq["Close"]
    xlu_close = prices_xlu["Close"]

    # 7-day momentum for each
    bito_ret7 = bito_close.pct_change(7)
    qqq_ret7 = qqq_close.pct_change(7)
    xlu_ret7 = xlu_close.pct_change(7)

    # Use QQQ index as reference trading days
    trading_days = qqq_close.index.tolist()

    # Align crypto fear/greed to trading days
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

        # Stop loss check
        if current_holding is not None and entry_price is not None:
            if current_holding == "BITO" and date in bito_close.index:
                current = float(bito_close.loc[date])
            elif current_holding == "QQQ":
                current = float(qqq_close.loc[date])
            elif current_holding == "XLU":
                current = float(xlu_close.loc[date])
            else:
                current = entry_price

            pct = (current - entry_price) / entry_price
            if pct <= -0.04:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
                current_holding = None
                entry_price = None
                last_rotation = i
                continue

        # Rotate every 3 days
        if i - last_rotation < 3:
            continue

        # Get crypto fear/greed
        fg_val = float(fg_aligned.loc[date]) if date in fg_aligned.index and not pd.isna(fg_aligned.loc[date]) else 50

        # Get momentum values
        bito_mom = float(bito_ret7.loc[date]) if date in bito_ret7.index and not pd.isna(bito_ret7.loc[date]) else 0
        qqq_mom = float(qqq_ret7.loc[date]) if date in qqq_ret7.index and not pd.isna(qqq_ret7.loc[date]) else 0
        xlu_mom = float(xlu_ret7.loc[date]) if date in xlu_ret7.index and not pd.isna(xlu_ret7.loc[date]) else 0

        # Determine target based on sentiment regime
        if fg_val < 30:
            # Extreme fear → contrarian, buy BITO if it has any positive momentum
            if bito_mom > -0.05:  # Not in complete freefall
                target = "BITO"
            else:
                # Even fear can't save a crash — go defensive
                target = "XLU"
        elif fg_val > 70:
            # Extreme greed → avoid crypto, pick best of QQQ/XLU
            target = "QQQ" if qqq_mom > xlu_mom else "XLU"
        else:
            # Neutral → momentum rotation across all 3
            moms = {"BITO": bito_mom, "QQQ": qqq_mom, "XLU": xlu_mom}
            target = max(moms, key=moms.get)

        # Execute rotation
        if target != current_holding:
            if current_holding is not None:
                portfolio.sell(current_holding, all_shares=True, date=date_str)

            dollars = portfolio.cash * 0.90
            result = portfolio.buy(target, dollars=dollars, date=date_str)
            if result:
                current_holding = target
                entry_price = result["exec_price"]

        last_rotation = i
