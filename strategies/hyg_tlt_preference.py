"""
HYG TLT Preference — HYG/TLT ratio direction captures the bond market's
preference between corporate credit and sovereign safety.

When HYG outperforms TLT (ratio rising), the bond market is risk-seeking
= growth assets benefit.
When TLT outperforms HYG (ratio falling), flight to quality = safety mode.

Different from HY credit spread (spread level) and HYG Credit Trend (HYG alone).
The RATIO is what matters — it captures relative preference, not absolute moves.
Combined with Wikipedia "credit_rating" attention.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "HYG TLT Preference",
    "hypothesis": "The HYG/TLT ratio is the bond market's real-time risk appetite vote. When investors prefer corporate bonds over treasuries, they're confident in corporate earnings = growth. When they flee to treasuries, fear dominates. The bond market is often right before equities react.",
    "universe": ["HYG", "TLT", "SOXX", "GDX", "SLV", "XLF"],
    "entry": "HYG/TLT rising (7d): buy SOXX/XLF. Ratio falling + credit rating wiki attention: buy GDX/SLV.",
    "exit": "Rotate every 5 trading days",
    "position_size": "100% in best 5d momentum candidate per regime",
    "eccentricity": "The corporate-treasury bond preference ratio reveals institutional positioning before equity markets price it in. Retail traders watch stock prices, smart money watches bond spreads.",
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

    if "HYG" not in prices or "TLT" not in prices or len(prices) < 4:
        return

    hyg = prices["HYG"]
    tlt = prices["TLT"]
    common = hyg.index.intersection(tlt.index)
    if len(common) < 20:
        return

    ratio = hyg.loc[common, "Close"] / tlt.loc[common, "Close"]

    try:
        wiki_cr = data_fetcher.get_wikipedia_pageviews("Credit_rating")
        if wiki_cr is not None and not wiki_cr.empty:
            wiki_cr.index = pd.to_datetime(wiki_cr.index)
            wiki_cr = wiki_cr.sort_index()
        else:
            wiki_cr = None
    except Exception:
        wiki_cr = None

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

        credit_concern = False
        if wiki_cr is not None:
            wc = wiki_cr[wiki_cr.index <= day]
            if len(wc) >= 20:
                recent = float(wc.iloc[-5:].mean())
                avg = float(wc.iloc[-20:].mean())
                if avg > 0:
                    credit_concern = recent > avg * 1.4

        if ratio_change > 0.002 and not credit_concern:
            candidates = [t for t in risk_on if t in prices]
        elif ratio_change < -0.002 or credit_concern:
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
