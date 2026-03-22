"""
Calm Asset Rotation — buy the asset with the LOWEST realized volatility
among SOXX/GDX/SLV/XLF every 5 trading days.

Hypothesis: money flows INTO calm assets and OUT OF volatile ones.
When an asset has low realized vol, it's experiencing steady buying pressure
(institutional accumulation). High vol = uncertainty = money leaving.

This is NOT a momentum or direction strategy — it uses volatility as
the sole selection criterion.
Combined with crypto fear/greed to avoid extreme environments.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Calm Asset Rotation",
    "hypothesis": "Low realized volatility signals institutional accumulation (steady buying). High volatility signals panic or distribution. By always holding the calmest asset, you ride the flow of smart money accumulation. This is the opposite of 'buy the dip' — it's 'buy the boring one.'",
    "universe": ["SOXX", "GDX", "SLV", "XLF"],
    "entry": "Buy the asset with lowest 10-day realized volatility among the universe every 5 trading days",
    "exit": "Rotate every 5 trading days into the new calmest asset",
    "position_size": "100% in the single calmest asset",
    "eccentricity": "Anti-momentum, anti-direction strategy. While everyone chases the hottest mover, this buys the most boring asset. It's the financial equivalent of 'still waters run deep.'",
}


def run(data_fetcher, portfolio, start_date, end_date):
    prices = {}
    for ticker in STRATEGY["universe"]:
        try:
            df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            prices[ticker] = df
        except Exception:
            continue

    if len(prices) < 3:
        return

    try:
        fear_greed = data_fetcher.get_crypto_fear_greed(days=400)
    except Exception:
        fear_greed = None

    all_dates = set()
    for df in prices.values():
        for dt in df.index:
            all_dates.add(dt)
    trading_days = sorted(all_dates)

    if len(trading_days) < 15:
        return

    current_holding = None
    last_rotation_idx = -999
    rotation_interval = 5
    vol_lookback = 10

    for i, day in enumerate(trading_days):
        if i < vol_lookback + 2:
            continue
        if i - last_rotation_idx < rotation_interval:
            continue

        date_str = day.strftime("%Y-%m-%d") if hasattr(day, 'strftime') else str(day)[:10]

        # Crypto fear filter
        fg_val = 50
        if fear_greed is not None and not fear_greed.empty:
            fg_before = fear_greed[fear_greed.index <= day]
            if len(fg_before) > 0:
                fg_val = float(fg_before.iloc[-1])
        if fg_val < 10:
            continue  # extreme panic

        # Compute realized vol for each asset
        vols = {}
        for ticker in STRATEGY["universe"]:
            if ticker not in prices:
                continue
            df = prices[ticker]
            df_before = df[df.index <= day]
            if len(df_before) < vol_lookback + 1:
                continue

            closes = df_before["Close"].iloc[-vol_lookback - 1:]
            returns = closes.pct_change().dropna()
            if len(returns) < vol_lookback:
                continue

            realized_vol = float(returns.std()) * np.sqrt(252)
            vols[ticker] = realized_vol

        if len(vols) < 2:
            continue

        # Buy the calmest (lowest vol) asset
        calmest = min(vols, key=vols.get)

        if calmest != current_holding:
            if current_holding and current_holding in portfolio.positions:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(calmest, dollars=portfolio.cash * 0.98, date=date_str)
            current_holding = calmest
            last_rotation_idx = i

    if current_holding and current_holding in portfolio.positions:
        end_str = trading_days[-1].strftime("%Y-%m-%d") if hasattr(trading_days[-1], 'strftime') else str(trading_days[-1])[:10]
        portfolio.sell(current_holding, all_shares=True, date=end_str)
