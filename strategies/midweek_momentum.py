"""
Midweek Momentum Burst — buy QQQ on Wednesday when Monday AND Tuesday were both up.

Thesis: When the stock market has two consecutive up days to start the week (Monday +
Tuesday), the weekly momentum tends to continue through Wednesday-Friday. This "midweek
confirmation" effect occurs because:
1. Institutional buying programs that start Monday take 3-5 days to execute
2. Positive early-week returns attract momentum chasers mid-week
3. Options dealers' gamma positioning amplifies continued buying

Entry: Buy QQQ on Wednesday's close when both Monday and Tuesday had positive close-to-close
returns AND VIX < 25 (not a volatile week where up days are just noise).
Exit: Sell on Friday's close (2-day hold).

This generates ~15-25 trades per year (roughly half of all weeks qualify).
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Midweek Momentum Burst",
    "hypothesis": "When SPY is up both Monday and Tuesday, weekly momentum continues Wed-Fri. Buy QQQ Wednesday, sell Friday. Day-of-week + trend confirmation.",
    "universe": ["QQQ", "SPY"],
    "entry": "Buy QQQ on Wednesday when SPY was up both Monday and Tuesday AND VIX < 25",
    "exit": "Sell Friday close (2-day hold)",
    "position_size": "90% of capital per trade",
    "eccentricity": "Day-of-week calendar effect combined with early-week momentum confirmation. Exploits institutional multi-day execution patterns.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    if spy.empty or qqq.empty or vix.empty:
        return

    spy_close = spy["Close"].dropna()
    qqq_close = qqq["Close"].dropna()
    spy_close.index = pd.to_datetime(spy_close.index)
    qqq_close.index = pd.to_datetime(qqq_close.index)
    vix.index = pd.to_datetime(vix.index)

    common = spy_close.index.intersection(qqq_close.index).intersection(vix.index)
    if len(common) < 10:
        return
    common = common.sort_values()

    spy_c = spy_close.loc[common]
    vix_c = vix.loc[common]

    in_trade = False
    days_held = 0

    for i in range(5, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        day_of_week = common[i].weekday()  # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri

        if in_trade:
            days_held += 1
            if day_of_week == 4 or days_held >= 3:  # Sell on Friday or after 3 days
                portfolio.sell("QQQ", all_shares=True, date=date_str)
                in_trade = False
                days_held = 0

        elif not in_trade and day_of_week == 2:  # Wednesday
            # Check if Monday and Tuesday were both positive
            # Find the last Monday and Tuesday in the common dates
            mon_ret = None
            tue_ret = None

            for j in range(i-1, max(i-5, 0), -1):
                if common[j].weekday() == 1 and tue_ret is None:  # Tuesday
                    tue_ret = (float(spy_c.iloc[j]) - float(spy_c.iloc[j-1])) / float(spy_c.iloc[j-1]) if j > 0 else 0
                elif common[j].weekday() == 0 and mon_ret is None:  # Monday
                    if j > 0:
                        mon_ret = (float(spy_c.iloc[j]) - float(spy_c.iloc[j-1])) / float(spy_c.iloc[j-1])

            vix_level = float(vix_c.iloc[i])

            if mon_ret is not None and tue_ret is not None and mon_ret > 0 and tue_ret > 0 and vix_level < 25:
                result = portfolio.buy("QQQ", dollars=portfolio.cash * 0.9, date=date_str)
                if result:
                    in_trade = True
                    days_held = 0

    if in_trade:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell("QQQ", all_shares=True, date=last_date)
