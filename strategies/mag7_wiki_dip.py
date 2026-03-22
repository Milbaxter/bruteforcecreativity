"""
Magnificent 7 Wiki Dip — buy individual mega-cap stocks when their Wikipedia
attention spikes AND price has dipped from recent high.

Attention spike + price dip = news-driven pullback that retail is reading
about but hasn't bought yet. Mean reversion kicks in 3-5 days later.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Mag 7 Wiki Dip",
    "hypothesis": "When a Magnificent 7 stock dips 2%+ from its 10-day high while Wikipedia attention is elevated, it signals a news-driven pullback that is likely to revert. Retail attention confirms the event is priced in.",
    "universe": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA"],
    "entry": "Buy when wiki attention >40% above 20d avg AND price is 2%+ below 10d high AND crypto fear/greed > 25",
    "exit": "Sell after 5 days or on +3% profit target or -4% stop loss",
    "position_size": "$3000 per trade, max 3 concurrent positions",
    "eccentricity": "Using Wikipedia as an event detector for mega-cap dip buying — institutional funds don't trade individual stocks based on Wikipedia pageviews. The attention signal confirms the dip is news-driven rather than sector rotation.",
}

# Wiki article names for each stock
WIKI_ARTICLES = {
    "AAPL": "Apple_Inc.",
    "MSFT": "Microsoft",
    "NVDA": "Nvidia",
    "GOOGL": "Alphabet_Inc.",
    "AMZN": "Amazon_(company)",
    "META": "Meta_Platforms",
    "TSLA": "Tesla,_Inc.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch prices
    prices = {}
    for ticker in STRATEGY["universe"]:
        try:
            df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            prices[ticker] = df
        except Exception:
            continue

    if len(prices) < 3:
        return

    # Fetch Wikipedia pageviews
    wiki_data = {}
    for ticker, article in WIKI_ARTICLES.items():
        if ticker not in prices:
            continue
        try:
            pv = data_fetcher.get_wikipedia_pageviews(article)
            if pv is not None and not pv.empty:
                pv.index = pd.to_datetime(pv.index)
                wiki_data[ticker] = pv.sort_index()
        except Exception:
            continue

    if len(wiki_data) < 3:
        return

    # Crypto fear/greed
    try:
        fear_greed = data_fetcher.get_crypto_fear_greed(days=400)
    except Exception:
        fear_greed = None

    # Get common trading days
    all_dates = set()
    for df in prices.values():
        for dt in df.index:
            all_dates.add(dt)
    trading_days = sorted(all_dates)

    if len(trading_days) < 25:
        return

    # Track open positions with entry info
    open_positions = {}  # ticker -> {entry_price, entry_idx, entry_date}
    max_concurrent = 3
    position_dollars = 3000
    max_hold = 5
    profit_target = 0.03
    stop_loss = -0.04
    lookback = 20
    dip_threshold = -0.02  # 2% below 10d high
    wiki_spike = 0.40  # 40% above 20d avg

    for i, day in enumerate(trading_days):
        if i < lookback + 1:
            continue

        date_str = day.strftime("%Y-%m-%d") if hasattr(day, 'strftime') else str(day)[:10]

        # Check exits first
        tickers_to_close = []
        for ticker, info in open_positions.items():
            if ticker not in prices:
                continue
            df = prices[ticker]
            df_before = df[df.index <= day]
            if df_before.empty:
                continue

            current_price = float(df_before["Close"].iloc[-1])
            entry_price = info["entry_price"]
            days_held = i - info["entry_idx"]

            pnl_pct = (current_price - entry_price) / entry_price

            if pnl_pct >= profit_target or pnl_pct <= stop_loss or days_held >= max_hold:
                if ticker in portfolio.positions:
                    portfolio.sell(ticker, all_shares=True, date=date_str)
                tickers_to_close.append(ticker)

        for t in tickers_to_close:
            del open_positions[t]

        # Check entries
        if len(open_positions) >= max_concurrent:
            continue

        # Crypto fear/greed filter
        fg_val = 50
        if fear_greed is not None and not fear_greed.empty:
            fg_before = fear_greed[fear_greed.index <= day]
            if len(fg_before) > 0:
                fg_val = float(fg_before.iloc[-1])

        if fg_val < 25:
            continue  # too fearful

        for ticker in STRATEGY["universe"]:
            if ticker in open_positions:
                continue
            if len(open_positions) >= max_concurrent:
                break
            if ticker not in prices or ticker not in wiki_data:
                continue

            df = prices[ticker]
            df_before = df[df.index <= day]
            if len(df_before) < lookback + 1:
                continue

            # Check price dip from 10d high
            recent_high = float(df_before["Close"].iloc[-10:].max())
            current_price = float(df_before["Close"].iloc[-1])
            dip_pct = (current_price - recent_high) / recent_high

            if dip_pct > dip_threshold:
                continue  # not enough of a dip

            # Check wiki attention spike
            wiki_pv = wiki_data[ticker]
            wiki_before = wiki_pv[wiki_pv.index <= day]
            if len(wiki_before) < lookback + 1:
                continue

            recent_wiki = float(wiki_before.iloc[-3:].mean())
            avg_wiki = float(wiki_before.iloc[-lookback:].mean())

            if avg_wiki <= 0:
                continue
            wiki_change = (recent_wiki - avg_wiki) / avg_wiki

            if wiki_change < wiki_spike:
                continue  # no attention spike

            # Signal! Buy
            result = portfolio.buy(ticker, dollars=position_dollars, date=date_str)
            if result:
                open_positions[ticker] = {
                    "entry_price": current_price,
                    "entry_idx": i,
                    "entry_date": date_str,
                }

    # Close all remaining positions
    end_str = trading_days[-1].strftime("%Y-%m-%d") if hasattr(trading_days[-1], 'strftime') else str(trading_days[-1])[:10]
    for ticker in list(open_positions.keys()):
        if ticker in portfolio.positions:
            portfolio.sell(ticker, all_shares=True, date=end_str)
