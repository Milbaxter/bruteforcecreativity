"""
ARKK Innovation Signal — ARKK ETF direction as a bellwether for
speculative growth appetite. When ARKK leads, risk appetite is high.
When ARKK lags, speculative excess is unwinding.

Combined with Wikipedia "Artificial_intelligence" attention as tech hype gauge.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "ARKK Innovation Signal",
    "hypothesis": "ARKK captures the most speculative growth stocks. Its momentum direction signals whether the market rewards or punishes innovation risk. When ARKK trends up and AI attention is rising, growth assets benefit. When ARKK trends down, safety wins.",
    "universe": ["ARKK", "SOXX", "GDX", "SLV", "XLF"],
    "entry": "ARKK 10d momentum positive + AI wiki attention not declining: buy SOXX/XLF. ARKK momentum negative: buy GDX/SLV.",
    "exit": "Rotate every 5 trading days",
    "position_size": "100% in best 5d momentum candidate per regime",
    "eccentricity": "Using Cathie Wood's ARKK as a macro sentiment gauge — it's the retail investor's barometer for innovation risk. Institutions won't publicly admit to watching ARKK for signals.",
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

    if "ARKK" not in prices or len(prices) < 4:
        return

    # Wikipedia AI attention
    try:
        wiki_ai = data_fetcher.get_wikipedia_pageviews("Artificial_intelligence")
        if wiki_ai is not None and not wiki_ai.empty:
            wiki_ai.index = pd.to_datetime(wiki_ai.index)
            wiki_ai = wiki_ai.sort_index()
        else:
            wiki_ai = None
    except Exception:
        wiki_ai = None

    all_dates = set()
    for df in prices.values():
        for dt in df.index:
            all_dates.add(dt)
    trading_days = sorted(all_dates)

    if len(trading_days) < 30:
        return

    growth_tickers = ["SOXX", "XLF"]
    safety_tickers = ["GDX", "SLV"]

    current_holding = None
    last_rotation_idx = -999
    rotation_interval = 5
    lookback = 10

    for i, day in enumerate(trading_days):
        if i < lookback + 5:
            continue
        if i - last_rotation_idx < rotation_interval:
            continue

        date_str = day.strftime("%Y-%m-%d") if hasattr(day, 'strftime') else str(day)[:10]

        # ARKK momentum
        arkk = prices["ARKK"]
        arkk_before = arkk[arkk.index <= day]
        if len(arkk_before) < lookback + 1:
            continue

        arkk_now = float(arkk_before["Close"].iloc[-1])
        arkk_past = float(arkk_before["Close"].iloc[-lookback - 1])
        if arkk_past == 0:
            continue

        arkk_mom = (arkk_now - arkk_past) / arkk_past

        # AI wiki attention direction
        ai_rising = True  # default
        if wiki_ai is not None:
            wa = wiki_ai[wiki_ai.index <= day]
            if len(wa) >= 14:
                recent = float(wa.iloc[-7:].mean())
                past = float(wa.iloc[-14:-7].mean())
                if past > 0:
                    ai_rising = recent >= past * 0.85

        # Determine regime
        if arkk_mom > 0.01 and ai_rising:
            candidates = [t for t in growth_tickers if t in prices]
        elif arkk_mom < -0.01:
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
