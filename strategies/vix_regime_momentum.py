"""
VIX Regime Momentum
Use VIX level to classify market regime, then pick the highest-momentum
asset within that regime's allowed universe.
"""

STRATEGY = {
    "name": "VIX Regime Momentum",
    "hypothesis": "VIX level classifies regimes: low VIX (< 16) = complacency → ride equity "
                  "momentum. Medium VIX (16-25) = uncertainty → diversify across asset classes. "
                  "High VIX (> 25) = panic → go defensive. Within each regime, pick the "
                  "5-day momentum leader. Rotate every 3 days.",
    "universe": ["QQQ", "SPY", "GLD", "TLT", "XLE"],
    "entry": "Low VIX: buy QQQ or SPY (5d momentum leader). "
             "Med VIX: buy best of GLD/SPY/XLE. "
             "High VIX: buy GLD or TLT.",
    "exit": "Rotate every 3 trading days into current regime's momentum leader",
    "position_size": "95% of cash into selected asset",
    "eccentricity": "VIX as a direct regime switch for asset selection. Combines volatility "
                    "regime classification with momentum — two signals that rarely mix in "
                    "institutional models.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    import pandas as pd
    import numpy as np

    # Fetch VIX
    vix = data_fetcher.get_vix(start=start_date, end=end_date)
    if vix is None or (hasattr(vix, 'empty') and vix.empty):
        return

    if isinstance(vix, pd.DataFrame):
        if isinstance(vix.columns, pd.MultiIndex):
            vix.columns = vix.columns.get_level_values(0)
        vix = vix["Close"] if "Close" in vix.columns else vix.iloc[:, 0]

    vix.index = pd.to_datetime(vix.index)

    # Fetch all asset prices
    tickers = ["QQQ", "SPY", "GLD", "TLT", "XLE"]
    prices = {}
    for ticker in tickers:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            prices[ticker] = df

    if len(prices) < 4:
        return

    # Common trading days
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

    # Parameters
    LOW_VIX = 16
    HIGH_VIX = 25
    MOMENTUM_LOOKBACK = 5
    ROTATION_DAYS = 3

    # Regime -> allowed tickers
    REGIMES = {
        "low": ["QQQ", "SPY"],
        "medium": ["GLD", "SPY", "XLE"],
        "high": ["GLD", "TLT"],
    }

    current_holding = None
    last_rotation_idx = -ROTATION_DAYS

    def get_momentum(ticker, date_ts, lookback):
        if ticker not in prices:
            return -999
        close = prices[ticker]["Close"].loc[:date_ts]
        if len(close) < lookback + 1:
            return -999
        return (float(close.iloc[-1]) - float(close.iloc[-lookback - 1])) / float(close.iloc[-lookback - 1])

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

        # Only rotate every N days
        if i - last_rotation_idx < ROTATION_DAYS:
            continue

        # Get current VIX
        vix_up_to = vix.loc[:date_ts]
        if vix_up_to.empty:
            continue
        current_vix = float(vix_up_to.iloc[-1])

        # Classify regime
        if current_vix < LOW_VIX:
            regime = "low"
        elif current_vix > HIGH_VIX:
            regime = "high"
        else:
            regime = "medium"

        # Pick momentum leader within regime
        allowed = REGIMES[regime]
        best_ticker = None
        best_momentum = -999

        for ticker in allowed:
            mom = get_momentum(ticker, date_ts, MOMENTUM_LOOKBACK)
            if mom > best_momentum:
                best_momentum = mom
                best_ticker = ticker

        if best_ticker is None:
            continue

        # Rotate if needed
        if best_ticker != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)

            cash = portfolio.cash * 0.95
            if cash >= 100:
                result = portfolio.buy(best_ticker, dollars=cash, date=date_str)
                if result:
                    current_holding = best_ticker
                    last_rotation_idx = i

    # Close remaining
    if current_holding and trading_days:
        portfolio.sell(current_holding, all_shares=True, date=trading_days[-1])
