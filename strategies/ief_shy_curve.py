"""
IEF SHY Yield Curve — IEF/SHY ratio direction as a yield curve signal
using ETF prices instead of FRED rate data.

When IEF outperforms SHY (long bonds outperforming short bonds),
yields are falling = curve steepening = growth-friendly.
When SHY outperforms IEF, short rates holding while long rates rise
= curve flattening = tightening.

Different from yield spread rotation (which used FRED 10Y-3M data).
Combined with Wikipedia "Federal_Reserve" attention.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "IEF SHY Yield Curve ETF",
    "hypothesis": "The IEF/SHY ratio is a market-priced yield curve measure. When long bonds outperform short bonds (ratio rising), the curve is steepening = monetary easing expected = growth assets benefit. When short bonds lead (ratio falling), tightening expectations = safety.",
    "universe": ["IEF", "SHY", "SOXX", "GDX", "SLV", "XLF"],
    "entry": "IEF/SHY rising (7d): buy SOXX/XLF. Ratio falling + Fed wiki attention: buy GDX/SLV.",
    "exit": "Rotate every 5 trading days",
    "position_size": "100% in best 5d momentum candidate per regime",
    "eccentricity": "Using bond ETF relative performance as a yield curve proxy — avoids FRED API delays and captures intraday curve moves that the rates data misses.",
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

    if "IEF" not in prices or "SHY" not in prices or len(prices) < 4:
        return

    ief = prices["IEF"]
    shy = prices["SHY"]
    common = ief.index.intersection(shy.index)
    if len(common) < 20:
        return

    ratio = ief.loc[common, "Close"] / shy.loc[common, "Close"]

    try:
        wiki_fed = data_fetcher.get_wikipedia_pageviews("Federal_Reserve")
        if wiki_fed is not None and not wiki_fed.empty:
            wiki_fed.index = pd.to_datetime(wiki_fed.index)
            wiki_fed = wiki_fed.sort_index()
        else:
            wiki_fed = None
    except Exception:
        wiki_fed = None

    all_dates = set()
    for df in prices.values():
        for dt in df.index:
            all_dates.add(dt)
    trading_days = sorted(all_dates)

    if len(trading_days) < 20:
        return

    easing_tickers = ["SOXX", "XLF"]
    tightening_tickers = ["GDX", "SLV"]

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

        fed_attention = False
        if wiki_fed is not None:
            wf = wiki_fed[wiki_fed.index <= day]
            if len(wf) >= 20:
                recent = float(wf.iloc[-5:].mean())
                avg = float(wf.iloc[-20:].mean())
                if avg > 0:
                    fed_attention = recent > avg * 1.3

        if ratio_change > 0.001:
            candidates = [t for t in easing_tickers if t in prices]
        elif ratio_change < -0.001 or fed_attention:
            candidates = [t for t in tightening_tickers if t in prices]
        else:
            candidates = [t for t in easing_tickers + tightening_tickers if t in prices]

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
