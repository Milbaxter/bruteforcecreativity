"""
VIX VXN Divergence — when S&P 500 volatility (VIX) diverges from Nasdaq
volatility (VXN), it signals sector-specific stress vs broad market stress.

VIX > VXN: broad market fear (SPX more stressed than NASDAQ) = unusual = buy gold
VXN > VIX: tech-specific fear = tech overvalued relative to market = rotate out of tech

Combined with Wikipedia "Stock_market_crash" attention as panic gauge.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "VIX VXN Divergence",
    "hypothesis": "VIX and VXN usually move together. When they diverge, it signals sector-specific stress. VIX leading VXN means broad fear (buy safety). VXN leading VIX means tech-specific fear (avoid tech, buy financials/commodities). Wiki crash attention confirms retail panic.",
    "universe": ["SOXX", "XLF", "GDX", "SLV"],
    "entry": "VIX/VXN ratio > 1.05 (broad fear): buy GDX/SLV. VIX/VXN < 0.95 (tech fear): buy XLF. Otherwise: best momentum.",
    "exit": "Rotate every 5 trading days",
    "position_size": "100% in best momentum candidate per regime",
    "eccentricity": "Cross-volatility-index divergence is a signal retail traders never look at. The VIX/VXN ratio reveals whether fear is concentrated in tech or spread across the market.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch VIX and VXN
    try:
        vix_data = data_fetcher.get_prices("^VIX", start=start_date, end=end_date)
        vxn_data = data_fetcher.get_prices("^VXN", start=start_date, end=end_date)
    except Exception:
        return

    if isinstance(vix_data.columns, pd.MultiIndex):
        vix_data.columns = vix_data.columns.get_level_values(0)
    if isinstance(vxn_data.columns, pd.MultiIndex):
        vxn_data.columns = vxn_data.columns.get_level_values(0)

    if vix_data.empty or vxn_data.empty:
        return

    # Get trading assets
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

    # Wikipedia crash attention
    try:
        wiki_crash = data_fetcher.get_wikipedia_pageviews("Stock_market_crash")
        if wiki_crash is not None and not wiki_crash.empty:
            wiki_crash.index = pd.to_datetime(wiki_crash.index)
            wiki_crash = wiki_crash.sort_index()
        else:
            wiki_crash = None
    except Exception:
        wiki_crash = None

    # Compute VIX/VXN ratio on common dates
    common_vol = vix_data.index.intersection(vxn_data.index)
    if len(common_vol) < 15:
        return

    vol_ratio = vix_data.loc[common_vol, "Close"] / vxn_data.loc[common_vol, "Close"]

    all_dates = set()
    for df in prices.values():
        for dt in df.index:
            all_dates.add(dt)
    trading_days = sorted(all_dates)

    if len(trading_days) < 20:
        return

    current_holding = None
    last_rotation_idx = -999
    rotation_interval = 5

    for i, day in enumerate(trading_days):
        if i < 15:
            continue
        if i - last_rotation_idx < rotation_interval:
            continue

        date_str = day.strftime("%Y-%m-%d") if hasattr(day, 'strftime') else str(day)[:10]

        # Get VIX/VXN ratio
        vr_before = vol_ratio[vol_ratio.index <= day]
        if len(vr_before) < 5:
            continue

        # Average over last 5 days to smooth
        avg_ratio = float(vr_before.iloc[-5:].mean())

        # Wiki crash attention — extra caution signal
        crash_panic = False
        if wiki_crash is not None:
            wc = wiki_crash[wiki_crash.index <= day]
            if len(wc) >= 20:
                recent = float(wc.iloc[-5:].mean())
                historical = float(wc.iloc[-20:].mean())
                if historical > 0:
                    crash_panic = recent > historical * 1.5

        # Determine regime
        if avg_ratio > 1.05 or crash_panic:
            # Broad market fear or panic attention → safety
            candidates = ["GDX", "SLV"]
        elif avg_ratio < 0.95:
            # Tech-specific fear → avoid tech, buy financials
            candidates = ["XLF", "GDX"]
        else:
            # Normal → best momentum across all
            candidates = list(STRATEGY["universe"])

        candidates = [t for t in candidates if t in prices]
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
