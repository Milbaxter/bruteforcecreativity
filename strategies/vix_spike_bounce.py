"""
Test strategy: buy SPY when VIX spikes >5% in a day (fear = opportunity),
sell after 3 trading days. Classic mean-reversion on fear.
"""

STRATEGY = {
    "name": "VIX Spike Bounce",
    "hypothesis": "When VIX spikes >5% in a single day, the market has overreacted to fear. Buying SPY and holding 3 days captures the mean-reversion bounce.",
    "universe": ["SPY", "^VIX"],
    "entry": "Buy SPY when VIX daily change > 5%",
    "exit": "Sell after 3 trading days",
    "position_size": "50% of available cash per trade",
    "eccentricity": "Uses volatility index as a contrarian entry — too 'timing the market' for institutional compliance",
}


def run(data_fetcher, portfolio, start_date, end_date):
    import pandas as pd

    # Fetch data
    spy_prices = data_fetcher.get_prices("SPY", start=start_date, end=end_date)
    vix_prices = data_fetcher.get_prices("^VIX", start=start_date, end=end_date)

    if spy_prices.empty or vix_prices.empty:
        return

    # Get close prices
    if isinstance(spy_prices.columns, pd.MultiIndex):
        spy_close = spy_prices[("Close", "SPY")]
    else:
        spy_close = spy_prices["Close"]

    if isinstance(vix_prices.columns, pd.MultiIndex):
        vix_close = vix_prices[("Close", "^VIX")]
    else:
        vix_close = vix_prices["Close"]

    # Compute VIX daily % change
    vix_pct_change = vix_close.pct_change()

    # Track pending sells (date to sell on)
    pending_sells = []

    trading_days = sorted(spy_close.dropna().index)

    for i, day in enumerate(trading_days):
        day_str = day.strftime("%Y-%m-%d")

        # Check pending sells first
        new_pending = []
        for sell_date, ticker in pending_sells:
            if day_str >= sell_date:
                portfolio.sell(ticker, all_shares=True, date=day_str)
            else:
                new_pending.append((sell_date, ticker))
        pending_sells = new_pending

        # Check VIX spike signal
        if day in vix_pct_change.index and vix_pct_change[day] > 0.05:
            # VIX spiked >5% — buy SPY
            result = portfolio.buy("SPY", dollars=portfolio.cash * 0.5, date=day_str)
            if result:
                # Schedule sell 3 trading days later
                if i + 3 < len(trading_days):
                    sell_day = trading_days[i + 3].strftime("%Y-%m-%d")
                    pending_sells.append((sell_day, "SPY"))

    # Close any remaining positions
    for ticker in list(portfolio.positions.keys()):
        portfolio.sell(ticker, all_shares=True, date=end_date)
