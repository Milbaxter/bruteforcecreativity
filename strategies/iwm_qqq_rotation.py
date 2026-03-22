"""
IWM QQQ Rotation — IWM/QQQ ratio direction as a broadening vs narrowing
market breadth signal. When small caps lead large caps (IWM/QQQ rising),
the rally is broadening = healthy. When QQQ leads (ratio falling),
money is concentrating into mega-cap = fragile.

Different from IWM/SPY Risk Appetite (which used IWM/SPY + crypto fear).
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "IWM QQQ Rotation",
    "hypothesis": "When IWM outperforms QQQ, money is flowing into riskier small-caps = broad risk appetite. This favors cyclical/value sectors. When QQQ outperforms IWM, mega-cap safety trade = fragile rally favoring gold/defensive positions.",
    "universe": ["IWM", "QQQ", "XLF", "GDX", "SLV", "XLE"],
    "entry": "IWM/QQQ ratio rising (7d): buy XLF/XLE (cyclical). Ratio falling: buy GDX/SLV (defensive). Momentum selects best in bucket.",
    "exit": "Rotate every 5 trading days",
    "position_size": "100% in single best candidate",
    "eccentricity": "Small-cap/large-cap relative strength is a breadth indicator most retail traders ignore. When everyone is in NVDA and AAPL, the small-cap signal reveals when the music stops.",
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

    if "IWM" not in prices or "QQQ" not in prices:
        return
    if len(prices) < 4:
        return

    # Compute IWM/QQQ ratio
    iwm = prices["IWM"]
    qqq = prices["QQQ"]
    common = iwm.index.intersection(qqq.index)
    if len(common) < 20:
        return

    ratio = iwm.loc[common, "Close"] / qqq.loc[common, "Close"]

    # Wikipedia "Stock_market" attention as secondary signal
    try:
        wiki = data_fetcher.get_wikipedia_pageviews("Stock_market")
        if wiki is not None and not wiki.empty:
            wiki.index = pd.to_datetime(wiki.index)
            wiki = wiki.sort_index()
        else:
            wiki = None
    except Exception:
        wiki = None

    all_dates = set()
    for df in prices.values():
        for dt in df.index:
            all_dates.add(dt)
    trading_days = sorted(all_dates)

    if len(trading_days) < 20:
        return

    broadening_tickers = ["XLF", "XLE"]  # cyclicals benefit from broad rally
    narrowing_tickers = ["GDX", "SLV"]  # defensive when narrow rally

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

        # Wiki attention as confirmation — high attention during narrowing = danger
        wiki_high = False
        if wiki is not None:
            wb = wiki[wiki.index <= day]
            if len(wb) >= 20:
                recent = float(wb.iloc[-5:].mean())
                avg = float(wb.iloc[-20:].mean())
                if avg > 0:
                    wiki_high = recent > avg * 1.3

        # Determine regime
        if ratio_change > 0.005:
            # Small caps leading = broadening rally
            candidates = [t for t in broadening_tickers if t in prices]
        elif ratio_change < -0.005:
            # Large caps leading = narrowing rally
            if wiki_high:
                # High stock market attention + narrowing = extra caution
                candidates = [t for t in narrowing_tickers if t in prices]
            else:
                candidates = [t for t in narrowing_tickers if t in prices]
        else:
            candidates = [t for t in broadening_tickers + narrowing_tickers if t in prices]

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
