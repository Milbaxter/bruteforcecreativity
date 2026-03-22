"""
Continued Claims Direction — use FRED continued unemployment claims (CCSA)
direction as an economic health signal for sector rotation.

Different from Claims Rotation (which uses initial claims ICSA).
Continued claims measure how many people remain unemployed, capturing
the economy's ability to reabsorb workers — a lagging but powerful signal.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Continued Claims Direction",
    "hypothesis": "Continued unemployment claims (CCSA) capture labor market healing/deterioration better than initial claims. Falling continued claims = recovery = growth assets outperform. Rising = stress = safety assets outperform.",
    "universe": ["SOXX", "XLF", "GLD", "GDX"],
    "entry": "Rotate into growth (SOXX/XLF best momentum) when 4-week CCSA trend is falling, safety (GLD/GDX best momentum) when rising",
    "exit": "Sell current position and rotate every 5 trading days based on updated signal",
    "position_size": "100% of capital in single best candidate per regime",
    "eccentricity": "Uses continued claims (not initial) as economic signal — a subtle distinction most quants ignore. Combined with momentum selection within regime buckets.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch continued claims from FRED
    try:
        ccsa = data_fetcher.get_fred_series("CCSA")
    except Exception:
        ccsa = None

    if ccsa is None or (hasattr(ccsa, 'empty') and ccsa.empty):
        # Fallback: use initial claims direction as proxy
        try:
            ccsa = data_fetcher.get_fred_series("ICNSA")  # not seasonally adjusted continued
        except Exception:
            return

    if ccsa is None or (hasattr(ccsa, 'empty') and ccsa.empty):
        return

    # Ensure it's a Series with datetime index
    if isinstance(ccsa, pd.DataFrame):
        ccsa = ccsa.iloc[:, 0]
    ccsa.index = pd.to_datetime(ccsa.index)
    ccsa = ccsa.sort_index()

    # Get price data for universe
    universe = STRATEGY["universe"]
    prices = {}
    for ticker in universe:
        try:
            df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            prices[ticker] = df
        except Exception:
            continue

    if len(prices) < 2:
        return

    # Get common trading days
    all_dates = set()
    for ticker, df in prices.items():
        for dt in df.index:
            all_dates.add(dt)
    trading_days = sorted(all_dates)

    if len(trading_days) < 30:
        return

    growth_tickers = ["SOXX", "XLF"]
    safety_tickers = ["GLD", "GDX"]

    current_holding = None
    last_rotation_idx = -999
    rotation_interval = 5  # trading days

    for i, day in enumerate(trading_days):
        if i < 20:  # need lookback
            continue

        # Only check rotation every N days
        if i - last_rotation_idx < rotation_interval:
            continue

        date_str = day.strftime("%Y-%m-%d") if hasattr(day, 'strftime') else str(day)[:10]

        # Get CCSA direction: compare latest available value to 4-week-ago value
        ccsa_before = ccsa[ccsa.index <= day]
        if len(ccsa_before) < 5:
            continue

        current_ccsa = ccsa_before.iloc[-1]
        # 4 weeks back (weekly data, so ~4 entries back)
        lookback_idx = max(0, len(ccsa_before) - 5)
        past_ccsa = ccsa_before.iloc[lookback_idx]

        if past_ccsa == 0:
            continue

        ccsa_change = (current_ccsa - past_ccsa) / past_ccsa

        # Determine regime
        if ccsa_change < -0.01:  # claims falling > 1% = recovery
            candidates = [t for t in growth_tickers if t in prices]
        elif ccsa_change > 0.01:  # claims rising > 1% = stress
            candidates = [t for t in safety_tickers if t in prices]
        else:
            # Neutral — pick best momentum across all
            candidates = [t for t in universe if t in prices]

        if not candidates:
            continue

        # Pick best 5d momentum among candidates
        best_ticker = None
        best_momentum = -999

        for ticker in candidates:
            df = prices[ticker]
            df_before = df[df.index <= day]
            if len(df_before) < 6:
                continue
            close_now = float(df_before["Close"].iloc[-1])
            close_5d = float(df_before["Close"].iloc[-6])
            if close_5d > 0:
                momentum = (close_now - close_5d) / close_5d
                if momentum > best_momentum:
                    best_momentum = momentum
                    best_ticker = ticker

        if best_ticker is None:
            continue

        # Rotate if needed
        if best_ticker != current_holding:
            # Sell current
            if current_holding and current_holding in portfolio.positions:
                portfolio.sell(current_holding, all_shares=True, date=date_str)

            # Buy new
            portfolio.buy(best_ticker, dollars=portfolio.cash * 0.98, date=date_str)
            current_holding = best_ticker
            last_rotation_idx = i

    # Close any open position at end
    if current_holding and current_holding in portfolio.positions:
        end_str = trading_days[-1].strftime("%Y-%m-%d") if hasattr(trading_days[-1], 'strftime') else str(trading_days[-1])[:10]
        portfolio.sell(current_holding, all_shares=True, date=end_str)
