"""
Precious Metals + Equity Rotation
Rotate between GLD, SLV, and SPY based on 7-day momentum.
Silver adds leveraged gold exposure + industrial demand component.
No stop loss — let momentum do the work.
"""

STRATEGY = {
    "name": "Precious Metals Equity Rotation",
    "hypothesis": "Gold and silver are correlated but silver has higher beta — it moves more in "
                  "both directions. When precious metals are trending, silver captures more upside. "
                  "When equities lead, SPY captures the trend. Rotate every 3 days into the "
                  "7-day momentum leader. No stop losses — the rotation IS the risk management.",
    "universe": ["GLD", "SLV", "SPY"],
    "entry": "Every 3 days, buy the asset with highest 7-day return",
    "exit": "Rotate out when another asset has higher momentum",
    "position_size": "95% of cash into selected asset",
    "eccentricity": "Silver as a gold-beta amplifier in a rotation strategy. SLV gives more "
                    "upside when gold is trending but more downside protection via SPY fallback.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    import pandas as pd

    tickers = ["GLD", "SLV", "SPY"]
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

    current_holding = None
    last_rotation_idx = -ROTATION_DAYS

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

        if i - last_rotation_idx < ROTATION_DAYS:
            continue
        if i < LOOKBACK:
            continue

        # Compute momentum for each asset
        best_ticker = None
        best_momentum = -999

        for ticker in tickers:
            close = prices[ticker]["Close"].loc[:date_ts]
            if len(close) < LOOKBACK + 1:
                continue
            mom = (float(close.iloc[-1]) - float(close.iloc[-LOOKBACK - 1])) / float(close.iloc[-LOOKBACK - 1])
            if mom > best_momentum:
                best_momentum = mom
                best_ticker = ticker

        if best_ticker is None:
            continue

        if best_ticker != current_holding:
            if current_holding and portfolio.positions.get(current_holding, 0) > 0:
                portfolio.sell(current_holding, all_shares=True, date=date_str)

            cash = portfolio.cash * 0.95
            if cash >= 100:
                result = portfolio.buy(best_ticker, dollars=cash, date=date_str)
                if result:
                    current_holding = best_ticker
                    last_rotation_idx = i

    if current_holding and trading_days:
        if portfolio.positions.get(current_holding, 0) > 0:
            portfolio.sell(current_holding, all_shares=True, date=trading_days[-1])
