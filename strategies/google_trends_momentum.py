"""
Google Trends Momentum: Track search interest for "buy stocks", "stock market",
"invest" and similar terms. When retail search interest spikes, ride the
momentum wave in QQQ for 5 days.

Thesis: Google Trends search volume for investing terms is a leading indicator
of retail money flows. When searches spike, retail money is about to pour in.
This creates a 3-7 day momentum wave as retail follows through on their searches.
"""

import pandas as pd

STRATEGY = {
    "name": "Google Trends Momentum",
    "hypothesis": "Spikes in retail search interest for investing terms precede retail money inflows by 3-7 days. Riding this wave captures the FOMO cascade.",
    "universe": ["QQQ"],
    "entry": "Buy QQQ when Google Trends for 'buy stocks' spikes 50%+ above its 4-week average",
    "exit": "Sell after 5 trading days",
    "position_size": "90% of cash",
    "eccentricity": "Using Google search data as a leading indicator for retail flows. Institutional quants track this but can't act on it — too much model risk for a compliance committee.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch Google Trends data
    try:
        trends = data_fetcher.get_google_trends(["buy stocks", "invest in stocks"])
    except Exception:
        return

    if trends.empty:
        return

    # Get QQQ prices
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    if isinstance(qqq.columns, pd.MultiIndex):
        qqq.columns = qqq.columns.get_level_values(0)

    qqq_close = qqq["Close"]
    trading_days = sorted(qqq_close.index)

    # Google Trends is weekly — we need to align with trading days
    # Use the first column (whichever keyword has data)
    trend_col = trends.columns[0]
    trend_data = trends[trend_col]

    # Compute 4-week rolling average
    trend_ma = trend_data.rolling(4).mean()

    in_position = False
    days_held = 0

    for i in range(1, len(trading_days)):
        day = trading_days[i]
        day_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]

        if in_position:
            days_held += 1
            if days_held >= 5:
                portfolio.sell("QQQ", all_shares=True, date=day_str)
                in_position = False
                days_held = 0
        else:
            # Find the most recent trends data point
            trend_mask = trend_data.index <= day
            ma_mask = trend_ma.index <= day
            if not trend_mask.any() or not ma_mask.any():
                continue

            current_trend = float(trend_data.loc[trend_mask].iloc[-1])
            current_ma = float(trend_ma.loc[ma_mask].iloc[-1])

            if pd.isna(current_ma) or current_ma < 1:
                continue

            # Spike: current is 50%+ above 4-week average
            spike_ratio = current_trend / current_ma
            if spike_ratio >= 1.5:
                result = portfolio.buy("QQQ", dollars=portfolio.cash * 0.90, date=day_str)
                if result:
                    in_position = True
                    days_held = 0

    # Close remaining
    if in_position and trading_days:
        last = trading_days[-1].strftime("%Y-%m-%d")
        portfolio.sell("QQQ", all_shares=True, date=last)
