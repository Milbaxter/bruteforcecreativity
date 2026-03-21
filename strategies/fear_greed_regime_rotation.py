"""
Fear & Greed Regime Rotation
Use CNN-style fear/greed composite index as a contrarian regime signal.
Fear = buy aggressive (QQQ, XLE). Greed = buy defensive (GLD, TLT).
"""

STRATEGY = {
    "name": "Fear Greed Regime Rotation",
    "hypothesis": "Fear/greed extremes are contrarian signals. When fear dominates (< 35), "
                  "markets have sold off too much — buy aggressive assets (QQQ, XLE) for the bounce. "
                  "When greed dominates (> 65), markets are extended — rotate into defensives (GLD, TLT). "
                  "In neutral zone, hold the asset with best 5-day momentum.",
    "universe": ["QQQ", "XLE", "GLD", "TLT", "SPY"],
    "entry": "Fear (< 35): buy QQQ or XLE (best 5d momentum). "
             "Greed (> 65): buy GLD or TLT (best 5d momentum). "
             "Neutral: buy SPY or best momentum of all 5.",
    "exit": "Rotate every 3 trading days based on current regime",
    "position_size": "95% of cash into selected asset",
    "eccentricity": "Using VIX/put-call/breadth composite as a contrarian regime switch. "
                    "Institutions can't flip their entire portfolio every 3 days based on "
                    "a fear/greed reading.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    import pandas as pd

    # Fetch fear/greed index
    fg = data_fetcher.get_fear_greed(start=start_date, end=end_date)
    if fg is None or (hasattr(fg, 'empty') and fg.empty):
        return

    if isinstance(fg, pd.DataFrame):
        if isinstance(fg.columns, pd.MultiIndex):
            fg.columns = fg.columns.get_level_values(0)
        fg = fg["Close"] if "Close" in fg.columns else fg.iloc[:, 0]

    fg.index = pd.to_datetime(fg.index)

    # Fetch asset prices
    tickers = ["QQQ", "XLE", "GLD", "TLT", "SPY"]
    prices = {}
    for ticker in tickers:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            prices[ticker] = df

    if len(prices) < 4:
        return

    # Common dates
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
    FEAR_THRESHOLD = 35
    GREED_THRESHOLD = 65
    MOMENTUM_LOOKBACK = 5
    ROTATION_DAYS = 3

    FEAR_ASSETS = ["QQQ", "XLE"]  # aggressive on fear
    GREED_ASSETS = ["GLD", "TLT"]  # defensive on greed
    ALL_ASSETS = tickers

    current_holding = None
    last_rotation_idx = -ROTATION_DAYS

    def get_momentum(ticker, date_ts, lookback):
        if ticker not in prices:
            return -999
        close = prices[ticker]["Close"].loc[:date_ts]
        if len(close) < lookback + 1:
            return -999
        return (float(close.iloc[-1]) - float(close.iloc[-lookback - 1])) / float(close.iloc[-lookback - 1])

    def pick_best(candidates, date_ts):
        best_t, best_m = None, -999
        for t in candidates:
            m = get_momentum(t, date_ts, MOMENTUM_LOOKBACK)
            if m > best_m:
                best_m = m
                best_t = t
        return best_t

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

        if i - last_rotation_idx < ROTATION_DAYS:
            continue
        if i < MOMENTUM_LOOKBACK:
            continue

        # Get fear/greed reading
        fg_up_to = fg.loc[:date_ts]
        if fg_up_to.empty:
            continue
        current_fg = float(fg_up_to.iloc[-1])

        # Determine regime and candidates
        if current_fg < FEAR_THRESHOLD:
            candidates = FEAR_ASSETS
        elif current_fg > GREED_THRESHOLD:
            candidates = GREED_ASSETS
        else:
            candidates = ALL_ASSETS

        target = pick_best(candidates, date_ts)
        if target is None:
            continue

        if target != current_holding:
            if current_holding and portfolio.positions.get(current_holding, 0) > 0:
                portfolio.sell(current_holding, all_shares=True, date=date_str)

            cash = portfolio.cash * 0.95
            if cash >= 100 and target in prices:
                result = portfolio.buy(target, dollars=cash, date=date_str)
                if result:
                    current_holding = target
                    last_rotation_idx = i

    if current_holding and trading_days:
        if portfolio.positions.get(current_holding, 0) > 0:
            portfolio.sell(current_holding, all_shares=True, date=trading_days[-1])
