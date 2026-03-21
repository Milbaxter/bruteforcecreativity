"""
Pre-Earnings Drift
Buy stocks 2 days before earnings announcement, sell the day after.
Exploits the well-documented pre-earnings announcement drift.
"""

STRATEGY = {
    "name": "Pre-Earnings Drift",
    "hypothesis": "Stocks tend to drift upward in the 2-3 days before earnings as informed traders "
                  "accumulate positions and implied volatility rises. Buy 2 days before, sell day "
                  "after announcement to capture drift + any positive surprise momentum.",
    "universe": ["AAPL", "MSFT", "GOOG", "AMZN", "META", "NVDA", "TSLA", "NFLX",
                 "AMD", "CRM", "ADBE", "PYPL", "INTC", "DIS", "BA"],
    "entry": "Buy 2 trading days before scheduled earnings date",
    "exit": "Sell 1 trading day after earnings, or -3% stop loss",
    "position_size": "25% of cash per earnings play, max 3 concurrent",
    "eccentricity": "Uses earnings calendar alt data. While institutional investors know about "
                    "earnings, they can't systematically trade the micro-drift without impacting "
                    "their larger positions. Small-capital edge.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    import pandas as pd

    tickers = STRATEGY["universe"]

    # Fetch earnings calendar for all tickers
    try:
        earnings = data_fetcher.get_earnings_calendar(tickers)
    except Exception:
        return

    if earnings is None or (hasattr(earnings, 'empty') and earnings.empty):
        return

    # Normalize earnings data
    if isinstance(earnings, pd.DataFrame):
        if "date" in earnings.columns:
            earnings["date"] = pd.to_datetime(earnings["date"])
        elif earnings.index.name == "date" or hasattr(earnings.index, 'date'):
            earnings = earnings.reset_index()
            if "date" not in earnings.columns and "Earnings Date" in earnings.columns:
                earnings = earnings.rename(columns={"Earnings Date": "date"})
            elif "date" not in earnings.columns:
                earnings.columns = ["date"] + list(earnings.columns[1:])
            earnings["date"] = pd.to_datetime(earnings["date"])

    # Fetch prices
    prices = {}
    for ticker in tickers:
        try:
            df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if not df.empty:
                prices[ticker] = df
        except Exception:
            continue

    if not prices:
        return

    # Get trading days
    all_dates = set()
    for df in prices.values():
        all_dates.update(df.index.strftime("%Y-%m-%d"))
    trading_days = sorted(d for d in all_dates if start_date <= d <= end_date)

    # Parameters
    ENTRY_DAYS_BEFORE = 2
    EXIT_DAYS_AFTER = 1
    STOP_LOSS = -0.03
    MAX_POSITIONS = 3
    CASH_PER_TRADE = 0.25

    # Build earnings schedule: for each ticker, list of earnings dates
    earnings_schedule = {}
    if "ticker" in earnings.columns and "date" in earnings.columns:
        for _, row in earnings.iterrows():
            t = row["ticker"]
            d = row["date"]
            if pd.notna(d) and t in prices:
                ds = d.strftime("%Y-%m-%d") if hasattr(d, 'strftime') else str(d)[:10]
                if start_date <= ds <= end_date:
                    if t not in earnings_schedule:
                        earnings_schedule[t] = []
                    earnings_schedule[t].append(ds)

    if not earnings_schedule:
        return

    # Pre-compute entry/exit windows
    trade_windows = []  # (entry_day, exit_day, ticker)
    for ticker, earn_dates in earnings_schedule.items():
        for earn_date in earn_dates:
            # Find the trading day that is ENTRY_DAYS_BEFORE before earnings
            earn_idx = None
            for i, d in enumerate(trading_days):
                if d >= earn_date:
                    earn_idx = i
                    break
            if earn_idx is None:
                continue

            entry_idx = earn_idx - ENTRY_DAYS_BEFORE
            exit_idx = earn_idx + EXIT_DAYS_AFTER

            if entry_idx >= 0 and exit_idx < len(trading_days):
                trade_windows.append((trading_days[entry_idx], trading_days[exit_idx],
                                      earn_date, ticker))

    # Sort by entry date
    trade_windows.sort(key=lambda x: x[0])

    # Track positions
    open_positions = {}  # ticker -> {"entry_date", "entry_price", "exit_date"}

    for date_str in trading_days:
        date_ts = pd.Timestamp(date_str)

        # Check exits
        for ticker in list(open_positions.keys()):
            pos = open_positions[ticker]

            # Scheduled exit
            if date_str >= pos["exit_date"]:
                portfolio.sell(ticker, all_shares=True, date=date_str)
                del open_positions[ticker]
                continue

            # Stop loss check
            if ticker in prices:
                current_data = prices[ticker]["Close"].loc[:date_ts]
                if not current_data.empty:
                    current_price = float(current_data.iloc[-1])
                    ret = (current_price - pos["entry_price"]) / pos["entry_price"]
                    if ret <= STOP_LOSS:
                        portfolio.sell(ticker, all_shares=True, date=date_str)
                        del open_positions[ticker]

        # Check entries
        if len(open_positions) >= MAX_POSITIONS:
            continue

        for entry_day, exit_day, earn_date, ticker in trade_windows:
            if entry_day != date_str:
                continue
            if ticker in open_positions:
                continue
            if len(open_positions) >= MAX_POSITIONS:
                break
            if ticker not in prices:
                continue

            cash = portfolio.cash * CASH_PER_TRADE
            if cash < 100:
                break

            result = portfolio.buy(ticker, dollars=cash, date=date_str)
            if result:
                cp = float(prices[ticker]["Close"].loc[:date_ts].iloc[-1])
                open_positions[ticker] = {
                    "entry_date": date_str,
                    "entry_price": cp,
                    "exit_date": exit_day,
                }

    # Close remaining
    if trading_days:
        last_day = trading_days[-1]
        for ticker in list(open_positions.keys()):
            portfolio.sell(ticker, all_shares=True, date=last_day)
