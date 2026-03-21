# bruteforcecreativity

An autonomous AI loop that generates eccentric investment strategies, backtests them against real market data, and surfaces the ones that actually work.

## The Idea

Every obvious strategy is already being run by firms with billions in capital. But they literally cannot play small. A $50B fund cannot deploy a strategy that only works at $10K-$100K scale.

This project brute-forces creativity: an AI agent generates hundreds of weird, niche, cross-domain trading strategies, backtests each one against 12 months of real data, and logs the results. You go to sleep, it runs all night, you wake up to a spreadsheet of strategies ranked by performance — with a handful of genuinely interesting ones you'd never have thought of.

**These are fast trades** — in and out in 1-10 days. Not buy-and-hold. Many small, quick, repeatable bets.

## How It Works

1. AI reads `CLAUDE.md` (the instruction set)
2. Generates a novel strategy with a specific hypothesis
3. Implements it as a Python file using the `Portfolio` class
4. Backtests it against real market data (yfinance, FRED, Google Trends, congressional trades, etc.)
5. Logs results to `results.tsv` with full metrics
6. Repeats forever until manually stopped

Winner criteria: beats SPY, Sharpe > 1.0, 8+ trades, avg holding <= 15 days, positive out-of-sample PnL.

## Project Structure

```
CLAUDE.md          # Agent instruction set (the brain)
backtest.py        # Backtesting engine (enforces slippage, computes metrics)
portfolio.py       # Portfolio class (strategies trade through this)
fetch_data.py      # Data fetching with caching (yfinance, FRED, etc.)
strategies/        # Generated strategy files (one per experiment)
results.tsv        # Experiment log (untracked)
```

## Setup

```bash
# Install dependencies
uv sync

# Populate data cache
uv run fetch_data.py --refresh

# Copy and fill in optional API keys
cp .env.example .env
```

Then start a Claude Code session in this directory. The agent will pick up `CLAUDE.md` and begin.

## Inspired By

[karpathy/autoresearch](https://github.com/karpathy/autoresearch) — same autonomous loop concept, applied to ML training rather than investment strategies.
