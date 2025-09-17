from __future__ import annotations

from typing import Dict, List, Tuple

import math
import pandas as pd
from .types import Fill


class Portfolio:
    def __init__(self, initial_cash: float):
        self.initial_cash: float = float(initial_cash)
        self.cash: float = float(initial_cash)
        self.shares: Dict[str, int] = {}
        self.market_value: float = 0.0
        self.equity: float = float(initial_cash)

    def apply_fills(self, fills: List[Fill]) -> None:
        for f in fills:
            qty = int(f.qty)
            price = float(f.fill_price)
            commission = float(f.commission)
            if f.side.upper() == "BUY":
                self.cash -= qty * price
                self.cash -= commission
                self.shares[f.symbol] = int(self.shares.get(f.symbol, 0) + qty)
            else:
                self.cash += qty * price
                self.cash -= commission
                self.shares[f.symbol] = int(self.shares.get(f.symbol, 0) - qty)
                if self.shares[f.symbol] == 0:
                    self.shares.pop(f.symbol, None)

    def mark_to_market(self, prices: Dict[str, float], dividends: Dict[str, float]) -> None:
        for symbol, qty in list(self.shares.items()):
            div = float(dividends.get(symbol, 0.0))
            if div:
                self.cash += float(qty) * div
        self.market_value = 0.0
        for symbol, qty in self.shares.items():
            pos = float(prices.get(symbol, 0.0))
            self.market_value += float(qty) * pos
        self.equity = self.cash + self.market_value

    def snapshot(self, date: pd.Timestamp) -> Dict[str, float]:
        nav = (self.equity / self.initial_cash) if self.initial_cash != 0 else 1.0
        return {
            "date": date,
            "cash": float(self.cash),
            "market_value": float(self.market_value),
            "equity": float(self.equity),
            "nav": float(nav),
            "gross_exposure": float(self.market_value),
            "net_exposure": float(self.market_value),
        }
