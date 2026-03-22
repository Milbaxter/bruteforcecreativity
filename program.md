# bruteforcecreativity

An autonomous loop that generates eccentric investment strategies, backtests them against real market data, and surfaces the ones that actually work.

## The Core Thesis

Every obvious strategy is already being run by firms with billions in capital and teams of PhDs. You cannot beat them at their game. But here's the thing: **they literally cannot play small**. A $50B fund cannot deploy a strategy that only works at $10K-$100K scale — the returns don't move their needle, the positions are too small for their compliance overhead, and the markets they'd trade in are too illiquid for institutional size.

This is the edge: **niche, eccentric, small-scale, repeatable patterns** that fly under the institutional radar. We're not looking for one big trade. We're looking for many small, weird, repeatable things — the kind of strategies a curious individual investor could actually execute with $10K-$100K. Things like:
- A pattern that works in microcap stocks too illiquid for funds to touch
- A cross-domain signal (weather + energy stocks) too silly for a risk committee to approve
- A behavioral exploit in prediction markets too small for prop desks to care about
- A congressional copycat trade that would be a PR nightmare for a named fund

The loop generates hundreds of these, tests them, and surfaces the ones that actually show repeatable edge. You don't need one strategy that returns 50%. You need ten strategies that each reliably return 8-15% in their niche, deployed with small capital across different uncorrelated bets.

**These are fast trades, not buy-and-hold.** We want strategies where you're in and out quickly — ideally 1-10 days per trade, almost never more than 15. Think: swing trades, event-driven plays, mean reversion snaps, momentum bursts. Get in on the signal, get out with the profit (or cut the loss), move on.

## Setup

To set up a new run, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `mar21`). The branch `run/<tag>` must not already exist — this is a fresh run.
2. **Create the branch**: `git checkout -b run/<tag>` from current main.
3. **Read the in-scope files**: Read these files for full context:
   - `program.md` — this file. The rules of engagement.
   - `fetch_data.py` — data fetching utilities. Pulls market data, alternative data, etc.
   - `backtest.py` — the backtesting engine. Enforces slippage, computes metrics, validates results.
   - `portfolio.py` — the Portfolio class. Strategies use this to execute trades. Slippage is applied automatically.
4. **Verify data cache exists**: Check that `~/.cache/bruteforcecreativity/` contains cached market data. If not, run `uv run fetch_data.py --refresh` to populate it.
5. **Initialize results.tsv**: Create `results.tsv` with just the header row. The baseline (buy-and-hold SPY) will be recorded after the first run.
6. **Confirm and go**: Confirm setup looks good with the user.

Once you get confirmation, kick off the experimentation.

## Data Sources

You have access to real market data through the following sources. Use `fetch_data.py` utilities or call APIs directly in strategy code:

### Core Market Data (via yfinance — free, no key, historical)
- **Stocks & ETFs** — daily/intraday OHLCV for any ticker. SPY, QQQ, sector ETFs, individual stocks, microcaps.
- **Crypto** — BTC-USD, ETH-USD, SOL-USD, and hundreds of altcoins. Full daily history.
- **Options chains** — calls/puts with strikes, Greeks, open interest, volume for any optionable ticker.
- **Fundamentals** — PE, market cap, sector, dividend yield, earnings dates via `get_fundamentals()`.
- **Commodities** — GLD (gold), USO (oil), SLV (silver), WEAT (wheat), CORN, UNG (nat gas) as ETFs.
- **Forex** — major pairs via yfinance: EURUSD=X, GBPUSD=X, JPYUSD=X, etc.
- **Bonds/Rates** — TLT (long bonds), ^TNX (10Y yield), ^IRX (T-bills), ^FVX (5Y yield).
- **Volatility** — ^VIX historical, with `get_vix()` convenience method.

### Macro Data (FRED with yfinance fallback)
- Treasury yields (DGS10, DTB3) — works without API key via yfinance ^TNX, ^IRX
- Full FRED access (CPI, unemployment, GDP, money supply, credit spreads) — requires free API key in `.env`
- Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html

