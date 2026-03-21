"""
Fear to Greed Swing: Buy leveraged QQQ (via concentrated position) when fear/greed
score transitions from fear (<30) to neutral (>35), ride it until greed (>70).

Thesis: Sentiment swings are self-reinforcing in the short term. When markets
transition from fear to neutral, the "all clear" signal triggers a rush of
buying that overshoots into greed. We ride this wave. The key is the TRANSITION
— not the absolute level — because the transition signals changing momentum.

We combine Fear/Greed with sector strength: buy the strongest sector ETF
during the fear-to-greed transition to amplify the bounce.
"""

import pandas as pd

STRATEGY = {
    "name": "Fear to Greed Swing",
    "hypothesis": "When market sentiment transitions from fear to neutral, it triggers cascading buy signals that push into greed. Riding this wave in the strongest sector amplifies returns.",
    "universe": [
        "SPY", "QQQ", "XLK", "XLF", "XLE", "XLV", "XLI", "XLY",
    ],
    "entry": "Buy when F&G crosses above 35 (coming from below 30), pick strongest 5-day sector",
    "exit": "Sell when F&G reaches 70+ (greed), or after 10 trading days, or -4% stop loss",
    "position_size": "80% of cash, concentrated in best momentum sector",
    "eccentricity": "Combines sentiment regime detection with sector momentum — two signals institutional models treat separately. The concentrated bet on one sector during sentiment transitions is too aggressive for fund mandates.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Get fear/greed scores
    fg = data_fetcher.get_fear_greed(start=start_date, end=end_date)
    if fg.empty:
        return

    # Get sector prices
    sectors = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "QQQ"]
    all_prices = {}
    for ticker in STRATEGY["universe"]:
        try:
            p = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
            if isinstance(p.columns, pd.MultiIndex):
                p.columns = p.columns.get_level_values(0)
            if not p.empty and "Close" in p.columns:
                all_prices[ticker] = p["Close"]
        except Exception:
            continue

    spy_prices = all_prices.get("SPY")
    if spy_prices is None:
        return

    trading_days = sorted(spy_prices.index)

    in_position = False
    current_ticker = None
    entry_price = None
    days_held = 0
    was_fearful = False  # Track if we were recently in fear territory

    for i in range(5, len(trading_days)):
        day = trading_days[i]
        day_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]

        # Get fear/greed score (use closest available date)
        fg_mask = fg.index <= day
        if not fg_mask.any():
            continue
        current_fg = float(fg.loc[fg_mask].iloc[-1])

        # Track fear state
        if current_fg < 30:
            was_fearful = True

        if in_position:
            days_held += 1

            # Current price check
            if current_ticker in all_prices and day in all_prices[current_ticker].index:
                current_price = float(all_prices[current_ticker].loc[day])
                pct_change = (current_price - entry_price) / entry_price

                # Exit conditions
                if current_fg > 70 or days_held >= 10 or pct_change <= -0.04:
                    portfolio.sell(current_ticker, all_shares=True, date=day_str)
                    in_position = False
                    current_ticker = None
                    entry_price = None
                    days_held = 0
                    was_fearful = False
        else:
            # Entry: was in fear (<30), now crossing above 35
            if was_fearful and current_fg > 35:
                # Find strongest sector over last 5 days
                lookback = trading_days[i - 5]
                momentum = {}
                for ticker in sectors:
                    if ticker in all_prices:
                        series = all_prices[ticker]
                        if day in series.index and lookback in series.index:
                            current = float(series.loc[day])
                            past = float(series.loc[lookback])
                            if past > 0:
                                momentum[ticker] = (current - past) / past

                if not momentum:
                    continue

                best_ticker = max(momentum, key=momentum.get)

                result = portfolio.buy(best_ticker, dollars=portfolio.cash * 0.80, date=day_str)
                if result:
                    in_position = True
                    current_ticker = best_ticker
                    entry_price = float(all_prices[best_ticker].loc[day])
                    days_held = 0
                    was_fearful = False

    # Close remaining
    if in_position and trading_days:
        last = trading_days[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_ticker, all_shares=True, date=last)
