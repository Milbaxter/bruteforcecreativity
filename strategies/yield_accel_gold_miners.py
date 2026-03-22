"""
Yield Acceleration Gold Miners

Hypothesis: When the 10Y yield is ACCELERATING its decline (rate of change is
increasingly negative), it signals intensifying flight-to-safety. Gold miners
(GDX) are leveraged to gold price and benefit disproportionately. We combine
yield acceleration with Wikipedia Federal Reserve pageview trends — rising Fed
attention confirms the macro narrative.

Inversely, when yield is accelerating UPWARD + Fed attention rising, risk-on
sectors benefit. Buy SOXX in that case.

Signals:
1. WHY: 10Y yield 5-day change is more negative than its 10-day change (acceleration)
2. WHEN: Wikipedia "Federal_Reserve" attention above 14-day average
3. ASSET: GDX when yield falling, SOXX when yield rising
4. WHEN NOT: VIX > 35

Eccentricity: Using yield curve second-derivative combined with Wikipedia Fed
attention. Quants use yield direction but not acceleration + attention combo.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Yield Accel Gold Miners",
    "hypothesis": "Accelerating 10Y yield decline + rising Fed Wikipedia attention = flight to safety favoring gold miners (GDX); rising yield = risk-on for SOXX.",
    "universe": ["GDX", "SOXX", "GLD"],
    "entry": "Buy GDX on yield acceleration down + Fed wiki up; SOXX on yield acceleration up + Fed wiki up",
    "exit": "Sell after 5 trading days or +4% gain or -3% stop loss; switch on signal reversal",
    "position_size": "50% of capital per trade",
    "eccentricity": "Yield curve second-derivative + Wikipedia Fed attention. Too meta for institutional models.",
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

    # 10Y yield
    yield_10y = data_fetcher.get_fred_series("DGS10", start=start_date, end=end_date)

    # Wikipedia Federal Reserve attention
    wiki_fed = data_fetcher.get_wikipedia_pageviews("Federal_Reserve", start=start_date, end=end_date)

    # VIX
    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    if gdx_close.empty or yield_10y.empty or wiki_fed.empty:
        return

    # Yield changes
    yield_chg5 = yield_10y.diff(5)  # 5-day change
    yield_chg10 = yield_10y.diff(10)  # 10-day change

    # Wiki Fed rolling average
    wiki_fed_ma14 = wiki_fed.rolling(14).mean()

    trading_days = gdx_close.index.strftime("%Y-%m-%d").tolist()
    in_trade = False
    trade_ticker = None
    entry_date = None
    entry_price = None

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

        # Get current prices
        gdx_price = gdx_close.iloc[i]

        # Exit
        if in_trade:
            days_held = (date_ts - pd.Timestamp(entry_date)).days
            if trade_ticker == "GDX":
                current_price = gdx_price
            elif trade_ticker == "SOXX":
                mask = soxx_close.index <= date_ts
                current_price = soxx_close[mask].iloc[-1] if mask.any() else entry_price
            else:
                mask = gld_close.index <= date_ts
                current_price = gld_close[mask].iloc[-1] if mask.any() else entry_price

            pct_change = (current_price - entry_price) / entry_price * 100
            if days_held >= 5 or pct_change >= 4.0 or pct_change <= -3.0:
                portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                in_trade = False
                trade_ticker = None
                entry_date = None
                entry_price = None
                continue

        # Entry
        if not in_trade and i >= 15:
            # Get yield acceleration
            chg5_mask = yield_chg5.dropna().index <= date_ts
            chg10_mask = yield_chg10.dropna().index <= date_ts
            if not chg5_mask.any() or not chg10_mask.any():
                continue

            current_chg5 = yield_chg5.dropna()[chg5_mask].iloc[-1]
            current_chg10 = yield_chg10.dropna()[chg10_mask].iloc[-1]

            # Determine direction: is yield change accelerating?
            # Acceleration down: 5d change < 10d change (falling faster recently)
            # Acceleration up: 5d change > 10d change (rising faster recently)
            yield_accel = current_chg5 - (current_chg10 / 2)  # normalized acceleration

            # Need clear acceleration (not noise)
            if abs(yield_accel) < 0.02:  # 2 basis points minimum
                continue

            # Wikipedia Fed attention above 14-day average
            wiki_mask = wiki_fed.index <= date_ts
            ma_mask = wiki_fed_ma14.dropna().index <= date_ts
            if not wiki_mask.any() or not ma_mask.any():
                continue
            current_wiki = wiki_fed[wiki_mask].iloc[-1]
            current_wiki_ma = wiki_fed_ma14.dropna()[ma_mask].iloc[-1]
            if current_wiki_ma <= 0 or current_wiki < current_wiki_ma:
                continue

            # VIX filter
            vix_mask = vix.index <= date_ts
            if vix_mask.any() and vix[vix_mask].iloc[-1] > 35:
                continue

            # Choose asset based on yield acceleration direction
            if yield_accel < -0.02:
                # Yield falling fast -> buy gold/miners
                # Pick GDX if GDX momentum > GLD momentum, else GLD
                ticker = "GDX"
                trade_price = gdx_price
                if i >= 5:
                    gdx_mom = (gdx_price - gdx_close.iloc[i-5]) / gdx_close.iloc[i-5]
                    gld_mask = gld_close.index <= date_ts
                    if gld_mask.any():
                        gld_recent = gld_close[gld_mask]
                        if len(gld_recent) >= 5:
                            gld_mom = (gld_recent.iloc[-1] - gld_recent.iloc[-5]) / gld_recent.iloc[-5]
                            if gld_mom > gdx_mom:
                                ticker = "GLD"
                                trade_price = gld_recent.iloc[-1]
            else:
                # Yield rising fast -> buy risk-on (SOXX)
                ticker = "SOXX"
                soxx_mask = soxx_close.index <= date_ts
                if not soxx_mask.any():
                    continue
                trade_price = soxx_close[soxx_mask].iloc[-1]

            dollars = portfolio.cash * 0.5
            if dollars > 100:
                result = portfolio.buy(ticker, dollars=dollars, date=date_str)
                if result:
                    in_trade = True
                    trade_ticker = ticker
                    entry_date = date_str
                    entry_price = trade_price

    if in_trade and trade_ticker:
        portfolio.sell(trade_ticker, all_shares=True, date=trading_days[-1])
