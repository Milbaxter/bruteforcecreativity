"""
Tech Semis Pair Reversion
Pairs trade between QQQ and SMH — buy the underperformer when the spread diverges.
Mean reversion on the tech vs semiconductors relative value.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Tech Semis Pair Reversion",
    "hypothesis": "QQQ and SMH are highly correlated. When their ratio diverges >1.5 stdev from the 20-day mean, the underperformer reverts within 3-5 days. VIX filter avoids trading during regime breaks.",
    "universe": ["QQQ", "SMH"],
    "entry": "Z-score of QQQ/SMH ratio > 1.5 or < -1.5 → buy the underperformer + VIX < 30",
    "exit": "Sell when z-score reverts to within 0.3 of mean, or after 5 days, or -2% stop loss",
    "position_size": "80% of capital per trade",
    "eccentricity": "Pairs/relative-value strategy between tech and semiconductors — exploits tight correlation with fast reversion that's too small for institutional pair desks to bother with at $10K scale",
}


def run(data_fetcher, portfolio, start_date, end_date):
    prices_qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    prices_smh = data_fetcher.get_prices("SMH", start=start_date, end=end_date)
    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    for df in [prices_qqq, prices_smh]:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

    if prices_qqq.empty or prices_smh.empty:
        return

    qqq_close = prices_qqq["Close"]
    smh_close = prices_smh["Close"]

    # Align indices
    common_idx = qqq_close.index.intersection(smh_close.index)
    qqq_close = qqq_close.loc[common_idx]
    smh_close = smh_close.loc[common_idx]

    # Compute ratio and z-score
    ratio = qqq_close / smh_close
    ratio_ma = ratio.rolling(20).mean()
    ratio_std = ratio.rolling(20).std()
    zscore = (ratio - ratio_ma) / ratio_std.replace(0, np.nan)

    vix_aligned = vix.reindex(common_idx, method="ffill")
    trading_days = common_idx.tolist()

    current_position = None  # "QQQ" or "SMH"
    entry_idx = None
    entry_price = None

    for i in range(25, len(trading_days)):
        date = trading_days[i]
        date_str = date.strftime("%Y-%m-%d")

        z = float(zscore.loc[date]) if not pd.isna(zscore.loc[date]) else 0
        vix_val = float(vix_aligned.loc[date]) if date in vix_aligned.index and not pd.isna(vix_aligned.loc[date]) else 15

        # Manage exit
        if current_position is not None:
            current_price_val = float(qqq_close.loc[date]) if current_position == "QQQ" else float(smh_close.loc[date])
            pct_change = (current_price_val - entry_price) / entry_price
            days_held = i - entry_idx

            # Exit conditions:
            # 1. Z-score reverted (within 0.3 of zero)
            # 2. 5 trading days elapsed
            # 3. -2% stop loss
            z_reverted = (current_position == "SMH" and z < 0.3) or (current_position == "QQQ" and z > -0.3)

            if z_reverted or days_held >= 5 or pct_change <= -0.02:
                portfolio.sell(current_position, all_shares=True, date=date_str)
                current_position = None
                entry_idx = None
                entry_price = None
                continue

        # Entry
        if current_position is not None:
            continue

        if vix_val >= 30:
            continue

        # Z > 1.5: QQQ is expensive relative to SMH → buy SMH (underperformer)
        if z > 1.5:
            dollars = portfolio.cash * 0.80
            result = portfolio.buy("SMH", dollars=dollars, date=date_str)
            if result:
                current_position = "SMH"
                entry_idx = i
                entry_price = result["exec_price"]

        # Z < -1.5: SMH is expensive relative to QQQ → buy QQQ (underperformer)
        elif z < -1.5:
            dollars = portfolio.cash * 0.80
            result = portfolio.buy("QQQ", dollars=dollars, date=date_str)
            if result:
                current_position = "QQQ"
                entry_idx = i
                entry_price = result["exec_price"]
