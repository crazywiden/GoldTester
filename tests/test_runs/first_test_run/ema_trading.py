import pandas as pd


def compute_target_weights(date, df_today: pd.DataFrame):
    """
    The strategy is as follows:
    1.  Filter for liquid stocks by removing stocks with no volume data and then
        selecting only those with volume above the median for the given day.
    2.  If 'EPS' (Earnings Per Share) data is available, rank the liquid stocks
        by EPS in descending order and select the top 50.
    3.  If 'EPS' data is not available, select the first 50 stocks from the liquid
        universe.
    4.  Construct an equal-weighted portfolio from the selected stocks.
    """
    if df_today is None or df_today.empty:
        return {}
    liquid = df_today.dropna(subset=["volume"]).copy()
    median_vol = float(liquid["volume"].quantile(0.5)) if not liquid.empty else 0.0
    liquid = liquid[liquid["volume"] > median_vol]
    if "EPS" in liquid.columns:
        liquid = liquid.assign(rank=liquid["EPS"].rank(ascending=False))
        picks = liquid.nsmallest(50, "rank")
    else:
        picks = liquid.head(50)
    if len(picks) == 0:
        return {}
    w = 1.0 / float(len(picks))
    return {sym: w for sym in picks["symbol"].tolist()}
