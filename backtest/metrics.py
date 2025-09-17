from __future__ import annotations

from typing import Dict, List, Mapping, Any

import numpy as np
import pandas as pd

from .utils import annual_to_daily_rate



class MetricsEngine:
    def __init__(self, cfg: Mapping[str, Any]):
        self.cfg = dict(cfg)
        self.dates: List[pd.Timestamp] = []
        self.equities: List[float] = []
        self.returns: List[float] = []
        mode = self.cfg.get("accounting", {}).get("risk_free_rate", {}).get("mode", "constant")
        if mode == "constant":
            const = self.cfg.get("accounting", {}).get("risk_free_rate", {}).get("constant_annual", 0.0)
            self.rf_daily_const = float(annual_to_daily_rate(float(const)))
        else:
            self.rf_daily_const = 0.0

    def update(self, date: pd.Timestamp, equity: float, prev_equity: float) -> Dict:
        self.dates.append(date)
        self.equities.append(float(equity))
        if prev_equity and prev_equity != 0:
            r = float(equity) / float(prev_equity) - 1.0
        else:
            r = 0.0
        self.returns.append(r)
        r_list = np.array(self.returns, dtype=float)
        alpha_return_arr = r_list - self.rf_daily_const
        vol_annualized = float(np.std(r_list, ddof=1) * np.sqrt(252)) if len(r_list) > 1 else 0.0

        sharpe_itd = 0.0
        if len(alpha_return_arr) > 1:
            mean_alpha_return = np.mean(alpha_return_arr)
            std_alpha_return = np.std(alpha_return_arr, ddof=1)
            denominator = std_alpha_return if std_alpha_return != 0 else 1.0
            sharpe_itd = (mean_alpha_return / denominator) * np.sqrt(252)

        window = 30
        sharpe_30d = 0.0
        if len(alpha_return_arr) >= 2:
            last = alpha_return_arr[-window:]
            if len(last) > 1:
                mean_last = np.mean(last)
                std_last = np.std(last, ddof=1)
                denominator = std_last if std_last != 0 else 1.0
                sharpe_30d = (mean_last / denominator) * np.sqrt(252)
        # drawdown
        equity_list = np.array(self.equities, dtype=float)
        peaks = np.maximum.accumulate(equity_list)
        dd = equity_list / np.where(peaks == 0, 1.0, peaks) - 1.0
        cur_dd = float(dd[-1]) if len(dd) else 0.0
        max_dd = float(np.min(dd)) if len(dd) else 0.0
        cumulative_return = 0.0
        if equity_list.size > 0:
            initial_equity = equity_list[0] if equity_list[0] != 0 else 1.0
            cumulative_return = float(equity_list[-1] / initial_equity - 1.0)

        return {
            "date": date,
            "daily_return": float(r),
            "cumulative_return": float(cumulative_return),
            "vol_annualized": float(vol_annualized),
            "sharpe_itd": float(sharpe_itd),
            "sharpe_30d": float(sharpe_30d),
            "max_drawdown": float(max_dd),
            "drawdown": float(cur_dd),
            "rf_daily": float(self.rf_daily_const),
        }
