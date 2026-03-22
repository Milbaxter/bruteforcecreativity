"""
Google Trends Layoffs Defensive

Hypothesis: Spikes in Google searches for "layoffs" are a leading indicator of
economic fear. When people search "layoffs" at elevated rates, it precedes risk-off
moves. Buying defensive assets (XLP staples, GLD gold) during these spikes captures
the flight-to-safety premium before it fully materializes.

Signals:
1. WHY: Google Trends "layoffs" interest is elevated (above its rolling median)
2. WHEN: SPY is below its 10-day MA (confirming weakness) + VIX > 18
3. WHEN NOT: VIX > 35 (panic already fully priced)

Eccentricity: Using Google search behavior as a labor market sentiment proxy.
No fund would tell LPs "we bought gold because people Googled layoffs."
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Google Layoffs Defensive",
    "hypothesis": "Google Trends for 'layoffs' spikes precede risk-off moves, making defensive assets (XLP, GLD) profitable entries.",
    "universe": ["XLP", "GLD", "SPY"],
    "entry": "Buy XLP or GLD when Google 'layoffs' trending up + SPY below 10d MA + VIX 18-35",
    "exit": "Sell after 5 trading days or +3% gain or -3% stop loss",
    "position_size": "50% of capital per trade",
    "eccentricity": "Google search behavior as economic fear proxy. Too reputationally embarrassing for institutional use.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch price data
    xlp = data_fetcher.get_prices("XLP", start=start_date, end=end_date)
    if isinstance(xlp.columns, pd.MultiIndex):
        xlp.columns = xlp.columns.get_level_values(0)
    xlp_close = xlp["Close"].dropna()

    gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)
    if isinstance(gld.columns, pd.MultiIndex):
        gld.columns = gld.columns.get_level_values(0)
    gld_close = gld["Close"].dropna()

    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
    spy_close = spy["Close"].dropna()

    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    # Google Trends for "layoffs" - weekly resolution
    try:
        trends = data_fetcher.get_google_trends(["layoffs"], timeframe=f"{start_date} {end_date}", geo="US")
    except Exception:
        trends = pd.DataFrame()

    if spy_close.empty or vix.empty or trends.empty:
        return

    layoffs_trend = trends["layoffs"] if "layoffs" in trends.columns else pd.Series(dtype=float)
    if layoffs_trend.empty:
        return

    # Compute rolling median of layoffs interest (8-week window)
    layoffs_median = layoffs_trend.rolling(8, min_periods=4).median()

    # SPY 10-day MA
    spy_ma10 = spy_close.rolling(10).mean()

    # GLD and XLP 5-day returns for selection
    gld_ret5 = gld_close.pct_change(5)
    xlp_ret5 = xlp_close.pct_change(5)

    trading_days = spy_close.index.strftime("%Y-%m-%d").tolist()
    in_trade = False
    trade_ticker = None
    entry_date = None
    entry_price = None

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)
        spy_price = spy_close.iloc[i]

        # Exit conditions
        if in_trade:
            days_held = (date_ts - pd.Timestamp(entry_date)).days
            if trade_ticker == "XLP":
                current_close = xlp_close
            else:
                current_close = gld_close
            mask = current_close.index <= date_ts
            if mask.any():
                current_price = current_close[mask].iloc[-1]
                pct_change = (current_price - entry_price) / entry_price * 100

                if days_held >= 5 or pct_change >= 3.0 or pct_change <= -3.0:
                    portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                    in_trade = False
                    trade_ticker = None
                    entry_date = None
                    entry_price = None
                    continue

        # Entry conditions
        if not in_trade and i >= 15:
            # Get most recent Google Trends value (weekly, so look back up to 7 days)
            trend_mask = layoffs_trend.index <= date_ts
            if not trend_mask.any():
                continue
            current_trend = layoffs_trend[trend_mask].iloc[-1]

            median_mask = layoffs_median.dropna().index <= date_ts
            if not median_mask.any():
                continue
            current_median = layoffs_median.dropna()[median_mask].iloc[-1]

            # Signal 1: Layoffs searches above rolling median
            if current_trend <= current_median:
                continue

            # Signal 2: SPY below 10-day MA
            ma10_mask = spy_ma10.dropna().index <= date_ts
            if not ma10_mask.any():
                continue
            if spy_price >= spy_ma10.dropna()[ma10_mask].iloc[-1]:
                continue

            # Signal 3: VIX between 18 and 35
            vix_mask = vix.index <= date_ts
            if not vix_mask.any():
                continue
            current_vix = vix[vix_mask].iloc[-1]
            if current_vix < 18 or current_vix > 35:
                continue

            # Choose between XLP and GLD: pick the one with better 5-day momentum
            gld_mask = gld_ret5.dropna().index <= date_ts
            xlp_mask = xlp_ret5.dropna().index <= date_ts

            pick_gld = True  # default
            if gld_mask.any() and xlp_mask.any():
                gld_mom = gld_ret5.dropna()[gld_mask].iloc[-1]
                xlp_mom = xlp_ret5.dropna()[xlp_mask].iloc[-1]
                pick_gld = gld_mom > xlp_mom

            ticker = "GLD" if pick_gld else "XLP"
            close_series = gld_close if pick_gld else xlp_close
            price_mask = close_series.index <= date_ts
            if not price_mask.any():
                continue
            price = close_series[price_mask].iloc[-1]

            dollars = portfolio.cash * 0.5
            if dollars > 100:
                result = portfolio.buy(ticker, dollars=dollars, date=date_str)
                if result:
                    in_trade = True
                    trade_ticker = ticker
                    entry_date = date_str
                    entry_price = price

    # Close remaining position
    if in_trade and trade_ticker:
        portfolio.sell(trade_ticker, all_shares=True, date=trading_days[-1])
