"""
Month-End Rebalancing Flow
Exploit institutional month-end rebalancing by buying equities 3 days before
month-end and selling 2 days into the new month.
"""

STRATEGY = {
    "name": "Month-End Flow",
    "hypothesis": "Pension funds, mutual funds, and index funds rebalance at month-end, "
                  "creating predictable buying pressure in the last few trading days. "
                  "This 'window dressing' effect is well-documented but too short-duration "
                  "for large funds to trade explicitly against.",
    "universe": ["SPY", "QQQ", "IWM", "DIA"],
    "entry": "Buy a basket of index ETFs 3 trading days before month-end",
    "exit": "Sell 2 trading days into the new month",
    "position_size": "Equal weight across all 4 ETFs, deploy 90% of cash",
    "eccentricity": "Exploiting calendar-driven institutional flows. Funds can't avoid "
                    "their own rebalancing effect. Too small-edge for big shops but "
                    "compounds nicely at small scale.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    import pandas as pd

    # Fetch prices for all ETFs
    tickers = ["SPY", "QQQ", "IWM", "DIA"]
    prices = {}
    for ticker in tickers:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            prices[ticker] = df

    if not prices:
        return

    # Get unified trading days
    all_dates = set()
    for df in prices.values():
        all_dates.update(df.index.strftime("%Y-%m-%d"))
    trading_days = sorted(d for d in all_dates if start_date <= d <= end_date)

    if len(trading_days) < 10:
        return

    # Group trading days by month
    td_dates = pd.DatetimeIndex(trading_days)
    td_periods = td_dates.to_period("M")
    months = td_periods.unique()

    in_position = False
    ENTRY_DAYS_BEFORE_END = 3  # enter 3 trading days before month-end
    EXIT_DAYS_INTO_NEW = 2  # exit 2 trading days into new month

    for i, month in enumerate(months):
        # Get trading days in this month
        month_mask = td_periods == month
        month_days = [d.strftime("%Y-%m-%d") for d in td_dates[month_mask]]

        if len(month_days) < ENTRY_DAYS_BEFORE_END + 1:
            continue

        # Entry: 3rd-to-last trading day of the month
        entry_day = month_days[-ENTRY_DAYS_BEFORE_END]

        if not in_position:
            # Buy equal weight across all 4 ETFs
            cash_per_ticker = (portfolio.cash * 0.90) / len(tickers)
            bought_any = False
            for ticker in tickers:
                if ticker in prices and cash_per_ticker >= 50:
                    result = portfolio.buy(ticker, dollars=cash_per_ticker, date=entry_day)
                    if result:
                        bought_any = True
            if bought_any:
                in_position = True

        # Exit: 2nd trading day of next month
        if in_position and i + 1 < len(months):
            next_month = months[i + 1]
            next_month_mask = td_periods == next_month
            next_month_days = [d.strftime("%Y-%m-%d") for d in td_dates[next_month_mask]]

            if len(next_month_days) >= EXIT_DAYS_INTO_NEW:
                exit_day = next_month_days[EXIT_DAYS_INTO_NEW - 1]

                for ticker in tickers:
                    if portfolio.positions.get(ticker, 0) > 0:
                        portfolio.sell(ticker, all_shares=True, date=exit_day)
                in_position = False

    # Close remaining positions
    if in_position and trading_days:
        last_day = trading_days[-1]
        for ticker in tickers:
            if portfolio.positions.get(ticker, 0) > 0:
                portfolio.sell(ticker, all_shares=True, date=last_day)
