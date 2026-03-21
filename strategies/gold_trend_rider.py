"""
Gold Trend Rider
Simple gold trend following with tactical entry: buy GLD when above 10-day SMA
and 10d momentum > 0.5%. Sell when momentum turns negative or at stop loss.
When not in gold, hold QQQ if it has positive momentum, else cash (SHY).
"""

STRATEGY = {
    "name": "Gold Trend Rider",
    "hypothesis": "Gold trends persist for weeks/months driven by macro forces. Simple trend "
                  "following captures the bulk of the move. Use 10-day SMA as trend filter and "
                  "momentum threshold for entry. When gold trend is off, catch equity momentum. "
                  "The simplicity IS the edge — fewer signals = fewer false signals.",
    "universe": ["GLD", "QQQ", "SHY"],
    "entry": "GLD above 10-day SMA AND 10d return > 0.5%: buy GLD. "
             "Else if QQQ 10d return > 0: buy QQQ. Else: SHY.",
    "exit": "Re-evaluate every 5 trading days. -3% stop loss on any position.",
    "position_size": "95% of cash into selected asset",
    "eccentricity": "Deliberately simple single-asset trend following. Institutions over-complicate "
                    "gold allocation with hedge ratios and correlations. Sometimes the simple "
                    "approach wins.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    import pandas as pd

    tickers = ["GLD", "QQQ", "SHY"]
    prices = {}
    for ticker in tickers:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            prices[ticker] = df

    if "GLD" not in prices or "QQQ" not in prices:
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

    SMA_PERIOD = 10
    MOMENTUM_THRESHOLD = 0.005  # 0.5%
    ROTATION_DAYS = 5
    STOP_LOSS = -0.03

    current_holding = None
    entry_price = None
    last_rotation_idx = -ROTATION_DAYS

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

        # Check stop loss
        if current_holding and entry_price and current_holding in prices:
            cur_data = prices[current_holding]["Close"].loc[:date_ts]
            if not cur_data.empty:
                cur_price = float(cur_data.iloc[-1])
                ret = (cur_price - entry_price) / entry_price
                if ret <= STOP_LOSS:
                    portfolio.sell(current_holding, all_shares=True, date=date_str)
                    current_holding = None
                    entry_price = None
                    last_rotation_idx = i

        if i - last_rotation_idx < ROTATION_DAYS:
            continue
        if i < SMA_PERIOD:
            continue

        # Compute gold signals
        gld_close = prices["GLD"]["Close"].loc[:date_ts]
        if len(gld_close) < SMA_PERIOD + 1:
            continue

        gld_price = float(gld_close.iloc[-1])
        gld_sma = float(gld_close.iloc[-SMA_PERIOD:].mean())
        gld_momentum = (gld_price - float(gld_close.iloc[-SMA_PERIOD - 1])) / float(gld_close.iloc[-SMA_PERIOD - 1])

        # Determine target
        if gld_price > gld_sma and gld_momentum > MOMENTUM_THRESHOLD:
            target = "GLD"
        else:
            # Check QQQ
            qqq_close = prices["QQQ"]["Close"].loc[:date_ts]
            if len(qqq_close) >= SMA_PERIOD + 1:
                qqq_momentum = (float(qqq_close.iloc[-1]) - float(qqq_close.iloc[-SMA_PERIOD - 1])) / float(qqq_close.iloc[-SMA_PERIOD - 1])
                if qqq_momentum > 0:
                    target = "QQQ"
                else:
                    target = "SHY"
            else:
                target = "SHY"

        if target != current_holding:
            if current_holding and portfolio.positions.get(current_holding, 0) > 0:
                portfolio.sell(current_holding, all_shares=True, date=date_str)

            cash = portfolio.cash * 0.95
            if cash >= 100 and target in prices:
                result = portfolio.buy(target, dollars=cash, date=date_str)
                if result:
                    cur_data = prices[target]["Close"].loc[:date_ts]
                    entry_price = float(cur_data.iloc[-1])
                    current_holding = target
                    last_rotation_idx = i

    if current_holding and trading_days:
        if portfolio.positions.get(current_holding, 0) > 0:
            portfolio.sell(current_holding, all_shares=True, date=trading_days[-1])
