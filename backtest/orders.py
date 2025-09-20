from typing import Dict, List, Optional, Any, Mapping

import math

from backtest.types import Order


class OrderGenerator:
    def __init__(self, cfg: Mapping[str, Any]):
        self.cfg = dict(cfg)

    def weights_to_target_shares(
        self,
        weights: Dict[str, float],
        available_equity: float,
        price_map: Dict[str, float],
    ) -> Dict[str, int]:
        raw_shares = {}
        notional = 0.0
        for symbol in weights:
            money_allocated = weights[symbol] * available_equity
            symbol_price = price_map[symbol]
            if symbol_price == 0:
                raw_shares[symbol] = 0
                continue
            raw_shares[symbol] = int(math.floor(money_allocated / symbol_price))
            notional += price_map[symbol] * raw_shares[symbol]

        if notional > available_equity and notional > 0:
            scale = available_equity / notional
            raw_shares = {s: int(math.floor(q * scale)) for s, q in raw_shares.items()}
        return {s: int(q) for s, q in raw_shares.items() if q > 0}

    def diff_to_orders(
        self,
        cur_shares: Dict[str, int],
        target_shares: Dict[str, int],
        ref_prices: Dict[str, float],
        order_specs: Optional[Dict[str, Dict[str, Any]]] = None,
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
            ref_price = float(ref_prices[symbol])
            
            # Get order specifications for this symbol
            symbol_spec = order_specs.get(symbol, {})
            order_type = symbol_spec.get("order_type", "MARKET")
            limit_price = symbol_spec.get("limit_price", None)
            
            orders.append(Order(
                date=None,
                symbol=symbol,
                side=side,
                qty=qty,
                ref_price=ref_price,
                order_type=order_type,
                limit_price=limit_price,
            ))
        return orders
