"""
Snowstorm Natural Gas Heating Play

Hypothesis: Heavy snowfall in the US Northeast (NYC + Chicago) drives short-term
natural gas demand spikes. UNG (natural gas ETF) tends to pop 1-3 days after major
snow events because heating demand is physical and lagged. Combining snow data with
UNG being below its 5-day MA catches the move before it's priced in.

Signals:
1. WHY: Heavy snowfall (>5cm) in NYC or Chicago from weather data
2. WHEN: UNG is below its 5-day MA (dip entry)
3. WHEN NOT: UNG already rallied >3% in last 2 days (already pricing in)

Eccentricity: Cross-domain weather-to-commodity signal. Too quirky and labor-intensive
for institutional quant teams who focus on supply/demand models, not actual weather events.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Snowstorm NatGas Heating",
    "hypothesis": "Heavy snowfall in Northeast US drives natural gas heating demand, creating short-term UNG price spikes with a 1-2 day lag.",
    "universe": ["UNG", "XLE"],
    "entry": "Buy UNG when snowfall > 5cm in NYC or Chicago AND UNG below 5-day MA",
    "exit": "Sell after 3 trading days or +4% gain or -3% stop loss",
    "position_size": "60% of capital per trade",
    "eccentricity": "Uses actual snowfall data from Open-Meteo as a commodity demand signal. No quant fund is checking weather.com before trading natural gas ETFs.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch price data
    ung = data_fetcher.get_prices("UNG", start=start_date, end=end_date)
    if isinstance(ung.columns, pd.MultiIndex):
        ung.columns = ung.columns.get_level_values(0)
    ung_close = ung["Close"].dropna()

    xle = data_fetcher.get_prices("XLE", start=start_date, end=end_date)
    if isinstance(xle.columns, pd.MultiIndex):
        xle.columns = xle.columns.get_level_values(0)
    xle_close = xle["Close"].dropna()

    # Fetch weather data for NYC and Chicago
    # NYC: 40.71, -74.01 | Chicago: 41.88, -87.63
    nyc_weather = data_fetcher.get_weather_history(40.71, -74.01, start=start_date, end=end_date)
    chi_weather = data_fetcher.get_weather_history(41.88, -87.63, start=start_date, end=end_date)

    if ung_close.empty or nyc_weather.empty or chi_weather.empty:
        return

    # Compute 5-day MA of UNG
    ung_ma5 = ung_close.rolling(5).mean()

    # Get snowfall columns
    nyc_snow = nyc_weather.get("snowfall_sum", pd.Series(dtype=float))
    chi_snow = chi_weather.get("snowfall_sum", pd.Series(dtype=float))

    trading_days = ung_close.index.strftime("%Y-%m-%d").tolist()
    in_trade = False
    trade_ticker = None
    entry_date = None
    entry_price = None

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)
        price = ung_close.iloc[i]

        # Check exit conditions
        if in_trade:
            days_held = (date_ts - pd.Timestamp(entry_date)).days
            current_price = ung_close.iloc[i] if trade_ticker == "UNG" else xle_close.get(date_ts, price)
            if isinstance(current_price, pd.Series):
                current_price = current_price.iloc[-1] if not current_price.empty else price
            pct_change = (price - entry_price) / entry_price * 100

            if days_held >= 3 or pct_change >= 4.0 or pct_change <= -3.0:
                portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                in_trade = False
                trade_ticker = None
                entry_date = None
                entry_price = None
                continue

        # Check entry conditions
        if not in_trade and i >= 7:
            # Check snowfall in last 2 days for NYC and Chicago
            snow_detected = False
            for offset in range(0, 2):
                check_date = date_ts - pd.Timedelta(days=offset)
                # NYC snow
                nyc_mask = nyc_snow.index <= check_date
                if nyc_mask.any():
                    nearest_nyc = nyc_snow[nyc_mask].iloc[-1]
                    if not pd.isna(nearest_nyc) and nearest_nyc > 5.0:
                        snow_detected = True
                        break
                # Chicago snow
                chi_mask = chi_snow.index <= check_date
                if chi_mask.any():
                    nearest_chi = chi_snow[chi_mask].iloc[-1]
                    if not pd.isna(nearest_chi) and nearest_chi > 5.0:
                        snow_detected = True
                        break

            if not snow_detected:
                continue

            # UNG below 5-day MA
            ma5_mask = ung_ma5.dropna().index <= date_ts
            if not ma5_mask.any():
                continue
            current_ma5 = ung_ma5.dropna()[ma5_mask].iloc[-1]
            if price >= current_ma5:
                continue

            # Not already rallied >3% in last 2 days
            if i >= 2:
                two_days_ago = ung_close.iloc[i-2]
                recent_rally = (price - two_days_ago) / two_days_ago * 100
                if recent_rally > 3.0:
                    continue

            # Buy UNG (primary) or XLE (backup if UNG not moving)
            dollars = portfolio.cash * 0.6
            if dollars > 100:
                result = portfolio.buy("UNG", dollars=dollars, date=date_str)
                if result:
                    in_trade = True
                    trade_ticker = "UNG"
                    entry_date = date_str
                    entry_price = price

    # Close any remaining position
    if in_trade and trade_ticker:
        portfolio.sell(trade_ticker, all_shares=True, date=trading_days[-1])
