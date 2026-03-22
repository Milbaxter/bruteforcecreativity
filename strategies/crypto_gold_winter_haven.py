"""
Crypto Gold Winter Haven

Hypothesis: Three independent fear signals converging = strong safe-haven flow into gold:
1. Crypto Fear & Greed in fear territory (crypto investors fleeing risk)
2. Wikipedia "Gold" pageviews elevated (retail searching for safe haven)
3. Cold weather in major financial centers (seasonal affective gloom + heating costs)

When all three align, GLD gets inflows from multiple directions simultaneously.
Each signal alone is weak; together they capture a genuine risk-off moment.

Eccentricity: Combining crypto sentiment, Wikipedia attention, and physical weather
into a single gold trade thesis. This is the exact kind of weird cross-domain signal
no institutional committee would approve.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Crypto Gold Winter Haven",
    "hypothesis": "Triple convergence of crypto fear + gold wiki attention + cold weather signals strong safe-haven demand for GLD.",
    "universe": ["GLD", "GDX"],
    "entry": "Buy GLD/GDX when crypto fear < 40 AND gold wiki > 1.2x avg AND cold weather in NYC/Chicago",
    "exit": "Sell after 5 trading days or +3% gain or -2.5% stop loss",
    "position_size": "60% of capital per trade, split GLD/GDX",
    "eccentricity": "Triple cross-domain signal: crypto sentiment + Wikipedia + weather. Too bizarre for any fund's risk model.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)
    if isinstance(gld.columns, pd.MultiIndex):
        gld.columns = gld.columns.get_level_values(0)
    gld_close = gld["Close"].dropna()

    gdx = data_fetcher.get_prices("GDX", start=start_date, end=end_date)
    if isinstance(gdx.columns, pd.MultiIndex):
        gdx.columns = gdx.columns.get_level_values(0)
    gdx_close = gdx["Close"].dropna()

    # Signals
    crypto_fg = data_fetcher.get_crypto_fear_greed(days=500)
    wiki_gold = data_fetcher.get_wikipedia_pageviews("Gold", start=start_date, end=end_date)
    nyc_weather = data_fetcher.get_weather_history(40.71, -74.01, start=start_date, end=end_date)
    chi_weather = data_fetcher.get_weather_history(41.88, -87.63, start=start_date, end=end_date)

    if gld_close.empty or crypto_fg.empty or wiki_gold.empty:
        return

    wiki_ma20 = wiki_gold.rolling(20).mean()
    gld_ma10 = gld_close.rolling(10).mean()

    trading_days = gld_close.index.strftime("%Y-%m-%d").tolist()
    in_trade = False
    trade_ticker = None
    entry_date = None
    entry_price = None

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)
        price = gld_close.iloc[i]

        # Exit
        if in_trade:
            days_held = (date_ts - pd.Timestamp(entry_date)).days
            if trade_ticker == "GDX":
                close_series = gdx_close
            else:
                close_series = gld_close
            mask = close_series.index <= date_ts
            if mask.any():
                current_price = close_series[mask].iloc[-1]
                pct_change = (current_price - entry_price) / entry_price * 100
                if days_held >= 5 or pct_change >= 3.0 or pct_change <= -2.5:
                    portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                    in_trade = False
                    trade_ticker = None
                    entry_date = None
                    entry_price = None
                    continue

        # Entry
        if not in_trade and i >= 25:
            # Signal 1: Crypto Fear & Greed < 40
            fg_mask = crypto_fg.index <= date_ts
            if not fg_mask.any():
                continue
            current_fg = crypto_fg[fg_mask].iloc[-1]
            if current_fg >= 40:
                continue

            # Signal 2: Gold Wikipedia attention > 1.2x 20-day average
            wiki_mask = wiki_gold.index <= date_ts
            if not wiki_mask.any():
                continue
            current_wiki = wiki_gold[wiki_mask].iloc[-1]

            ma_mask = wiki_ma20.dropna().index <= date_ts
            if not ma_mask.any():
                continue
            current_ma = wiki_ma20.dropna()[ma_mask].iloc[-1]

            if current_ma <= 0 or current_wiki < current_ma * 1.2:
                continue

            # Signal 3: Cold weather - low temp < 0°C in NYC or Chicago in last 3 days
            cold_detected = False
            for offset in range(0, 3):
                check_date = date_ts - pd.Timedelta(days=offset)
                for wx in [nyc_weather, chi_weather]:
                    if not wx.empty and "temperature_2m_min" in wx.columns:
                        wx_mask = wx.index <= check_date
                        if wx_mask.any():
                            temp = wx.loc[wx_mask, "temperature_2m_min"].iloc[-1]
                            if not pd.isna(temp) and temp < 0.0:
                                cold_detected = True
                                break
                if cold_detected:
                    break

            if not cold_detected:
                continue

            # Choose GDX (leveraged gold exposure) if GDX has better 5d momentum, else GLD
            ticker = "GLD"
            trade_price = price
            if i >= 5:
                gld_mom = (price - gld_close.iloc[i-5]) / gld_close.iloc[i-5]
                gdx_mask = gdx_close.index <= date_ts
                if gdx_mask.any():
                    gdx_recent = gdx_close[gdx_mask]
                    if len(gdx_recent) >= 5:
                        gdx_mom = (gdx_recent.iloc[-1] - gdx_recent.iloc[-5]) / gdx_recent.iloc[-5]
                        if gdx_mom > gld_mom:
                            ticker = "GDX"
                            trade_price = gdx_recent.iloc[-1]

            dollars = portfolio.cash * 0.6
            if dollars > 100:
                result = portfolio.buy(ticker, dollars=dollars, date=date_str)
                if result:
                    in_trade = True
                    trade_ticker = ticker
                    entry_date = date_str
                    entry_price = trade_price

    if in_trade and trade_ticker:
        portfolio.sell(trade_ticker, all_shares=True, date=trading_days[-1])
