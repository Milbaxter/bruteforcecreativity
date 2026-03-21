"""
Gold Miners Momentum
When gold (GLD) has positive momentum, buy gold miners (GDX/GDXJ) for
leveraged exposure to the gold trend. Miners amplify gold moves 2-3x.
"""

STRATEGY = {
    "name": "Gold Miners Momentum",
    "hypothesis": "Gold miners (GDX) have 2-3x beta to gold price moves. When gold has positive "
                  "5-day momentum, buying miners captures the leveraged upside. Switch to GLD "
                  "when momentum is flat (safety), and cash/TLT when momentum is negative.",
    "universe": ["GLD", "GDX", "GDXJ", "TLT"],
    "entry": "Strong gold momentum (5d > 1%): buy GDX+GDXJ. "
             "Mild positive (0-1%): buy GLD. "
             "Negative: buy TLT or cash.",
    "exit": "Rotate every 3 trading days based on current gold momentum regime",
    "position_size": "90% of cash into selected asset(s)",
    "eccentricity": "Using gold ETFs to signal gold miner entries — cross-asset leverage "
                    "play. Too volatile for institutional risk limits but captures the "
                    "miner beta amplification effect at small scale.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    import pandas as pd
    import numpy as np

    tickers = ["GLD", "GDX", "GDXJ", "TLT"]
    prices = {}
    for ticker in tickers:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            prices[ticker] = df

    if "GLD" not in prices or "GDX" not in prices:
        return

    # Common dates
    common_dates = prices["GLD"].index
    for t in prices:
        common_dates = common_dates.intersection(prices[t].index)

    trading_days = sorted([d.strftime("%Y-%m-%d") for d in common_dates
                           if start_date <= d.strftime("%Y-%m-%d") <= end_date])

    if len(trading_days) < 15:
        return

    # Parameters
    MOMENTUM_LOOKBACK = 5
    STRONG_THRESHOLD = 0.01  # 1% gold momentum = strong
    ROTATION_DAYS = 3

    current_holdings = []  # list of tickers currently held
    last_rotation_idx = -ROTATION_DAYS

    def get_gold_momentum(date_ts):
        close = prices["GLD"]["Close"].loc[:date_ts]
        if len(close) < MOMENTUM_LOOKBACK + 1:
            return 0
        return (float(close.iloc[-1]) - float(close.iloc[-MOMENTUM_LOOKBACK - 1])) / float(close.iloc[-MOMENTUM_LOOKBACK - 1])

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

        if i - last_rotation_idx < ROTATION_DAYS:
            continue

        gold_mom = get_gold_momentum(date_ts)

        # Determine target allocation
        if gold_mom > STRONG_THRESHOLD:
            targets = ["GDX", "GDXJ"]  # leveraged gold exposure
        elif gold_mom > 0:
            targets = ["GLD"]  # mild gold exposure
        else:
            targets = ["TLT"]  # defensive

        # Check if we need to rotate
        if set(targets) != set(current_holdings):
            # Sell current
            for ticker in current_holdings:
                if portfolio.positions.get(ticker, 0) > 0:
                    portfolio.sell(ticker, all_shares=True, date=date_str)

            # Buy targets
            cash = portfolio.cash * 0.90
            per_target = cash / len(targets)

            new_holdings = []
            for ticker in targets:
                if ticker in prices and per_target >= 50:
                    result = portfolio.buy(ticker, dollars=per_target, date=date_str)
                    if result:
                        new_holdings.append(ticker)

            current_holdings = new_holdings
            last_rotation_idx = i

    # Close remaining
    if trading_days:
        last_day = trading_days[-1]
        for ticker in current_holdings:
            if portfolio.positions.get(ticker, 0) > 0:
                portfolio.sell(ticker, all_shares=True, date=last_day)
