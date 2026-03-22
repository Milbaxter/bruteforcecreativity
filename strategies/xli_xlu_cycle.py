"""
XLI XLU Cycle — Industrial vs Utility ratio as a real-time business
cycle indicator for sector rotation.

Rising XLI/XLU = economic expansion (industrials outperform defensives)
Falling XLI/XLU = contraction/recession (defensives outperform cyclicals)

Combined with Wikipedia "recession" attention as sentiment confirmation.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "XLI XLU Cycle",
    "hypothesis": "The XLI/XLU ratio is a pure market-based business cycle indicator. When industrials outperform utilities, the economy is expanding and cyclical/growth assets benefit. When utilities lead, recession risk is rising and safety assets win. Daily frequency beats monthly economic reports.",
    "universe": ["XLI", "XLU", "SOXX", "GDX", "SLV", "XLF"],
    "entry": "XLI/XLU rising (7d): buy SOXX/XLF. Ratio falling + wiki recession attention rising: buy GDX/SLV.",
    "exit": "Rotate every 5 trading days",
    "position_size": "100% in best 5d momentum candidate per regime",
    "eccentricity": "Using the industrial-utility spread as a cycle clock — a signal hiding in plain sight that most retail traders overlook in favor of VIX or yield curve.",
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

    if "XLI" not in prices or "XLU" not in prices or len(prices) < 4:
        return

    # Compute XLI/XLU ratio
    xli = prices["XLI"]
    xlu = prices["XLU"]
    common = xli.index.intersection(xlu.index)
    if len(common) < 20:
        return

    ratio = xli.loc[common, "Close"] / xlu.loc[common, "Close"]

    # Wikipedia recession attention
    try:
        wiki_rec = data_fetcher.get_wikipedia_pageviews("Recession")
        if wiki_rec is not None and not wiki_rec.empty:
            wiki_rec.index = pd.to_datetime(wiki_rec.index)
            wiki_rec = wiki_rec.sort_index()
        else:
            wiki_rec = None
    except Exception:
        wiki_rec = None

    all_dates = set()
    for df in prices.values():
        for dt in df.index:
            all_dates.add(dt)
    trading_days = sorted(all_dates)

    if len(trading_days) < 20:
        return

    expansion_tickers = ["SOXX", "XLF"]
    contraction_tickers = ["GDX", "SLV"]

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

        ratio_before = ratio[ratio.index <= day]
        if len(ratio_before) < lookback + 1:
            continue

        current_r = float(ratio_before.iloc[-1])
        past_r = float(ratio_before.iloc[-lookback - 1])
        if past_r == 0:
            continue

        ratio_change = (current_r - past_r) / past_r

        # Wiki recession rising = extra caution
        recession_fear = False
        if wiki_rec is not None:
            wr = wiki_rec[wiki_rec.index <= day]
            if len(wr) >= 20:
                recent = float(wr.iloc[-5:].mean())
                avg = float(wr.iloc[-20:].mean())
                if avg > 0:
                    recession_fear = recent > avg * 1.3

        # Determine regime
        if ratio_change > 0.003 and not recession_fear:
            candidates = [t for t in expansion_tickers if t in prices]
        elif ratio_change < -0.003 or recession_fear:
            candidates = [t for t in contraction_tickers if t in prices]
        else:
            candidates = [t for t in expansion_tickers + contraction_tickers if t in prices]

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
