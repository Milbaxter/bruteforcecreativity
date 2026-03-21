"""
Baseline strategy: buy SPY and hold for the entire backtest period.
This establishes the benchmark. It will always be classified as 'mediocre'
because it has only 1 trade and long holding period — by design.
"""

STRATEGY = {
    "name": "SPY Buy and Hold",
    "hypothesis": "Passive index investing is the benchmark. Every strategy must beat this.",
    "universe": ["SPY"],
    "entry": "Buy SPY on day 1 with all capital",
    "exit": "Hold until end of backtest period",
    "position_size": "100% of capital",
    "eccentricity": "None — this is the boring baseline",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Buy SPY on the first available date with all capital
    portfolio.buy("SPY", dollars=portfolio.cash, date=start_date)
    # Sell at end
    portfolio.sell("SPY", all_shares=True, date=end_date)
