"""
Sector Relative Strength Rotation
Rotate between sector ETFs based on 5-day relative strength vs SPY.
Buy the sector outperforming SPY the most, sell on underperformance.
"""

STRATEGY = {
    "name": "Sector Relative Strength",
    "hypothesis": "Sector leadership persists for 3-7 days as institutional flows rotate into "
                  "hot sectors. By measuring 5-day relative strength vs SPY, we can ride sector "
                  "momentum. Rotate every 3 days into the strongest sector. Different from the "
                  "GLD/QQQ/XLE rotation — this is pure sector momentum within equities.",
    "universe": ["XLK", "XLF", "XLV", "XLI", "XLE", "XLY", "XLP", "XLU", "XLB", "XLRE"],
    "entry": "Buy the sector ETF with highest 5-day return relative to SPY",
    "exit": "Rotate every 3 trading days into new relative strength leader",
    "position_size": "95% of cash into top sector",
    "eccentricity": "Pure sector momentum with fast rotation. Institutions do sector rotation "
                    "monthly — this does it every 3 days which is too granular for large AUM.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    import pandas as pd
    import numpy as np

    tickers = ["XLK", "XLF", "XLV", "XLI", "XLE", "XLY", "XLP", "XLU", "XLB", "XLRE"]

    # Fetch prices
    prices = {}
    for ticker in tickers:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            prices[ticker] = df

    # Fetch SPY for relative strength
    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
    if spy.empty:
        return

    if len(prices) < 5:
        return

    # Common dates across all available sectors + SPY
    common_dates = spy.index
    for df in prices.values():
        common_dates = common_dates.intersection(df.index)

    trading_days = sorted([d.strftime("%Y-%m-%d") for d in common_dates
                           if start_date <= d.strftime("%Y-%m-%d") <= end_date])

    if len(trading_days) < 15:
        return

    # Parameters
    RS_LOOKBACK = 5
    ROTATION_DAYS = 3

    current_holding = None
    last_rotation_idx = -ROTATION_DAYS

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

        if i - last_rotation_idx < ROTATION_DAYS:
            continue
        if i < RS_LOOKBACK:
            continue

        # Compute relative strength for each sector
        spy_close = spy["Close"].loc[:date_ts]
        if len(spy_close) < RS_LOOKBACK + 1:
            continue

        spy_ret = (float(spy_close.iloc[-1]) - float(spy_close.iloc[-RS_LOOKBACK - 1])) / float(spy_close.iloc[-RS_LOOKBACK - 1])

        best_ticker = None
        best_rs = -999

        for ticker in prices:
            close = prices[ticker]["Close"].loc[:date_ts]
            if len(close) < RS_LOOKBACK + 1:
                continue

            ticker_ret = (float(close.iloc[-1]) - float(close.iloc[-RS_LOOKBACK - 1])) / float(close.iloc[-RS_LOOKBACK - 1])
            rs = ticker_ret - spy_ret

            if rs > best_rs:
                best_rs = rs
                best_ticker = ticker

        if best_ticker is None:
            continue

        # Only enter if the best sector actually outperforms SPY
        if best_rs <= 0:
            # No sector outperforming — go to cash
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
                current_holding = None
                last_rotation_idx = i
            continue

        if best_ticker != current_holding:
            # Sell current
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)

            # Buy best sector
            cash = portfolio.cash * 0.95
            if cash >= 100:
                result = portfolio.buy(best_ticker, dollars=cash, date=date_str)
                if result:
                    current_holding = best_ticker
                    last_rotation_idx = i

    # Close remaining
    if current_holding and trading_days:
        portfolio.sell(current_holding, all_shares=True, date=trading_days[-1])
