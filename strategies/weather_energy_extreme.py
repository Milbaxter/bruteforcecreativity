"""
Weather Energy Extreme
Trade energy ETFs based on extreme temperature readings in major US cities.
Extreme cold/heat = energy demand spike = energy stock momentum.
"""

STRATEGY = {
    "name": "Weather Energy Extreme",
    "hypothesis": "Extreme temperatures (cold winters, hot summers) drive energy demand spikes "
                  "that take 1-3 days to fully price into energy stocks. By detecting extreme "
                  "weather in major US population centers, we front-run the demand signal.",
    "universe": ["UNG", "XLE", "XOP"],
    "entry": "Buy UNG on extreme cold (< 5th percentile temp) in Chicago/NYC composite, "
             "buy XLE/XOP on extreme heat (> 95th percentile) in Houston/Phoenix",
    "exit": "Sell after 5 days or at -4% stop loss",
    "position_size": "50% of cash per signal, max 2 concurrent positions",
    "eccentricity": "Cross-domain: weather data + energy ETFs. No quant fund trades 'it's cold "
                    "in Chicago, buy natural gas.' Too crude for models but the demand effect is real.",
}

# Major US cities: lat, lon, and which energy they affect
CITIES = {
    "Chicago": {"lat": 41.88, "lon": -87.63, "type": "cold", "tickers": ["UNG"]},
    "NYC": {"lat": 40.71, "lon": -74.01, "type": "cold", "tickers": ["UNG"]},
    "Houston": {"lat": 29.76, "lon": -95.37, "type": "heat", "tickers": ["XLE", "XOP"]},
    "Phoenix": {"lat": 33.45, "lon": -112.07, "type": "heat", "tickers": ["XLE"]},
}


def run(data_fetcher, portfolio, start_date, end_date):
    import pandas as pd
    import numpy as np

    # Fetch weather data for all cities
    weather_data = {}
    for city, info in CITIES.items():
        try:
            weather = data_fetcher.get_weather_history(info["lat"], info["lon"])
            if weather is not None and not (hasattr(weather, 'empty') and weather.empty):
                weather.index = pd.to_datetime(weather.index)
                weather_data[city] = weather
        except Exception:
            continue

    if not weather_data:
        return

    # Fetch prices
    tickers = ["UNG", "XLE", "XOP"]
    prices = {}
    for ticker in tickers:
        try:
            df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if not df.empty:
                prices[ticker] = df
        except Exception:
            continue

    if not prices:
        return

    # Parameters
    LOOKBACK = 90  # days for percentile computation
    COLD_PCTILE = 5  # below this = extreme cold
    HEAT_PCTILE = 95  # above this = extreme heat
    MAX_HOLD_DAYS = 5
    STOP_LOSS = -0.04
    MAX_POSITIONS = 2
    CASH_PER_SIGNAL = 0.50

    # Get trading days
    all_dates = set()
    for df in prices.values():
        all_dates.update(df.index.strftime("%Y-%m-%d"))
    trading_days = sorted(d for d in all_dates if start_date <= d <= end_date)

    # Track positions
    open_positions = {}  # ticker -> {"entry_date", "entry_price"}

    for date_str in trading_days:
        date_ts = pd.Timestamp(date_str)

        # Check exits
        for ticker in list(open_positions.keys()):
            if ticker not in prices:
                continue
            pos = open_positions[ticker]
            entry_price = pos["entry_price"]
            entry_date = pd.Timestamp(pos["entry_date"])
            days_held = (date_ts - entry_date).days

            current_data = prices[ticker]["Close"].loc[:date_ts]
            if current_data.empty:
                continue
            current_price = float(current_data.iloc[-1])
            ret = (current_price - entry_price) / entry_price

            if days_held >= MAX_HOLD_DAYS or ret <= STOP_LOSS:
                portfolio.sell(ticker, all_shares=True, date=date_str)
                del open_positions[ticker]

        if len(open_positions) >= MAX_POSITIONS:
            continue

        # Check weather signals
        cold_signal = False
        heat_signal = False

        for city, info in CITIES.items():
            if city not in weather_data:
                continue
            w = weather_data[city]

            # Get temp column
            temp_col = None
            for col in ["temp_max", "temperature_2m_max", "temp_min", "temperature_2m_min"]:
                if col in w.columns:
                    temp_col = col
                    break
            if temp_col is None:
                continue

            w_up_to = w.loc[:date_ts]
            if len(w_up_to) < LOOKBACK + 1:
                continue

            # Compute rolling percentile
            recent_temps = w_up_to[temp_col].iloc[-LOOKBACK - 1:-1]
            current_temp = float(w_up_to[temp_col].iloc[-1])

            if info["type"] == "cold":
                threshold = float(np.percentile(recent_temps.dropna(), COLD_PCTILE))
                if current_temp <= threshold:
                    cold_signal = True
            elif info["type"] == "heat":
                threshold = float(np.percentile(recent_temps.dropna(), HEAT_PCTILE))
                if current_temp >= threshold:
                    heat_signal = True

        # Execute trades based on signals
        if cold_signal and "UNG" not in open_positions and "UNG" in prices:
            cash = portfolio.cash * CASH_PER_SIGNAL
            if cash >= 100:
                result = portfolio.buy("UNG", dollars=cash, date=date_str)
                if result:
                    cp = float(prices["UNG"]["Close"].loc[:date_ts].iloc[-1])
                    open_positions["UNG"] = {"entry_date": date_str, "entry_price": cp}

        if heat_signal:
            for ticker in ["XLE", "XOP"]:
                if len(open_positions) >= MAX_POSITIONS:
                    break
                if ticker in open_positions or ticker not in prices:
                    continue
                cash = portfolio.cash * CASH_PER_SIGNAL
                if cash >= 100:
                    result = portfolio.buy(ticker, dollars=cash, date=date_str)
                    if result:
                        cp = float(prices[ticker]["Close"].loc[:date_ts].iloc[-1])
                        open_positions[ticker] = {"entry_date": date_str, "entry_price": cp}

    # Close remaining positions
    if trading_days:
        last_day = trading_days[-1]
        for ticker in list(open_positions.keys()):
            portfolio.sell(ticker, all_shares=True, date=last_day)
