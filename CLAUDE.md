# bruteforcecreativity

An autonomous loop that generates eccentric investment strategies, backtests them against real market data, and surfaces the ones that actually work. The premise: every obvious strategy is already being run by firms with billions in capital. The edge for small players is in ideas too weird for institutional risk committees to approve.

## Setup

To set up a new run, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `mar21`). The branch `run/<tag>` must not already exist — this is a fresh run.
2. **Create the branch**: `git checkout -b run/<tag>` from current main.
3. **Read the in-scope files**: Read these files for full context:
   - `CLAUDE.md` — this file. The rules of engagement.
   - `fetch_data.py` — data fetching utilities. Pulls market data, alternative data, etc.
   - `backtest.py` — the backtesting engine. Takes a strategy and returns performance metrics.
   - `score.py` — scoring function. Ranks strategies by risk-adjusted returns.
4. **Verify data cache exists**: Check that `~/.cache/bruteforcecreativity/` contains cached market data. If not, run `uv run fetch_data.py --refresh` to populate it.
5. **Initialize results.tsv**: Create `results.tsv` with just the header row. The baseline (buy-and-hold SPY) will be recorded after the first run.
6. **Confirm and go**: Confirm setup looks good with the user.

Once you get confirmation, kick off the experimentation.

## Data Sources

You have access to real market data through the following sources. Use `fetch_data.py` utilities or call APIs directly in strategy code:

### Core Market Data
- **yfinance** — stock prices (daily/intraday), options chains, fundamentals, ETFs, crypto. Free, no key needed.
- **FRED (Federal Reserve)** — macroeconomic indicators: interest rates, inflation (CPI/PCE), unemployment, GDP, money supply. Free API key in `.env`.
- **Polygon.io** — tick-level stocks, options, crypto. API key in `.env`. Use for granular intraday strategies.

### Alternative / Eccentric Data
- **Polymarket API** — prediction market prices and volumes. Trade based on real-world event probabilities.
- **Google Trends (pytrends)** — search interest over time. Retail attention proxy.
- **Congressional trading (QuiverQuant)** — congress member stock trades. Historically suspicious alpha.
- **OpenInsider** — insider buying/selling clusters. Conviction signal.
- **NOAA Weather API** — weather data by region. Correlates with energy, agriculture, retail.
- **Reddit (via API)** — subreddit sentiment, especially r/wallstreetbets, r/stocks. Meme momentum.
- **News sentiment (NewsAPI / GDELT)** — event-driven signals.
- **Fear & Greed Index (CNN)** — market sentiment extremes.
- **VIX / options flow** — volatility and unusual options activity.

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
6. **Position sizing**: how much capital per trade. Assume $10,000 starting capital.
7. **Eccentricity factor**: what makes this weird? Why wouldn't a big fund do this?

### What Makes a Good Strategy

- **Eccentric**: crosses domains (weather + energy, congressional trades + options, Google Trends + crypto). Combines signals that institutional quants wouldn't put in the same model.
- **Specific**: not "buy low sell high" — specific ticker selection logic, specific indicators, specific thresholds.
- **Testable**: can be backtested with available data. No strategies that require data you can't access.
- **Small-capital friendly**: works with $10K. No strategies that require massive positions to move markets or get fills.
- **Novel across the run**: don't repeat strategies. Check `results.tsv` to see what's been tried. Riff on winners but don't duplicate.

### What to Avoid

- Plain vanilla: simple moving average crossovers, basic RSI, standard mean reversion. These are table stakes.
- Untestable: strategies based on data you can't actually fetch.
- Overfitted: a strategy that only works on one specific stock in one specific month is worthless.
- Illegal: no insider trading (using actual nonpublic info), no market manipulation. Congressional trade data is public record — that's fair game.

## Strategy Implementation

Each strategy is implemented as a standalone Python file in `strategies/`.

```python
# strategies/congressional_copycat_momentum.py

STRATEGY = {
    "name": "Congressional Copycat Momentum",
    "hypothesis": "Congress members' disclosed trades, combined with 5-day momentum confirmation, outperform because they trade on policy knowledge with a legal reporting delay.",
    "universe": ["SPY", "QQQ", "XLF", "XLE", "XLV"],
    "entry": "Buy when a congress member discloses a purchase AND the stock has positive 5-day momentum",
    "exit": "Sell after 20 trading days or at -5% stop loss",
    "position_size": "Equal weight, max 20% per position",
    "eccentricity": "Combines public political trading data with momentum — too reputationally risky for big funds to openly copy politicians",
}

def run(data_fetcher, start_date, end_date, starting_capital=10000):
    """
    Execute the backtest. Returns a dict with:
    - trades: list of (date, ticker, action, price, shares)
    - portfolio_values: list of (date, value)
    - final_value: float
    - total_return_pct: float
    - max_drawdown_pct: float
    - sharpe_ratio: float
    - win_rate: float
    - num_trades: int
    """
    # ... strategy logic here ...
```

## Backtesting Rules

- **Starting capital**: $10,000
- **Period**: trailing 12 months
- **Benchmark**: buy-and-hold SPY over the same period
- **Transaction costs**: assume $0 commissions, but 0.1% slippage per trade
- **No fractional shares** unless the instrument supports it (crypto yes, stocks no)
- **Metrics to compute**:
  - Total return %
  - Sharpe ratio (annualized, risk-free rate from FRED)
  - Max drawdown %
  - Win rate %
  - Number of trades
  - Calmar ratio
  - Profit factor

