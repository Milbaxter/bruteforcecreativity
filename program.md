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

**These are fast trades, not buy-and-hold.** We want strategies where you're in and out quickly — ideally 1-10 days per trade, almost never more than 15. The idea is high-frequency-for-humans: many quick, decisive trades based on specific signals, not sitting on a position for months hoping it goes up. Think: swing trades, event-driven plays, mean reversion snaps, momentum bursts. Get in on the signal, get out with the profit (or cut the loss), move on to the next one.

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
- **Insider trading (OpenInsider)** — corporate insider buys/sells scraped from openinsider.com. Cluster buys = conviction signal. Use `get_insider_trades()`.
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
get_insider_trades(ticker)             → DataFrame of insider buys/sells
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

### What Makes a Good Strategy

- **Eccentric**: crosses domains (weather + energy, congressional trades + options, Google Trends + crypto). Combines signals that institutional quants wouldn't put in the same model.
- **Specific**: not "buy low sell high" — specific ticker selection logic, specific indicators, specific thresholds.
- **Testable**: can be backtested with available data. No strategies that require data you can't access.
- **Small-capital friendly**: works with $10K-$100K. No strategies that require massive positions to move markets or get fills. Ideally trades in markets or instruments too small for institutional players.
- **Repeatable**: the pattern should recur — not a one-time event. We want strategies we can deploy month after month. A strategy that only fired once in 12 months is useless even if that one trade was amazing.
- **Novel across the run**: don't repeat strategies. Check `results.tsv` to see what's been tried. Riff on winners but don't duplicate.

### What to Avoid

