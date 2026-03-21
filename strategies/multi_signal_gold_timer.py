"""
Multi-Signal Gold Timer
Combine VIX regime + fear/greed index + gold momentum into a composite
score that determines GLD vs QQQ vs SPY allocation. Multiple confirming
signals should be stronger than any single one.
"""

STRATEGY = {
    "name": "Multi-Signal Gold Timer",
    "hypothesis": "Three independent signals all point to gold allocation: "
                  "1) High VIX (> 20) = uncertainty favors gold. "
                  "2) Fear/greed < 40 = fear favors safe havens. "
                  "3) Gold 7-day momentum > SPY momentum = trend confirmation. "
                  "When 2+ of 3 signals align for gold, go GLD. When 2+ favor risk-on, go QQQ. "
                  "Mixed signals = SPY. Multi-signal confirmation reduces false signals.",
    "universe": ["GLD", "QQQ", "SPY"],
    "entry": "Score 3 signals: VIX regime, fear/greed level, gold vs SPY relative momentum. "
             "2+ gold signals → GLD. 2+ risk-on signals → QQQ. Mixed → SPY.",
    "exit": "Rotate every 3 trading days based on composite score",
    "position_size": "95% of cash into selected asset",
    "eccentricity": "Multi-factor composite signal crossing volatility, sentiment, and momentum "
                    "domains. No single signal dominates — the combination is the edge.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    import pandas as pd

    # Fetch VIX
    vix = data_fetcher.get_vix(start=start_date, end=end_date)
    if isinstance(vix, pd.DataFrame):
        if isinstance(vix.columns, pd.MultiIndex):
            vix.columns = vix.columns.get_level_values(0)
        vix = vix["Close"] if "Close" in vix.columns else vix.iloc[:, 0]
    if vix is None or (hasattr(vix, 'empty') and vix.empty):
        return
    vix.index = pd.to_datetime(vix.index)

    # Fetch fear/greed
    fg = data_fetcher.get_fear_greed(start=start_date, end=end_date)
    if isinstance(fg, pd.DataFrame):
        if isinstance(fg.columns, pd.MultiIndex):
            fg.columns = fg.columns.get_level_values(0)
        fg = fg["Close"] if "Close" in fg.columns else fg.iloc[:, 0]
    if fg is None or (hasattr(fg, 'empty') and fg.empty):
        return
    fg.index = pd.to_datetime(fg.index)

    # Fetch prices
    tickers = ["GLD", "QQQ", "SPY"]
    prices = {}
    for ticker in tickers:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            prices[ticker] = df

    if len(prices) < 3:
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

    # Parameters
    VIX_HIGH = 20  # above this favors gold
    FG_FEAR = 40   # below this favors gold
    MOMENTUM_LOOKBACK = 7
    ROTATION_DAYS = 3

    current_holding = None
    last_rotation_idx = -ROTATION_DAYS

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

        if i - last_rotation_idx < ROTATION_DAYS:
            continue
        if i < MOMENTUM_LOOKBACK:
            continue

        # Signal 1: VIX regime
        vix_up = vix.loc[:date_ts]
        if vix_up.empty:
            continue
        current_vix = float(vix_up.iloc[-1])
        vix_gold = 1 if current_vix > VIX_HIGH else 0

        # Signal 2: Fear/greed level
        fg_up = fg.loc[:date_ts]
        if fg_up.empty:
            continue
        current_fg = float(fg_up.iloc[-1])
        fg_gold = 1 if current_fg < FG_FEAR else 0

        # Signal 3: Gold vs SPY relative momentum
        gld_close = prices["GLD"]["Close"].loc[:date_ts]
        spy_close = prices["SPY"]["Close"].loc[:date_ts]

        if len(gld_close) < MOMENTUM_LOOKBACK + 1 or len(spy_close) < MOMENTUM_LOOKBACK + 1:
            continue

        gld_mom = (float(gld_close.iloc[-1]) - float(gld_close.iloc[-MOMENTUM_LOOKBACK - 1])) / float(gld_close.iloc[-MOMENTUM_LOOKBACK - 1])
        spy_mom = (float(spy_close.iloc[-1]) - float(spy_close.iloc[-MOMENTUM_LOOKBACK - 1])) / float(spy_close.iloc[-MOMENTUM_LOOKBACK - 1])
        mom_gold = 1 if gld_mom > spy_mom else 0

        # Composite score
        gold_score = vix_gold + fg_gold + mom_gold

        if gold_score >= 2:
            target = "GLD"
        elif gold_score == 0:
            target = "QQQ"
        else:
            target = "SPY"

        if target != current_holding:
            if current_holding and portfolio.positions.get(current_holding, 0) > 0:
                portfolio.sell(current_holding, all_shares=True, date=date_str)

            cash = portfolio.cash * 0.95
            if cash >= 100:
                result = portfolio.buy(target, dollars=cash, date=date_str)
                if result:
                    current_holding = target
                    last_rotation_idx = i

    if current_holding and trading_days:
        if portfolio.positions.get(current_holding, 0) > 0:
            portfolio.sell(current_holding, all_shares=True, date=trading_days[-1])
