"""
Multi-Asset Pullback Rotation
Combines pullback entry (proven winner) with multi-asset rotation (proven winner).
Buy whichever asset from GLD/QQQ/XLE pulls back most from its high, with momentum filter.
"""

STRATEGY = {
    "name": "Multi-Asset Pullback Rotation",
    "hypothesis": "Pullback entries on QQQ were a winner. GLD/QQQ/XLE rotation was a winner. "
                  "Combining both: wait for a pullback in any of the three assets, then enter "
                  "the one with best trailing momentum. This avoids buying at the top (pullback "
                  "entry) while staying in the strongest trend (momentum filter).",
    "universe": ["GLD", "QQQ", "XLE"],
    "entry": "When any asset pulls back 1.5%+ from its 10-day high AND has positive 20-day "
             "momentum, buy it. If multiple qualify, buy the one with strongest momentum.",
    "exit": "Sell when price recovers to within 0.3% of 10-day high, after 8 days max, "
            "or at -3% stop loss",
    "position_size": "90% of cash into selected asset",
    "eccentricity": "Cross-domain rotation with tactical pullback entry. Institutions rotate "
                    "on fixed schedules — this waits for the dip, which is too tactical for "
                    "large-scale asset allocation.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    import pandas as pd
    import numpy as np

    tickers = ["GLD", "QQQ", "XLE"]
    prices = {}
    for ticker in tickers:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            prices[ticker] = df

    if len(prices) < 3:
        return

    # Common dates
    common_dates = prices["GLD"].index
    for t in tickers[1:]:
        common_dates = common_dates.intersection(prices[t].index)
    trading_days = sorted([d.strftime("%Y-%m-%d") for d in common_dates
                           if start_date <= d.strftime("%Y-%m-%d") <= end_date])

    if len(trading_days) < 25:
        return

    # Parameters
    HIGH_LOOKBACK = 10
    PULLBACK_THRESHOLD = -0.015  # 1.5% pullback from high
    MOMENTUM_LOOKBACK = 20
    RECOVERY_THRESHOLD = -0.003  # within 0.3% of high
    MAX_HOLD_DAYS = 8
    STOP_LOSS = -0.03

    current_holding = None
    entry_date = None
    entry_price = None

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

        # Check exit conditions
        if current_holding:
            cur_data = prices[current_holding]["Close"].loc[:date_ts]
            if not cur_data.empty:
                cur_price = float(cur_data.iloc[-1])
                days_held = (date_ts - entry_date).days
                ret = (cur_price - entry_price) / entry_price

                # 10-day high for recovery check
                recent_high = float(cur_data.iloc[-HIGH_LOOKBACK:].max()) if len(cur_data) >= HIGH_LOOKBACK else float(cur_data.max())
                pct_from_high = (cur_price - recent_high) / recent_high

                should_exit = False
                if pct_from_high >= RECOVERY_THRESHOLD:  # recovered to near high
                    should_exit = True
                if days_held >= MAX_HOLD_DAYS:
                    should_exit = True
                if ret <= STOP_LOSS:
                    should_exit = True

                if should_exit:
                    portfolio.sell(current_holding, all_shares=True, date=date_str)
                    current_holding = None
                    entry_date = None
                    entry_price = None

        # Check entry conditions (only if not in position)
        if current_holding is not None:
            continue

        candidates = []
        for ticker in tickers:
            close = prices[ticker]["Close"].loc[:date_ts]
            if len(close) < max(HIGH_LOOKBACK, MOMENTUM_LOOKBACK) + 1:
                continue

            cur_price = float(close.iloc[-1])

            # 10-day high
            high_10d = float(close.iloc[-HIGH_LOOKBACK:].max())
            pullback = (cur_price - high_10d) / high_10d

            # 20-day momentum
            mom_20d = (cur_price - float(close.iloc[-MOMENTUM_LOOKBACK - 1])) / float(close.iloc[-MOMENTUM_LOOKBACK - 1])

            # Must be pulled back AND have positive momentum
            if pullback <= PULLBACK_THRESHOLD and mom_20d > 0:
                candidates.append((ticker, mom_20d, pullback))

        if not candidates:
            continue

        # Pick the one with strongest momentum
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_ticker = candidates[0][0]

        cash = portfolio.cash * 0.90
        if cash < 100:
            continue

        result = portfolio.buy(best_ticker, dollars=cash, date=date_str)
        if result:
            cur_data = prices[best_ticker]["Close"].loc[:date_ts]
            current_holding = best_ticker
            entry_date = date_ts
            entry_price = float(cur_data.iloc[-1])

    # Close remaining
    if current_holding and trading_days:
        portfolio.sell(current_holding, all_shares=True, date=trading_days[-1])
