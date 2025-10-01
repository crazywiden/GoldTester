from typing import Dict, List, Mapping, Any

import numpy as np
import pandas as pd

from backtest.utils import annual_to_daily_rate



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

    def update(self, date: pd.Timestamp, equity: float) -> Dict:
        self.dates.append(date)
        prev_equity = -1.0
        daily_return = 0.0
        if len(self.equities) > 1:
            prev_equity = self.equities[-1]
        if prev_equity > 0:
            daily_return = float(equity) / float(prev_equity) - 1.0
        self.equities.append(float(equity))
        self.returns.append(daily_return)

        return_list = np.array(self.returns, dtype=float)
        alpha_return_arr = return_list - self.rf_daily_const
        if len(return_list) > 1:
            vol_annualized = float(np.std(return_list, ddof=1) * np.sqrt(252))
        else:
            vol_annualized = 0.0

        sharpe_itd = 0.0
        if len(alpha_return_arr) > 1:
            mean_alpha_return = np.mean(alpha_return_arr)
            std_alpha_return = np.std(alpha_return_arr, ddof=1)
            denominator = std_alpha_return if std_alpha_return != 0 else 1.0
            sharpe_itd = (mean_alpha_return / denominator) * np.sqrt(252)

        # drawdown
        equity_list = np.array(self.equities, dtype=float)
        peaks = np.maximum.accumulate(equity_list)
        drawdown_list = equity_list / np.where(peaks == 0, 1.0, peaks) - 1.0
        cur_dd = float(drawdown_list[-1]) if len(drawdown_list) else 0.0
        max_dd = float(np.min(drawdown_list)) if len(drawdown_list) else 0.0
        cumulative_return = 0.0
        if equity_list.size > 0:
            initial_equity = equity_list[0] if equity_list[0] != 0 else 1.0
            cumulative_return = float(equity_list[-1] / initial_equity - 1.0)

        return {
            "date": date,
            "daily_return": float(daily_return),
            "cumulative_return": float(cumulative_return),
            "vol_annualized": float(vol_annualized),
            "sharpe_itd": float(sharpe_itd),
            "max_drawdown": float(max_dd),
            "drawdown": float(cur_dd),
            "rf_daily": float(self.rf_daily_const),
        }
