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


@dataclass
class Lot:
    date_acquired: pd.Timestamp
    qty: int
    fill_price: float
