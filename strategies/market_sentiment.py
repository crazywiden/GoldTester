from typing import Dict
import pandas as pd
from backtest.accounting import Portfolio


def compute_target_weights(
    date,
    df_today: pd.DataFrame,
    df_prev: pd.DataFrame,
    portfolio: Portfolio,
) -> Dict[str, float]:
    """
    The strategy is as follows:
    1. Filter for liquid stocks by removing stocks with no volume data and then
        selecting only those with volume above the median for the given day.
    2. Select the first 50 stocks from the liquid universe.
    3. Construct an equal-weighted portfolio from the selected stocks.
    """
    if df_today is None or df_today.empty:
        return {}
    liquid = df_today.dropna(subset=["volume"]).copy()
    median_vol = float(liquid["volume"].quantile(0.5)) if not liquid.empty else 0.0
    liquid = liquid[liquid["volume"] > median_vol]
    picks = liquid.head(50)
    if len(picks) == 0:
        return {}
    w = 1.0 / float(len(picks))
    return {sym: w for sym in picks["symbol"].tolist()}
