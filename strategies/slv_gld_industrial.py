"""
Silver Gold Industrial Signal — SLV/GLD ratio direction as an indicator
of industrial demand vs pure safety demand.

Silver has industrial uses (solar panels, electronics). When SLV outperforms
GLD (ratio rising), it signals industrial demand is strong = growth.
When GLD outperforms SLV (ratio falling), pure safety demand dominates = risk off.

Different from Gold Silver Rotation (simple momentum between the two).
Combined with crypto fear/greed as confirmation.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Silver Gold Industrial Signal",
    "hypothesis": "Silver's dual nature (industrial + monetary) makes the SLV/GLD ratio a uniquely informative signal. Rising ratio = industrial demand lifting silver above gold = economic growth. Falling ratio = flight to gold safety = contraction risk.",
    "universe": ["SLV", "GLD", "SOXX", "GDX", "XLF"],
    "entry": "SLV/GLD rising (7d) + crypto fear > 25: buy SOXX/XLF. Ratio falling: buy GDX (leveraged gold exposure).",
    "exit": "Rotate every 5 trading days",
    "position_size": "100% in best 5d momentum candidate per regime",
    "eccentricity": "Most people view gold and silver as interchangeable precious metals. But their ratio reveals industrial vs monetary demand — a signal hiding in plain sight.",
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

    if "SLV" not in prices or "GLD" not in prices or len(prices) < 4:
        return

    slv = prices["SLV"]
    gld = prices["GLD"]
    common = slv.index.intersection(gld.index)
    if len(common) < 20:
        return

    ratio = slv.loc[common, "Close"] / gld.loc[common, "Close"]

    try:
        fear_greed = data_fetcher.get_crypto_fear_greed(days=400)
    except Exception:
        fear_greed = None

    all_dates = set()
    for df in prices.values():
        for dt in df.index:
            all_dates.add(dt)
    trading_days = sorted(all_dates)

    if len(trading_days) < 20:
        return

    industrial_tickers = ["SOXX", "XLF"]
    safety_tickers = ["GDX"]

    current_holding = None
    last_rotation_idx = -999
    rotation_interval = 5
    lookback = 7

    for i, day in enumerate(trading_days):
        if i < lookback + 5:
            continue
        if i - last_rotation_idx < rotation_interval:
            continue

        date_str = day.strftime("%Y-%m-%d") if hasattr(day, 'strftime') else str(day)[:10]

        fg_val = 50
        if fear_greed is not None and not fear_greed.empty:
            fg_before = fear_greed[fear_greed.index <= day]
            if len(fg_before) > 0:
                fg_val = float(fg_before.iloc[-1])
        if fg_val < 15:
            continue

        ratio_before = ratio[ratio.index <= day]
        if len(ratio_before) < lookback + 1:
            continue

        current_r = float(ratio_before.iloc[-1])
        past_r = float(ratio_before.iloc[-lookback - 1])
        if past_r == 0:
            continue

        ratio_change = (current_r - past_r) / past_r

        if ratio_change > 0.005 and fg_val > 25:
            candidates = [t for t in industrial_tickers if t in prices]
        elif ratio_change < -0.005:
            candidates = [t for t in safety_tickers if t in prices]
        else:
            candidates = [t for t in industrial_tickers + safety_tickers if t in prices]

        if not candidates:
            continue

        best_ticker = None
        best_mom = -999
        for ticker in candidates:
            df = prices[ticker]
            df_before = df[df.index <= day]
            if len(df_before) < 6:
                continue
            c_now = float(df_before["Close"].iloc[-1])
            c_5d = float(df_before["Close"].iloc[-6])
            if c_5d > 0:
                mom = (c_now - c_5d) / c_5d
                if mom > best_mom:
                    best_mom = mom
                    best_ticker = ticker

        if best_ticker is None:
            continue

        if best_ticker != current_holding:
            if current_holding and current_holding in portfolio.positions:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(best_ticker, dollars=portfolio.cash * 0.98, date=date_str)
            current_holding = best_ticker
            last_rotation_idx = i

    if current_holding and current_holding in portfolio.positions:
        end_str = trading_days[-1].strftime("%Y-%m-%d") if hasattr(trading_days[-1], 'strftime') else str(trading_days[-1])[:10]
        portfolio.sell(current_holding, all_shares=True, date=end_str)
