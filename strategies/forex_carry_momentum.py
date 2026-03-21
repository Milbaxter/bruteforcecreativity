"""
Forex Carry Momentum
Exploit currency trends with momentum on forex ETFs.
Combines: FXA/FXE/FXY momentum + USD strength signal + yield curve filter.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Forex Carry Momentum",
    "hypothesis": "Currency ETFs (FXA=AUD, FXE=EUR, FXY=JPY, UUP=USD bull) trend strongly "
                  "when central bank policy diverges. When USD is weakening (UUP declining), "
                  "foreign currency ETFs rally — rotate into the strongest momentum foreign "
                  "currency ETF. When USD is strengthening, hold UUP. The key insight: currency "
                  "trends persist because central bank policy cycles are slow and predictable, "
                  "creating momentum that lasts weeks. 7-day momentum + USD trend filter.",
    "universe": ["FXA", "FXE", "FXY", "UUP", "FXB"],
    "entry": "If UUP 10-day return < -0.5% (USD weakening), buy strongest momentum foreign FX ETF. "
             "If UUP 10-day return > 0.5% (USD strengthening), buy UUP.",
    "exit": "Rotate every 3 trading days to current leader, -3% stop loss",
    "position_size": "85% of capital in selected ETF",
    "eccentricity": "Forex ETFs are unloved by retail (boring) and too small for institutional FX "
                    "desks who trade actual FX. Momentum rotation across these niche ETFs exploits "
                    "the gap between retail apathy and institutional irrelevance.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    fx_tickers = ["FXA", "FXE", "FXY", "FXB"]  # Foreign currency ETFs
    usd_ticker = "UUP"  # USD bull ETF
    all_tickers = fx_tickers + [usd_ticker]

    # Fetch price data
    price_data = {}
    for ticker in all_tickers:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            price_data[ticker] = df["Close"]

    if len(price_data) < 3:
        return

    # Align all tickers to common dates
    common_idx = None
    for t in price_data:
        if common_idx is None:
            common_idx = price_data[t].index
        else:
            common_idx = common_idx.intersection(price_data[t].index)

    if common_idx is None or len(common_idx) < 20:
        return

    closes = {t: price_data[t].loc[common_idx] for t in price_data}
    moms = {t: closes[t].pct_change(7) for t in closes}

    trading_days = common_idx.tolist()

    current_holding = None
    entry_price = None
    last_rotation = -999

    for i in range(15, len(trading_days)):
        date = trading_days[i]
        date_str = date.strftime("%Y-%m-%d")

        # Stop loss check
        if current_holding is not None and entry_price is not None:
            current = float(closes[current_holding].loc[date])
            pct = (current - entry_price) / entry_price
            if pct <= -0.03:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
                current_holding = None
                entry_price = None
                last_rotation = i
                continue

        # Rotate every 3 days
        if i - last_rotation < 3:
            continue

        # USD trend: 10-day return of UUP
        if usd_ticker in closes:
            uup = closes[usd_ticker]
            uup_now = float(uup.iloc[min(i, len(uup)-1)])
            uup_10d = float(uup.iloc[max(0, min(i-10, len(uup)-1))])
            usd_trend = (uup_now - uup_10d) / uup_10d if uup_10d > 0 else 0
        else:
            usd_trend = 0

        if usd_trend > 0.005:
            # USD strengthening — hold UUP
            target = usd_ticker if usd_ticker in closes else None
        else:
            # USD weakening — pick strongest foreign FX momentum
            fx_moms = {}
            for t in fx_tickers:
                if t in moms:
                    m = float(moms[t].iloc[min(i, len(moms[t])-1)])
                    if not np.isnan(m):
                        fx_moms[t] = m

            if fx_moms:
                target = max(fx_moms, key=fx_moms.get)
            else:
                target = None

        if target is None:
            continue

        if target != current_holding:
            if current_holding is not None:
                portfolio.sell(current_holding, all_shares=True, date=date_str)

            dollars = portfolio.cash * 0.85
            result = portfolio.buy(target, dollars=dollars, date=date_str)
            if result:
                current_holding = target
                entry_price = result["exec_price"]

        last_rotation = i