### Alternative / Eccentric Data
- **Google Trends (pytrends)** — search interest over time for any term. Retail attention proxy. Weekly resolution, 12+ months history. Use `get_google_trends()`.
- **Congressional trading (CapitolTrades)** — congress member stock trades scraped from capitoltrades.com. Historically suspicious alpha. Use `get_congressional_trades()`.
- **Crypto on-chain** — via CoinGecko free API: market data, trading volume, market cap rankings for 10,000+ coins. Use `get_coingecko_market_data()`.
- **Earnings calendar** — earnings dates and surprise data via yfinance `Ticker.earnings_dates`. Use `get_earnings_calendar()`.
- **Economic calendar** — FOMC dates, CPI releases, jobs reports with historical dates. Use `get_economic_calendar()`.
- **Short interest** — via yfinance `Ticker.info` for current short % of float. Historical short interest via `get_short_interest()`.
- **Fear & Greed proxy** — computed from VIX level, put/call ratio, and market breadth. Use `get_fear_greed()`.
- **Wikipedia pageviews** — daily page view counts for any Wikipedia article (public attention proxy). Free, no key, data back to 2015. Use `get_wikipedia_pageviews('Tesla,_Inc.')`. Great for detecting retail attention spikes on stocks.
- **Weather history (Open-Meteo)** — historical daily weather for any location since 1940. Free, no key. Temp, precipitation, wind, snow. Use `get_weather_history(lat, lon)`. Cross with energy, ag, retail stocks.
- **Crypto Fear & Greed Index** — daily crypto sentiment score (0=Extreme Fear, 100=Extreme Greed) from alternative.me. Daily since 2018. Use `get_crypto_fear_greed()`. Contrarian crypto entry signal.

### What each method returns (quick reference)
```
get_prices(tickers, start, end)        → DataFrame OHLCV
get_fundamentals(ticker)               → dict with PE, sector, market_cap, etc.
get_options_chain(ticker)              → dict with 'calls' and 'puts' DataFrames
get_vix(start, end)                    → Series of VIX close prices
get_crypto_prices(symbols, start, end) → DataFrame OHLCV (use 'BTC-USD' format)
get_google_trends(keywords)            → DataFrame of search interest (0-100)
get_congressional_trades(days_back)    → DataFrame: date, representative, ticker, type, amount
get_coingecko_market_data(vs, count)   → DataFrame: coin, price, volume, market_cap, 24h_change
get_earnings_calendar(tickers)         → DataFrame: ticker, date, eps_estimate, eps_actual, surprise
get_economic_calendar()                → DataFrame: date, event, previous, forecast, actual
get_short_interest(tickers)            → DataFrame: ticker, short_pct_float, short_ratio
get_fear_greed(start, end)             → Series: daily fear/greed score (0-100)
get_fred_series(series_id)             → Series of economic data
get_wikipedia_pageviews(article)       → Series of daily pageview counts
get_weather_history(lat, lon)          → DataFrame: temp_max, temp_min, precip, wind, snow
get_crypto_fear_greed(days)            → Series: daily crypto fear/greed score (0-100)
get_risk_free_rate()                   → float (annualized)
get_spy_benchmark(start, end)          → DataFrame OHLCV for SPY
```

### Data Rules
- Always cache fetched data to `~/.cache/bruteforcecreativity/` to avoid redundant API calls.
- Backtest window: trailing 12 months from today's date unless the strategy specifically requires longer history.
- Never look-ahead bias. Strategies can only use data available at the time of each simulated trade.
- Treat API rate limits seriously. If you get rate-limited, wait and retry, don't hammer.

## Strategy Generation

Each iteration, you generate ONE novel investment strategy. A strategy must include:

1. **Name**: a short memorable name (e.g. "Congressional Copycat Momentum", "Weather-Gapped Energy Shorts")
2. **Hypothesis**: a clear, testable thesis. Why would this work? What inefficiency does it exploit?
3. **Universe**: what instruments does it trade? (specific stocks, ETFs, sectors, crypto, prediction markets, etc.)
4. **Entry signal**: precise conditions for entering a position.
5. **Exit signal**: precise conditions for exiting (take-profit, stop-loss, time-based, signal reversal).
6. **Position sizing**: how much capital per trade. Assume $10,000-$100,000 starting capital. Strategies should work at this scale.
7. **Eccentricity factor**: what makes this weird? Why wouldn't a big fund do this? Why does it only work at small scale?
8. **Repeatability**: is this a one-off or does the pattern recur? We want strategies we can run again and again, not one-time events.

### What to Avoid

- **Buy-and-hold** or anything with avg hold > 15 days. Fast in, fast out.
- **Too few trades**: aim for 8+ minimum, ideally 20+.
- **Strategies that resemble anything already in results.tsv** — even vaguely.

## Strategy Implementation

Each strategy is implemented as a standalone Python file in `strategies/`.

