from dataclasses import dataclass
from typing import Dict, Optional

import pandas as pd


@dataclass
class Order:
    date: pd.Timestamp
    symbol: str
    side: str  # "BUY" | "SELL"
    qty: int
    ref_price: float
    order_type: str = "MARKET"  # "MARKET" | "LIMIT"
    limit_price: Optional[float] = None
    base_price: Optional[float] = None  # For BUY: fill_price, For SELL: avg cost of sold lots


@dataclass
class Fill:
    order_id: str
    date: pd.Timestamp
    symbol: str
    side: str
    qty: int
    ref_price: float
    fill_price: float
    slippage: float
    commission: float
    order_type: str = "MARKET"
    base_price: Optional[float] = None  # For BUY: fill_price, For SELL: avg cost of sold lots


@dataclass
class Lot:
    date_acquired: pd.Timestamp
    qty: int
    fill_price: float
