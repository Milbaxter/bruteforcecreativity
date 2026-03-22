"""
USD JPY Carry Signal — USD/JPY direction as a carry trade risk appetite
signal for sector rotation.

Rising USD/JPY = yen weakening = carry trade profitable = risk on.
Falling USD/JPY = yen strengthening = carry unwind = risk off.
The yen carry trade is the world's largest macro trade — its direction
predicts equity risk appetite.

Combined with Wikipedia "Bank_of_Japan" attention as policy intervention signal.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "USD JPY Carry Signal",
    "hypothesis": "The yen carry trade (borrow cheap yen, invest in higher-yielding assets) is the backbone of global risk appetite. When USD/JPY rises, carry is profitable and risk assets thrive. When USD/JPY falls, carry unwind cascades into equity selling. The August 2024 crash proved this.",
    "universe": ["SOXX", "GDX", "SLV", "XLF"],
    "entry": "USD/JPY rising (7d): buy SOXX/XLF. USD/JPY falling + BOJ wiki attention: buy GDX/SLV.",
    "exit": "Rotate every 5 trading days",
    "position_size": "100% in best 5d momentum candidate per regime",
    "eccentricity": "Using the FX carry trade as an equity rotation signal — retail equity traders rarely monitor USD/JPY. But it's the world's risk appetite thermometer.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch USD/JPY
    try:
        usdjpy = data_fetcher.get_prices("JPY=X", start=start_date, end=end_date)
        if isinstance(usdjpy.columns, pd.MultiIndex):
            usdjpy.columns = usdjpy.columns.get_level_values(0)
    except Exception:
        return

    if usdjpy.empty:
        return

    # Get trading asset prices
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

    # Wikipedia BOJ attention
    try:
        wiki_boj = data_fetcher.get_wikipedia_pageviews("Bank_of_Japan")
        if wiki_boj is not None and not wiki_boj.empty:
            wiki_boj.index = pd.to_datetime(wiki_boj.index)
            wiki_boj = wiki_boj.sort_index()
        else:
            wiki_boj = None
    except Exception:
        wiki_boj = None

    all_dates = set()
    for df in prices.values():
        for dt in df.index:
            all_dates.add(dt)
    trading_days = sorted(all_dates)

    if len(trading_days) < 20:
        return

    risk_on = ["SOXX", "XLF"]
    risk_off = ["GDX", "SLV"]

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

        # USD/JPY direction
        fx_before = usdjpy[usdjpy.index <= day]
        if len(fx_before) < lookback + 1:
            continue

        fx_now = float(fx_before["Close"].iloc[-1])
        fx_past = float(fx_before["Close"].iloc[-lookback - 1])
        if fx_past == 0:
            continue

        fx_change = (fx_now - fx_past) / fx_past

        # BOJ attention
        boj_concern = False
        if wiki_boj is not None:
            wb = wiki_boj[wiki_boj.index <= day]
            if len(wb) >= 20:
                recent = float(wb.iloc[-5:].mean())
                avg = float(wb.iloc[-20:].mean())
                if avg > 0:
                    boj_concern = recent > avg * 1.5

        # Note: JPY=X is USD per 1 JPY, so HIGHER means yen strengthening
        # We want USD/JPY rising (yen weakening) = risk on
        # JPY=X rising = yen strengthening = risk OFF
        if fx_change < -0.003 and not boj_concern:
            # Yen weakening (JPY=X falling) = carry trade on = risk on
            candidates = [t for t in risk_on if t in prices]
        elif fx_change > 0.003 or boj_concern:
            # Yen strengthening (JPY=X rising) = carry unwind = risk off
            candidates = [t for t in risk_off if t in prices]
        else:
            candidates = [t for t in risk_on + risk_off if t in prices]

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
