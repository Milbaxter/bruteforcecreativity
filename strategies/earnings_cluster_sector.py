"""
Earnings Cluster Sector — buy sector when multiple companies beat earnings in same week.

Thesis: When multiple companies in the same sector report strong earnings in the same
week, it signals a broad sector tailwind (not just one company doing well). This cluster
effect drives sector ETF momentum for 5-10 more days as:
1. Analysts revise sector-wide estimates
2. Sector rotation flows kick in
3. Short covering amplifies the move

Scan: Check earnings calendar for recent beats. When 2+ companies in a sector beat
in the same week AND the sector ETF has positive 5-day return → buy the sector ETF.

Map companies to sectors via their sector ETF. Use earnings surprise > 3% as threshold.
"""

import pandas as pd
import numpy as np

# Map tickers to sector ETFs for aggregation
SECTOR_MAP = {
    "XLK": ["AAPL", "MSFT", "NVDA", "GOOG", "META", "AVGO", "CRM"],
    "XLF": ["JPM", "BAC", "WFC", "GS", "MS", "C", "AXP"],
    "XLV": ["UNH", "JNJ", "PFE", "MRK", "ABBV", "LLY", "TMO"],
    "XLE": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX"],
    "XLI": ["CAT", "DE", "UNP", "HON", "BA", "RTX", "GE"],
}

ALL_TICKERS = []
for tickers in SECTOR_MAP.values():
    ALL_TICKERS.extend(tickers)

SECTOR_ETFS = list(SECTOR_MAP.keys())

STRATEGY = {
    "name": "Earnings Cluster Sector",
    "hypothesis": "When 2+ companies in a sector beat earnings in the same week, sector ETF momentum continues 5-10 days. Cluster effect > single company effect.",
    "universe": SECTOR_ETFS + ["SPY"],
    "entry": "Buy sector ETF when 2+ sector companies beat earnings >3% in past 10 days AND sector ETF 5d return > 0",
    "exit": "Sell after 7 days or +3%/-2.5% stop",
    "position_size": "80% of capital per trade",
    "eccentricity": "Earnings cluster detection across sectors. Aggregate company-level earnings into sector-level signals. Nobody tracks cross-company earnings clusters for ETF timing.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch earnings calendar for sector companies
    try:
        earnings = data_fetcher.get_earnings_calendar(ALL_TICKERS)
    except Exception:
        earnings = pd.DataFrame()

    if earnings.empty:
        return

    # Fetch sector ETF prices
    sector_prices = {}
    for etf in SECTOR_ETFS:
        df = data_fetcher.get_prices(etf, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            sector_prices[etf] = s

    if len(sector_prices) < 3:
        return

    # Common dates
    common = None
    for s in sector_prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 15:
        return
    common = common.sort_values()

    pm = pd.DataFrame({e: sector_prices[e].loc[common] for e in sector_prices})
    ret5 = pm.pct_change(5)

    # Process earnings data
    if "date" in earnings.columns:
        earnings["date"] = pd.to_datetime(earnings["date"], errors="coerce")
    elif "earnings_date" in earnings.columns:
        earnings["date"] = pd.to_datetime(earnings["earnings_date"], errors="coerce")

    in_trade = False
    trade_ticker = None
    entry_price = None
    days_held = 0

    for i in range(10, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        current_date = common[i]

        if in_trade:
            days_held += 1
            curr = float(pm[trade_ticker].iloc[i])
            pnl_pct = (curr - entry_price) / entry_price

            if days_held >= 7 or pnl_pct >= 0.03 or pnl_pct <= -0.025:
                portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                in_trade = False
                trade_ticker = None
                entry_price = None
                days_held = 0

        elif not in_trade:
            # Count recent earnings beats per sector
            lookback = pd.Timedelta(days=10)
            best_sector = None
            best_beats = 0
            best_ret = 0

            for etf, tickers in SECTOR_MAP.items():
                if etf not in sector_prices:
                    continue

                # Count beats in this sector in the last 10 days
                beats = 0
                for _, row in earnings.iterrows():
                    if pd.notna(row.get("date")) and pd.notna(row.get("ticker")):
                        if row["ticker"] in tickers:
                            row_date = row["date"].tz_localize(None) if hasattr(row["date"], 'tz') and row["date"].tz else row["date"]
                            if current_date - lookback <= row_date <= current_date:
                                surprise = row.get("surprise", row.get("eps_surprise", 0))
                                if pd.notna(surprise) and float(surprise) > 3:
                                    beats += 1

                if beats >= 2:
                    sector_ret = float(ret5[etf].iloc[i]) if pd.notna(ret5[etf].iloc[i]) else 0
                    if sector_ret > 0 and beats > best_beats:
                        best_beats = beats
                        best_sector = etf
                        best_ret = sector_ret

            if best_sector:
                price = float(pm[best_sector].iloc[i])
                result = portfolio.buy(best_sector, dollars=portfolio.cash * 0.8, date=date_str)
                if result:
                    in_trade = True
                    trade_ticker = best_sector
                    entry_price = price
                    days_held = 0

    if in_trade:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(trade_ticker, all_shares=True, date=last_date)