**IMPORTANT**: Strategies receive a `Portfolio` object from the backtest engine. All trades MUST go through `portfolio.buy()` and `portfolio.sell()`. This is how slippage is enforced — you cannot bypass it. Do NOT compute portfolio values yourself; the engine handles that.

```python
# strategies/congressional_copycat_momentum.py

STRATEGY = {
    "name": "Congressional Copycat Momentum",
    "hypothesis": "Congress members' disclosed trades, combined with 5-day momentum confirmation, outperform because they trade on policy knowledge with a legal reporting delay.",
    "universe": ["SPY", "QQQ", "XLF", "XLE", "XLV"],  # MUST list all tickers the strategy trades
    "entry": "Buy when a congress member discloses a purchase AND the stock has positive 5-day momentum",
    "exit": "Sell after 5 trading days or at -3% stop loss",
    "position_size": "Equal weight, max 20% per position",
    "eccentricity": "Combines public political trading data with momentum — too reputationally risky for big funds to openly copy politicians",
}

def run(data_fetcher, portfolio, start_date, end_date):
    """
    Execute the strategy using portfolio.buy() and portfolio.sell().

    Args:
        data_fetcher: DataFetcher instance — use to fetch any data you need
        portfolio: Portfolio instance — use to execute trades (slippage enforced)
            portfolio.buy(ticker, shares=N, date="YYYY-MM-DD")
            portfolio.buy(ticker, dollars=N, date="YYYY-MM-DD")  # auto-compute shares
            portfolio.sell(ticker, shares=N, date="YYYY-MM-DD")
            portfolio.sell(ticker, all_shares=True, date="YYYY-MM-DD")
            portfolio.cash  # current cash available
            portfolio.positions  # dict of ticker -> shares held
        start_date: str "YYYY-MM-DD"
        end_date: str "YYYY-MM-DD"
    """
    # Fetch data
    prices = data_fetcher.get_prices("SPY", start=start_date, end=end_date)
    congress = data_fetcher.get_congressional_trades()

    # Your signal logic here...
    # For each signal: portfolio.buy(...) or portfolio.sell(...)
```

### Universe Declaration

The `STRATEGY["universe"]` list MUST contain every ticker the strategy might trade. The backtest engine pre-loads price data for these tickers and passes it to the Portfolio for price lookups and slippage computation. If you trade a ticker not in the universe, the Portfolio will not have price data and the trade will fail silently.

## Backtesting Rules

