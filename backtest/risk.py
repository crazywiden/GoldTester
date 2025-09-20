from typing import Dict, Any, Mapping, Optional

import pandas as pd
from loguru import logger

from backtest.accounting import Portfolio


def _get_risk_cfg(cfg: Mapping[str, Any]) -> Dict[str, Any]:
    risk = dict(cfg.get("risk", {}))
    # defaults
    risk.setdefault("enabled", False)
    risk.setdefault("stop_loss", None)  # e.g., 0.05 for 5%
    risk.setdefault("take_profit", None)  # e.g., 0.1 for 10%
    risk.setdefault("action", "LIQUIDATE")  # LIQUIDATE | REDUCE | NONE
    risk.setdefault("reduce_fraction", 1.0)
    risk.setdefault("use_intraday_extremes", True)
    return risk


def evaluate_stop_levels(
    date: pd.Timestamp,
    cfg: Mapping[str, Any],
    portfolio: Portfolio,
    prices_today: Dict[str, float],
    intraday_high: Optional[Dict[str, float]] = None,
    intraday_low: Optional[Dict[str, float]] = None,
) -> Dict[str, int]:
    """
    Returns target shares map after applying stop-loss and take-profit rules.

    Inputs:
    - prices_today: valuation prices used for marking (e.g., close)
    - intraday_high/low: optional extremes for the same date for more conservative triggers

    Behavior:
    - For each held symbol, compute return from average cost to trigger price.
    - If return <= -stop_loss -> action
    - If return >= take_profit -> action
    Action either liquidates (target 0) or reduces by reduce_fraction.
    """
    risk = _get_risk_cfg(cfg)
    if not bool(risk.get("enabled", False)):
        return portfolio.get_total_shares_map()

    stop_loss = risk.get("stop_loss")
    take_profit = risk.get("take_profit")
    action = str(risk.get("action", "LIQUIDATE")).upper()
    reduce_fraction = float(risk.get("reduce_fraction", 1.0))
    use_extremes = bool(risk.get("use_intraday_extremes", True))

    current_shares = portfolio.get_total_shares_map()
    avg_costs = portfolio.get_average_cost_map()
    target_after_risk: Dict[str, int] = dict(current_shares)

    for symbol, qty in current_shares.items():
        if qty == 0:
            continue
        avg_cost = float(avg_costs.get(symbol, 0.0))
        if avg_cost <= 0.0:
            continue

        price_for_check = float(prices_today.get(symbol, 0.0))
        if use_extremes and intraday_high is not None and intraday_low is not None:
            # For long positions, we consider worst-case for SL (low) and best-case for TP (high)
            # This is a conservative approach to detect if a trigger would have occurred intraday.
            if qty > 0:
                low = float(intraday_low.get(symbol, price_for_check))
                high = float(intraday_high.get(symbol, price_for_check))
                sl_check_price = low
                tp_check_price = high
            else:
                # For short positions, invert logic (not currently used if allow_short=false)
                high = float(intraday_high.get(symbol, price_for_check))
                low = float(intraday_low.get(symbol, price_for_check))
                sl_check_price = high  # adverse move up
                tp_check_price = low   # favorable move down
        else:
            sl_check_price = price_for_check
            tp_check_price = price_for_check

        ret_sl = (sl_check_price / avg_cost) - 1.0 if avg_cost != 0 else 0.0
        ret_tp = (tp_check_price / avg_cost) - 1.0 if avg_cost != 0 else 0.0

        triggered = False
        if stop_loss is not None and ret_sl <= -float(stop_loss):
            triggered = True
            reason = f"STOP_LOSS {ret_sl:.4f} <= {-float(stop_loss):.4f}"
        elif take_profit is not None and ret_tp >= float(take_profit):
            triggered = True
            reason = f"TAKE_PROFIT {ret_tp:.4f} >= {float(take_profit):.4f}"
        else:
            reason = None

        if triggered:
            if action == "LIQUIDATE":
                target_after_risk[symbol] = 0
            elif action == "REDUCE":
                new_qty = int(round(qty * max(0.0, 1.0 - reduce_fraction)))
                target_after_risk[symbol] = max(0, new_qty)
            elif action == "NONE":
                pass
            else:
                logger.error(f"Unknown risk action: {action}, defaulting to LIQUIDATE")
                target_after_risk[symbol] = 0
            if reason:
                logger.info(f"Risk trigger on {date.date()} {symbol}: {reason}; action={action}")

    return target_after_risk


