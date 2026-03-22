"""
GDX/GLD Ratio Mean Reversion

Hypothesis: Gold miners (GDX) and gold (GLD) are correlated, but GDX is leveraged
to gold moves. When the GDX/GLD ratio deviates significantly from its rolling mean,
it tends to revert. This creates a systematic pairs-like trade:

- When GDX/GLD ratio is too LOW (GDX underperforming gold) → buy GDX (catch-up trade)
- When GDX/GLD ratio is too HIGH (GDX overextended vs gold) → buy GLD (reversion)

Crypto fear/greed adds timing: in fear environments, GDX tends to lag more than
it should (miners get sold off with equities even when gold is rising). This makes
the ratio signal stronger during fear periods.

Signals:
1. WHY: GDX/GLD ratio z-score deviation from 20-day rolling mean
2. WHEN: z-score > 1.2 or < -1.2 (significant deviation)
3. CONFIRMATION: Crypto fear/greed aligns (fear + low ratio = strong GDX buy)
4. WHEN NOT: VIX > 40

Eccentricity: Pure ratio mean-reversion between related assets, enhanced by crypto
sentiment. A statistical arbitrage approach at retail scale.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "GDX/GLD Ratio Reversion",
    "hypothesis": "GDX/GLD ratio mean-reverts; deviations are amplified by crypto fear/greed, creating predictable entry points.",
    "universe": ["GDX", "GLD"],
    "entry": "Buy GDX when ratio z-score < -1.2; buy GLD when z-score > 1.2. Crypto fear boosts GDX signal.",
    "exit": "Sell after 5 days or ratio reverts to mean or -3% stop loss",
    "position_size": "60% of capital per trade",
    "eccentricity": "Ratio mean-reversion between gold and gold miners with crypto sentiment timing. Statistical arbitrage for the little guy.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    gdx = data_fetcher.get_prices("GDX", start=start_date, end=end_date)
    if isinstance(gdx.columns, pd.MultiIndex):
        gdx.columns = gdx.columns.get_level_values(0)
    gdx_close = gdx["Close"].dropna()

    gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)
    if isinstance(gld.columns, pd.MultiIndex):
        gld.columns = gld.columns.get_level_values(0)
    gld_close = gld["Close"].dropna()

    vix = data_fetcher.get_vix(start=start_date, end=end_date)
    crypto_fg = data_fetcher.get_crypto_fear_greed(days=500)

    if gdx_close.empty or gld_close.empty:
        return

    # Compute GDX/GLD ratio
    common_idx = gdx_close.index.intersection(gld_close.index)
    gdx_aligned = gdx_close.reindex(common_idx)
    gld_aligned = gld_close.reindex(common_idx)
    ratio = gdx_aligned / gld_aligned

    # Rolling z-score of ratio
    ratio_ma20 = ratio.rolling(20).mean()
    ratio_std20 = ratio.rolling(20).std()
    ratio_zscore = (ratio - ratio_ma20) / ratio_std20

    trading_days = common_idx.strftime("%Y-%m-%d").tolist()
    in_trade = False
    trade_ticker = None
    entry_date = None
    entry_price = None
    entry_zscore = None

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

        # Exit
        if in_trade:
            days_held = (date_ts - pd.Timestamp(entry_date)).days
            if trade_ticker == "GDX":
                current_price = gdx_aligned.iloc[i]
            else:
                current_price = gld_aligned.iloc[i]

            pct_change = (current_price - entry_price) / entry_price * 100
            current_z = ratio_zscore.iloc[i] if i < len(ratio_zscore) and not pd.isna(ratio_zscore.iloc[i]) else 0

            # Exit: 5 days, stop loss, or ratio reverted (z-score back near 0)
            reverted = False
            if entry_zscore is not None:
                if entry_zscore < 0 and current_z > -0.3:  # Was low, came back
                    reverted = True
                elif entry_zscore > 0 and current_z < 0.3:  # Was high, came back
                    reverted = True

            if days_held >= 5 or pct_change <= -3.0 or pct_change >= 4.0 or reverted:
                portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                in_trade = False
                trade_ticker = None
                entry_date = None
                entry_price = None
                entry_zscore = None
                # Can enter new trade

        # Entry
        if not in_trade and i >= 25:
            z = ratio_zscore.iloc[i]
            if pd.isna(z):
                continue

            # VIX filter
            vix_mask = vix.index <= date_ts
            if vix_mask.any() and vix[vix_mask].iloc[-1] > 40:
                continue

            # Get crypto fear/greed
            fg_val = 50  # default neutral
            fg_mask = crypto_fg.index <= date_ts
            if fg_mask.any():
                fg_val = crypto_fg[fg_mask].iloc[-1]

            # Determine trade
            ticker = None
            if z < -1.2:
                # GDX underperforming gold → buy GDX (catch-up)
                # Signal is STRONGER when crypto fear is present (GDX sold off with equities)
                if fg_val < 45:  # Fear amplifies the signal
                    ticker = "GDX"
                elif z < -1.5:  # Without fear confirmation, need stronger deviation
                    ticker = "GDX"
            elif z > 1.2:
                # GDX overextended vs gold → buy GLD (reversion)
                if fg_val > 50:  # Greed environment, miners overextended
                    ticker = "GLD"
                elif z > 1.5:
                    ticker = "GLD"

            if ticker is None:
                continue

            if ticker == "GDX":
                price = gdx_aligned.iloc[i]
            else:
                price = gld_aligned.iloc[i]

            dollars = portfolio.cash * 0.6
            if dollars > 100:
                result = portfolio.buy(ticker, dollars=dollars, date=date_str)
                if result:
                    in_trade = True
                    trade_ticker = ticker
                    entry_date = date_str
                    entry_price = price
                    entry_zscore = z

    if in_trade and trade_ticker:
        portfolio.sell(trade_ticker, all_shares=True, date=trading_days[-1])
