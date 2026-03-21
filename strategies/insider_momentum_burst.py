"""
Insider Momentum Burst
Track insider cluster buys and ride the momentum burst that follows.
Uses OpenInsider data — when 3+ insiders buy within a week, the stock moves.
"""

STRATEGY = {
    "name": "Insider Momentum Burst",
    "hypothesis": "When multiple corporate insiders buy their own stock within a short window "
                  "(cluster buy), it signals strong insider conviction. Unlike single buys "
                  "(which could be diversification), clusters suggest they know something. "
                  "Buy on cluster signal, ride 5-7 day momentum burst.",
    "universe": ["AAPL", "MSFT", "GOOG", "AMZN", "META", "NVDA", "JPM", "BAC", "WFC",
                 "XOM", "CVX", "JNJ", "UNH", "PFE", "DIS"],
    "entry": "Buy when OpenInsider shows 2+ insider buys for a ticker in the trailing 7 days",
    "exit": "Sell after 7 trading days, or at -3% stop loss",
    "position_size": "30% of cash per signal, max 3 concurrent",
    "eccentricity": "Insider trading data is public but most retail ignores it. Institutions "
                    "can't publicly trade on 'following insider buys' without scrutiny. "
                    "Small capital can quietly ride the signal.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    import pandas as pd

    tickers = STRATEGY["universe"]

    # Fetch insider trades for each ticker
    insider_data = {}
    for ticker in tickers:
        try:
            insiders = data_fetcher.get_insider_trades(ticker)
            if insiders is not None and not (hasattr(insiders, 'empty') and insiders.empty):
                if isinstance(insiders, pd.DataFrame):
                    insiders.index = pd.to_datetime(insiders.index) if not isinstance(insiders.index, pd.DatetimeIndex) else insiders.index
                    # Try to get a date column
                    if "date" in insiders.columns:
                        insiders["date"] = pd.to_datetime(insiders["date"])
                    elif "Filing Date" in insiders.columns:
                        insiders["date"] = pd.to_datetime(insiders["Filing Date"])
                    elif "Trade Date" in insiders.columns:
                        insiders["date"] = pd.to_datetime(insiders["Trade Date"])
                    else:
                        # Use index as date
                        insiders["date"] = insiders.index

                    # Try to identify buy transactions
                    if "type" in insiders.columns:
                        buys = insiders[insiders["type"].str.contains("Buy|Purchase|P -", case=False, na=False)]
                    elif "Transaction" in insiders.columns:
                        buys = insiders[insiders["Transaction"].str.contains("Buy|Purchase|P -", case=False, na=False)]
                    elif "transaction_type" in insiders.columns:
                        buys = insiders[insiders["transaction_type"].str.contains("Buy|Purchase|P -", case=False, na=False)]
                    else:
                        buys = insiders  # assume all are buys if can't filter

                    if not buys.empty:
                        insider_data[ticker] = buys
        except Exception:
            continue

    if not insider_data:
        return

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

    if len(trading_days) < 10:
        return

    # Parameters
    CLUSTER_WINDOW = 7  # days to look for clusters
    MIN_CLUSTER = 2  # minimum insider buys in window
    HOLD_DAYS = 7
    STOP_LOSS = -0.03
    MAX_POSITIONS = 3
    CASH_PER_TRADE = 0.30

    open_positions = {}  # ticker -> {"entry_date", "entry_price"}

    for date_str in trading_days:
        date_ts = pd.Timestamp(date_str)

        # Check exits
        for ticker in list(open_positions.keys()):
            pos = open_positions[ticker]
            entry_date = pd.Timestamp(pos["entry_date"])
            days_held = (date_ts - entry_date).days

            if ticker in prices:
                cur_data = prices[ticker]["Close"].loc[:date_ts]
                if not cur_data.empty:
                    cur_price = float(cur_data.iloc[-1])
                    ret = (cur_price - pos["entry_price"]) / pos["entry_price"]

                    if days_held >= HOLD_DAYS or ret <= STOP_LOSS:
                        portfolio.sell(ticker, all_shares=True, date=date_str)
                        del open_positions[ticker]

        # Check entries
        if len(open_positions) >= MAX_POSITIONS:
            continue

        for ticker, buys_df in insider_data.items():
            if ticker in open_positions:
                continue
            if ticker not in prices:
                continue
            if len(open_positions) >= MAX_POSITIONS:
                break

            # Count insider buys in the last CLUSTER_WINDOW days
            window_start = date_ts - pd.Timedelta(days=CLUSTER_WINDOW)
            recent_buys = buys_df[(buys_df["date"] >= window_start) & (buys_df["date"] <= date_ts)]

            if len(recent_buys) >= MIN_CLUSTER:
                cash = portfolio.cash * CASH_PER_TRADE
                if cash < 100:
                    break

                result = portfolio.buy(ticker, dollars=cash, date=date_str)
                if result:
                    cur_data = prices[ticker]["Close"].loc[:date_ts]
                    open_positions[ticker] = {
                        "entry_date": date_str,
                        "entry_price": float(cur_data.iloc[-1]),
                    }

    # Close remaining
    if trading_days:
        last_day = trading_days[-1]
        for ticker in list(open_positions.keys()):
            portfolio.sell(ticker, all_shares=True, date=last_day)
