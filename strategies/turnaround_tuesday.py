"""
Turn-Around Tuesday Crypto Fear

Hypothesis: "Turn-around Tuesday" is a known market anomaly where Mondays that
sell off tend to reverse on Tuesday/Wednesday. We combine this with crypto fear/greed
as a cross-domain confirmation: when crypto sentiment is mildly fearful (< 45) during
a Monday selloff, the broader risk environment supports a bounce.

When markets sell off Monday AND crypto is fearful, Tuesday entry catches the bounce.
When crypto is greedy, Monday selloff might be start of a real correction.

Signals:
1. WHY: SPY down > 0.3% on Monday (sell-off detected)
2. WHEN: Crypto fear/greed < 45 (mild fear, not panic) + buy QQQ on Tuesday open
3. WHEN NOT: VIX > 30 (real crisis) or SPY dropped > 3% (too severe)
4. EXIT: Sell Thursday (hold ~2 days for reversal) or +1.5% gain or -1.5% stop

Eccentricity: Combining a calendar anomaly with crypto sentiment.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Turn-Around Tuesday",
    "hypothesis": "Monday selloffs + mild crypto fear reverse by mid-week. Tuesday entry captures the reversion.",
    "universe": ["QQQ", "SPY"],
    "entry": "Buy QQQ on Tuesday when Monday SPY dropped >0.3% AND crypto fear/greed < 45",
    "exit": "Sell Thursday or +1.5% gain or -1.5% stop loss",
    "position_size": "60% of capital per trade",
    "eccentricity": "Calendar anomaly (Turn-around Tuesday) validated by crypto market sentiment. Cross-domain timing.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    if isinstance(qqq.columns, pd.MultiIndex):
        qqq.columns = qqq.columns.get_level_values(0)
    qqq_close = qqq["Close"].dropna()

    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
    spy_close = spy["Close"].dropna()

    vix = data_fetcher.get_vix(start=start_date, end=end_date)
    crypto_fg = data_fetcher.get_crypto_fear_greed(days=500)

    if qqq_close.empty or spy_close.empty or crypto_fg.empty:
        return

    trading_days = qqq_close.index
    in_trade = False
    entry_date = None
    entry_price = None

    for i in range(1, len(trading_days)):
        date_ts = trading_days[i]
        date_str = date_ts.strftime("%Y-%m-%d")
        prev_date = trading_days[i-1]
        day_of_week = date_ts.dayofweek  # 0=Monday, 1=Tuesday, ...

        price = qqq_close.iloc[i]

        # Exit: sell on Thursday (dayofweek=3) or stop/target
        if in_trade:
            days_held = (date_ts - pd.Timestamp(entry_date)).days
            pct_change = (price - entry_price) / entry_price * 100

            # Exit on Thursday, or after 3 days, or stop/target
            if day_of_week >= 3 or days_held >= 3 or pct_change >= 1.5 or pct_change <= -1.5:
                portfolio.sell("QQQ", all_shares=True, date=date_str)
                in_trade = False
                entry_date = None
                entry_price = None
                continue

        # Entry: only on Tuesday (dayofweek=1)
        if not in_trade and day_of_week == 1:
            # Check if Monday (previous day) was indeed Monday
            if prev_date.dayofweek != 0:
                continue

            # Check Monday SPY return
            if i < 2:
                continue
            spy_mon_mask = spy_close.index <= prev_date
            spy_fri_mask = spy_close.index < prev_date
            if not spy_mon_mask.any() or not spy_fri_mask.any():
                continue

            spy_monday = spy_close[spy_mon_mask].iloc[-1]
            spy_friday = spy_close[spy_fri_mask].iloc[-1]
            monday_ret = (spy_monday - spy_friday) / spy_friday * 100

            # Monday must be down > 0.3% but not catastrophic (< -3%)
            if monday_ret > -0.3 or monday_ret < -3.0:
                continue

            # Crypto fear/greed < 45
            fg_mask = crypto_fg.index <= date_ts
            if not fg_mask.any():
                continue
            current_fg = crypto_fg[fg_mask].iloc[-1]
            if current_fg >= 45:
                continue

            # VIX < 30
            vix_mask = vix.index <= date_ts
            if vix_mask.any() and vix[vix_mask].iloc[-1] > 30:
                continue

            dollars = portfolio.cash * 0.6
            if dollars > 100:
                result = portfolio.buy("QQQ", dollars=dollars, date=date_str)
                if result:
                    in_trade = True
                    entry_date = date_str
                    entry_price = price

    if in_trade:
        last_date = trading_days[-1].strftime("%Y-%m-%d")
        portfolio.sell("QQQ", all_shares=True, date=last_date)
