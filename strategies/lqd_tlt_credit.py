"""
LQD TLT Credit Preference — LQD/TLT ratio direction (investment grade
corporate bonds vs treasuries) as an institutional risk appetite signal.

When LQD outperforms TLT, institutional investors prefer corporate credit
over sovereign safety = risk on. Different from HYG/TLT (which used junk
bonds) — LQD captures investment-grade sentiment, a cleaner signal.

Combined with Wikipedia "bond_market" attention as awareness filter.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "LQD TLT Credit Preference",
    "hypothesis": "The LQD/TLT ratio is a cleaner risk signal than HYG/TLT because investment-grade bonds reflect institutional sentiment without junk bond distortions. When institutions prefer IG credit over treasuries, they're confident in corporate earnings = growth assets win.",
    "universe": ["LQD", "TLT", "SOXX", "GDX", "SLV", "XLF"],
    "entry": "LQD/TLT rising (7d): buy SOXX/XLF. Ratio falling: buy GDX/SLV.",
    "exit": "Rotate every 5 trading days",
    "position_size": "100% in best 5d momentum candidate per regime",
    "eccentricity": "Investment-grade credit preference as a macro signal — even many professional equity traders don't monitor IG bond flows. The LQD/TLT ratio reveals where the smart money is positioned.",
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

    if "LQD" not in prices or "TLT" not in prices or len(prices) < 4:
        return

    lqd = prices["LQD"]
    tlt = prices["TLT"]
    common = lqd.index.intersection(tlt.index)
    if len(common) < 20:
        return

    ratio = lqd.loc[common, "Close"] / tlt.loc[common, "Close"]

    try:
        wiki_bond = data_fetcher.get_wikipedia_pageviews("Bond_market")
        if wiki_bond is not None and not wiki_bond.empty:
            wiki_bond.index = pd.to_datetime(wiki_bond.index)
            wiki_bond = wiki_bond.sort_index()
        else:
            wiki_bond = None
    except Exception:
        wiki_bond = None

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

        ratio_before = ratio[ratio.index <= day]
        if len(ratio_before) < lookback + 1:
            continue

        current_r = float(ratio_before.iloc[-1])
        past_r = float(ratio_before.iloc[-lookback - 1])
        if past_r == 0:
            continue

        ratio_change = (current_r - past_r) / past_r

        bond_concern = False
        if wiki_bond is not None:
            wb = wiki_bond[wiki_bond.index <= day]
            if len(wb) >= 20:
                recent = float(wb.iloc[-5:].mean())
                avg = float(wb.iloc[-20:].mean())
                if avg > 0:
                    bond_concern = recent > avg * 1.5

        if ratio_change > 0.001 and not bond_concern:
            candidates = [t for t in risk_on if t in prices]
        elif ratio_change < -0.001 or bond_concern:
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