- **Plain vanilla**: simple moving average crossovers, basic RSI, standard mean reversion. These are table stakes.
- **Buy-and-hold**: we are NOT looking for "buy this and wait 6 months." Every strategy must have a clear, fast exit. Target 1-10 day holding periods.
- **Untestable**: strategies based on data you can't actually fetch.
- **Overfitted**: a strategy that only works on one specific stock in one specific month is worthless. It must work across the out-of-sample period too.
- **Too few trades**: if your strategy only fires 3 times in 12 months, it's statistically meaningless no matter how good those 3 trades were. Aim for 8+ trades minimum, ideally 20+.
- **Illegal**: no insider trading (using actual nonpublic info), no market manipulation. Congressional trade data is public record — that's fair game.

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
- Max drawdown >= -15% (limited downside — we don't want strategies that can lose big)
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

## Output Format

After each backtest completes, the engine prints:

```
---
strategy:          Congressional Copycat Momentum
status:            winner
total_return_pct:  18.45
sharpe_ratio:      1.23
max_drawdown_pct:  -8.72
win_rate_pct:      62.5
num_trades:        24
avg_holding_days:  4.2
max_holding_days:  8
calmar_ratio:      2.12
profit_factor:     1.87
vs_spy_pct:        +5.32
spy_return_pct:    13.13
oos_num_trades:    7
oos_win_rate_pct:  71.4
oos_total_pnl:     342.50
elapsed_seconds:   12.3
```

## Logging Results

When an experiment is done, log it to `results.tsv` (tab-separated, NOT comma-separated).

Header and columns:

```
commit	strategy_name	total_return_pct	sharpe_ratio	max_drawdown_pct	win_rate_pct	num_trades	avg_holding_days	vs_spy_pct	oos_pnl	status	description
```

- **commit**: git commit hash (short, 7 chars)
- **strategy_name**: short name
- **total_return_pct**: e.g. 18.45
- **sharpe_ratio**: e.g. 1.23
- **max_drawdown_pct**: e.g. -8.72 (negative number)
- **win_rate_pct**: e.g. 62.5
- **num_trades**: integer (round-trip trades)
- **avg_holding_days**: e.g. 4.2 (lower is better)
- **vs_spy_pct**: excess return vs buy-and-hold SPY (e.g. +5.32 or -3.10)
- **oos_pnl**: out-of-sample total PnL in dollars (last 3 months)
- **status**: `winner`, `mediocre`, `loser`, or `crash`
  - `winner`: beats SPY, Sharpe > 1.0, max drawdown >= -15%, 8+ trades, avg hold <= 15 days, positive OOS PnL, AND passes walk-forward validation (2/3 windows)
  - `mediocre`: positive return but doesn't meet all winner criteria, OR passed initial screen but failed walk-forward
  - `loser`: negative return or worse than SPY by > 5%
  - `crash`: code errored out
- **description**: one-line description of the hypothesis

Example:
```
a1b2c3d	SPY Buy and Hold	13.13	0.89	-7.20	100.0	1	365.0	0.00	0.00	mediocre	baseline buy-and-hold SPY benchmark
b2c3d4e	Congressional Copycat	18.45	1.23	-8.72	62.5	24	4.2	+5.32	342.50	winner	copy congress trades with momentum filter
c3d4e5f	Full Moon Longs	-2.30	-0.15	-12.40	41.2	26	14.1	-15.43	-120.00	loser	buy SPY on full moons sell on new moons
d4e5f6g	Sentiment Vix Arb	0.00	0.00	0.00	0.0	0	0.0	0.00	0.00	crash	reddit sentiment vs VIX divergence trade (API error)
```

## The Experiment Loop

The experiment runs on a dedicated branch (e.g. `run/mar21`).

**LOOP FOREVER:**

1. **Review state**: check `results.tsv` to see what's been tried, what worked, what didn't. Look at the current best strategies for inspiration.
2. **Diversity check (MANDATORY)**: before generating, look at the last 3 strategies in `results.tsv`. If they share the same core signal type or universe (e.g., all rotate GLD/QQQ/XLE, or all use momentum on the same ETFs), you MUST use a completely different data source and signal for the next strategy. Specifically:
   - **No more than 3 strategies in a row** with the same universe or signal type. If the last 3 all traded the same tickers or used the same indicator, break the pattern.
   - **Every 5th strategy MUST use an alternative data source**: Wikipedia pageviews, weather (Open-Meteo), crypto fear/greed index, congressional trades, insider trades, Google Trends, or earnings calendar. Not just price/volume data.
   - **Penalize repetition**: if you catch yourself generating "X Rotation v3" or "Y Momentum with different parameters", STOP. That's parameter optimization, not creativity. The whole point is brute force CREATIVITY — explore different domains, different asset classes, different signal types.
   - **Diversify across asset classes**: if recent strategies all trade equities/ETFs, try crypto, forex, or commodities. If they're all US-focused, look at international ETFs.
3. **Generate a strategy**: come up with a novel, eccentric strategy. Be creative. Cross domains. Combine weird signals. Think about what a bored quant at 2am would try that they'd never pitch to their boss.
4. **Implement it**: write the strategy file in `strategies/`. Include the full `STRATEGY` dict and `run()` function.
5. **git commit**: commit the strategy file.
6. **Run the backtest**: `uv run backtest.py strategies/<name>.py > run.log 2>&1`
7. **Read results**: extract the metrics from `run.log`.
8. **If crashed**: read `tail -n 50 run.log` for the traceback. If it's a simple fix (typo, API issue, missing data), fix and re-run. If fundamentally broken, log as crash and move on.
9. **Log to results.tsv**: record the outcome.
10. **If winner**: keep the commit, celebrate internally, think about variations — but not more than 2 variations before moving to a completely different idea.
11. **If not winner**: keep the commit anyway (we want the history), but note the status.
12. **Evolve**: every 5-10 strategies, look at patterns in results.tsv. What domains/signals appear in winners? Generate variations on winning themes. But also keep throwing wild ideas — the whole point is brute force creativity.
13. **GOTO 1**

### Creativity Directives

When generating strategies, draw from these idea wells:

All strategies should be **fast in, fast out** (1-10 day holds). Think swing trades, not investments.

#### COMBO STRATEGIES (the default — single-signal strategies are discouraged)

**Every strategy should combine 2-3 uncorrelated signals into one entry condition.** Single-signal strategies (just momentum, just mean reversion, just one indicator) are too simple — they're what every quant screen already runs. The edge comes from combining signals that nobody else is combining because they come from different domains.

Examples of good combo entries:
- Congressional buy disclosure + stock has positive 5-day momentum + short interest < 5% → BUY
- Wikipedia pageview spike > 2 standard deviations + insider cluster buy in past 10 days + price above 20-day MA → BUY
- Crypto Fear & Greed < 20 (extreme fear) + BTC above 200-day MA + weekend (lower liquidity) → BUY BTC
- Extreme cold weather in Houston (Open-Meteo) + natural gas ETF (UNG) dropped > 3% in past 5 days + VIX > 20 → BUY UNG
- Earnings beat > 5% + Google Trends for company name rising + stock pulled back > 2% from post-earnings high → BUY
- FOMC announcement day + VIX > 25 + SPY below 10-day MA → BUY SPY (fear + event + oversold)

The pattern: **domain signal (WHY to look) + momentum/mean-reversion filter (WHEN to enter) + risk filter (WHEN NOT to enter)**. Three signals, three different data sources, one entry.

**If you catch yourself writing a strategy with only one entry condition, STOP and add at least one more uncorrelated signal.** Two signals minimum, three preferred.

#### Idea Wells

Think WEIRD. Think niche. Think "what would a curious person with $50K and too much free time try that a hedge fund never would?"

- **Cross-domain combos**: weather extremes + energy/agriculture ETFs + momentum confirmation. Wikipedia attention spikes + stock pullback + insider buying. Crypto sentiment + on-chain signals + weekend timing. Google Trends for disease keywords + pharma stocks + earnings proximity.
- **Temporal anomalies + confirmation**: day-of-week effects + volume confirmation + VIX regime. Month-end rebalancing flows + sector strength + short interest. Options expiration week + unusual volume + price compression. Post-holiday drift + momentum + retail attention.
- **Behavioral exploits + filters**: retail panic selling (VIX spike) + stock is above 200-day MA (healthy stock in temporary fear). Meme stock lifecycle (Reddit attention spike) + low short interest (squeeze potential) + positive earnings surprise. IPO lockup expiry + insider NOT selling (confidence signal) + sector tailwind.
- **Copycat combos**: congressional buy + momentum + low short interest. Insider cluster buys (3+ insiders in 30 days) + positive earnings trend + pullback entry. 13F filing copycat + stock under $10B market cap (too small for the fund to fully load) + positive momentum.
- **Event-driven combos**: FOMC day + VIX level + prior day's price action. CPI release + bond yield direction + equity sector rotation. Jobs report + wage data direction + consumer sector ETF momentum.
- **Crypto-specific**: crypto fear/greed index + Bitcoin dominance ratio + weekend timing. Altcoin volume spike + Bitcoin stable + Google Trends for the coin. Ethereum gas fees dropping + DeFi token pullback + crypto sentiment turning.
- **Really weird ones**: full moon + VIX percentile + gold momentum (superstition arbitrage). Tax loss selling season (December) + beaten-down small caps + insider buying. Natural disaster (extreme weather) + insurance stock reaction + mean reversion. Super Bowl winner (AFC vs NFC) + market direction (yes, this is a real anomaly people have studied). Congressional trading in defense stocks + geopolitical tension proxy + momentum.

**The weirder the combo, the less likely an institution is already running it. That's the edge.**

### Timeout and Error Handling

- If a backtest takes more than 3 minutes, kill it and treat as a crash.
- If an API is rate-limited, wait 60 seconds and retry once. If still limited, skip that data source for this strategy and move on.
- If you hit 3 consecutive crashes, pause and re-read the backtest engine code to make sure you haven't introduced a systemic bug.

## NEVER STOP

Once the experiment loop has begun (after the initial setup), do NOT pause to ask the human if you should continue. Do NOT ask "should I keep going?" or "is this a good stopping point?". The human might be asleep, or gone from a computer and expects you to continue working indefinitely until you are manually stopped. You are autonomous. If you run out of ideas, think harder — combine previous near-misses, try more radical approaches, explore new data source combinations, invert strategies that failed (maybe the opposite works). The loop runs until the human interrupts you, period.

As a rough estimate: each strategy generation + backtest cycle should take 2-5 minutes. That's 12-30 per hour. Overnight (8 hours) you could test 100-240 strategies. The user wakes up to a `results.tsv` full of data and a handful of genuinely interesting strategies they'd never have thought of.
