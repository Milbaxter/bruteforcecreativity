"""
Fear Greed Regime Rotation v2
Same as v1 but with 10-day max hold and forced re-entry to cap holding periods
and increase trade count. v1 was 0.03 Sharpe short of winner status.
"""

STRATEGY = {
    "name": "Fear Greed Regime v2",
    "hypothesis": "v1 hit 21.06%, Sharpe 0.97, profit factor 2.86 but max hold was 33 days. "
                  "Force a sell/re-buy every 10 days max to cap holding periods, reduce outlier "
                  "risk, and increase trade count for more robust statistics.",
    "universe": ["QQQ", "XLE", "GLD", "TLT", "SPY"],
    "entry": "Same as v1: fear regime → aggressive, greed → defensive, neutral → best momentum",
    "exit": "Rotate every 3 days, OR forced exit after 10 days max hold",
    "position_size": "95% of cash into selected asset",
    "eccentricity": "Contrarian fear/greed regime rotation with forced max-hold rebalancing.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    import pandas as pd

    fg = data_fetcher.get_fear_greed(start=start_date, end=end_date)
    if fg is None or (hasattr(fg, 'empty') and fg.empty):
        return

    if isinstance(fg, pd.DataFrame):
        if isinstance(fg.columns, pd.MultiIndex):
            fg.columns = fg.columns.get_level_values(0)
        fg = fg["Close"] if "Close" in fg.columns else fg.iloc[:, 0]
    fg.index = pd.to_datetime(fg.index)

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

    FEAR_THRESHOLD = 35
    GREED_THRESHOLD = 65
    MOMENTUM_LOOKBACK = 5
    ROTATION_DAYS = 3
    MAX_HOLD_DAYS = 10

    FEAR_ASSETS = ["QQQ", "XLE"]
    GREED_ASSETS = ["GLD", "TLT"]
    ALL_ASSETS = tickers

    current_holding = None
    entry_date_ts = None
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

        # Check max hold - force exit if held too long
        force_rotation = False
        if current_holding and entry_date_ts:
            days_held = (date_ts - entry_date_ts).days
            if days_held >= MAX_HOLD_DAYS:
                force_rotation = True

        if not force_rotation and i - last_rotation_idx < ROTATION_DAYS:
            continue
        if i < MOMENTUM_LOOKBACK:
            continue

        fg_up_to = fg.loc[:date_ts]
        if fg_up_to.empty:
            continue
        current_fg = float(fg_up_to.iloc[-1])

        if current_fg < FEAR_THRESHOLD:
            candidates = FEAR_ASSETS
        elif current_fg > GREED_THRESHOLD:
            candidates = GREED_ASSETS
        else:
            candidates = ALL_ASSETS

        target = pick_best(candidates, date_ts)
        if target is None:
            continue

        # Rotate if target changed OR max hold exceeded
        if target != current_holding or force_rotation:
            if current_holding and portfolio.positions.get(current_holding, 0) > 0:
                portfolio.sell(current_holding, all_shares=True, date=date_str)

            cash = portfolio.cash * 0.95
            if cash >= 100 and target in prices:
                result = portfolio.buy(target, dollars=cash, date=date_str)
                if result:
                    current_holding = target
                    entry_date_ts = date_ts
                    last_rotation_idx = i

    if current_holding and trading_days:
        if portfolio.positions.get(current_holding, 0) > 0:
            portfolio.sell(current_holding, all_shares=True, date=trading_days[-1])
