"""
Earnings Wiki Drift
Post-earnings drift amplified by sustained Wikipedia attention.
Combines: earnings beat > 3% + Wikipedia pageviews rising + price above 5-day MA.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Earnings Wiki Drift",
    "hypothesis": "Stocks that beat earnings by >3% continue drifting up for 5-10 days (post-earnings "
                  "announcement drift is well-documented). BUT we filter for only those where Wikipedia "
                  "pageviews are RISING after earnings — sustained attention means the beat is being "
                  "digested, not a one-day spike. Also require price above 5-day MA (trend confirmation). "
                  "Three independent signals: fundamental surprise + attention persistence + price trend.",
    "universe": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "NFLX",
                 "CRM", "ORCL", "AVGO", "ADBE", "INTC", "PYPL"],
    "entry": "Buy 2 days after earnings IF: (1) EPS surprise > 3%, (2) Wikipedia pageviews "
             "for company are above their 30-day average, (3) price > 5-day MA",
    "exit": "Sell 7 days after entry, +6% take profit, -3% stop loss",
    "position_size": "25% of capital per position, max 3 concurrent",
    "eccentricity": "Combining earnings fundamental data with Wikipedia attention data is absurd — "
                    "no quant model includes Wikipedia pageviews as a factor. But sustained attention "
                    "after a beat predicts continued drift because it means the story has legs.",
}

# Map tickers to Wikipedia article names
WIKI_ARTICLES = {
    "AAPL": "Apple_Inc.",
    "MSFT": "Microsoft",
    "NVDA": "Nvidia",
    "AMZN": "Amazon_(company)",
    "GOOGL": "Alphabet_Inc.",
    "META": "Meta_Platforms",
    "TSLA": "Tesla,_Inc.",
    "AMD": "Advanced_Micro_Devices",
    "NFLX": "Netflix",
    "CRM": "Salesforce",
    "ORCL": "Oracle_Corporation",
    "AVGO": "Broadcom_Inc.",
    "ADBE": "Adobe_Inc.",
    "INTC": "Intel",
    "PYPL": "PayPal",
}


def run(data_fetcher, portfolio, start_date, end_date):
    tickers = STRATEGY["universe"]

    # Fetch price data
    price_data = {}
    for ticker in tickers:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            price_data[ticker] = df

    # Fetch earnings calendar
    earnings = data_fetcher.get_earnings_calendar(tickers)

    # Fetch Wikipedia pageviews
    wiki_data = {}
    for ticker, article in WIKI_ARTICLES.items():
        try:
            views = data_fetcher.get_wikipedia_pageviews(article)
            if views is not None and not views.empty:
                wiki_data[ticker] = views
        except Exception:
            pass

    if earnings is None or earnings.empty:
        return
    if not price_data:
        return

    # Parse earnings into a usable format: {ticker: [(date, surprise_pct), ...]}
    earnings_events = {}
    for _, row in earnings.iterrows():
        ticker = row.get("ticker") or row.get("Ticker") or row.get("symbol")
        if ticker is None:
            continue
        ticker = str(ticker).upper()
        if ticker not in tickers:
            continue

        date = row.get("date") or row.get("Date") or row.get("Earnings Date")
        if date is None:
            continue
        if isinstance(date, str):
            try:
                date = pd.Timestamp(date)
            except Exception:
                continue

        # Calculate surprise percentage
        estimate = row.get("eps_estimate") or row.get("EPS Estimate") or row.get("epsEstimate")
        actual = row.get("eps_actual") or row.get("Reported EPS") or row.get("epsActual")
        surprise = row.get("surprise") or row.get("Surprise(%)")

        surprise_pct = None
        if surprise is not None:
            try:
                surprise_pct = float(surprise)
            except (ValueError, TypeError):
                pass

        if surprise_pct is None and estimate is not None and actual is not None:
            try:
                est = float(estimate)
                act = float(actual)
                if abs(est) > 0.01:
                    surprise_pct = ((act - est) / abs(est)) * 100
            except (ValueError, TypeError):
                pass

        if surprise_pct is not None:
            if ticker not in earnings_events:
                earnings_events[ticker] = []
            earnings_events[ticker].append((date, surprise_pct))

    if not earnings_events:
        return

    # Get trading days
    ref_ticker = next(iter(price_data))
    trading_days = price_data[ref_ticker].index.tolist()

    open_positions = {}  # ticker -> {entry_date, entry_price}
    MAX_POSITIONS = 3
    # Track which earnings we've already acted on
    used_earnings = set()

    for i in range(10, len(trading_days)):
        date = trading_days[i]
        date_str = date.strftime("%Y-%m-%d")

        # Check exits
        tickers_to_close = []
        for ticker, pos in open_positions.items():
            if ticker not in price_data:
                continue
            current_price = float(price_data[ticker]["Close"].loc[:date].iloc[-1])
            entry_price = pos["entry_price"]
            days_held = (date - pos["entry_date"]).days
            pct_change = (current_price - entry_price) / entry_price

            if days_held >= 7 or pct_change >= 0.06 or pct_change <= -0.03:
                portfolio.sell(ticker, all_shares=True, date=date_str)
                tickers_to_close.append(ticker)

        for t in tickers_to_close:
            del open_positions[t]

        if len(open_positions) >= MAX_POSITIONS:
            continue

        # Check for earnings events 2 days ago
        check_date = trading_days[i - 2] if i >= 2 else trading_days[0]

        for ticker, events in earnings_events.items():
            if ticker in open_positions:
                continue
            if ticker not in price_data:
                continue

            for earn_date, surprise_pct in events:
                event_key = f"{ticker}_{earn_date}"
                if event_key in used_earnings:
                    continue

                # Check if earnings was ~2 trading days ago
                # Normalize timezones for comparison
                date_naive = pd.Timestamp(date).tz_localize(None) if hasattr(date, 'tzinfo') and date.tzinfo else pd.Timestamp(date)
                earn_naive = pd.Timestamp(earn_date).tz_localize(None) if hasattr(earn_date, 'tzinfo') and earn_date.tzinfo else pd.Timestamp(earn_date)
                days_since = (date_naive - earn_naive).days
                if days_since < 1 or days_since > 5:
                    continue

                # Signal 1: EPS surprise > 3%
                if surprise_pct < 3.0:
                    continue

                # Signal 2: Wikipedia attention above 30-day average
                if ticker in wiki_data:
                    wiki = wiki_data[ticker]
                    wiki_recent = wiki.loc[:date_str]
                    if len(wiki_recent) >= 30:
                        recent_avg = wiki_recent.tail(5).mean()
                        baseline_avg = wiki_recent.tail(30).mean()
                        if baseline_avg > 0 and recent_avg < baseline_avg * 1.0:
                            continue  # Attention not elevated

                # Signal 3: Price above 5-day MA
                closes = price_data[ticker]["Close"].loc[:date]
                if len(closes) < 6:
                    continue
                price_now = float(closes.iloc[-1])
                ma_5 = float(closes.tail(5).mean())
                if price_now < ma_5:
                    continue

                # All three signals confirmed — buy
                used_earnings.add(event_key)

                if len(open_positions) >= MAX_POSITIONS:
                    break

                dollars = portfolio.cash * 0.25
                if dollars < 100:
                    break

                result = portfolio.buy(ticker, dollars=dollars, date=date_str)
                if result:
                    open_positions[ticker] = {
                        "entry_date": date,
                        "entry_price": result["exec_price"],
                    }
