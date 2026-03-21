"""
Portfolio simulator for bruteforcecreativity.
This is infrastructure — the autonomous agent should NOT modify this file.

Provides a Portfolio class that strategies use to execute trades.
All slippage, accounting, and position tracking is handled here — strategies
cannot cheat on prices or skip transaction costs.

Usage in strategies:
    def run(data_fetcher, portfolio, start_date, end_date):
        portfolio.buy("AAPL", shares=10, date="2025-03-21")
        portfolio.sell("AAPL", shares=10, date="2025-03-25")
"""

from datetime import datetime
import math

import numpy as np
import pandas as pd


SLIPPAGE_PCT = 0.001  # 0.1% slippage applied to every trade


class Portfolio:
    """
    Tracks cash, positions, and trade history with enforced slippage.

    The backtest engine creates this and passes it to strategies.
    Strategies call buy()/sell(). The engine extracts metrics afterward.
    """

    def __init__(self, starting_capital: float, price_data: dict[str, pd.DataFrame]):
        """
        Args:
            starting_capital: initial cash
            price_data: dict of ticker -> DataFrame with at least 'Close' and 'Volume' columns,
                        indexed by date. Preloaded by the backtest engine.
        """
        self.starting_capital = starting_capital
        self.cash = starting_capital
        self.positions: dict[str, int] = {}  # ticker -> shares held
        self.price_data = price_data  # ticker -> OHLCV DataFrame
        self.trades: list[dict] = []  # completed round-trip trades
        self._open_trades: dict[str, list[dict]] = {}  # ticker -> list of open buy records
        self._daily_values: dict[str, float] = {}  # date_str -> portfolio value
        self._all_dates: set[str] = set()

        # Collect all trading dates from price data
        for ticker, df in price_data.items():
            for dt in df.index:
                date_str = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)[:10]
                self._all_dates.add(date_str)

    def _get_price(self, ticker: str, date: str) -> float | None:
        """Look up the close price for a ticker on a given date."""
        if ticker not in self.price_data:
            return None
        df = self.price_data[ticker]
        # Find the closest date on or before the requested date
        target = pd.Timestamp(date)
        mask = df.index <= target
        if not mask.any():
            return None
        row = df.loc[mask].iloc[-1]
        if "Close" in df.columns:
            return float(row["Close"])
        return None

    def _get_volume(self, ticker: str, date: str) -> float | None:
        """Look up the volume for a ticker on a given date."""
        if ticker not in self.price_data:
            return None
        df = self.price_data[ticker]
        target = pd.Timestamp(date)
        mask = df.index <= target
        if not mask.any():
            return None
        row = df.loc[mask].iloc[-1]
        if "Volume" in df.columns:
            return float(row["Volume"])
        return None

    def buy(self, ticker: str, shares: int = 0, dollars: float = 0, date: str = "") -> dict | None:
        """
        Buy shares of a ticker. Slippage is automatically applied.

        Args:
            ticker: stock/ETF ticker
            shares: number of shares to buy (ignored if dollars is set)
            dollars: dollar amount to buy (will compute shares, no fractional)
            date: trade date as string 'YYYY-MM-DD'

        Returns:
            Trade record dict, or None if trade couldn't execute.
        """
        if not date:
            raise ValueError("date is required for every trade")

        price = self._get_price(ticker, date)
        if price is None or price <= 0:
            return None

        # Apply slippage (buy at slightly higher price)
        exec_price = price * (1 + SLIPPAGE_PCT)

        # Compute shares from dollars if needed
        if dollars > 0:
            shares = math.floor(dollars / exec_price)
        if shares <= 0:
            return None

        cost = shares * exec_price
        if cost > self.cash:
            # Buy what we can afford
            shares = math.floor(self.cash / exec_price)
            if shares <= 0:
                return None
            cost = shares * exec_price

        # Volume check: warn but don't block (logged for metrics)
        volume = self._get_volume(ticker, date)
        volume_pct = None
        if volume and volume > 0:
            volume_pct = (shares / volume) * 100

        self.cash -= cost
        self.positions[ticker] = self.positions.get(ticker, 0) + shares

        record = {
            "date": date,
            "ticker": ticker,
            "action": "BUY",
            "shares": shares,
            "price": round(price, 4),
            "exec_price": round(exec_price, 4),
            "cost": round(cost, 2),
            "volume_pct": round(volume_pct, 2) if volume_pct else None,
        }

        # Track open position for round-trip matching
        if ticker not in self._open_trades:
            self._open_trades[ticker] = []
        self._open_trades[ticker].append(record)

        return record

    def sell(self, ticker: str, shares: int = 0, all_shares: bool = False, date: str = "") -> dict | None:
        """
        Sell shares of a ticker. Slippage is automatically applied.

        Args:
            ticker: stock/ETF ticker
            shares: number of shares to sell
            all_shares: if True, sell entire position
            date: trade date as string 'YYYY-MM-DD'

        Returns:
            Trade record dict, or None if trade couldn't execute.
        """
        if not date:
            raise ValueError("date is required for every trade")

        held = self.positions.get(ticker, 0)
        if held <= 0:
            return None

        if all_shares:
            shares = held
        if shares > held:
            shares = held
        if shares <= 0:
            return None

        price = self._get_price(ticker, date)
        if price is None or price <= 0:
            return None

        # Apply slippage (sell at slightly lower price)
        exec_price = price * (1 - SLIPPAGE_PCT)
        proceeds = shares * exec_price

        self.cash += proceeds
        self.positions[ticker] -= shares
        if self.positions[ticker] == 0:
            del self.positions[ticker]

        # Match against open trades (FIFO) to compute PnL and holding period
        pnl = 0.0
        holding_days = 0
        shares_to_match = shares

        if ticker in self._open_trades:
            while shares_to_match > 0 and self._open_trades[ticker]:
                open_trade = self._open_trades[ticker][0]
                matched = min(shares_to_match, open_trade["shares"])

                entry_cost = matched * open_trade["exec_price"]
                exit_proceeds = matched * exec_price
                pnl += exit_proceeds - entry_cost

                # Holding period in calendar days
                try:
                    entry_date = datetime.strptime(open_trade["date"], "%Y-%m-%d")
                    exit_date = datetime.strptime(date, "%Y-%m-%d")
                    holding_days = max(holding_days, (exit_date - entry_date).days)
                except (ValueError, TypeError):
                    pass

                open_trade["shares"] -= matched
                if open_trade["shares"] <= 0:
                    self._open_trades[ticker].pop(0)
                shares_to_match -= matched

        record = {
            "date": date,
            "ticker": ticker,
            "action": "SELL",
            "shares": shares,
            "price": round(price, 4),
            "exec_price": round(exec_price, 4),
            "proceeds": round(proceeds, 2),
            "pnl": round(pnl, 2),
            "holding_days": holding_days,
        }

        self.trades.append(record)
        return record

    def record_daily_value(self, date: str):
        """
        Snapshot the total portfolio value on a given date.
        Called by the backtest engine, not by strategies.
        """
        total = self.cash
        for ticker, shares in self.positions.items():
            price = self._get_price(ticker, date)
            if price:
                total += shares * price
        self._daily_values[date] = total

    def get_portfolio_values(self) -> list[tuple[str, float]]:
        """Return sorted daily portfolio values as (date, value) list."""
        return sorted(self._daily_values.items(), key=lambda x: x[0])

    def get_final_value(self) -> float:
        """Current portfolio value (cash + positions at last known price)."""
        total = self.cash
        for ticker, shares in self.positions.items():
            # Use the most recent price
            if ticker in self.price_data:
                df = self.price_data[ticker]
                if not df.empty and "Close" in df.columns:
                    total += shares * float(df["Close"].iloc[-1])
        return total

    def get_trade_stats(self) -> dict:
        """Compute trade-level statistics."""
        if not self.trades:
            return {
                "num_trades": 0,
                "win_rate_pct": 0.0,
                "avg_holding_days": 0.0,
                "max_holding_days": 0,
                "profit_factor": 0.0,
                "avg_pnl": 0.0,
            }

        wins = [t for t in self.trades if t.get("pnl", 0) > 0]
        losses = [t for t in self.trades if t.get("pnl", 0) < 0]
        holding_days = [t.get("holding_days", 0) for t in self.trades]

        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))

        return {
            "num_trades": len(self.trades),
            "win_rate_pct": round(len(wins) / len(self.trades) * 100, 1) if self.trades else 0.0,
            "avg_holding_days": round(sum(holding_days) / len(holding_days), 1) if holding_days else 0.0,
            "max_holding_days": max(holding_days) if holding_days else 0,
            "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0),
            "avg_pnl": round(sum(t.get("pnl", 0) for t in self.trades) / len(self.trades), 2),
        }

    def get_volume_warnings(self) -> list[str]:
        """Return warnings for trades that exceeded 1% of daily volume."""
        warnings = []
        for t in self._open_trades.values():
            for trade in t:
                if trade.get("volume_pct") and trade["volume_pct"] > 1.0:
                    warnings.append(
                        f"{trade['date']} {trade['ticker']}: trade was {trade['volume_pct']:.1f}% of daily volume"
                    )
        return warnings
