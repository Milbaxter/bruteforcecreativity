"""
Value Growth Regime — VTV/VUG ratio (value vs growth) direction as a
sector rotation regime signal.

When value outperforms growth (ratio rising), the market favors earnings
over innovation = commodity/financial rotation.
When growth outperforms value (ratio falling), innovation leads = SOXX.

Combined with crypto fear/greed as risk filter.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Value Growth Regime",
    "hypothesis": "The VTV/VUG ratio captures the fundamental market rotation between value and growth styles. When value leads, it signals a mature cycle favoring commodity producers and financials. When growth leads, innovation and AI spending are driving returns.",
    "universe": ["VTV", "VUG", "SOXX", "GDX", "SLV", "XLF"],
    "entry": "VTV/VUG ratio rising (7d): buy XLF/GDX/SLV (value/commodity play). Ratio falling: buy SOXX (growth play).",
    "exit": "Rotate every 5 trading days",
    "position_size": "100% in best 5d momentum candidate per regime",
    "eccentricity": "Style factor rotation as a macro signal — most retail traders don't track value/growth relative performance. The VTV/VUG ratio is a clean, daily measure of where institutional money is flowing.",
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

    if "VTV" not in prices or "VUG" not in prices or len(prices) < 4:
        return

    # Compute VTV/VUG ratio
    vtv = prices["VTV"]
    vug = prices["VUG"]
    common = vtv.index.intersection(vug.index)
    if len(common) < 20:
        return

    ratio = vtv.loc[common, "Close"] / vug.loc[common, "Close"]

    # Crypto fear/greed
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

    value_tickers = ["XLF", "GDX", "SLV"]
    growth_tickers = ["SOXX"]

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

        # Crypto fear filter
        fg_val = 50
        if fear_greed is not None and not fear_greed.empty:
            fg_before = fear_greed[fear_greed.index <= day]
            if len(fg_before) > 0:
                fg_val = float(fg_before.iloc[-1])
        if fg_val < 15:
            continue

        # VTV/VUG ratio direction
        ratio_before = ratio[ratio.index <= day]
        if len(ratio_before) < lookback + 1:
            continue

        current_r = float(ratio_before.iloc[-1])
        past_r = float(ratio_before.iloc[-lookback - 1])
        if past_r == 0:
            continue

        ratio_change = (current_r - past_r) / past_r

        # Determine regime
        if ratio_change > 0.003:
            # Value leading = commodity/financial mode
            candidates = [t for t in value_tickers if t in prices]
        elif ratio_change < -0.003:
            # Growth leading = innovation mode
            candidates = [t for t in growth_tickers if t in prices]
        else:
            candidates = [t for t in value_tickers + growth_tickers if t in prices]

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
