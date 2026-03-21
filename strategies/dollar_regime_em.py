"""
Dollar Regime Emerging Markets
Buy emerging market ETFs when the US dollar is weakening + EM momentum is positive + VIX is low.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Dollar Regime Emerging Markets",
    "hypothesis": "When the US dollar weakens, capital flows to emerging markets. Combining dollar trend (UUP below 20-day MA) with EM momentum and low volatility catches these flows before institutions rotate.",
    "universe": ["EEM", "VWO", "UUP", "SPY"],
    "entry": "UUP below 20-day MA (dollar weakening) + EEM 5-day return > 0.5% + VIX < 25",
    "exit": "Sell after 5 trading days or at -2% stop loss",
    "position_size": "50% of capital per trade, split between EEM and VWO",
    "eccentricity": "Cross-domain signal combining FX regime with EM equities and volatility filter — too many moving parts for single-asset quant models",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch data
    prices_eem = data_fetcher.get_prices("EEM", start=start_date, end=end_date)
    prices_vwo = data_fetcher.get_prices("VWO", start=start_date, end=end_date)
    prices_uup = data_fetcher.get_prices("UUP", start=start_date, end=end_date)
    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    # Flatten multi-index if needed
    for df in [prices_eem, prices_vwo, prices_uup]:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

    if prices_eem.empty or prices_uup.empty:
        return

    eem_close = prices_eem["Close"]
    vwo_close = prices_vwo["Close"] if not prices_vwo.empty else None
    uup_close = prices_uup["Close"]

    # Compute signals
    uup_ma20 = uup_close.rolling(20).mean()
    eem_ret5 = eem_close.pct_change(5)

    # Align VIX to trading days
    vix_aligned = vix.reindex(eem_close.index, method="ffill")

    trading_days = eem_close.index.tolist()

    i = 25  # start after enough data for indicators
    while i < len(trading_days):
        date = trading_days[i]
        date_str = date.strftime("%Y-%m-%d")

        # Check if we have open positions - manage exits first
        if portfolio.positions:
            # Check stop loss and time-based exit
            for ticker in list(portfolio.positions.keys()):
                if ticker in ["EEM", "VWO"]:
                    # Find entry date from events
                    entry_price = None
                    entry_idx = None
                    for evt in reversed(portfolio._all_events):
                        if evt["ticker"] == ticker and evt["action"] == "BUY":
                            entry_price = evt["exec_price"]
                            entry_idx = trading_days.index(pd.Timestamp(evt["date"])) if pd.Timestamp(evt["date"]) in trading_days else None
                            break

                    if entry_price is not None:
                        current_price = float(eem_close.loc[date]) if ticker == "EEM" else (float(vwo_close.loc[date]) if vwo_close is not None and date in vwo_close.index else None)
                        if current_price is None:
                            continue

                        pct_change = (current_price - entry_price) / entry_price
                        days_held = i - entry_idx if entry_idx is not None else 999

                        # Exit: -2% stop loss or 5 trading days
                        if pct_change <= -0.02 or days_held >= 5:
                            portfolio.sell(ticker, all_shares=True, date=date_str)

            i += 1
            continue

        # Entry signals
        if date not in uup_close.index or date not in uup_ma20.index:
            i += 1
            continue

        uup_val = float(uup_close.loc[date])
        uup_ma = float(uup_ma20.loc[date]) if not pd.isna(uup_ma20.loc[date]) else None
        eem_momentum = float(eem_ret5.loc[date]) if date in eem_ret5.index and not pd.isna(eem_ret5.loc[date]) else None
        vix_val = float(vix_aligned.loc[date]) if date in vix_aligned.index and not pd.isna(vix_aligned.loc[date]) else 999

        if uup_ma is None or eem_momentum is None:
            i += 1
            continue

        # Entry: dollar weakening + EM momentum + low VIX
        if uup_val < uup_ma and eem_momentum > 0.005 and vix_val < 25:
            # Split capital between EEM and VWO
            half_cash = portfolio.cash * 0.45
            portfolio.buy("EEM", dollars=half_cash, date=date_str)
            if vwo_close is not None:
                portfolio.buy("VWO", dollars=half_cash, date=date_str)

        i += 1
