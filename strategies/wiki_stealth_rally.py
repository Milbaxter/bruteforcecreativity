"""
Wikipedia Stealth Rally
Stocks rising quietly without retail attention have room to run.
Combines: price momentum + LOW Wikipedia attention + VIX filter.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Wiki Stealth Rally",
    "hypothesis": "Stocks that are trending up BUT have declining or flat Wikipedia pageviews "
                  "are 'stealth rallies' — rising without retail FOMO. These tend to continue "
                  "because the retail crowd hasn't piled in yet. Once Wikipedia/Google attention "
                  "spikes, the easy money is gone. We buy the quiet risers and sell before the "
                  "crowd arrives. VIX filter avoids buying into broad panic.",
    "universe": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "NFLX", "CRM"],
    "entry": "Buy when stock has >5% gain in 20 days AND Wikipedia pageviews are flat/declining "
             "over same period AND VIX < 25 (no panic). Sell after 7 days or +5% gain or -3% stop.",
    "exit": "7-day time exit, +5% take profit, or -3% stop loss",
    "position_size": "25% of capital per position, max 2 concurrent",
    "eccentricity": "Inverse of the typical attention trade — instead of buying attention spikes, "
                    "we buy LACK of attention on rising stocks. No fund would use Wikipedia "
                    "pageviews as a negative signal filter.",
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

    # Fetch VIX
    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    # Fetch Wikipedia pageviews for each ticker's company page
    wiki_articles = {
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
    }

    wiki_data = {}
    for ticker, article in wiki_articles.items():
        try:
            views = data_fetcher.get_wikipedia_pageviews(article)
            if views is not None and not views.empty:
                wiki_data[ticker] = views
        except Exception:
            pass

    if not price_data or not wiki_data:
        return

    # Get trading days from SPY-like reference
    ref_ticker = next(iter(price_data))
    trading_days = price_data[ref_ticker].index.tolist()

    # Track open positions: ticker -> {entry_date, entry_price, shares}
    open_positions = {}
    MAX_POSITIONS = 2

    for i in range(25, len(trading_days)):
        date = trading_days[i]
        date_str = date.strftime("%Y-%m-%d")

        # Check exits first
        tickers_to_close = []
        for ticker, pos in open_positions.items():
            if ticker not in price_data:
                continue
            current_price = float(price_data[ticker]["Close"].loc[:date].iloc[-1])
            entry_price = pos["entry_price"]
            days_held = (date - pos["entry_date"]).days

            pct_change = (current_price - entry_price) / entry_price

            # Exit conditions: 7-day hold, +5% take profit, -3% stop loss
            if days_held >= 7 or pct_change >= 0.05 or pct_change <= -0.03:
                portfolio.sell(ticker, all_shares=True, date=date_str)
                tickers_to_close.append(ticker)

        for t in tickers_to_close:
            del open_positions[t]

        # Check entries (only if we have room)
        if len(open_positions) >= MAX_POSITIONS:
            continue

        # VIX filter: no entries during high fear
        vix_val = None
        if vix is not None and not vix.empty:
            vix_before = vix.loc[:date]
            if not vix_before.empty:
                vix_val = float(vix_before.iloc[-1])

        if vix_val is not None and vix_val >= 25:
            continue

        # Score each ticker
        candidates = []
        for ticker in tickers:
            if ticker in open_positions:
                continue
            if ticker not in price_data:
                continue

            closes = price_data[ticker]["Close"].loc[:date]
            if len(closes) < 25:
                continue

            # Price momentum: 20-day return
            price_now = float(closes.iloc[-1])
            price_20d_ago = float(closes.iloc[-21]) if len(closes) > 21 else float(closes.iloc[0])
            price_mom = (price_now - price_20d_ago) / price_20d_ago

            # Need >5% gain over 20 days
            if price_mom < 0.05:
                continue

            # Wikipedia pageview trend over last 20 days
            if ticker not in wiki_data:
                continue

            wiki = wiki_data[ticker]
            # Wiki data is daily — get the last ~20 days
            wiki_recent = wiki.loc[:date_str].tail(20)
            if len(wiki_recent) < 10:
                continue

            # Check if pageviews are flat or declining
            # Compare first half average to second half average
            half = len(wiki_recent) // 2
            first_half_avg = wiki_recent.iloc[:half].mean()
            second_half_avg = wiki_recent.iloc[half:].mean()

            if first_half_avg <= 0:
                continue

            wiki_change = (second_half_avg - first_half_avg) / first_half_avg

            # We want FLAT or DECLINING attention (wiki_change <= 0.1)
            # Strong momentum + low attention = stealth rally
            if wiki_change > 0.10:
                continue  # Skip — attention is rising, crowd already noticed

            # Score: higher price momentum + lower wiki attention = better
            score = price_mom - wiki_change
            candidates.append((ticker, score, price_mom, wiki_change))

        # Sort by score (best stealth rally first)
        candidates.sort(key=lambda x: x[1], reverse=True)

        for ticker, score, mom, wiki_chg in candidates:
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
