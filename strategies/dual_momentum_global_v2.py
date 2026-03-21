"""
Dual Momentum Global v2
Faster rotation (3-day) + 7-day lookback + stop loss protection.
Tuned from v1 which was close to winner (Sharpe 0.85, needed > 1.0).
"""

STRATEGY = {
    "name": "Dual Momentum Global v2",
    "hypothesis": "v1 hit 20.99% return, +4.67% vs SPY, profit factor 2.06 but Sharpe 0.85. "
                  "This v2 uses 3-day rotation (faster exit from losers), 7-day momentum lookback "
                  "(faster signal), and -3% stop loss to cut drawdowns and improve risk-adjusted returns.",
    "universe": ["SPY", "EFA", "GLD", "TLT", "SHY"],
    "entry": "Every 3 days: rank SPY/EFA/GLD/TLT by 7-day momentum. "
             "Buy top-ranked if positive absolute momentum. Else SHY.",
    "exit": "Rotate every 3 days, or -3% stop loss triggers immediate rotation",
    "position_size": "95% of cash into selected asset",
    "eccentricity": "Fast dual momentum with stop loss. Academic framework at swing-trade speed.",
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

    common_dates = None
    for df in prices.values():
        if common_dates is None:
            common_dates = df.index
        else:
            common_dates = common_dates.intersection(df.index)

    trading_days = sorted([d.strftime("%Y-%m-%d") for d in common_dates
                           if start_date <= d.strftime("%Y-%m-%d") <= end_date])

    if len(trading_days) < 15:
        return

    MOMENTUM_LOOKBACK = 7
    ROTATION_DAYS = 3
    STOP_LOSS = -0.03
    RISK_ASSETS = ["SPY", "EFA", "GLD", "TLT"]

    current_holding = None
    entry_price = None
    last_rotation_idx = -ROTATION_DAYS

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

        # Check stop loss
        if current_holding and entry_price:
            if current_holding in prices:
                cur_data = prices[current_holding]["Close"].loc[:date_ts]
                if not cur_data.empty:
                    cur_price = float(cur_data.iloc[-1])
                    ret = (cur_price - entry_price) / entry_price
                    if ret <= STOP_LOSS:
                        portfolio.sell(current_holding, all_shares=True, date=date_str)
                        current_holding = None
                        entry_price = None
                        last_rotation_idx = i

        # Only rotate every N days
        if i - last_rotation_idx < ROTATION_DAYS:
            continue
        if i < MOMENTUM_LOOKBACK:
            continue

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

        positive = {t: m for t, m in momentums.items() if m > 0}

        if positive:
            target = max(positive, key=positive.get)
        else:
            target = "SHY"

        if target != current_holding:
            if current_holding and portfolio.positions.get(current_holding, 0) > 0:
                portfolio.sell(current_holding, all_shares=True, date=date_str)

            cash = portfolio.cash * 0.95
            if cash >= 100 and target in prices:
                result = portfolio.buy(target, dollars=cash, date=date_str)
                if result:
                    cur_data = prices[target]["Close"].loc[:date_ts]
                    entry_price = float(cur_data.iloc[-1])
                    current_holding = target
                    last_rotation_idx = i

    if current_holding and trading_days:
        if portfolio.positions.get(current_holding, 0) > 0:
            portfolio.sell(current_holding, all_shares=True, date=trading_days[-1])
