import math
from loguru import logger
from typing import Dict, List, Optional, Any, Mapping

from backtest.backtest_types import Order


class OrderGenerator:
    def __init__(self, cfg: Mapping[str, Any]):
        self.cfg = dict(cfg)

    def weights_to_target_shares(
        self,
        weights: Dict[str, float],
        available_equity: float,
        target_prices_map: Dict[str, float],
    ) -> Dict[str, int]:
        raw_shares = {}
        notional = 0.0
        for symbol in weights:
            money_allocated = weights[symbol] * available_equity
            symbol_price = target_prices_map[symbol]
            if symbol_price == 0:
                logger.warning(f"Price for {symbol} is 0, skipping")
                raw_shares[symbol] = 0
                continue
            raw_shares[symbol] = int(math.floor(money_allocated / symbol_price))
            notional += target_prices_map[symbol] * raw_shares[symbol]

        if notional > available_equity and notional > 0:
            scale = available_equity / notional
            raw_shares = {s: int(math.floor(q * scale)) for s, q in raw_shares.items()}
        return {s: int(q) for s, q in raw_shares.items() if q > 0}

    def diff_to_orders(
        self,
        cur_shares: Dict[str, int],
        target_shares: Dict[str, int],
        target_prices: Dict[str, float],
        order_specs: Optional[Dict[str, Dict[str, Any]]] = None,
        portfolio=None,
    ) -> List[Order]:
        orders: List[Order] = []
        if order_specs is None:
            order_specs = {}
        
        # get union of the current symbols and the target symbols
        all_symbols = set(cur_shares.keys()) | set(target_shares.keys())
        for symbol in sorted(all_symbols):
            current = int(cur_shares.get(symbol, 0))
            target = int(target_shares.get(symbol, 0))
            delta = target - current
            if delta == 0:
                continue
            side = "BUY" if delta > 0 else "SELL"
            qty = abs(delta)
            ref_price = float(target_prices[symbol])
            
            # Get order specifications for this symbol
            symbol_spec = order_specs.get(symbol, {})
            order_type = symbol_spec.get("order_type", "MARKET")
            limit_price = symbol_spec.get("limit_price", None)

            # Calculate base price
            base_price = None
            if side == "BUY":
                # For BUY orders, base_price will be set to fill_price during execution
                base_price = None
            elif side == "SELL" and portfolio is not None:
                # For SELL orders, calculate the average cost of shares being sold (FIFO)
                base_price = portfolio.get_sell_cost_basis(symbol, qty)

            orders.append(Order(
                date=None,
                symbol=symbol,
                side=side,
                qty=qty,
                ref_price=ref_price,
                order_type=order_type,
                limit_price=limit_price,
                base_price=base_price,
            ))
        return orders
