"""
Emerging Markets Crypto Risk
Use crypto fear/greed index as a leading risk-on/risk-off indicator
for emerging market ETF rotation.
Combines: crypto sentiment + EM momentum + volatility filter.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "EM Crypto Risk",
    "hypothesis": "Crypto fear/greed index leads broader risk appetite by 1-3 days because crypto "
                  "trades 24/7 and reacts faster than equity markets. When crypto sentiment turns "
                  "greedy (>60), risk-on assets like EM equities rally. When it turns fearful (<40), "
                  "rotate to safety. Among EMs, use 5-day momentum to pick the strongest country ETF. "
                  "EWZ (Brazil), INDA (India), EWT (Taiwan) — each driven by different macro factors "
                  "(commodities, tech, domestic growth) so there's always a momentum leader.",
    "universe": ["EWZ", "INDA", "EWT", "TLT"],
    "entry": "If crypto fear/greed > 55 (risk-on): buy strongest momentum EM ETF. "
             "If crypto fear/greed < 35 (risk-off): buy TLT. "
             "Neutral zone (35-55): hold current position.",
    "exit": "Rotate every 3 trading days based on regime and momentum leader, -4% stop loss",
    "position_size": "90% of capital in selected ETF",
    "eccentricity": "Using crypto sentiment to time emerging market equities is deeply eccentric. "
                    "No institutional EM fund uses Bitcoin fear/greed as a risk signal. But crypto "
                    "IS a leading indicator for global risk appetite in the post-2020 regime.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    em_tickers = ["EWZ", "INDA", "EWT"]
    safety_ticker = "TLT"
    all_tickers = em_tickers + [safety_ticker]

    # Fetch prices
    price_data = {}
    for ticker in all_tickers:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            price_data[ticker] = df["Close"]

    if len(price_data) < 3:
        return

    # Fetch crypto fear/greed index
    crypto_fg = data_fetcher.get_crypto_fear_greed(days=400)
    if crypto_fg is None or crypto_fg.empty:
        return

    # Align dates
    common_idx = None
    for t in price_data:
        if common_idx is None:
            common_idx = price_data[t].index
        else:
            common_idx = common_idx.intersection(price_data[t].index)

    if common_idx is None or len(common_idx) < 15:
        return

    closes = {t: price_data[t].loc[common_idx] for t in price_data}
    moms_5d = {t: closes[t].pct_change(5) for t in em_tickers if t in closes}

    trading_days = common_idx.tolist()

    current_holding = None
    entry_price = None
    last_rotation = -999

    for i in range(10, len(trading_days)):
        date = trading_days[i]
        date_str = date.strftime("%Y-%m-%d")

        # Stop loss
        if current_holding is not None and entry_price is not None:
            if current_holding in closes:
                current = float(closes[current_holding].loc[date])
                pct = (current - entry_price) / entry_price
                if pct <= -0.04:
                    portfolio.sell(current_holding, all_shares=True, date=date_str)
                    current_holding = None
                    entry_price = None
                    last_rotation = i
                    continue

        # Rotate every 3 days
        if i - last_rotation < 3:
            continue

        # Get crypto fear/greed value
        cfg_before = crypto_fg.loc[:date_str]
        if cfg_before.empty:
            continue
        cfg_val = float(cfg_before.iloc[-1])

        if cfg_val > 55:
            # Risk-on: pick strongest EM momentum
            em_moms = {}
            for t in em_tickers:
                if t in moms_5d:
                    idx = min(i, len(moms_5d[t]) - 1)
                    m = float(moms_5d[t].iloc[idx])
                    if not np.isnan(m):
                        em_moms[t] = m

            if em_moms:
                target = max(em_moms, key=em_moms.get)
            else:
                continue
        elif cfg_val < 35:
            # Risk-off: safety in bonds
            if safety_ticker in closes:
                target = safety_ticker
            else:
                continue
        else:
            # Neutral zone — hold current
            last_rotation = i
            continue

        if target != current_holding:
            if current_holding is not None:
                portfolio.sell(current_holding, all_shares=True, date=date_str)

            dollars = portfolio.cash * 0.90
            result = portfolio.buy(target, dollars=dollars, date=date_str)
            if result:
                current_holding = target
                entry_price = result["exec_price"]

        last_rotation = i
