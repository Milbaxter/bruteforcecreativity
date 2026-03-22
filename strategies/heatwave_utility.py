"""
Heatwave Utility Boost

Hypothesis: Extreme temperatures (hot or cold) in major US metros stress the power grid,
driving up electricity demand and benefiting utility stocks. XLU tends to see inflows
during weather extremes as utilities earn more from peak pricing. We combine temperature
extremes with VIX as a risk filter — if markets are also nervous, utilities get double
tailwinds (safe haven + demand).

Signals:
1. WHY: Temperature > 37°C in Houston/Phoenix OR temperature < -8°C in NYC/Chicago
2. WHEN: XLU is below its 10-day MA (dip entry, not chasing) + VIX > 16
3. WHEN NOT: XLU already up > 2% in last 3 days

Eccentricity: Weather data as utility stock demand signal. Obvious to anyone who
pays electricity bills but invisible to quant models focused on earnings/multiples.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Heatwave Utility Boost",
    "hypothesis": "Extreme temperatures drive electricity demand, benefiting utility stocks (XLU) with a short lag.",
    "universe": ["XLU", "SPY"],
    "entry": "Buy XLU when extreme temp in major metros AND XLU below 10d MA AND VIX > 16",
    "exit": "Sell after 5 trading days or +3% gain or -2.5% stop loss",
    "position_size": "60% of capital per trade",
    "eccentricity": "Physical weather data as utility stock signal — too prosaic for quantitative finance.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    xlu = data_fetcher.get_prices("XLU", start=start_date, end=end_date)
    if isinstance(xlu.columns, pd.MultiIndex):
        xlu.columns = xlu.columns.get_level_values(0)
    xlu_close = xlu["Close"].dropna()

    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)

    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    # Weather data for 4 cities
    # Houston: 29.76, -95.37 | Phoenix: 33.45, -112.07
    # NYC: 40.71, -74.01 | Chicago: 41.88, -87.63
    houston = data_fetcher.get_weather_history(29.76, -95.37, start=start_date, end=end_date)
    phoenix = data_fetcher.get_weather_history(33.45, -112.07, start=start_date, end=end_date)
    nyc = data_fetcher.get_weather_history(40.71, -74.01, start=start_date, end=end_date)
    chicago = data_fetcher.get_weather_history(41.88, -87.63, start=start_date, end=end_date)

    if xlu_close.empty or vix.empty:
        return

    xlu_ma10 = xlu_close.rolling(10).mean()

    trading_days = xlu_close.index.strftime("%Y-%m-%d").tolist()
    in_trade = False
    entry_date = None
    entry_price = None

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)
        price = xlu_close.iloc[i]

        # Exit
        if in_trade:
            days_held = (date_ts - pd.Timestamp(entry_date)).days
            pct_change = (price - entry_price) / entry_price * 100
            if days_held >= 5 or pct_change >= 3.0 or pct_change <= -2.5:
                portfolio.sell("XLU", all_shares=True, date=date_str)
                in_trade = False
                entry_date = None
                entry_price = None
                continue

        # Entry
        if not in_trade and i >= 12:
            # Check temperature extremes in last 2 days
            extreme_detected = False
            for offset in range(0, 3):
                check_date = date_ts - pd.Timedelta(days=offset)

                # Hot extremes: Houston > 37°C or Phoenix > 40°C
                for wx, threshold in [(houston, 37.0), (phoenix, 40.0)]:
                    if not wx.empty and "temperature_2m_max" in wx.columns:
                        mask = wx.index <= check_date
                        if mask.any():
                            temp = wx.loc[mask, "temperature_2m_max"].iloc[-1]
                            if not pd.isna(temp) and temp > threshold:
                                extreme_detected = True
                                break

                # Cold extremes: NYC < -8°C or Chicago < -12°C
                if not extreme_detected:
                    for wx, threshold in [(nyc, -8.0), (chicago, -12.0)]:
                        if not wx.empty and "temperature_2m_min" in wx.columns:
                            mask = wx.index <= check_date
                            if mask.any():
                                temp = wx.loc[mask, "temperature_2m_min"].iloc[-1]
                                if not pd.isna(temp) and temp < threshold:
                                    extreme_detected = True
                                    break

                if extreme_detected:
                    break

            if not extreme_detected:
                continue

            # XLU below 10-day MA
            ma_mask = xlu_ma10.dropna().index <= date_ts
            if not ma_mask.any():
                continue
            if price >= xlu_ma10.dropna()[ma_mask].iloc[-1]:
                continue

            # VIX > 16
            vix_mask = vix.index <= date_ts
            if not vix_mask.any():
                continue
            if vix[vix_mask].iloc[-1] < 16:
                continue

            # Not already rallied
            if i >= 3:
                three_ago = xlu_close.iloc[i-3]
                if (price - three_ago) / three_ago * 100 > 2.0:
                    continue

            dollars = portfolio.cash * 0.6
            if dollars > 100:
                result = portfolio.buy("XLU", dollars=dollars, date=date_str)
                if result:
                    in_trade = True
                    entry_date = date_str
                    entry_price = price

    if in_trade:
        portfolio.sell("XLU", all_shares=True, date=trading_days[-1])
