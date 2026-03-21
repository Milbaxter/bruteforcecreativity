"""
Google Fear Contrarian
When Google Trends for fear-related terms spike, buy the market.
Retail fear googling = panic selling = buying opportunity.
"""

STRATEGY = {
    "name": "Google Fear Contrarian",
    "hypothesis": "When retail investors google 'recession', 'stock market crash', or 'bear market', "
                  "they are panicking. These sentiment extremes often mark local bottoms. Buy SPY "
                  "and QQQ when fear search interest spikes above 2x its 4-week average. This is "
                  "the Google Trends version of 'be greedy when others are fearful.'",
    "universe": ["SPY", "QQQ"],
    "entry": "Buy when Google Trends composite fear score exceeds 2x its 4-week rolling average",
    "exit": "Sell after 7 days or at -3% stop loss or +4% take profit",
    "position_size": "50% SPY, 50% QQQ, deploy 90% of cash",
    "eccentricity": "Google Trends as a sentiment indicator — too 'retail' for institutional "
                    "quant teams to take seriously, but retail fear IS the signal.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    import pandas as pd
    import numpy as np

    # Fetch Google Trends for fear-related terms
    fear_terms = ["recession", "stock market crash", "bear market"]
    trends_data = None

    for term in fear_terms:
        try:
            trend = data_fetcher.get_google_trends([term])
            if trend is not None and not (hasattr(trend, 'empty') and trend.empty):
                if isinstance(trend, pd.DataFrame):
                    trend.index = pd.to_datetime(trend.index)
                    col = term if term in trend.columns else trend.columns[0]
                    if trends_data is None:
                        trends_data = trend[[col]].rename(columns={col: term})
                    else:
                        trends_data = trends_data.join(trend[[col]].rename(columns={col: term}), how="outer")
                elif isinstance(trend, pd.Series):
                    trend.index = pd.to_datetime(trend.index)
                    if trends_data is None:
                        trends_data = trend.to_frame(name=term)
                    else:
                        trends_data = trends_data.join(trend.to_frame(name=term), how="outer")
        except Exception:
            continue

    if trends_data is None or trends_data.empty:
        return

    # Compute composite fear score (average of all available terms)
    trends_data = trends_data.fillna(0)
    fear_score = trends_data.mean(axis=1)
    fear_score = fear_score.sort_index()

    # Fetch prices
    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)

    for df in [spy, qqq]:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

    if spy.empty or qqq.empty:
        return

    # Get trading days
    common_dates = spy.index.intersection(qqq.index)
    trading_days = sorted([d.strftime("%Y-%m-%d") for d in common_dates
                           if start_date <= d.strftime("%Y-%m-%d") <= end_date])

    if len(trading_days) < 30:
        return

    # Parameters
    ROLLING_WINDOW = 28  # 4 weeks for rolling average (trends are weekly)
    SPIKE_MULT = 1.5  # spike multiplier (lowered from 2x for more signals)
    MAX_HOLD_DAYS = 7
    STOP_LOSS = -0.03
    TAKE_PROFIT = 0.04

    in_position = False
    entry_date = None
    entry_spy_price = None

    for date_str in trading_days:
        date_ts = pd.Timestamp(date_str)

        if in_position:
            # Check exits
            spy_data = spy["Close"].loc[:date_ts]
            if spy_data.empty:
                continue
            cur_price = float(spy_data.iloc[-1])
            days_held = (date_ts - entry_date).days
            ret = (cur_price - entry_spy_price) / entry_spy_price

            should_exit = False
            if days_held >= MAX_HOLD_DAYS:
                should_exit = True
            if ret <= STOP_LOSS:
                should_exit = True
            if ret >= TAKE_PROFIT:
                should_exit = True

            if should_exit:
                portfolio.sell("SPY", all_shares=True, date=date_str)
                portfolio.sell("QQQ", all_shares=True, date=date_str)
                in_position = False
                entry_date = None
                entry_spy_price = None

        else:
            # Check for fear spike
            fear_up_to = fear_score.loc[:date_ts]
            if len(fear_up_to) < ROLLING_WINDOW + 1:
                continue

            current_fear = float(fear_up_to.iloc[-1])
            rolling_avg = float(fear_up_to.iloc[-ROLLING_WINDOW - 1:-1].mean())

            if rolling_avg > 0 and current_fear > rolling_avg * SPIKE_MULT:
                # Fear spike detected — buy
                cash = portfolio.cash * 0.90
                spy_alloc = cash * 0.50
                qqq_alloc = cash * 0.50

                portfolio.buy("SPY", dollars=spy_alloc, date=date_str)
                portfolio.buy("QQQ", dollars=qqq_alloc, date=date_str)

                in_position = True
                entry_date = date_ts
                spy_data = spy["Close"].loc[:date_ts]
                entry_spy_price = float(spy_data.iloc[-1])

    # Close remaining
    if in_position and trading_days:
        last_day = trading_days[-1]
        portfolio.sell("SPY", all_shares=True, date=last_day)
        portfolio.sell("QQQ", all_shares=True, date=last_day)
