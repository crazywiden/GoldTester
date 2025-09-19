from typing import List, Mapping, Any

import math
import pandas as pd
from loguru import logger

from backtest.types import Order, Fill
from backtest.utils import typical_price
from backtest.data_loader import DataLoader


class ExecutionSimulator:
    def __init__(self, cfg: Mapping[str, Any], data_loader: DataLoader):
        self.cfg = dict(cfg)
        self.data_loader = data_loader

    def _commission(self, qty: int) -> float:
        cm = self.cfg.get("execution", {}).get("commission_model", {})
        per_share = float(cm.get("per_share", 0.0))
        min_fee = float(cm.get("min_per_order", 0.0))
        fee = per_share * float(qty)
        return float(max(fee, min_fee))

    def _apply_slippage(self, side_sign: int, ref_price: float, qty: int, adv_shares: float) -> float:
        slip_cfg = self.cfg.get("execution", {}).get("slippage_model", {})
        slip_type = slip_cfg.get("type", "bps_per_turnover")
        if slip_type == "bps_per_turnover":
            bps = float(slip_cfg.get("bps_per_1x_turnover", 0.0))
            return side_sign * (bps / 10_000.0) * ref_price
        elif slip_type == "square_root_impact":
            k = float(slip_cfg.get("k", 0.0))
            if adv_shares <= 0:
                logger.error(f"ADV shares are 0, using 0.0 as slippage")
                return 0.0
            impact = k * ref_price * math.sqrt(float(qty) / float(adv_shares))
            return side_sign * impact
        logger.error(f"Invalid slippage model: {slip_type}, using 0.0 as slippage")
        return 0.0

    def _base_fill_price(self, date: pd.Timestamp, symbol: str) -> float:
        bar = self.data_loader.get_bar(date, symbol)
        if bar is None:
            logger.error(f"Bar not found for date: {date}, symbol: {symbol}, using NaN as base fill price")
            return float("nan")
        method = self.cfg.get("execution", {}).get("order_fill_method", "next_close")
        if method == "next_open":
            return float(bar.get("open", float("nan")))
        if method == "next_close":
            return float(bar.get("close", float("nan")))
        if method == "vwap_proxy":
            return float(typical_price(bar.get("high", float("nan")), bar.get("low", float("nan")), bar.get("close", float("nan"))))
        return float(bar.get("close", float("nan")))

    def fill_orders(self, date: pd.Timestamp, orders: List[Order]) -> List[Fill]:
        if not orders:
            return []
        # Halts for date
        halts = self.data_loader.halts
        halted_symbols = set()
        try:
            day_halts = halts.loc[(date,), :]
            if not day_halts.empty:
                halted_symbols = set(day_halts[day_halts["is_halted"] == True]["symbol"].tolist())
        except KeyError:
            pass
        fills = []
        for idx, order in enumerate(orders):
            symbol = order.symbol
            if symbol in halted_symbols and bool(self.cfg.get("execution", {}).get("skip_if_halted", True)):
                logger.error(f"Symbol {symbol} is halted, skipping execution for date: {date}")
                continue
            bar_today = self.data_loader.get_bar(date, symbol)
            if bar_today is None:
                logger.error(f"Bar not found for date: {date}, symbol: {symbol}, skipping execution")
                continue
            last_tradable = bar_today.get("delisting_date")
            if pd.notna(last_tradable) and date > last_tradable and bool(self.cfg.get("execution", {}).get("respect_delisting", True)):
                logger.error(f"Symbol {symbol} is delisted, skipping execution for date: {date}")
                continue
            # ADV / participation cap
            adv_lookback = int(self.cfg.get("execution", {}).get("slippage_model", {}).get("daily_adv_lookback", 20))
            adv_shares = self.data_loader.get_adv(symbol, date, lookback=adv_lookback)
            cap = float(self.cfg.get("execution", {}).get("max_participation_adv", 1.0))
            max_qty = int(math.floor(cap * adv_shares)) if adv_shares > 0 else order.qty
            if bool(self.cfg.get("execution", {}).get("allow_partial_fills", False)):
                # by default, we don't allow partial fills
                qty = min(order.qty, max_qty)
            else:
                if order.qty <= max_qty:
                    qty = order.qty
                else:
                    qty = 0
            if qty <= 0:
                logger.error(f"Quantity is 0, skipping execution for date: {date}, symbol: {symbol}")
                continue
            # Determine base fill price
            base_price = self._base_fill_price(date, symbol)
            if base_price == float("nan"):
                logger.error(f"Base fill price is NaN, skipping execution for date: {date}, symbol: {symbol}")
                continue
            side_sign = 1 if order.side.upper() == "BUY" else -1
            slip = self._apply_slippage(side_sign, order.ref_price, qty, adv_shares)
            fill_price = base_price + slip
            commission = self._commission(qty)
            fill = Fill(
                order_id=f"ord_{str(date.date())}_{symbol}_{idx}",
                date=date,
                symbol=symbol,
                side=order.side,
                qty=qty,
                ref_price=float(order.ref_price),
                fill_price=float(fill_price),
                slippage=float(slip * qty),
                commission=float(commission),
            )
            fills.append(fill)
        return fills
