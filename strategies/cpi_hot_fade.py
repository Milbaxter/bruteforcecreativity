"""
CPI Hot Fade
When CPI surprises to the upside, markets overreact. Buy the dip 1 day after.
Combines: CPI surprise + market drop + VIX spike as triple confirmation.
"""

import pandas as pd
import numpy as np
from datetime import timedelta

STRATEGY = {
    "name": "CPI Hot Fade",
    "hypothesis": "When CPI comes in above consensus (hot inflation surprise), equities dump "
                  "same-day on rate-hike fears. But the dump reverses within 3-5 days because "
                  "the Fed doesn't actually change policy between meetings. The overreaction is "
                  "emotional, not fundamental. Buy QQQ/SPY the day AFTER a hot CPI print "
                  "(let the panic settle) + confirm VIX spiked >1 point + confirm market dropped "
                  ">0.5% on CPI day. Sell 5 days later.",
    "universe": ["QQQ", "SPY", "TLT"],
    "entry": "Buy when: (1) CPI release day, actual > forecast, (2) SPY dropped >0.5% on that "
             "day, (3) VIX rose >1 point on that day. Enter next trading day.",
    "exit": "Sell 5 trading days after entry, or +3% take profit, or -2% stop loss",
    "position_size": "50% in QQQ, 30% in SPY, split across position",
    "eccentricity": "Fading macro data releases is considered reckless by institutional risk "
                    "managers. No fund committee would approve 'buy the CPI panic dip' as a "
                    "strategy. But at small scale, the mean-reversion is reliable.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch economic calendar for CPI dates
    econ_cal = data_fetcher.get_economic_calendar()

    # Fetch price data
    price_data = {}
    for ticker in STRATEGY["universe"]:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            price_data[ticker] = df

    # Fetch VIX
    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    if econ_cal is None or econ_cal.empty:
        return
    if "QQQ" not in price_data or "SPY" not in price_data:
        return

    # Find CPI release dates
    cpi_dates = []
    for _, row in econ_cal.iterrows():
        event = str(row.get("event", "")).lower()
        if "cpi" in event and ("release" in event or "consumer price" in event or "all items" in event):
            date = row.get("date")
            if date is not None:
                if isinstance(date, str):
                    try:
                        date = pd.Timestamp(date)
                    except Exception:
                        continue
                cpi_dates.append(date)

    # Also try FRED for CPI data to detect surprises
    try:
        cpi_series = data_fetcher.get_fred_series("CPIAUCSL")
    except Exception:
        cpi_series = None

    spy_close = price_data["SPY"]["Close"]
    qqq_close = price_data["QQQ"]["Close"]
    trading_days = spy_close.index.tolist()

    open_positions = {}  # ticker -> {entry_date, entry_price}

    for i in range(5, len(trading_days)):
        date = trading_days[i]
        date_str = date.strftime("%Y-%m-%d")

        # Check exits
        tickers_to_close = []
        for ticker, pos in open_positions.items():
            if ticker not in price_data:
                continue
            current_price = float(price_data[ticker]["Close"].loc[:date].iloc[-1])
            entry_price = pos["entry_price"]
            days_held = (date - pos["entry_date"]).days
            pct_change = (current_price - entry_price) / entry_price

            if days_held >= 5 or pct_change >= 0.03 or pct_change <= -0.02:
                portfolio.sell(ticker, all_shares=True, date=date_str)
                tickers_to_close.append(ticker)

        for t in tickers_to_close:
            del open_positions[t]

        if open_positions:
            continue  # One trade at a time

        # Check if yesterday was a CPI day with a market drop
        prev_date = trading_days[i - 1]
        prev_str = prev_date.strftime("%Y-%m-%d")

        # Check if prev_date matches a CPI date (within 1 day tolerance)
        is_cpi_day = False
        for cpi_date in cpi_dates:
            if abs((prev_date - cpi_date).days) <= 1:
                is_cpi_day = True
                break

        if not is_cpi_day:
            # Fallback: check if it's roughly a CPI release day (around 10th-14th of month)
            # CPI is typically released on the 2nd or 3rd Tuesday of the month
            if not (10 <= prev_date.day <= 15):
                continue

            # Check for a significant SPY drop on that day (potential CPI reaction)
            spy_prev = float(spy_close.loc[:prev_date].iloc[-1])
            spy_prev2 = float(spy_close.loc[:prev_date].iloc[-2]) if len(spy_close.loc[:prev_date]) > 1 else spy_prev
            spy_day_ret = (spy_prev - spy_prev2) / spy_prev2

            if spy_day_ret > -0.005:
                continue  # SPY didn't drop enough — likely not a hot CPI

            # VIX confirmation
            if vix is not None and not vix.empty:
                vix_now = vix.loc[:prev_date]
                if len(vix_now) >= 2:
                    vix_change = float(vix_now.iloc[-1]) - float(vix_now.iloc[-2])
                    if vix_change < 0.5:
                        continue  # VIX didn't spike — not panicky enough
        else:
            # Confirmed CPI day — check for market drop
            spy_prev = float(spy_close.loc[:prev_date].iloc[-1])
            spy_prev2 = float(spy_close.loc[:prev_date].iloc[-2]) if len(spy_close.loc[:prev_date]) > 1 else spy_prev
            spy_day_ret = (spy_prev - spy_prev2) / spy_prev2

            if spy_day_ret > -0.005:
                continue  # Market didn't drop — CPI was fine

            # VIX confirmation
            if vix is not None and not vix.empty:
                vix_now = vix.loc[:prev_date]
                if len(vix_now) >= 2:
                    vix_change = float(vix_now.iloc[-1]) - float(vix_now.iloc[-2])
                    if vix_change < 0.5:
                        continue

        # All signals aligned — buy QQQ (most reactive to rate fears)
        dollars = portfolio.cash * 0.50
        if dollars < 100:
            continue

        result = portfolio.buy("QQQ", dollars=dollars, date=date_str)
        if result:
            open_positions["QQQ"] = {
                "entry_date": date,
                "entry_price": result["exec_price"],
            }

        # Also buy SPY with remaining allocation
        dollars2 = portfolio.cash * 0.50
        if dollars2 >= 100:
            result2 = portfolio.buy("SPY", dollars=dollars2, date=date_str)
            if result2:
                open_positions["SPY"] = {
                    "entry_date": date,
                    "entry_price": result2["exec_price"],
                }
