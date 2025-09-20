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
        cm = self.cfg["execution"].get("commission_model", {})
        per_share = float(cm.get("per_share", 0.0))
        min_fee = float(cm.get("min_per_order", 0.0))
        fee = per_share * float(qty)
        return float(max(fee, min_fee))

    def _apply_slippage(
        self,
        side_sign: int,
        ref_price: float,
        qty: int,
        extra_volume: float,
    ) -> float:
        """returns the diff in price between the reference price and the fill price
        """
        slip_cfg = self.cfg["execution"].get("slippage_model", {})
        slip_type = slip_cfg.get("type", "bps_per_turnover")
        if slip_type == "bps_per_turnover":
            bps = float(slip_cfg.get("bps_per_1x_turnover", 0.0))
            return side_sign * (bps / 10_000.0) * ref_price
        elif slip_type == "square_root_impact":
            k = float(slip_cfg.get("k", 0.0))
            if extra_volume <= 0:
                logger.error(f"volume larger than Average Volume are 0, using 0.0 as slippage")
                return 0.0
            impact = k * ref_price * math.sqrt(float(qty) / float(extra_volume))
            return side_sign * impact
        logger.error(f"Invalid slippage model: {slip_type}, using 0.0 as slippage")
        return 0.0

    def _base_fill_price(self, date: pd.Timestamp, symbol: str) -> float:
        bar = self.data_loader.get_bar(date, symbol)
        if bar is None:
            logger.error(f"Bar not found for date: {date}, symbol: {symbol}, using NaN as base fill price")
            return float("nan")
        method = self.cfg["execution"].get("order_fill_method", "next_close")
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
            if symbol in halted_symbols:
                logger.error(f"Symbol {symbol} is halted, skipping execution for date: {date}")
                continue
            bar_today = self.data_loader.get_bar(date, symbol)
            if bar_today is None:
                logger.error(f"Bar not found for date: {date}, symbol: {symbol}, skipping execution")
                continue

            adv_lookback = int(self.cfg["execution"].get("slippage_model", {}).get("daily_adv_lookback", 20))
            average_volume = self.data_loader.get_adv(symbol, date, lookback=adv_lookback)
            qty = order.qty
            if qty <= 0:
                logger.error(f"Quantity is 0, skipping execution for date: {date}, symbol: {symbol}")
                continue
            # Handle limit vs market orders
            if order.order_type == "LIMIT" and order.limit_price is not None:
                # Check if limit order can be filled within [low, high] range
                high = float(bar_today.get("high", float("nan")))
                low = float(bar_today.get("low", float("nan")))
                
                if high == float("nan") or low == float("nan"):
                    logger.error(f"High/Low prices are NaN for date: {date}, symbol: {symbol}, skipping limit order")
                    continue
                
                can_fill = False
                if order.side.upper() == "BUY":
                    # Buy limit order: can fill if limit_price >= low
                    can_fill = order.limit_price >= low
                else:
                    # Sell limit order: can fill if limit_price <= high  
                    can_fill = order.limit_price <= high
                
                if not can_fill:
                    logger.info(f"Limit order cannot be filled: {order.side} {symbol} at {order.limit_price}, range [{low}, {high}]")
                    continue
                
                # Use limit price as fill price for limit orders
                fill_price = order.limit_price
                commission = self._commission(qty)
                fill = Fill(
                    order_id=f"ord_{str(date.date())}_{symbol}_{idx}",
                    date=date,
                    symbol=symbol,
                    side=order.side,
                    qty=qty,
                    ref_price=float(order.ref_price),
                    fill_price=float(fill_price),
                    slippage=0.0,  # No slippage for limit orders
                    commission=float(commission),
                    order_type="LIMIT",
                )
                fills.append(fill)
            else:
                # Market order - existing logic
                base_price = self._base_fill_price(date, symbol)
                if base_price == float("nan"):
                    logger.error(f"Base fill price is NaN, skipping execution for date: {date}, symbol: {symbol}")
                    continue
                side_sign = 1 if order.side.upper() == "BUY" else -1
                slip = self._apply_slippage(
                    side_sign, order.ref_price, qty, qty - average_volume,
                )
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
                    order_type="MARKET",
                )
                fills.append(fill)
        return fills
