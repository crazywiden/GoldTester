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
RETURN_THRESHOLD_R: float = -0.05 
D_LOOKBACK_DAYS: int = 20

DROP_THRESHOLD_PCT: float = 5
TARGET_RECOVERY_PCT: float = 2
VOLUME_LOOKBACK_DAYS: int = 365  # 1 year for average volume calculation
MIN_VOLUME_PAST_N_DAYS: int = 2_000_000
RANKER_COLUMNS: List[str] = ["recovery_rate_pct", "one_day_recovery_rate_pct", "return", ]
RANKER_DIRECTIONS: List[bool] = [False, False, True, ] # True: choose lower, False: choose higher

def get_days_held(
    portfolio: Portfolio,
    symbol: str,
    today_date: pd.Timestamp,
) -> int:
    """Estimate holding days from the earliest lot date."""
    lots = portfolio.shares[symbol]
    if not lots:
        return 0
    # Get the earliest date from all lots
    first_date = min(lot["date"] for lot in lots)
    delta = pd.Timestamp(today_date).normalize() - pd.Timestamp(first_date).normalize()
    return int(max(0, delta.days))


def get_return_in_n_days(
    df_today: pd.DataFrame,
    df_prev: pd.DataFrame,
    n_days: int,
) -> pd.DataFrame:
    if df_today.empty:
        return pd.DataFrame(columns=["return"])
    date_n_days_ago = df_today["date"] - pd.Timedelta(days=n_days)
    # Handle timezone mismatch: compare date parts only
    # Get the first date from the series for comparison
    target_date = date_n_days_ago.iloc[0].date()
    df_n_days_ago = df_prev[df_prev["date"].dt.date == target_date]
    today_close = (
        df_today[["symbol", "close"]]
        .dropna(subset=["symbol", "close"])
        .groupby("symbol")["close"]
        .first()
    )
    if df_n_days_ago is None or df_n_days_ago.empty:
        return pd.DataFrame({"return": float("nan")}, index=today_close.index)
    prev_close = (
        df_n_days_ago
        .dropna(subset=["symbol", "close"])
        .groupby("symbol")["close"]
        .last()
    )
    joined = today_close.to_frame("close").join(prev_close.to_frame("prev_close"), how="left")
    joined["return"] = (joined["close"] / joined["prev_close"]) - 1.0
    return joined[["return"]]


def get_avg_volume_past_n_days(df_today: pd.DataFrame, df_prev: pd.DataFrame, n_days: int):
    '''
    Get the average volume of the last n days for each symbol.
    Input dataframes should have the following columns:
    - symbol
    - date
    - volume
    Output a dataframe with the following columns:
    - symbol
    - avg_volume_past_n_days of this symbol
    '''
    if df_prev is None or df_prev.empty:
        return pd.DataFrame(columns=['symbol', 'avg_volume_past_n_days'])
    
    # Combine today's and previous data
    combined_df = pd.concat([df_prev, df_today], ignore_index=True) if df_today is not None and not df_today.empty else df_prev
    
    # Sort by symbol and date
    combined_df = combined_df.sort_values(['symbol', 'date']).copy()
    
    # get last n days for each symbol and calculate mean
    last_n_days = combined_df.groupby('symbol').tail(n_days)
    avg_volumes = last_n_days.groupby('symbol')['volume'].mean()
    
    # Convert to DataFrame with proper column name
    result_df = avg_volumes.to_frame('avg_volume_past_n_days')
    
    return result_df 

