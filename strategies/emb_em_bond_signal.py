"""
EMB EM Bond Signal — iShares EM Bond ETF (EMB) direction as a global
risk appetite signal for sector rotation.

When EM bonds trend up, global capital flows are healthy = risk on.
When EM bonds trend down, capital fleeing EM = risk off.
Combined with Wikipedia "emerging_market" attention as confirmation.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "EMB EM Bond Signal",
    "hypothesis": "EM bonds (EMB) are the canary in the coal mine for global risk appetite. When EMB trends up, carry trade is alive and risk assets thrive. When EMB trends down, dollar strength and EM stress predict broader risk-off. More sensitive than US credit spreads.",
    "universe": ["EMB", "SOXX", "GDX", "SLV", "XLF"],
    "entry": "EMB 7d momentum positive + wiki EM not spiking in panic: buy SOXX/XLF. EMB negative: buy GDX/SLV.",
    "exit": "Rotate every 5 trading days",
    "position_size": "100% in best 5d momentum candidate per regime",
    "eccentricity": "EM bond ETF as a macro signal for US sector rotation — most retail traders watch VIX or treasury yields, not emerging market debt flows.",
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

    if "EMB" not in prices or len(prices) < 4:
        return

    # Wikipedia EM attention
    try:
        wiki_em = data_fetcher.get_wikipedia_pageviews("Emerging_market")
        if wiki_em is not None and not wiki_em.empty:
            wiki_em.index = pd.to_datetime(wiki_em.index)
            wiki_em = wiki_em.sort_index()
        else:
            wiki_em = None
    except Exception:
        wiki_em = None

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

        # EMB direction
        emb = prices["EMB"]
        emb_before = emb[emb.index <= day]
        if len(emb_before) < lookback + 1:
            continue

        emb_now = float(emb_before["Close"].iloc[-1])
        emb_past = float(emb_before["Close"].iloc[-lookback - 1])
        if emb_past == 0:
            continue

        emb_mom = (emb_now - emb_past) / emb_past

        # Wiki EM attention — rising attention = concern
        em_concern = False
        if wiki_em is not None:
            we = wiki_em[wiki_em.index <= day]
            if len(we) >= 20:
                recent = float(we.iloc[-5:].mean())
                avg = float(we.iloc[-20:].mean())
                if avg > 0:
                    em_concern = recent > avg * 1.4

        # Determine regime
        if emb_mom > 0.002 and not em_concern:
            candidates = [t for t in growth_tickers if t in prices]
        elif emb_mom < -0.002 or em_concern:
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
