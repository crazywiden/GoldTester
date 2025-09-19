from typing import Dict, List

import math

from backtest.types import Order
from typing import Mapping, Any


class OrderGenerator:
	def __init__(self, cfg: Mapping[str, Any]):
		self.cfg = dict(cfg)

	def _apply_constraints(self, weights: Dict[str, float]) -> Dict[str, float]:
		max_w = float(self.cfg.get("signals", {}).get("constraints", {}).get("max_weight_per_symbol", 1.0))
		rounded_step = float(self.cfg.get("signals", {}).get("constraints", {}).get("target_weight_rounding", 0.0))
		capped = {s: min(max(v, 0.0), max_w) for s, v in weights.items()}
		total = sum(capped.values())
		if total > 1.0:
			capped = {s: v / total for s, v in capped.items()}
		if rounded_step > 0:
			capped = {s: round(v / rounded_step) * rounded_step for s, v in capped.items()}
		return capped

	def weights_to_target_shares(
        self,
        weights: Dict[str, float],
        equity: float,
        price_map: Dict[str, float],
    ) -> Dict[str, int]:
		weights = self._apply_constraints(weights)
		raw_shares = {s: int(math.floor((weights.get(s, 0.0) * equity) / max(price_map.get(s, 1.0), 1e-9))) for s in weights}
		notional = sum(price_map.get(s, 0.0) * q for s, q in raw_shares.items())
		if notional > equity and notional > 0:
			scale = equity / notional
			raw_shares = {s: int(math.floor(q * scale)) for s, q in raw_shares.items()}
		return {s: int(q) for s, q in raw_shares.items() if q > 0}

	def diff_to_orders(self, cur_shares: Dict[str, int], target_shares: Dict[str, int], ref_prices: Dict[str, float]) -> List[Order]:
		orders: List[Order] = []
		all_symbols = set(cur_shares.keys()) | set(target_shares.keys())
		for symbol in sorted(all_symbols):
			current = int(cur_shares.get(symbol, 0))
			target = int(target_shares.get(symbol, 0))
			delta = target - current
			if delta == 0:
				continue
			side = "BUY" if delta > 0 else "SELL"
			qty = abs(delta)
			ref_price = float(ref_prices.get(symbol, 0.0))
			orders.append(Order(date=None, symbol=symbol, side=side, qty=qty, ref_price=ref_price))
		return orders
