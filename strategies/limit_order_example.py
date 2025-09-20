from typing import Dict, Tuple, Any
import pandas as pd
from backtest.accounting import Portfolio


def compute_target_weights_and_orders(
    date,
    df_today: pd.DataFrame,
    df_prev: pd.DataFrame,
    portfolio: Portfolio,
) -> Tuple[Dict[str, float], Dict[str, Dict[str, Any]]]:
    """
    Example limit order strategy that demonstrates 
    the new signal interface.
    
    Strategy logic:
    1. Select top 10 liquid stocks by volume
    2. Place limit buy orders 2% below current close price
    3. Place limit sell orders 2% above current close price (for rebalancing)
    4. Equal weight the selected stocks
    
    Returns:
        Tuple of (weights, order_specifications)
    """
    if df_today is None or df_today.empty:
        return {}, {}
        
    # Filter for liquid stocks with volume data
    liquid = df_today.dropna(subset=["volume"]).copy()
    if liquid.empty:
        return {}, {}
        
    # Select top 10 stocks by volume
    liquid = liquid.nlargest(10, "volume")
    
    if len(liquid) == 0:
        return {}, {}
        
    # Create equal weights
    weight_per_stock = 1.0 / len(liquid)
    weights = {}
    order_specs = {}
    
    for _, row in liquid.iterrows():
        symbol = row["symbol"]
        close_price = float(row["close"])
        
        weights[symbol] = weight_per_stock
        
        # Determine if we're buying or selling based on current position
        current_shares = portfolio.get_total_shares(symbol)
        
        if current_shares == 0:
            # New position - place aggressive limit buy at 2% below close
            limit_price = close_price * 0.98
            order_specs[symbol] = {
                "order_type": "LIMIT",
                "limit_price": limit_price
            }
        else:
            # Existing position - use market orders for simplicity in rebalancing
            # (in practice, you might want more sophisticated limit logic here)
            order_specs[symbol] = {
                "order_type": "MARKET"
            }
    
    return weights, order_specs
