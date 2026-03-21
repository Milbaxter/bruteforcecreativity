"""
Precious Metals Equity Rotation v2
Same rotation but with 10-day max hold forced re-entry and
cash circuit breaker when peak drawdown exceeds 10%.
v1 had 58% return but -37% drawdown.
"""

STRATEGY = {
    "name": "Precious Metals Equity v2",
    "hypothesis": "v1 returned 58.27% but drawdown hit -37.62% from silver volatility. "
                  "v2 adds: 1) 10-day max hold to force re-entry and reduce stale positions, "
                  "2) cash circuit breaker — if portfolio drops 10% from peak, switch to SHY "
                  "until momentum recovers. This should cap drawdown while keeping the alpha.",
    "universe": ["GLD", "SLV", "SPY", "SHY"],
    "entry": "Same momentum rotation, plus circuit breaker override to SHY on drawdown",
    "exit": "Rotate every 3 days, 10-day max hold, or circuit breaker to SHY",
    "position_size": "95% of cash into selected asset",
    "eccentricity": "Precious metals + equity rotation with dynamic drawdown control.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    import pandas as pd

    tickers = ["GLD", "SLV", "SPY", "SHY"]
    prices = {}
    for ticker in tickers:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            prices[ticker] = df

    if len(prices) < 3:
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

    LOOKBACK = 7
    ROTATION_DAYS = 3
    MAX_HOLD_DAYS = 10
    CIRCUIT_BREAKER_DD = -0.10  # go to cash if down 10% from peak
    RISK_ASSETS = ["GLD", "SLV", "SPY"]

    current_holding = None
    entry_date_ts = None
    last_rotation_idx = -ROTATION_DAYS
    peak_value = portfolio.cash
    in_circuit_breaker = False

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

        # Estimate current portfolio value
        current_value = portfolio.cash
        for t, shares in portfolio.positions.items():
            if t in prices:
                close_data = prices[t]["Close"].loc[:date_ts]
                if not close_data.empty:
                    current_value += shares * float(close_data.iloc[-1])

        # Track peak
        if current_value > peak_value:
            peak_value = current_value

        # Check circuit breaker
        if peak_value > 0:
            dd = (current_value - peak_value) / peak_value
            if dd <= CIRCUIT_BREAKER_DD and not in_circuit_breaker:
                # Trigger circuit breaker — go to cash
                if current_holding and portfolio.positions.get(current_holding, 0) > 0:
                    portfolio.sell(current_holding, all_shares=True, date=date_str)
                cash = portfolio.cash * 0.95
                if cash >= 100 and "SHY" in prices:
                    portfolio.buy("SHY", dollars=cash, date=date_str)
                    current_holding = "SHY"
                    entry_date_ts = date_ts
                    last_rotation_idx = i
                in_circuit_breaker = True
                continue
            elif dd > CIRCUIT_BREAKER_DD / 2:
                # Recovery — allow re-entry
                in_circuit_breaker = False

        if in_circuit_breaker:
            continue

        # Check max hold
        force_rotation = False
        if current_holding and entry_date_ts:
            days_held = (date_ts - entry_date_ts).days
            if days_held >= MAX_HOLD_DAYS:
                force_rotation = True

        if not force_rotation and i - last_rotation_idx < ROTATION_DAYS:
            continue
        if i < LOOKBACK:
            continue

        # Compute momentum for risk assets
        best_ticker = None
        best_momentum = -999

        for ticker in RISK_ASSETS:
            if ticker not in prices:
                continue
            close = prices[ticker]["Close"].loc[:date_ts]
            if len(close) < LOOKBACK + 1:
                continue
            mom = (float(close.iloc[-1]) - float(close.iloc[-LOOKBACK - 1])) / float(close.iloc[-LOOKBACK - 1])
            if mom > best_momentum:
                best_momentum = mom
                best_ticker = ticker

        if best_ticker is None:
            continue

        # If best momentum is negative, go to cash
        if best_momentum < 0:
            best_ticker = "SHY"

        if best_ticker != current_holding or force_rotation:
            if current_holding and portfolio.positions.get(current_holding, 0) > 0:
                portfolio.sell(current_holding, all_shares=True, date=date_str)

            cash = portfolio.cash * 0.95
            if cash >= 100 and best_ticker in prices:
                result = portfolio.buy(best_ticker, dollars=cash, date=date_str)
                if result:
                    current_holding = best_ticker
                    entry_date_ts = date_ts
                    last_rotation_idx = i

    if current_holding and trading_days:
        if portfolio.positions.get(current_holding, 0) > 0:
            portfolio.sell(current_holding, all_shares=True, date=trading_days[-1])