## Output Format

After each backtest completes, print a summary:

```
---
strategy:         Congressional Copycat Momentum
total_return_pct: 18.45
sharpe_ratio:     1.23
max_drawdown_pct: -8.72
win_rate_pct:     62.5
num_trades:       24
calmar_ratio:     2.12
profit_factor:    1.87
vs_spy_pct:       +5.32
```

## Logging Results

When an experiment is done, log it to `results.tsv` (tab-separated, NOT comma-separated).

Header and columns:

```
commit	strategy_name	total_return_pct	sharpe_ratio	max_drawdown_pct	win_rate_pct	num_trades	vs_spy_pct	status	description
```

- **commit**: git commit hash (short, 7 chars)
- **strategy_name**: short name
- **total_return_pct**: e.g. 18.45
- **sharpe_ratio**: e.g. 1.23
- **max_drawdown_pct**: e.g. -8.72 (negative number)
- **win_rate_pct**: e.g. 62.5
- **num_trades**: integer
- **vs_spy_pct**: excess return vs buy-and-hold SPY (e.g. +5.32 or -3.10)
- **status**: `winner`, `mediocre`, `loser`, or `crash`
  - `winner`: beats SPY AND Sharpe > 1.0
  - `mediocre`: positive return but doesn't meet winner criteria
  - `loser`: negative return or worse than SPY by > 5%
  - `crash`: code errored out
- **description**: one-line description of the hypothesis

Example:
```
a1b2c3d	SPY Buy and Hold	13.13	0.89	-7.20	100.0	1	0.00	mediocre	baseline buy-and-hold SPY benchmark
b2c3d4e	Congressional Copycat	18.45	1.23	-8.72	62.5	24	+5.32	winner	copy congress trades with momentum filter
c3d4e5f	Full Moon Longs	-2.30	-0.15	-12.40	41.2	26	-15.43	loser	buy SPY on full moons sell on new moons
d4e5f6g	Sentiment Vix Arb	0.00	0.00	0.00	0.0	0	0.00	crash	reddit sentiment vs VIX divergence trade (API error)
```

## The Experiment Loop

The experiment runs on a dedicated branch (e.g. `run/mar21`).

**LOOP FOREVER:**

1. **Review state**: check `results.tsv` to see what's been tried, what worked, what didn't. Look at the current best strategies for inspiration.
2. **Generate a strategy**: come up with a novel, eccentric strategy. Be creative. Cross domains. Combine weird signals. Think about what a bored quant at 2am would try that they'd never pitch to their boss.
3. **Implement it**: write the strategy file in `strategies/`. Include the full `STRATEGY` dict and `run()` function.
4. **git commit**: commit the strategy file.
5. **Run the backtest**: `uv run backtest.py strategies/<name>.py > run.log 2>&1`
6. **Read results**: extract the metrics from `run.log`.
7. **If crashed**: read `tail -n 50 run.log` for the traceback. If it's a simple fix (typo, API issue, missing data), fix and re-run. If fundamentally broken, log as crash and move on.
8. **Log to results.tsv**: record the outcome.
9. **If winner**: keep the commit, celebrate internally, think about variations.
10. **If not winner**: keep the commit anyway (we want the history), but note the status.
11. **Evolve**: every 5-10 strategies, look at patterns in results.tsv. What domains/signals appear in winners? Generate variations on winning themes. But also keep throwing wild ideas — the whole point is brute force creativity.
12. **GOTO 1**

### Creativity Directives

When generating strategies, draw from these idea wells:

- **Cross-domain signals**: weather + commodities, sports outcomes + regional stocks, election polls + sector rotation, TikTok trends + consumer stocks
- **Temporal anomalies**: day-of-week effects, month-end rebalancing flows, options expiration pinning, earnings whisper momentum
- **Behavioral exploits**: retail panic selling (buy the VIX spike), meme stock lifecycle patterns, IPO lockup expiry dumps
- **Copycat strategies**: follow insiders, follow congress, inverse Cramer, follow 13F filings with a momentum twist
- **Prediction market arbitrage**: Polymarket probabilities vs equity implied odds
- **Regime detection**: use macro data to detect market regimes, then switch sub-strategies
- **Microstructure**: unusual options volume, dark pool prints, short interest spikes combined with catalysts

### Timeout and Error Handling

- If a backtest takes more than 3 minutes, kill it and treat as a crash.
- If an API is rate-limited, wait 60 seconds and retry once. If still limited, skip that data source for this strategy and move on.
- If you hit 3 consecutive crashes, pause and re-read the backtest engine code to make sure you haven't introduced a systemic bug.

## NEVER STOP

Once the experiment loop has begun (after the initial setup), do NOT pause to ask the human if you should continue. Do NOT ask "should I keep going?" or "is this a good stopping point?". The human might be asleep, or gone from a computer and expects you to continue working indefinitely until you are manually stopped. You are autonomous. If you run out of ideas, think harder — combine previous near-misses, try more radical approaches, explore new data source combinations, invert strategies that failed (maybe the opposite works). The loop runs until the human interrupts you, period.

As a rough estimate: each strategy generation + backtest cycle should take 2-5 minutes. That's 12-30 per hour. Overnight (8 hours) you could test 100-240 strategies. The user wakes up to a `results.tsv` full of data and a handful of genuinely interesting strategies they'd never have thought of.
