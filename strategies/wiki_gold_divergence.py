"""
Wikipedia Gold Divergence Trader

Hypothesis: Wikipedia "Gold" daily pageviews track retail attention to gold.
When gold attention is rising AND the GLD/SPY ratio is increasing (gold outperforming
stocks), it signals a fear regime → buy GDX (gold miners, leveraged gold exposure).
When gold attention is declining AND GLD/SPY ratio falling, it's risk-on → buy SOXX.

The Wikipedia signal adds a behavioral dimension beyond pure price:
rising gold attention = people seeking safety information
falling gold attention = people not worried about their portfolio

Signals:
1. WHY: Wikipedia Gold pageview 7-day trend direction
2. WHEN: GLD/SPY ratio 5-day direction confirms wiki signal
3. ASSET: GDX on fear (wiki up + ratio up), SOXX on greed (wiki down + ratio down)
4. TIMING: Rotate every 5 days when signal changes
5. WHEN NOT: VIX > 40

Eccentricity: Wikipedia Gold article traffic as market fear proxy, combined with
relative price action. Double-confirmation from different domains.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Wiki Gold Divergence",
    "hypothesis": "Wikipedia Gold attention direction + GLD/SPY ratio direction determine fear/greed regime for GDX vs SOXX allocation.",
    "universe": ["GDX", "SOXX", "GLD", "SPY"],
    "entry": "Buy GDX when wiki gold rising + GLD/SPY ratio rising; SOXX when both falling",
    "exit": "Hold 5 days then reassess; -4% stop loss on any position",
    "position_size": "70% of capital per trade",
    "eccentricity": "Wikipedia daily traffic analysis as fear barometer. Retail information-seeking behavior as a tradeable signal.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    gdx = data_fetcher.get_prices("GDX", start=start_date, end=end_date)
    if isinstance(gdx.columns, pd.MultiIndex):
        gdx.columns = gdx.columns.get_level_values(0)
    gdx_close = gdx["Close"].dropna()

    soxx = data_fetcher.get_prices("SOXX", start=start_date, end=end_date)
    if isinstance(soxx.columns, pd.MultiIndex):
        soxx.columns = soxx.columns.get_level_values(0)
    soxx_close = soxx["Close"].dropna()

    gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)
    if isinstance(gld.columns, pd.MultiIndex):
        gld.columns = gld.columns.get_level_values(0)
    gld_close = gld["Close"].dropna()

    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
    spy_close = spy["Close"].dropna()

    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    wiki_gold = data_fetcher.get_wikipedia_pageviews("Gold", start=start_date, end=end_date)

    if gdx_close.empty or soxx_close.empty or wiki_gold.empty:
        return

    # Compute GLD/SPY ratio
    common_idx = gld_close.index.intersection(spy_close.index)
    gld_spy_ratio = gld_close.reindex(common_idx) / spy_close.reindex(common_idx)

    # Wiki Gold 7-day MA for trend
    wiki_ma7 = wiki_gold.rolling(7).mean()
    wiki_ma21 = wiki_gold.rolling(21).mean()

    trading_days = gdx_close.index.strftime("%Y-%m-%d").tolist()
    in_trade = False
    trade_ticker = None
    entry_date = None
    entry_price = None
    last_signal = None  # "fear" or "greed"

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

        # Exit conditions
        if in_trade:
            days_held = (date_ts - pd.Timestamp(entry_date)).days
            if trade_ticker == "GDX":
                close_s = gdx_close
            else:
                close_s = soxx_close
            mask = close_s.index <= date_ts
            if mask.any():
                current_price = close_s[mask].iloc[-1]
                pct_change = (current_price - entry_price) / entry_price * 100

                # Stop loss
                if pct_change <= -4.0:
                    portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                    in_trade = False
                    trade_ticker = None
                    entry_date = None
                    entry_price = None
                    last_signal = None
                    continue

                # Rebalance after 5 days
                if days_held >= 5:
                    portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                    in_trade = False
                    trade_ticker = None
                    entry_date = None
                    entry_price = None
                    # Fall through to potentially enter new position

        # Signal computation
        if i >= 25:
            # VIX filter
            vix_mask = vix.index <= date_ts
            if vix_mask.any() and vix[vix_mask].iloc[-1] > 40:
                continue

            # Wikipedia Gold trend: 7d MA vs 21d MA
            wiki_7_mask = wiki_ma7.dropna().index <= date_ts
            wiki_21_mask = wiki_ma21.dropna().index <= date_ts
            if not wiki_7_mask.any() or not wiki_21_mask.any():
                continue
            wiki_short = wiki_ma7.dropna()[wiki_7_mask].iloc[-1]
            wiki_long = wiki_ma21.dropna()[wiki_21_mask].iloc[-1]

            wiki_rising = wiki_short > wiki_long  # Gold attention trending up

            # GLD/SPY ratio direction (5-day change)
            ratio_mask = gld_spy_ratio.dropna().index <= date_ts
            if not ratio_mask.any():
                continue
            recent_ratio = gld_spy_ratio.dropna()[ratio_mask]
            if len(recent_ratio) < 6:
                continue
            ratio_chg = recent_ratio.iloc[-1] - recent_ratio.iloc[-6]
            ratio_rising = ratio_chg > 0

            # Determine signal
            if wiki_rising and ratio_rising:
                signal = "fear"
            elif not wiki_rising and not ratio_rising:
                signal = "greed"
            else:
                signal = "mixed"

            # Only trade clear signals, skip mixed
            if signal == "mixed":
                continue

            # Skip if same signal as current position
            if in_trade and signal == last_signal:
                continue

            # Enter new position
            if not in_trade:
                if signal == "fear":
                    ticker = "GDX"
                    p_mask = gdx_close.index <= date_ts
                    price = gdx_close[p_mask].iloc[-1] if p_mask.any() else None
                else:
                    ticker = "SOXX"
                    p_mask = soxx_close.index <= date_ts
                    price = soxx_close[p_mask].iloc[-1] if p_mask.any() else None

                if price is None:
                    continue

                dollars = portfolio.cash * 0.7
                if dollars > 100:
                    result = portfolio.buy(ticker, dollars=dollars, date=date_str)
                    if result:
                        in_trade = True
                        trade_ticker = ticker
                        entry_date = date_str
                        entry_price = price
                        last_signal = signal

    if in_trade and trade_ticker:
        portfolio.sell(trade_ticker, all_shares=True, date=trading_days[-1])
