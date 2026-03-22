"""
JNK Junk Bond Direction — SPDR High Yield (JNK) direction as a credit
risk appetite signal. Different from HYG credit trend (which was a loser)
and credit spread direction (which used HY spread not ETF price).

When JNK rises, credit is healthy = growth.
When JNK falls, credit stress = safety.
Combined with Wikipedia "default" attention as credit fear gauge.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "JNK Junk Bond Direction",
    "hypothesis": "JNK tracks junk bond prices directly. Rising JNK = credit markets healthy = risk on. Falling JNK = credit stress = capital flight to safety. JNK is more responsive than spread calculations because it captures both yield and price movements.",
    "universe": ["JNK", "SOXX", "GDX", "SLV", "XLF"],
    "entry": "JNK 7d momentum positive + wiki default not spiking: buy SOXX/XLF. JNK negative: buy GDX/SLV.",
    "exit": "Rotate every 5 trading days",
    "position_size": "100% in best 5d momentum candidate per regime",
    "eccentricity": "Using the junk bond ETF as a macro canary — most retail traders watch VIX, not credit markets. JNK tells you when institutional money is scared before equities react.",
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

    if "JNK" not in prices or len(prices) < 4:
        return

    # Wikipedia default attention
    try:
        wiki_def = data_fetcher.get_wikipedia_pageviews("Default_(finance)")
        if wiki_def is not None and not wiki_def.empty:
            wiki_def.index = pd.to_datetime(wiki_def.index)
            wiki_def = wiki_def.sort_index()
        else:
            wiki_def = None
    except Exception:
        wiki_def = None

    all_dates = set()
    for df in prices.values():
        for dt in df.index:
            all_dates.add(dt)
    trading_days = sorted(all_dates)

    if len(trading_days) < 20:
        return

    growth_tickers = ["SOXX", "XLF"]
    safety_tickers = ["GDX", "SLV"]

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

        jnk = prices["JNK"]
        jnk_before = jnk[jnk.index <= day]
        if len(jnk_before) < lookback + 1:
            continue

        jnk_now = float(jnk_before["Close"].iloc[-1])
        jnk_past = float(jnk_before["Close"].iloc[-lookback - 1])
        if jnk_past == 0:
            continue

        jnk_mom = (jnk_now - jnk_past) / jnk_past

        # Wiki default attention
        default_fear = False
        if wiki_def is not None:
            wd = wiki_def[wiki_def.index <= day]
            if len(wd) >= 20:
                recent = float(wd.iloc[-5:].mean())
                avg = float(wd.iloc[-20:].mean())
                if avg > 0:
                    default_fear = recent > avg * 1.4

        if jnk_mom > 0.001 and not default_fear:
            candidates = [t for t in growth_tickers if t in prices]
        elif jnk_mom < -0.001 or default_fear:
            candidates = [t for t in safety_tickers if t in prices]
        else:
            candidates = [t for t in growth_tickers + safety_tickers if t in prices]

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