- **Starting capital**: $10,000
- **Period**: trailing 12 months (first 9 months in-sample, last 3 months out-of-sample)
- **Benchmark**: buy-and-hold SPY over the same period
- **Slippage**: 0.1% per trade, enforced by the Portfolio (you cannot skip it)
- **No fractional shares** for stocks (crypto yes)
- **Metrics computed by the engine** (you don't compute these):
  - Total return %
  - Sharpe ratio (annualized, risk-free rate from FRED)
  - Max drawdown %
  - Win rate %
  - Number of trades
  - **Average holding days** (key metric — lower is better, target 1-10 days)
  - Max holding days
  - Calmar ratio
  - Profit factor
  - **Out-of-sample metrics** (trades in last 3 months evaluated separately)

### Winner Criteria

A strategy earns "winner" status ONLY if ALL of these are true:
- Beats SPY return
- Sharpe ratio > 1.0
- At least 8 round-trip trades (prevents flukes)
- Average holding period <= 15 days (we want fast in-and-out)
- At least 2 out-of-sample trades with positive total PnL (proves it's not just curve-fitted to old data)

### Walk-Forward Validation

When a strategy passes the initial screen as a "winner", the engine automatically re-runs it on 2 additional 12-month windows to confirm robustness:
- **Window 1**: 24 months ago → 12 months ago
- **Window 2**: 18 months ago → 6 months ago
- **Window 3**: the original (12 months ago → today) — already tested

Each additional window must show: positive return, Sharpe > 0.5, max drawdown >= -20%, at least 5 trades. The strategy passes walk-forward if it clears at least 2 of 3 windows.

**If walk-forward passes**: the strategy is promoted to `winners/` (auto-copied) and logged to `winners/results.tsv`. These are the strategies worth deploying.

**If walk-forward fails**: the strategy is downgraded to "mediocre". It got lucky in one period but doesn't generalize — not worth real money.

### Volume Warnings

The engine logs warnings when a trade exceeds 1% of daily volume. This flags unrealistic fills — a strategy that "works" but requires buying 10% of a microcap's daily volume would not actually be executable.

## Logging Results

Log each experiment to `results.tsv` (tab-separated). The engine prints a structured summary after each backtest — extract metrics from there.

Header: `commit	strategy_name	total_return_pct	sharpe_ratio	max_drawdown_pct	win_rate_pct	num_trades	avg_holding_days	vs_spy_pct	oos_pnl	status	description`

Status: `winner` (beats SPY, Sharpe>1.0, 8+ trades, avg hold ≤15d, positive OOS, passes walk-forward 2/3), `mediocre`, `loser`, or `crash`.

## The Experiment Loop

The experiment runs on a dedicated branch (e.g. `run/mar21`).

**LOOP FOREVER:**

1. **Check what's been tried**: quickly scan `results.tsv` ONLY to avoid duplicating a strategy that already exists. Do NOT look at winners for "inspiration" — that leads to riffing on the same idea with different parameters, which is exactly what we don't want. The goal is to discover NEW kinds of winners, not optimize old ones.
2. **Generate a completely new strategy**: every single strategy must be a fresh, novel hypothesis. Different data sources, different asset classes, different logic from anything already in results.tsv. If your idea resembles anything already tested — even vaguely — throw it out and think harder. No "v2", no variations, no parameter tweaks. FRESH IDEAS ONLY.
3. **Implement it**: write the strategy file in `strategies/`. Include the full `STRATEGY` dict and `run()` function.
4. **git commit**: commit the strategy file.
5. **Run the backtest**: `uv run backtest.py strategies/<name>.py > run.log 2>&1`
6. **Read results**: extract the metrics from `run.log`.
7. **If crashed**: read `tail -n 50 run.log` for the traceback. If it's a simple fix (typo, API issue, missing data), fix and re-run. If fundamentally broken, log as crash and move on.
8. **Log to results.tsv**: record the outcome.
9. **Move on immediately**: do not dwell on results. Do not generate variations. Do not "evolve" a winner. Just log it and generate the next completely different idea. The brute force IS the method — volume of diverse ideas, not depth on any single one.
10. **GOTO 1**

### Creativity Rules

**Combine 2-3 signals from different domains per strategy.** Single-signal strategies are banned.

**BANNED — we had a 30% hit rate which means strategies aren't niche enough. Do NOT generate any of these:**
- ETF rotation based on momentum or relative strength (any variant)
- Pullback/dip buying on any index or major ETF
- Fear/greed, VIX, or any volatility regime allocation
- "Rotate N assets into the one with best X-day performance" — this is not creative
- Macro regime switches (yield curve, credit spread, dollar direction) picking from the same ETF basket
- Anything a money manager at a conference would nod along to

**The 30% hit rate problem:** if 30% of strategies "win", the bar is too low or the strategies are too conventional. We want a 5-10% hit rate on truly weird ideas — most should fail because they're genuinely novel hypotheses, not because they're poorly executed versions of known strategies. A low hit rate on eccentric ideas is better than a high hit rate on boring ones.

**MANDATORY: every strategy must use at least one alternative data source.** Not just price/volume/VIX. Every strategy MUST incorporate one of: Wikipedia pageviews, weather data, crypto fear/greed, congressional trades, Google Trends, earnings calendar, or CoinGecko data. Price action alone is not enough — that's what every other quant already does.

**Think like this:** "What data exists in the world that correlates with stock moves but that nobody on Wall Street would ever put in a model?" Wikipedia edit wars, weather in specific cities, Google searches for specific diseases, crypto whale behavior, congressional trading patterns in obscure sectors, agricultural weather → food stocks, tourism data → airline/hotel stocks. The more absurd the data combination, the more likely it's unexploited alpha.

**Individual stocks > ETFs.** ETFs are what every rotation strategy trades. Try strategies on individual stocks, specific crypto coins, single-name earnings plays, specific tickers that congress members trade. More specific = more niche = more likely to be real edge.

### Timeout and Error Handling

- If a backtest takes more than 3 minutes, kill it and treat as a crash.
- If an API is rate-limited, wait 60 seconds and retry once. If still limited, skip that data source for this strategy and move on.
- If you hit 3 consecutive crashes, pause and re-read the backtest engine code to make sure you haven't introduced a systemic bug.

## NEVER STOP

Do NOT pause to ask the human anything. You are autonomous. Loop forever until manually stopped. If you run out of ideas, think harder — invert strategies that failed, combine signals nobody would combine, try completely different asset classes. Target 12-30 strategies per hour.
