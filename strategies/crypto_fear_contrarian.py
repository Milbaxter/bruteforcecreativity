"""
Crypto Fear & Greed Contrarian
Buy BTC when crypto fear/greed index hits extreme fear, sell on recovery.
Classic contrarian play using crypto-specific sentiment alternative data.
"""

STRATEGY = {
    "name": "Crypto Fear Contrarian",
    "hypothesis": "Crypto fear/greed index extreme fear readings (< 25) represent panic selling. "
                  "Buying BTC during fear and selling when sentiment recovers (> 45) captures "
                  "the snap-back rally. Retail-driven market overreacts to fear.",
    "universe": ["BTC-USD", "ETH-USD"],
    "entry": "Buy BTC-USD when crypto fear/greed index drops below 25 (extreme fear) "
             "and was above 25 within the last 5 days (fresh fear signal)",
    "exit": "Sell when fear/greed recovers above 45, or after 10 days max hold, "
            "or at -5% stop loss",
    "position_size": "70% BTC, 30% ETH on each signal, using 90% of available cash",
    "eccentricity": "Uses crypto-specific sentiment data that traditional quants ignore. "
                    "Too volatile and 'unserious' for institutional risk committees.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    import pandas as pd

    # Fetch crypto fear/greed index
    fng = data_fetcher.get_crypto_fear_greed(days=400)
    if fng is None or (hasattr(fng, 'empty') and fng.empty):
        return

    # Convert to DataFrame if Series
    if isinstance(fng, pd.Series):
        fng = fng.to_frame(name="score")
    elif "score" not in fng.columns and len(fng.columns) == 1:
        fng.columns = ["score"]

    # Ensure datetime index
    fng.index = pd.to_datetime(fng.index)
    fng = fng.sort_index()
    fng = fng.loc[start_date:end_date]

    # Fetch BTC and ETH prices
    btc = data_fetcher.get_prices("BTC-USD", start=start_date, end=end_date)
    eth = data_fetcher.get_prices("ETH-USD", start=start_date, end=end_date)

    if btc.empty or eth.empty:
        return

    # Flatten multi-index columns if needed
    for df in [btc, eth]:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

    btc_close = btc["Close"]
    eth_close = eth["Close"]

    # Trading logic
    FEAR_THRESHOLD = 25
    RECOVERY_THRESHOLD = 45
    MAX_HOLD_DAYS = 10
    STOP_LOSS_PCT = -0.05

    in_position = False
    entry_date = None
    entry_btc_price = None

    trading_days = sorted(set(btc_close.index.strftime("%Y-%m-%d")) &
                          set(fng.index.strftime("%Y-%m-%d")))

    for date_str in trading_days:
        date_ts = pd.Timestamp(date_str)

        # Get fear/greed score
        fng_on_date = fng.loc[:date_ts]
        if fng_on_date.empty:
            continue
        current_score = float(fng_on_date.iloc[-1]["score"] if "score" in fng_on_date.columns
                              else fng_on_date.iloc[-1].iloc[0])

        if not in_position:
            # Check for fresh fear signal: currently below threshold
            # and was above threshold within last 5 days
            if current_score < FEAR_THRESHOLD:
                recent_scores = fng_on_date.tail(6)
                if len(recent_scores) >= 2:
                    recent_vals = recent_scores["score"] if "score" in recent_scores.columns else recent_scores.iloc[:, 0]
                    was_above_recently = any(float(v) >= FEAR_THRESHOLD for v in recent_vals.iloc[:-1])
                    if was_above_recently:
                        # Enter position: 70% BTC, 30% ETH
                        cash_to_deploy = portfolio.cash * 0.9
                        btc_alloc = cash_to_deploy * 0.7
                        eth_alloc = cash_to_deploy * 0.3

                        portfolio.buy("BTC-USD", dollars=btc_alloc, date=date_str)
                        portfolio.buy("ETH-USD", dollars=eth_alloc, date=date_str)

                        in_position = True
                        entry_date = date_ts
                        entry_btc_price = float(btc_close.loc[:date_ts].iloc[-1])

        else:
            # Check exit conditions
            current_btc = float(btc_close.loc[:date_ts].iloc[-1])
            days_held = (date_ts - entry_date).days
            btc_return = (current_btc - entry_btc_price) / entry_btc_price

            should_exit = False

            # Recovery exit
            if current_score > RECOVERY_THRESHOLD:
                should_exit = True

            # Time exit
            if days_held >= MAX_HOLD_DAYS:
                should_exit = True

            # Stop loss
            if btc_return <= STOP_LOSS_PCT:
                should_exit = True

            if should_exit:
                portfolio.sell("BTC-USD", all_shares=True, date=date_str)
                portfolio.sell("ETH-USD", all_shares=True, date=date_str)
                in_position = False
                entry_date = None
                entry_btc_price = None

    # Close any remaining position on last day
    if in_position and trading_days:
        last_day = trading_days[-1]
        portfolio.sell("BTC-USD", all_shares=True, date=last_day)
        portfolio.sell("ETH-USD", all_shares=True, date=last_day)
