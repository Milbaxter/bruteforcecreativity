"""
Gap Down Reversal: Buy stocks that gap down >3% from previous close to open,
betting on intraday/next-day mean reversion.

Thesis: Large overnight gaps in liquid stocks are often driven by pre-market
panic on news that doesn't warrant the full move. Market makers widen spreads,
retail panic sells, and by mid-day or next day the gap fills partially.
This is a well-known daytrader pattern scaled to daily bars.
"""

import pandas as pd

STRATEGY = {
    "name": "Gap Down Reversal",
    "hypothesis": "Stocks that gap down >3% overnight tend to partially fill the gap within 1-2 days. The overnight panic overshoots and mean reverts during regular hours.",
    "universe": [
        "SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
        "JPM", "V", "AMD", "NFLX", "CRM", "BA", "DIS", "COST", "WMT",
        "XLF", "XLE", "XLV", "XLK",
    ],
    "entry": "Buy when a stock gaps down >3% (open vs previous close)",
    "exit": "Sell next trading day, or at +2% take profit / -2% stop loss intraday",
    "position_size": "25% of available cash per trade, max 3 concurrent",
    "eccentricity": "Pure overnight gap exploitation — too fast for institutional approval processes. Funds can't trade on 'the stock gapped down, buy it' as a thesis.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    universe = STRATEGY["universe"]

    # Load all price data
    all_prices = {}
    for ticker in universe:
        try:
            p = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
            if isinstance(p.columns, pd.MultiIndex):
                p.columns = p.columns.get_level_values(0)
            if not p.empty and "Open" in p.columns and "Close" in p.columns:
                all_prices[ticker] = p
        except Exception:
            continue

    if not all_prices:
        return

    # Use SPY trading days as reference
    ref_ticker = "SPY" if "SPY" in all_prices else list(all_prices.keys())[0]
    trading_days = sorted(all_prices[ref_ticker].index)

    open_positions = {}  # ticker -> {entry_date, entry_price}
    max_concurrent = 3

    for i in range(1, len(trading_days)):
        today = trading_days[i]
        yesterday = trading_days[i - 1]
        today_str = today.strftime("%Y-%m-%d") if hasattr(today, "strftime") else str(today)[:10]

        # First: close any open positions (sell next day)
        tickers_to_close = []
        for ticker in list(open_positions.keys()):
            tickers_to_close.append(ticker)

        for ticker in tickers_to_close:
            portfolio.sell(ticker, all_shares=True, date=today_str)
            del open_positions[ticker]

        # Then: scan for new gap-down entries
        if len(open_positions) >= max_concurrent:
            continue

        candidates = []
        for ticker, prices in all_prices.items():
            if ticker in open_positions:
                continue
            if today not in prices.index or yesterday not in prices.index:
                continue

            prev_close = float(prices.loc[yesterday, "Close"])
            today_open = float(prices.loc[today, "Open"])

            if prev_close <= 0:
                continue

            gap_pct = (today_open - prev_close) / prev_close

            # Gap down more than 3%
            if gap_pct < -0.03:
                candidates.append((ticker, gap_pct))

        # Sort by largest gap (most oversold first)
        candidates.sort(key=lambda x: x[1])

        for ticker, gap_pct in candidates:
            if len(open_positions) >= max_concurrent:
                break

            cash_per_trade = portfolio.cash * 0.25
            if cash_per_trade < 100:
                break

            result = portfolio.buy(ticker, dollars=cash_per_trade, date=today_str)
            if result:
                today_close = float(all_prices[ticker].loc[today, "Close"])
                open_positions[ticker] = {
                    "entry_date": today_str,
                    "entry_price": today_close,
                }

    # Close remaining
    if trading_days and open_positions:
        last = trading_days[-1].strftime("%Y-%m-%d")
        for ticker in list(open_positions.keys()):
            portfolio.sell(ticker, all_shares=True, date=last)
