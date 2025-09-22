from typing import Dict, List, Tuple, Any

import math
import pandas as pd
from backtest.backtest_types import Fill


class Portfolio:
    def __init__(self, initial_cash: float):
        self.initial_cash: float = float(initial_cash)
        self.cash: float = float(initial_cash)
        # symbol -> list of lots; each lot is {"date": pd.Timestamp, "qty": int, "fill_price": float}
        self.shares: Dict[str, List[Dict[str, Any]]] = {}
        self.market_value: float = 0.0
        self.equity: float = float(initial_cash)

    def apply_fills(self, fills: List[Fill]) -> None:
        for f in fills:
            qty = int(f.qty)
            price = float(f.fill_price)
            commission = float(f.commission)
            symbol = f.symbol
            side = f.side.upper()
            if side == "BUY":
                # Pay cash and add a new lot
                self.cash -= qty * price
                self.cash -= commission
                lots = self.shares.setdefault(symbol, [])
                lots.append({
                    "date": f.date,
                    "qty": int(qty),
                    "fill_price": float(price),
                })
            else:
                # Receive cash and reduce existing lots FIFO
                self.cash += qty * price
                self.cash -= commission
                lots = self.shares.get(symbol, [])
                remaining = qty
                new_lots: List[Dict[str, Any]] = []
                for lot in lots:
                    if remaining <= 0:
                        new_lots.append(lot)
                        continue
                    lot_qty = int(lot["qty"])
                    if lot_qty <= remaining:
                        # consume entire lot
                        remaining -= lot_qty
                        continue
                    else:
                        # partially reduce this lot
                        lot_copy = dict(lot)
                        lot_copy["qty"] = int(lot_qty - remaining)
                        remaining = 0
                        new_lots.append(lot_copy)
                if new_lots:
                    self.shares[symbol] = new_lots
                else:
                    # remove symbol if no lots left
                    self.shares.pop(symbol, None)

    def mark_to_market(self, prices: Dict[str, float], dividends: Dict[str, float]) -> None:
        # credit dividends
        for symbol, lots in list(self.shares.items()):
            total_qty = sum(int(lot["qty"]) for lot in lots)
            div = float(dividends.get(symbol, 0.0))
            if div and total_qty:
                self.cash += float(total_qty) * div
        self.market_value = 0.0
        for symbol, lots in self.shares.items():
            pos = float(prices.get(symbol, 0.0))
            total_qty = sum(int(lot["qty"]) for lot in lots)
            self.market_value += float(total_qty) * pos
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

    def get_total_shares(self, symbol: str) -> int:
        lots = self.shares.get(symbol, [])
        return int(sum(int(lot["qty"]) for lot in lots))

    def get_total_shares_map(self) -> Dict[str, int]:
        return {symbol: self.get_total_shares(symbol) for symbol in self.shares.keys()}

    def get_average_cost(self, symbol: str) -> float:
        lots = self.shares.get(symbol, [])
        total_qty = sum(int(lot["qty"]) for lot in lots)
        if total_qty <= 0:
            return 0.0
        total_cost = 0.0
        for lot in lots:
            qty = int(lot["qty"])
            price = float(lot["fill_price"])
            total_cost += qty * price
        return float(total_cost) / float(total_qty)

    def get_average_cost_map(self) -> Dict[str, float]:
        return {symbol: self.get_average_cost(symbol) for symbol in self.shares.keys()}
