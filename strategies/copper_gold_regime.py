"""
Copper Gold Regime Switch
Use copper/gold ratio as a growth vs safety indicator.
Rising ratio = risk-on (buy QQQ). Falling ratio = risk-off (buy GLD/TLT).
"""

STRATEGY = {
    "name": "Copper Gold Regime",
    "hypothesis": "The copper/gold ratio is a classic macro indicator: copper rises with growth "
                  "expectations, gold rises with fear. A rising ratio signals risk-on (buy tech), "
                  "falling ratio signals risk-off (buy gold/bonds). Rotate every 3 days based on "
                  "7-day regime change.",
    "universe": ["CPER", "GLD", "QQQ", "TLT"],
    "entry": "Risk-on (copper/gold ratio 7d change > 0.5%): buy QQQ. "
             "Risk-off (ratio 7d change < -0.5%): buy GLD. "
             "Neutral: buy TLT.",
    "exit": "Rotate every 3 trading days into current regime leader",
    "position_size": "90% of cash into selected asset, concentrated bet",
    "eccentricity": "Using industrial metal/precious metal ratio as a regime indicator. "
                    "Cross-commodity signal for equity allocation — too weird for compliance.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    import pandas as pd
    import numpy as np

    # Fetch copper ETF (CPER) and gold (GLD) for the ratio
    cper = data_fetcher.get_prices("CPER", start=start_date, end=end_date)
    gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    tlt = data_fetcher.get_prices("TLT", start=start_date, end=end_date)

    for df in [cper, gld, qqq, tlt]:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

    if cper.empty or gld.empty or qqq.empty or tlt.empty:
        return

    # Compute copper/gold ratio
    # Align dates
    common_dates = cper.index.intersection(gld.index).intersection(qqq.index).intersection(tlt.index)
    if len(common_dates) < 20:
        return

    cper_close = cper.loc[common_dates, "Close"]
    gld_close = gld.loc[common_dates, "Close"]

    ratio = cper_close / gld_close

    # Parameters
    LOOKBACK = 7  # days for ratio change
    THRESHOLD = 0.005  # 0.5% change threshold
    ROTATION_DAYS = 3
    STOP_LOSS = -0.03

    trading_days = [d.strftime("%Y-%m-%d") for d in sorted(common_dates)]
    trading_days = [d for d in trading_days if start_date <= d <= end_date]

    current_holding = None
    entry_date = None
    entry_price = None
    last_rotation_idx = -ROTATION_DAYS  # force first rotation

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

        # Check stop loss
        if current_holding and entry_price:
            prices_map = {"QQQ": qqq, "GLD": gld, "TLT": tlt}
            if current_holding in prices_map:
                cur_data = prices_map[current_holding]["Close"].loc[:date_ts]
                if not cur_data.empty:
                    cur_price = float(cur_data.iloc[-1])
                    ret = (cur_price - entry_price) / entry_price
                    if ret <= STOP_LOSS:
                        portfolio.sell(current_holding, all_shares=True, date=date_str)
                        current_holding = None
                        entry_date = None
                        entry_price = None
                        last_rotation_idx = i

        # Only rotate every N days
        if i - last_rotation_idx < ROTATION_DAYS:
            continue

        # Compute ratio change
        ratio_up_to = ratio.loc[:date_ts]
        if len(ratio_up_to) < LOOKBACK + 1:
            continue

        current_ratio = float(ratio_up_to.iloc[-1])
        past_ratio = float(ratio_up_to.iloc[-LOOKBACK - 1])
        ratio_change = (current_ratio - past_ratio) / past_ratio

        # Determine target
        if ratio_change > THRESHOLD:
            target = "QQQ"  # risk-on
        elif ratio_change < -THRESHOLD:
            target = "GLD"  # risk-off
        else:
            target = "TLT"  # neutral

        # Rotate if needed
        if target != current_holding:
            # Sell current
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)

            # Buy target
            cash = portfolio.cash * 0.95
            if cash >= 100:
                prices_map = {"QQQ": qqq, "GLD": gld, "TLT": tlt}
                result = portfolio.buy(target, dollars=cash, date=date_str)
                if result:
                    cur_data = prices_map[target]["Close"].loc[:date_ts]
                    entry_price = float(cur_data.iloc[-1])
                    current_holding = target
                    entry_date = date_ts
                    last_rotation_idx = i

    # Close remaining
    if current_holding and trading_days:
        portfolio.sell(current_holding, all_shares=True, date=trading_days[-1])
