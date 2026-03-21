"""
Baseline strategy: buy SPY and hold for the entire backtest period.
This establishes the benchmark that all eccentric strategies must beat.
"""

STRATEGY = {
    "name": "SPY Buy and Hold",
    "hypothesis": "Passive index investing is the benchmark. Every strategy must beat this to be considered a winner.",
    "universe": ["SPY"],
    "entry": "Buy SPY on day 1 with all capital",
    "exit": "Hold until end of backtest period",
    "position_size": "100% of capital",
    "eccentricity": "None — this is the boring baseline",
}


def run(data_fetcher, start_date, end_date, starting_capital=10000):
    import pandas as pd
    import math

    # Fetch SPY prices
    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)

    if isinstance(spy.columns, pd.MultiIndex):
        close = spy[("Close", "SPY")]
    else:
        close = spy["Close"]

    close = close.dropna()

    if close.empty:
        return {
            "trades": [],
            "portfolio_values": [],
            "final_value": starting_capital,
        }

    # Buy on first day
    buy_price = close.iloc[0]
    shares = math.floor(starting_capital / (buy_price * 1.001))  # 0.1% slippage
    cost = shares * buy_price * 1.001
    cash = starting_capital - cost

    # Track portfolio value daily
    portfolio_values = []
    for date, price in close.items():
        value = cash + shares * price
        portfolio_values.append((date, value))

    final_value = portfolio_values[-1][1]
    sell_price = close.iloc[-1]
    pnl = (sell_price - buy_price) * shares

    trades = [
        {"date": close.index[0], "ticker": "SPY", "action": "BUY", "price": buy_price, "shares": shares, "pnl": None},
        {"date": close.index[-1], "ticker": "SPY", "action": "SELL", "price": sell_price, "shares": shares, "pnl": pnl},
    ]

    return {
        "trades": trades,
        "portfolio_values": portfolio_values,
        "final_value": final_value,
    }
