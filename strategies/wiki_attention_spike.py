"""
Wikipedia Attention Spike
Buy stocks when their Wikipedia page gets anomalous traffic spikes.
Retail attention proxy — spikes often precede or accompany price moves.
"""

STRATEGY = {
    "name": "Wiki Attention Spike",
    "hypothesis": "Unusual spikes in Wikipedia pageviews for a company indicate surging retail "
                  "attention. This attention often precedes short-term price momentum as retail "
                  "traders pile in. Buy the spike, ride the momentum 3-5 days, get out.",
    "universe": ["TSLA", "NVDA", "AMD", "AMZN", "META", "NFLX", "AAPL", "GOOG", "MSFT", "PLTR"],
    "entry": "Buy when a stock's Wikipedia pageviews exceed 2x its 30-day rolling average",
    "exit": "Sell after 5 trading days, or at -3% stop loss, or +5% take profit",
    "position_size": "Equal weight, deploy 30% of cash per signal, max 3 concurrent positions",
    "eccentricity": "Wikipedia pageviews as a trading signal is too 'silly' for institutional "
                    "quant teams. No risk committee would approve 'we buy when people Google a stock.' "
                    "But retail attention = retail flow = short-term momentum.",
}

# Map tickers to Wikipedia article names
TICKER_TO_WIKI = {
    "TSLA": "Tesla,_Inc.",
    "NVDA": "Nvidia",
    "AMD": "Advanced_Micro_Devices",
    "AMZN": "Amazon_(company)",
    "META": "Meta_Platforms",
    "NFLX": "Netflix",
    "AAPL": "Apple_Inc.",
    "GOOG": "Alphabet_Inc.",
    "MSFT": "Microsoft",
    "PLTR": "Palantir_Technologies",
}


def run(data_fetcher, portfolio, start_date, end_date):
    import pandas as pd
    import numpy as np

    # Fetch Wikipedia pageviews for all tracked companies
    wiki_data = {}
    for ticker, article in TICKER_TO_WIKI.items():
        try:
            views = data_fetcher.get_wikipedia_pageviews(article)
            if views is not None and not (hasattr(views, 'empty') and views.empty):
                if isinstance(views, pd.Series):
                    views = views.to_frame(name="views")
                views.index = pd.to_datetime(views.index)
                wiki_data[ticker] = views
        except Exception:
            continue

    if not wiki_data:
        return

    # Fetch price data (already preloaded by engine, but we need full date range)
    prices = {}
    for ticker in TICKER_TO_WIKI:
        try:
            df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if not df.empty:
                prices[ticker] = df
        except Exception:
            continue

    # Parameters
    LOOKBACK = 30  # days for rolling average
    SPIKE_MULT = 2.0  # pageview spike multiplier
    MAX_HOLD_DAYS = 5
    STOP_LOSS = -0.03
    TAKE_PROFIT = 0.05
    MAX_POSITIONS = 3
    CASH_PER_SIGNAL = 0.30

    # Get all trading days
    all_dates = set()
    for df in prices.values():
        all_dates.update(df.index.strftime("%Y-%m-%d"))
    trading_days = sorted(d for d in all_dates if start_date <= d <= end_date)

    # Track open positions
    open_positions = {}  # ticker -> {"entry_date": str, "entry_price": float}

    for date_str in trading_days:
        date_ts = pd.Timestamp(date_str)

        # Check exits first
        for ticker in list(open_positions.keys()):
            if ticker not in prices:
                continue
            pos = open_positions[ticker]
            entry_price = pos["entry_price"]
            entry_date = pd.Timestamp(pos["entry_date"])
            days_held = (date_ts - entry_date).days

            current_price_data = prices[ticker]["Close"].loc[:date_ts]
            if current_price_data.empty:
                continue
            current_price = float(current_price_data.iloc[-1])
            ret = (current_price - entry_price) / entry_price

            should_exit = False
            if days_held >= MAX_HOLD_DAYS:
                should_exit = True
            if ret <= STOP_LOSS:
                should_exit = True
            if ret >= TAKE_PROFIT:
                should_exit = True

            if should_exit:
                portfolio.sell(ticker, all_shares=True, date=date_str)
                del open_positions[ticker]

        # Check entries
        if len(open_positions) >= MAX_POSITIONS:
            continue

        # Score all tickers by pageview spike strength
        candidates = []
        for ticker, wiki_df in wiki_data.items():
            if ticker in open_positions:
                continue
            if ticker not in prices:
                continue

            # Get pageviews up to current date
            wiki_up_to = wiki_df.loc[:date_ts]
            if len(wiki_up_to) < LOOKBACK + 1:
                continue

            col = "views" if "views" in wiki_up_to.columns else wiki_up_to.columns[0]
            recent = wiki_up_to[col].iloc[-LOOKBACK - 1:-1]
            current_views = float(wiki_up_to[col].iloc[-1])
            avg_views = float(recent.mean())

            if avg_views > 0 and current_views > avg_views * SPIKE_MULT:
                spike_ratio = current_views / avg_views
                candidates.append((ticker, spike_ratio))

        # Sort by spike strength, take top candidates
        candidates.sort(key=lambda x: x[1], reverse=True)

        for ticker, spike_ratio in candidates:
            if len(open_positions) >= MAX_POSITIONS:
                break

            cash_available = portfolio.cash * CASH_PER_SIGNAL
            if cash_available < 100:
                break

            result = portfolio.buy(ticker, dollars=cash_available, date=date_str)
            if result:
                price_data = prices[ticker]["Close"].loc[:date_ts]
                entry_price = float(price_data.iloc[-1])
                open_positions[ticker] = {
                    "entry_date": date_str,
                    "entry_price": entry_price,
                }

    # Close any remaining positions
    if trading_days:
        last_day = trading_days[-1]
        for ticker in list(open_positions.keys()):
            portfolio.sell(ticker, all_shares=True, date=last_day)
