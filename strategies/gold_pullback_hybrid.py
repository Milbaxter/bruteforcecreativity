"""
Gold Pullback Hybrid: Combines two winning themes:
1. Gold/QQQ regime rotation (from Gold Momentum Rotation v2)
2. Pullback buying (from Pullback Sniper)

When the regime favors QQQ (SPY outperforming GLD), buy QQQ on pullbacks.
When the regime favors GLD (GLD outperforming SPY), buy GLD on pullbacks.
This combines a regime filter with a timing signal for entries.
"""

import pandas as pd

STRATEGY = {
    "name": "Gold Pullback Hybrid",
    "hypothesis": "Use gold vs SPY relative performance to select regime (risk-on=QQQ, risk-off=GLD), then time entries using pullback signals. Combines regime awareness with tactical entry.",
    "universe": ["GLD", "QQQ", "SPY"],
    "entry": "When regime target (QQQ or GLD) pulls back 1.5%+ from 7-day high, buy aggressively",
    "exit": "Sell when price recovers to within 0.5% of 7-day high, or after 7 days, or -4% stop",
    "position_size": "90% of cash",
    "eccentricity": "Cross-asset regime detection + tactical timing. Two simple signals combined into something no single model would produce.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)

    for name, df in [("gld", gld), ("qqq", qqq), ("spy", spy)]:
        if isinstance(df.columns, pd.MultiIndex):
            if name == "gld":
                gld.columns = gld.columns.get_level_values(0)
            elif name == "qqq":
                qqq.columns = qqq.columns.get_level_values(0)
            else:
                spy.columns = spy.columns.get_level_values(0)

    gld_close = gld["Close"]
    qqq_close = qqq["Close"]
    spy_close = spy["Close"]

    common = sorted(set(gld_close.index) & set(qqq_close.index) & set(spy_close.index))
    if len(common) < 15:
        return

    in_position = False
    current_ticker = None
    entry_price = None
    days_held = 0

    for i in range(10, len(common)):
        day = common[i]
        day_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]

        # Determine regime: 10-day relative performance
        lookback_regime = common[i - 10]
        gld_ret = (float(gld_close.loc[day]) - float(gld_close.loc[lookback_regime])) / float(gld_close.loc[lookback_regime])
        spy_ret = (float(spy_close.loc[day]) - float(spy_close.loc[lookback_regime])) / float(spy_close.loc[lookback_regime])

        target_ticker = "GLD" if gld_ret > spy_ret else "QQQ"

        if in_position:
            days_held += 1
            current_price = float((gld_close if current_ticker == "GLD" else qqq_close).loc[day])
            pct_from_entry = (current_price - entry_price) / entry_price

            # Compute 7-day high for current holding
            prices_series = gld_close if current_ticker == "GLD" else qqq_close
            lookback_prices = [float(prices_series.loc[common[j]]) for j in range(max(0, i - 7), i + 1)]
            rolling_high = max(lookback_prices)
            drawdown = (current_price - rolling_high) / rolling_high

            # Exit: recovered, time limit, stop loss, OR regime changed
            regime_changed = target_ticker != current_ticker
            if drawdown > -0.005 or days_held >= 7 or pct_from_entry <= -0.04 or regime_changed:
                portfolio.sell(current_ticker, all_shares=True, date=day_str)
                in_position = False
                current_ticker = None
                entry_price = None
                days_held = 0

                # If regime changed, immediately check for pullback in new target
                if regime_changed:
                    pass  # Will be evaluated in the entry block below

        if not in_position:
            # Check for pullback in the target ticker
            target_series = gld_close if target_ticker == "GLD" else qqq_close
            current_price = float(target_series.loc[day])
            lookback_prices = [float(target_series.loc[common[j]]) for j in range(max(0, i - 7), i + 1)]
            rolling_high = max(lookback_prices)
            drawdown = (current_price - rolling_high) / rolling_high

            if drawdown <= -0.015:  # 1.5% pullback
                result = portfolio.buy(target_ticker, dollars=portfolio.cash * 0.90, date=day_str)
                if result:
                    in_position = True
                    current_ticker = target_ticker
                    entry_price = current_price
                    days_held = 0

    if in_position and common:
        last = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_ticker, all_shares=True, date=last)
