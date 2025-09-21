from typing import Dict, Tuple, Any, Optional, List

import pandas as pd
from loguru import logger
from backtest.accounting import Portfolio

"""Every time, we will all in one stock. The decision will do the following:

every day after the market close,
step 1: check if we are holding any stock
    if yes, check if we already hold this stock for T days
        if yes, sell it at the high price of the next day. End.
        if no. place one limit order target for 2% returns
    if no, go to step 2

step 2: rank all the stocks on the market by the return of today.
    return_of_today = (close_price - close_price_of_yesterday) / close_price_of_yesterday
    find all the stocks with return_of_today <= R
    
step 3: for stocks after step 2, do the following filter:
    filter 1: the stock should be within a predefined list: S
    filter 2: the stock should have market cap >= M

step 4: for stocks after step 3, pick the stock with the highest return with in past D days
step 5: all in that stock, and place order with next day open price
"""

# Optional whitelist. If empty, do not filter by list.
TICKER_LIST: set[str] = set()


HOLD_DAYS_T: int = 5
TAKE_PROFIT_PCT: float = 0.02
RETURN_THRESHOLD_R: float = -0.1 
D_LOOKBACK_DAYS: int = 20


def get_days_held(
    portfolio: Portfolio,
    symbol: str,
    today_date: pd.Timestamp,
) -> int:
    """Estimate holding days from the earliest lot date."""
    symbol_info = portfolio.shares[symbol]
    first_date = symbol_info["date"]
    delta = pd.Timestamp(today_date).normalize() - pd.Timestamp(first_date).normalize()
    return int(max(0, delta.days))


def get_return_in_n_days(
    df_today: pd.DataFrame,
    df_prev: pd.DataFrame,
    n_days: int,
) -> pd.DataFrame:
    date_n_days_ago = df_today["date"].iloc[0] - pd.Timedelta(days=n_days)
    df_n_days_ago = df_prev[df_prev["date"] == date_n_days_ago]

    if df_n_days_ago is None or df_n_days_ago.empty:
        logger.warning(f"No data for {date_n_days_ago}")
        return pd.DataFrame()

    today_close = (
        df_today[["symbol", "close"]]
        .dropna(subset=["symbol", "close"])
        .groupby("symbol")["close"]
        .first()
    )
    if df_n_days_ago is None or df_n_days_ago.empty:
        logger.warning(f"No data for {date_n_days_ago}")
        return pd.DataFrame({"symbol": today_close.index, "ret_today": float("nan")}).set_index("symbol")
    prev_close = (
        df_n_days_ago
        .dropna(subset=["symbol", "close"])
        .groupby("symbol")["close"]
        .last()
    )
    joined = today_close.to_frame("close").join(prev_close.to_frame("prev_close"), how="left")
    joined["return"] = (joined["close"] / joined["prev_close"]) - 1.0
    return joined[["return"]]

def compute_target_weights(
    date,
    df_today: pd.DataFrame,
    df_prev: pd.DataFrame,
    portfolio: Portfolio,
) -> Tuple[Dict[str, float], Dict[str, Dict[str, Any]]]:
    if df_today is None or df_today.empty:
        return {}, {}

    if df_prev is None or df_prev.empty:
        return {}, {}

    shares_map = portfolio.get_total_shares_map()
    if len(shares_map) > 1:
        # we should always only hold one stock at max
        error_msg = f"More than one stock held. current holdings: {shares_map}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # if we are holding one stock, get the symbol
    if len(shares_map) == 1:
        current_symbol = list(shares_map.keys())[0]

        days_held = get_days_held(portfolio, current_symbol, date)


        if days_held >= HOLD_DAYS_T:  # we've held for too long
            weights: Dict[str, float] = {current_symbol: 0.0}
            order_specs: Dict[str, Dict[str, Any]] = {current_symbol: {"order_type": "MARKET"}}
            return weights, order_specs

        avg_cost = float(portfolio.get_average_cost(current_symbol))
        if avg_cost <= 0.0:
            weights = {}
            order_specs = {current_symbol: {"order_type": "MARKET"}}
            return weights, order_specs
        limit_price = avg_cost * (1.0 + float(TAKE_PROFIT_PCT))
        weights = {}
        order_specs = {
            current_symbol: {
                "order_type": "LIMIT",
                "limit_price": float(limit_price),
            }
        }
        return weights, order_specs

    # if we don't hold any stock, go find one stock that has trading opportunity
    ret_today = get_return_in_n_days(df_today, df_prev, 1)
    if ret_today.empty:
        logger.warning(f"No stocks with return at {date}")
        return {}, {}

    candidates = ret_today[ret_today["return"] <= float(RETURN_THRESHOLD_R)].copy()
    if candidates.empty:
        logger.warning(f"No stocks with return <= {RETURN_THRESHOLD_R} at {date}")
        return {}, {}

    candidates = candidates[candidates.index.isin(TICKER_LIST)]
    if candidates.empty:
        logger.warning(f"No stocks in the whitelist at {date}")
        return {}, {}

    candidate_symbols = candidates.index
    candidate_df_today = df_today[df_today["symbol"].isin(candidate_symbols)]
    candidate_df_prev = df_prev[df_prev["symbol"].isin(candidate_symbols)]
    candidate_return_df = get_return_in_n_days(
        candidate_df_today,
        candidate_df_prev,
        D_LOOKBACK_DAYS,
    )
    if candidate_return_df.empty:
        logger.warning(f"we don't have enought data for {date}")
        return {}, {}
    joined = candidate_return_df.sort_values(
        ["return"], ascending=False
    )
    chosen_symbol = joined.index[0]

    weights = {chosen_symbol: 1.0}
    order_specs = {chosen_symbol: {"order_type": "MARKET"}}
    return weights, order_specs
