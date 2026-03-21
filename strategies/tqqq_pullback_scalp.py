"""
TQQQ Pullback Scalp
Buy 3x leveraged Nasdaq (TQQQ) on QQQ pullbacks, scalp the bounce.
Leveraged ETFs amplify mean reversion — perfect for small capital.
"""

STRATEGY = {
    "name": "TQQQ Pullback Scalp",
    "hypothesis": "QQQ pullbacks of 2%+ from recent highs reliably bounce within 1-5 days. "
                  "TQQQ (3x leveraged) amplifies this bounce 3x. The Pullback Sniper strategy "
                  "was a winner on QQQ — this adds leverage for amplified returns on the same signal.",
    "universe": ["TQQQ", "QQQ"],
    "entry": "Buy TQQQ when QQQ pulls back 2%+ from its 10-day high",
    "exit": "Sell when QQQ recovers to within 0.5% of 10-day high, after 5 days max, "
            "or at -5% stop loss on TQQQ (wider stop for leverage)",
    "position_size": "80% of cash into TQQQ on each signal",
    "eccentricity": "Leveraged ETFs are explicitly warned against for institutional use due to "
                    "decay and volatility. But for 1-5 day holds, decay is negligible and "
                    "the 3x amplification of mean reversion is pure alpha.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    import pandas as pd

    # Fetch QQQ for signal and TQQQ for trading
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    tqqq = data_fetcher.get_prices("TQQQ", start=start_date, end=end_date)

    for df in [qqq, tqqq]:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

    if qqq.empty or tqqq.empty:
        return

    # Common dates
    common_dates = qqq.index.intersection(tqqq.index)
    trading_days = sorted([d.strftime("%Y-%m-%d") for d in common_dates
                           if start_date <= d.strftime("%Y-%m-%d") <= end_date])

    if len(trading_days) < 15:
        return

    # Parameters
    HIGH_LOOKBACK = 10
    PULLBACK_THRESHOLD = -0.02  # 2% pullback on QQQ
    RECOVERY_THRESHOLD = -0.005  # within 0.5% of QQQ high
    MAX_HOLD_DAYS = 5
    STOP_LOSS_TQQQ = -0.05  # 5% stop on TQQQ (wider for leverage)

    in_position = False
    entry_date = None
    entry_tqqq_price = None

    for date_str in trading_days:
        date_ts = pd.Timestamp(date_str)

        qqq_close = qqq["Close"].loc[:date_ts]
        tqqq_close = tqqq["Close"].loc[:date_ts]

        if len(qqq_close) < HIGH_LOOKBACK + 1:
            continue

        if in_position:
            # Check exits
            cur_tqqq = float(tqqq_close.iloc[-1])
            cur_qqq = float(qqq_close.iloc[-1])
            days_held = (date_ts - entry_date).days
            tqqq_ret = (cur_tqqq - entry_tqqq_price) / entry_tqqq_price

            # QQQ recovery check
            qqq_high_10d = float(qqq_close.iloc[-HIGH_LOOKBACK:].max())
            qqq_pct_from_high = (cur_qqq - qqq_high_10d) / qqq_high_10d

            should_exit = False
            if qqq_pct_from_high >= RECOVERY_THRESHOLD:  # QQQ recovered
                should_exit = True
            if days_held >= MAX_HOLD_DAYS:
                should_exit = True
            if tqqq_ret <= STOP_LOSS_TQQQ:
                should_exit = True

            if should_exit:
                portfolio.sell("TQQQ", all_shares=True, date=date_str)
                in_position = False
                entry_date = None
                entry_tqqq_price = None

        else:
            # Check for QQQ pullback
            cur_qqq = float(qqq_close.iloc[-1])
            qqq_high_10d = float(qqq_close.iloc[-HIGH_LOOKBACK:].max())
            pullback = (cur_qqq - qqq_high_10d) / qqq_high_10d

            if pullback <= PULLBACK_THRESHOLD:
                cash = portfolio.cash * 0.80
                if cash >= 100:
                    result = portfolio.buy("TQQQ", dollars=cash, date=date_str)
                    if result:
                        in_position = True
                        entry_date = date_ts
                        entry_tqqq_price = float(tqqq_close.iloc[-1])

    # Close remaining
    if in_position and trading_days:
        portfolio.sell("TQQQ", all_shares=True, date=trading_days[-1])
