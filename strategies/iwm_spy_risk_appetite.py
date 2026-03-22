"""
IWM/SPY Risk Appetite Ratio

Hypothesis: The IWM/SPY ratio (small caps vs large caps) is a market risk appetite
barometer. Small caps outperforming large caps (ratio rising) signals increasing
risk appetite. Small caps underperforming (ratio falling) signals risk aversion.

This ratio captures something different from VIX or credit spreads: it measures
where equity investors are ACTUALLY putting money, not options market pricing.

When risk appetite is rising → buy growth/cyclical (SOXX, XLI)
When risk appetite is falling → buy safety (GLD, GDX)
Use crypto fear/greed as cross-domain confirmation.

Signals:
1. WHY: IWM/SPY 7-day ratio trend direction
2. WHEN: Ratio above 7d MA and rising = risk-on; below and falling = risk-off
3. CONFIRMATION: Crypto fear/greed aligns with ratio direction
4. ASSET: Risk-on → SOXX; Risk-off → GDX; Mixed → XLF
5. WHEN NOT: VIX > 40

Eccentricity: Small-cap relative performance as risk barometer + crypto sentiment.
Cross-equity + cross-asset class signal combination.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "IWM/SPY Risk Appetite",
    "hypothesis": "IWM/SPY ratio direction captures equity risk appetite; combined with crypto sentiment for sector allocation.",
    "universe": ["SOXX", "GDX", "XLF", "GLD", "IWM", "SPY"],
    "entry": "Ratio rising + crypto neutral/greed: SOXX. Ratio falling + crypto fear: GDX. Mixed: XLF or GLD.",
    "exit": "Hold 5 days, reassess; -4% stop loss",
    "position_size": "70% of capital per trade",
    "eccentricity": "Small-cap relative performance as risk regime signal + crypto fear/greed cross-market confirmation.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    iwm = data_fetcher.get_prices("IWM", start=start_date, end=end_date)
    if isinstance(iwm.columns, pd.MultiIndex):
        iwm.columns = iwm.columns.get_level_values(0)
    iwm_close = iwm["Close"].dropna()

    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
    spy_close = spy["Close"].dropna()

    soxx = data_fetcher.get_prices("SOXX", start=start_date, end=end_date)
    if isinstance(soxx.columns, pd.MultiIndex):
        soxx.columns = soxx.columns.get_level_values(0)
    soxx_close = soxx["Close"].dropna()

    gdx = data_fetcher.get_prices("GDX", start=start_date, end=end_date)
    if isinstance(gdx.columns, pd.MultiIndex):
        gdx.columns = gdx.columns.get_level_values(0)
    gdx_close = gdx["Close"].dropna()

    xlf = data_fetcher.get_prices("XLF", start=start_date, end=end_date)
    if isinstance(xlf.columns, pd.MultiIndex):
        xlf.columns = xlf.columns.get_level_values(0)
    xlf_close = xlf["Close"].dropna()

    gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)
    if isinstance(gld.columns, pd.MultiIndex):
        gld.columns = gld.columns.get_level_values(0)
    gld_close = gld["Close"].dropna()

    vix = data_fetcher.get_vix(start=start_date, end=end_date)
    crypto_fg = data_fetcher.get_crypto_fear_greed(days=500)

    if iwm_close.empty or spy_close.empty:
        return

    # IWM/SPY ratio
    common_idx = iwm_close.index.intersection(spy_close.index)
    ratio = iwm_close.reindex(common_idx) / spy_close.reindex(common_idx)
    ratio_ma7 = ratio.rolling(7).mean()
    ratio_ma15 = ratio.rolling(15).mean()

    close_map = {"SOXX": soxx_close, "GDX": gdx_close, "XLF": xlf_close, "GLD": gld_close}
    trading_days = soxx_close.index.strftime("%Y-%m-%d").tolist()

    in_trade = False
    trade_ticker = None
    entry_date = None
    entry_price = None

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

        # Exit
        if in_trade:
            days_held = (date_ts - pd.Timestamp(entry_date)).days
            close_s = close_map.get(trade_ticker, soxx_close)
            mask = close_s.index <= date_ts
            if mask.any():
                current_price = close_s[mask].iloc[-1]
                pct_change = (current_price - entry_price) / entry_price * 100
                if days_held >= 5 or pct_change <= -4.0 or pct_change >= 5.0:
                    portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                    in_trade = False
                    trade_ticker = None
                    entry_date = None
                    entry_price = None

        # Signal
        if not in_trade and i >= 20:
            # IWM/SPY ratio direction
            r_mask7 = ratio_ma7.dropna().index <= date_ts
            r_mask15 = ratio_ma15.dropna().index <= date_ts
            if not r_mask7.any() or not r_mask15.any():
                continue

            r_current = ratio[ratio.index <= date_ts].iloc[-1] if (ratio.index <= date_ts).any() else None
            if r_current is None:
                continue
            r_7 = ratio_ma7.dropna()[r_mask7].iloc[-1]
            r_15 = ratio_ma15.dropna()[r_mask15].iloc[-1]

            ratio_rising = r_current > r_7 and r_7 > r_15  # Strong uptrend
            ratio_falling = r_current < r_7 and r_7 < r_15  # Strong downtrend

            # VIX filter
            vix_mask = vix.index <= date_ts
            if vix_mask.any() and vix[vix_mask].iloc[-1] > 40:
                continue

            # Crypto fear/greed
            fg_val = 50
            fg_mask = crypto_fg.index <= date_ts
            if fg_mask.any():
                fg_val = crypto_fg[fg_mask].iloc[-1]

            # Asset selection
            if ratio_rising and fg_val > 35:
                ticker = "SOXX"
            elif ratio_falling and fg_val < 45:
                ticker = "GDX"
            elif ratio_falling:
                ticker = "GLD"
            elif ratio_rising:
                ticker = "XLF"
            else:
                ticker = "XLF"  # Mixed signal

            close_s = close_map[ticker]
            p_mask = close_s.index <= date_ts
            if not p_mask.any():
                continue
            price = close_s[p_mask].iloc[-1]

            dollars = portfolio.cash * 0.7
            if dollars > 100:
                result = portfolio.buy(ticker, dollars=dollars, date=date_str)
                if result:
                    in_trade = True
                    trade_ticker = ticker
                    entry_date = date_str
                    entry_price = price

    if in_trade and trade_ticker:
        portfolio.sell(trade_ticker, all_shares=True, date=trading_days[-1])
