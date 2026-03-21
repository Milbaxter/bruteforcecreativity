"""
Bond Ratio Regime Switch
Use TLT/SHY ratio changes as yield curve proxy.
Rising ratio (long bonds outperforming) → risk-off → buy GLD.
Falling ratio (short bonds outperforming) → risk-on → buy QQQ.
"""

STRATEGY = {
    "name": "Bond Ratio Regime",
    "hypothesis": "The TLT/SHY ratio proxies the yield curve. When long-term bonds rally vs "
                  "short-term (ratio rising → curve flattening/rates falling), it signals "
                  "risk-off → buy gold. When the ratio falls (steepening/rates rising), it "
                  "signals growth → buy tech. Combines yield curve signal with asset rotation.",
    "universe": ["GLD", "QQQ", "TLT", "SHY", "SPY"],
    "entry": "7-day TLT/SHY ratio rising > 0.3%: buy GLD. "
             "Falling > 0.3%: buy QQQ. Flat: buy SPY.",
    "exit": "Rotate every 3 days based on current regime",
    "position_size": "95% of cash into selected asset",
    "eccentricity": "Bond term structure as an equity/gold switch. Cross-asset signal that "
                    "bridges fixed income and commodity analysis — rarely combined at this frequency.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    import pandas as pd

    tickers = ["GLD", "QQQ", "TLT", "SHY", "SPY"]
    prices = {}
    for ticker in tickers:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            prices[ticker] = df

    if len(prices) < 5:
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

    # Compute TLT/SHY ratio
    tlt_close = prices["TLT"]["Close"]
    shy_close = prices["SHY"]["Close"]

    LOOKBACK = 7
    THRESHOLD = 0.003  # 0.3% ratio change
    ROTATION_DAYS = 3

    current_holding = None
    last_rotation_idx = -ROTATION_DAYS

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

        if i - last_rotation_idx < ROTATION_DAYS:
            continue
        if i < LOOKBACK:
            continue

        # Compute TLT/SHY ratio change
        tlt_up = tlt_close.loc[:date_ts]
        shy_up = shy_close.loc[:date_ts]

        if len(tlt_up) < LOOKBACK + 1 or len(shy_up) < LOOKBACK + 1:
            continue

        current_ratio = float(tlt_up.iloc[-1]) / float(shy_up.iloc[-1])
        past_ratio = float(tlt_up.iloc[-LOOKBACK - 1]) / float(shy_up.iloc[-LOOKBACK - 1])
        ratio_change = (current_ratio - past_ratio) / past_ratio

        # Determine target
        if ratio_change > THRESHOLD:
            target = "GLD"  # risk-off, buy gold
        elif ratio_change < -THRESHOLD:
            target = "QQQ"  # risk-on, buy tech
        else:
            target = "SPY"  # neutral

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
