from dataclasses import dataclass
from typing import Dict

import pandas as pd


@dataclass
class Order:
    date: pd.Timestamp
    symbol: str
    side: str  # "BUY" | "SELL"
    qty: int
    ref_price: float


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
