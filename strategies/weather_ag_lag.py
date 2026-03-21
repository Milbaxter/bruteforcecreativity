"""
Weather-Agriculture Lag
Extreme Midwest weather (heat/cold) predicts agriculture commodity moves.
Weather data leads WEAT/CORN prices by 1-3 days.
Combines: extreme temp + ag ETF hasn't moved yet + trend confirmation.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Weather Ag Lag",
    "hypothesis": "Extreme temperatures in the US Midwest corn/wheat belt (Iowa, Illinois) "
                  "affect crop yields. When Open-Meteo shows extreme heat (>95°F / 35°C) or "
                  "extreme cold (<10°F / -12°C) for 3+ days AND agriculture ETFs haven't reacted "
                  "yet (< 1% move in past 3 days), there's a 1-3 day lag before supply concern "
                  "pricing. Buy WEAT or CORN ahead of the move. Weather data is free and real-time "
                  "but ag commodity traders are slow to react to gradual temperature extremes.",
    "universe": ["WEAT", "CORN", "DBA"],
    "entry": "Buy when: (1) 3-day avg max temp in Iowa >35°C or 3-day avg min temp <-12°C, "
             "(2) WEAT hasn't moved >1% in past 3 days, (3) 20-day MA trending up or flat",
    "exit": "Sell after 5 trading days, or +3% take profit, or -2.5% stop loss",
    "position_size": "40% of capital per trade, max 2 positions",
    "eccentricity": "Cross-domain weather-to-commodity signal. No fund has a system that feeds "
                    "Open-Meteo temperature data into WEAT/CORN entry signals. Weather is public "
                    "but nobody automates the agriculture connection at this speed.",
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

    if not price_data:
        return

    # Fetch weather for key Midwest agricultural locations
    # Des Moines, Iowa (corn belt center)
    iowa_weather = data_fetcher.get_weather_history(lat=41.6, lon=-93.6)
    # Champaign, Illinois (corn/soybean belt)
    illinois_weather = data_fetcher.get_weather_history(lat=40.1, lon=-88.2)
    # Wichita, Kansas (wheat belt)
    kansas_weather = data_fetcher.get_weather_history(lat=37.7, lon=-97.3)

    if iowa_weather is None or iowa_weather.empty:
        return

    # Get trading days from first available ticker
    ref_ticker = next(iter(price_data))
    trading_days = price_data[ref_ticker].index.tolist()

    # Combine weather data — average across locations
    weather_sources = [w for w in [iowa_weather, illinois_weather, kansas_weather]
                       if w is not None and not w.empty]
    if not weather_sources:
        return

    # Track positions
    open_positions = {}  # ticker -> {entry_date, entry_price}
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

            # Exit: 5-day hold, +3% TP, -2.5% SL
            if days_held >= 5 or pct_change >= 0.03 or pct_change <= -0.025:
                portfolio.sell(ticker, all_shares=True, date=date_str)
                tickers_to_close.append(ticker)

        for t in tickers_to_close:
            del open_positions[t]

        if len(open_positions) >= MAX_POSITIONS:
            continue

        # Check weather extremes over the past 3 days
        extreme_heat = False
        extreme_cold = False

        for weather in weather_sources:
            w_before = weather.loc[:date_str].tail(3)
            if len(w_before) < 3:
                continue

            if "temperature_2m_max" in weather.columns:
                avg_max_temp = w_before["temperature_2m_max"].mean()
                if avg_max_temp > 35:  # >95°F — extreme heat
                    extreme_heat = True

            if "temperature_2m_min" in weather.columns:
                avg_min_temp = w_before["temperature_2m_min"].mean()
                if avg_min_temp < -12:  # <10°F — extreme cold
                    extreme_cold = True

        if not extreme_heat and not extreme_cold:
            continue

        # Check each ag ETF for entry signals
        for ticker in tickers:
            if ticker in open_positions:
                continue
            if ticker not in price_data:
                continue

            closes = price_data[ticker]["Close"].loc[:date]
            if len(closes) < 25:
                continue

            # Condition 2: ETF hasn't moved much in past 3 days (market hasn't priced it in)
            price_now = float(closes.iloc[-1])
            price_3d_ago = float(closes.iloc[-4]) if len(closes) > 4 else float(closes.iloc[0])
            recent_move = abs((price_now - price_3d_ago) / price_3d_ago)

            if recent_move > 0.01:
                continue  # Already moved — we're late

            # Condition 3: 20-day MA flat or trending up (not in a downtrend)
            ma_20 = closes.rolling(20).mean()
            if len(ma_20.dropna()) < 5:
                continue

            ma_now = float(ma_20.iloc[-1])
            ma_5d_ago = float(ma_20.iloc[-6]) if len(ma_20.dropna()) > 5 else ma_now
            ma_trend = (ma_now - ma_5d_ago) / ma_5d_ago if ma_5d_ago > 0 else 0

            if ma_trend < -0.01:
                continue  # Downtrending — skip

            # All conditions met — buy
            if len(open_positions) >= MAX_POSITIONS:
                break

            dollars = portfolio.cash * 0.40
            if dollars < 100:
                break

            result = portfolio.buy(ticker, dollars=dollars, date=date_str)
            if result:
                open_positions[ticker] = {
                    "entry_date": date,
                    "entry_price": result["exec_price"],
                }
