"""
Dual Momentum Global
Gary Antonacci's dual momentum at fast timeframe: combine absolute momentum
(is it going up?) with relative momentum (which is going up most?).
Rotate across SPY/EFA/GLD/TLT every 5 days.
"""

STRATEGY = {
    "name": "Dual Momentum Global",
    "hypothesis": "Dual momentum combines absolute momentum (trend filter) with relative "
                  "momentum (cross-sectional ranking). Only buy assets with positive absolute "
                  "momentum, then pick the strongest. This avoids buying falling assets while "
                  "riding the strongest trend. Applied at 5-day frequency for fast rotation.",
    "universe": ["SPY", "EFA", "GLD", "TLT", "SHY"],
    "entry": "Every 5 days: rank SPY/EFA/GLD/TLT by 10-day momentum. "
             "Buy the top-ranked IF it has positive absolute momentum. "
             "If none positive, buy SHY (cash equivalent).",
    "exit": "Re-evaluate every 5 trading days and rotate",
    "position_size": "95% of cash into selected asset",
    "eccentricity": "Academic dual momentum framework applied at swing-trade frequency. "
                    "Antonacci's version uses monthly — this uses 5-day periods, which is "
                    "too fast for institutions but captures trend shifts quicker.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    import pandas as pd

    tickers = ["SPY", "EFA", "GLD", "TLT", "SHY"]
    prices = {}
    for ticker in tickers:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            prices[ticker] = df

    if len(prices) < 4:
        return

    # Common dates
    common_dates = None
    for df in prices.values():
        if common_dates is None:
            common_dates = df.index
        else:
            common_dates = common_dates.intersection(df.index)

    trading_days = sorted([d.strftime("%Y-%m-%d") for d in common_dates
                           if start_date <= d.strftime("%Y-%m-%d") <= end_date])

    if len(trading_days) < 20:
        return

    # Parameters
    MOMENTUM_LOOKBACK = 10
    ROTATION_DAYS = 5
    RISK_ASSETS = ["SPY", "EFA", "GLD", "TLT"]  # SHY is the cash fallback

    current_holding = None
    last_rotation_idx = -ROTATION_DAYS

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

        if i - last_rotation_idx < ROTATION_DAYS:
            continue
        if i < MOMENTUM_LOOKBACK:
            continue

        # Compute absolute + relative momentum for each risk asset
        momentums = {}
        for ticker in RISK_ASSETS:
            if ticker not in prices:
                continue
            close = prices[ticker]["Close"].loc[:date_ts]
            if len(close) < MOMENTUM_LOOKBACK + 1:
                continue
            mom = (float(close.iloc[-1]) - float(close.iloc[-MOMENTUM_LOOKBACK - 1])) / float(close.iloc[-MOMENTUM_LOOKBACK - 1])
            momentums[ticker] = mom

        if not momentums:
            continue

        # Filter for positive absolute momentum
        positive = {t: m for t, m in momentums.items() if m > 0}

        if positive:
            # Pick the strongest relative momentum
            target = max(positive, key=positive.get)
        else:
            # All negative — go to cash equivalent (SHY)
            target = "SHY"

        # Rotate if needed
        if target != current_holding:
            if current_holding and portfolio.positions.get(current_holding, 0) > 0:
                portfolio.sell(current_holding, all_shares=True, date=date_str)

            cash = portfolio.cash * 0.95
            if cash >= 100 and target in prices:
                result = portfolio.buy(target, dollars=cash, date=date_str)
                if result:
                    current_holding = target
                    last_rotation_idx = i

    # Close remaining
    if current_holding and trading_days:
        if portfolio.positions.get(current_holding, 0) > 0:
            portfolio.sell(current_holding, all_shares=True, date=trading_days[-1])