def get_history_recovery_rate_and_days(df_prev: pd.DataFrame):
    '''
    What is a drop?
    - change_pct = (close - close_prev) / close_prev, if change_pct <= DROP_THRESHOLD_PCT, then it is a drop. 
    What is a recovery?
    - recovery = (high on a future day - close) / close, if recovery >= TARGET_RECOVERY_PCT, then it is a recovery.
    - the recovery days is the days between the drop and the recovery. If there is no recovery, then the recovery days is float('nan').
    Output a dataframe with the following columns:
    1. symbol
    2. the number of recovered drops in all the drops.  
    3. the % of recovered drops in all the drops. 
    4. the average recover days.
    5. the % of 1 day recovery in all recovered drops.
    Existing column names:
    - symbol
    - date
    - close
    - high
    '''
    if df_prev is None or df_prev.empty:
        return pd.DataFrame(columns=['symbol', 'total_drops', 'recovered_drops', 'recovery_rate_pct', 'avg_recovery_days', 'one_day_recovery_rate_pct'])
    
    data_sorted = df_prev.sort_values(["symbol", "date"]).copy()
    
    # Calculate daily change percentage for each symbol
    data_sorted['daily_change_pct'] = data_sorted.groupby('symbol')['close'].pct_change() * 100
    
    # Identify drops (daily change <= DROP_THRESHOLD_PCT)
    drops = data_sorted[data_sorted['daily_change_pct'] <= DROP_THRESHOLD_PCT].copy()
    
    if drops.empty:
        # Return empty DataFrame with proper columns
        return pd.DataFrame(columns=['symbol', 'total_drops', 'recovered_drops', 'recovery_rate_pct', 'avg_recovery_days', 'one_day_recovery_rate_pct'])
    
    # Group drops by symbol and calculate per-symbol statistics
    results = []
    
    for symbol in drops['symbol'].unique():
        symbol_drops = drops[drops['symbol'] == symbol].copy()
        symbol_data = data_sorted[data_sorted['symbol'] == symbol].copy()
        
        recovery_days_list = []
        one_day_recoveries = 0
        
        # For each drop of this symbol, check if it recovers
        for idx, drop in symbol_drops.iterrows():
            drop_date = drop['date']
            drop_close = drop['close']
            target_price = drop_close * (1 + TARGET_RECOVERY_PCT / 100)
            
            # Look for recovery in future dates for the same symbol
            future_data = symbol_data[symbol_data['date'] > drop_date].copy()
            
            if future_data.empty:
                # No future data, no recovery possible
                recovery_days_list.append(float('nan'))
                continue
                
            # Check if any future high reaches target price
            recovery_found = False
            for future_idx, future_row in future_data.iterrows():
                if future_row['high'] >= target_price:
                    # Recovery found
                    recovery_days = (future_row['date'] - drop_date).days
                    recovery_days_list.append(recovery_days)
                    if recovery_days == 1:
                        one_day_recoveries += 1
                    recovery_found = True
                    break
            
            if not recovery_found:
                # No recovery found
                recovery_days_list.append(float('nan'))
        
        # Calculate metrics for this symbol
        total_drops = len(symbol_drops)
        recovered_drops = sum(1 for days in recovery_days_list if not pd.isna(days))
        
        # Recovery rate percentage
        recovery_rate_pct = (recovered_drops / total_drops * 100) if total_drops > 0 else 0.0
        
        # Average recovery days (only for recovered drops)
        valid_recovery_days = [days for days in recovery_days_list if not pd.isna(days)]
        avg_recovery_days = float('nan')
        if valid_recovery_days:
            avg_recovery_days = sum(valid_recovery_days) / len(valid_recovery_days)
        
        # One-day recovery rate percentage
        one_day_recovery_rate_pct = float('nan')
        if recovered_drops > 0:
            one_day_recovery_rate_pct = (one_day_recoveries / recovered_drops * 100)
        
        results.append({
            'symbol': symbol,
            'total_drops': total_drops,
            'recovered_drops': recovered_drops,
            'recovery_rate_pct': recovery_rate_pct,
            'avg_recovery_days': avg_recovery_days,
            'one_day_recovery_rate_pct': one_day_recovery_rate_pct
        })
    results_df = pd.DataFrame(results)
    results_df.set_index("symbol", inplace=True)
    results_df.dropna(inplace=True)
    return results_df


def compute_target_weights(
    date,
    df_today: pd.DataFrame,
    df_prev: pd.DataFrame,
    portfolio: Portfolio,
) -> Tuple[Dict[str, float], Dict[str, Dict[str, Any]]]:
    if df_today is None or df_today.empty:
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
            logger.info(f"Selling {current_symbol} - held for {days_held} days (max: {HOLD_DAYS_T})")
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

    if len(TICKER_LIST) > 0:
        candidates = candidates[candidates.index.isin(TICKER_LIST)]
        if candidates.empty:
            logger.warning(f"No stocks in the whitelist at {date}")
            return {}, {}
    
    avg_volume_past_n_days = get_avg_volume_past_n_days(df_today, df_prev, VOLUME_LOOKBACK_DAYS)
    candidates = candidates.join(avg_volume_past_n_days, how="inner")
    candidates = candidates[candidates["avg_volume_past_n_days"] >= MIN_VOLUME_PAST_N_DAYS]
    
    if candidates.empty:
        logger.warning(f"No stocks with enough volume at {date}")
        return {}, {}

    # Log candidates found
    logger.info(f"Candidates found: {list(candidates.index)}")
    
    candidate_df_today = df_today[df_today["symbol"].isin(candidates.index)]
    candidate_df_prev = df_prev[df_prev["symbol"].isin(candidates.index)]
    
    candidate_return_df = get_return_in_n_days(
        candidate_df_today,
        candidate_df_prev,
        D_LOOKBACK_DAYS,
    )
    
    candidate_recovery_df = get_history_recovery_rate_and_days(candidate_df_prev)

    joined = candidate_return_df.join(candidate_recovery_df, how="left")
    
    if joined.empty:
        logger.warning("No candidates found for trading, returning empty weights")
        return {}, {}
    
    joined = joined.sort_values(RANKER_COLUMNS, ascending=RANKER_DIRECTIONS)
    chosen_symbol = joined.index[0]
    
    # Log selected symbol and its stats
    logger.info(f"Selected: {chosen_symbol}")
    logger.info(f"Selected stats: {joined.loc[chosen_symbol].to_dict()}")

    weights = {chosen_symbol: 1.0}
    order_specs = {chosen_symbol: {"order_type": "MARKET"}}
    return weights, order_specs
