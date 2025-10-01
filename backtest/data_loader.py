from typing import Dict, Optional, Tuple, Any, Mapping

import os
import pandas as pd
from loguru import logger

from backtest.utils import parse_date


REQUIRED_COLS = ["open", "high", "low", "close", "volume"]


class DataLoader:
    def __init__(self, cfg: Mapping[str, Any]):
        self.cfg = dict(cfg)
        self._market: Optional[pd.DataFrame] = None
        self._halts: Optional[pd.DataFrame] = None

    @property
    def market(self) -> pd.DataFrame:
        if self._market is None:
            self._market = self.load_market()
        return self._market

    @property
    def halts(self) -> pd.DataFrame:
        if self._halts is None:
            self._halts = self.load_halts()
        return self._halts

    def load_market(self) -> pd.DataFrame:
        """we expect data has the following columns:
        
        date, symbol, open, high, low, close, volume
        """
        path = self.cfg.get("io", {}).get("market_data_path")
        if not path or not os.path.exists(path):
            logger.error(f"Market data not found: {path}")
            raise FileNotFoundError(f"Market data not found: {path}")
        df = pd.read_csv(path)
        missing = [c for c in ["date", "symbol"] + REQUIRED_COLS if c not in df.columns]
        if missing:
            logger.error(f"Market data missing columns: {missing}")
            raise FileNotFoundError(f"Market data missing columns: {missing}")

        df["date"] = pd.to_datetime(
            df["date"],
            errors="coerce",
            utc=True
        ).dt.tz_convert("America/New_York")
        if "delisting_date" in df.columns:
            df["delisting_date"] = pd.to_datetime(df["delisting_date"]).dt.normalize()
        df = df.sort_values(["date", "symbol"])  # Keep columns; do not set MultiIndex
        return df

    def load_halts(self) -> pd.DataFrame:
        """we expect data has the following columns:
        
        date, symbol, is_halted
        """
        path = self.cfg.get("io", {}).get("halts_path")
        if not path or not os.path.exists(path):
            logger.error(f"Halts data not found: {path}")
            raise FileNotFoundError(f"Halts data not found: {path}")
        df = pd.read_csv(path)
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        df = df.sort_values(["date", "symbol"])  # Keep columns; do not set MultiIndex
        return df

    def get_slice(self, date: pd.Timestamp) -> pd.DataFrame:
        d = parse_date(date)
        df = self.market
        # Handle timezone mismatch: compare date parts only
        return df[df["date"].dt.date == d.date()]

    def get_bar(self, date: pd.Timestamp, symbol: str) -> Optional[pd.Series]:
        d = parse_date(date)
        df = self.market
        # Handle timezone mismatch: compare date parts only
        rows = df[(df["date"].dt.date == d.date()) & (df["symbol"] == symbol)]
        if rows.empty:
            return None
        return rows.iloc[0]

    def get_market_data_before(self, date: pd.Timestamp) -> pd.DataFrame:
        d = parse_date(date)
        # Handle timezone mismatch: compare date parts only
        return self.market[self.market["date"].dt.date < d.date()]

    def get_adv(self, symbol: str, date: pd.Timestamp, lookback: int = 20) -> float:
        d = parse_date(date)
        start = pd.Timestamp(d - pd.tseries.offsets.BDay(lookback), tz=None)
        end = (d - pd.Timedelta(days=1)).tz_localize(None)
        df = self.market
        if "date" not in df.columns:
            return 0.0
        # Handle timezone mismatch: compare date parts only
        start_date = start.date()
        end_date = end.date()
        mask = (df["symbol"] == symbol) & (df["date"].dt.date >= start_date) & (df["date"].dt.date <= end_date)
        panel = df.loc[mask]
        if panel.empty or "volume" not in panel.columns:
            return 0.0
        return float(panel["volume"].tail(lookback).mean())


def choose_target_prices_for_next_fill(
    date: pd.Timestamp,
    data_loader: DataLoader,
    cfg: Mapping[str, Any],
    order_specs: Dict[str, Any],
) -> Dict[str, float]:
    method = cfg["execution"]["order_fill_method"]
    df = data_loader.get_slice(date)
    target_prices_map = {}
    if df.empty:
        logger.error(f"Data for date {date} is empty, skipping")
        return {}
    if method == "next_open":
        base = df["open"]
    elif method == "next_close":
        base = df["close"]
    elif method == "vwap_proxy":
        base = (df["high"] + df["low"] + df["close"]) / 3.0
    else:
        base = df["close"]
    
    all_target_prices = base.groupby(df["symbol"]).first().to_dict()
    for symbol, spec in order_specs.items():
        order_type = spec.get("order_type", "MARKET").upper()
        if order_type == "LIMIT":
            target_prices_map[symbol] = round(spec.get("limit_price"), 2)
        elif order_type == "MARKET":
            target_prices_map[symbol] = round(all_target_prices[symbol], 2)
    return target_prices_map


def get_marking_series(
    date: pd.Timestamp,
    data_loader: DataLoader,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    df = data_loader.get_slice(date)
    if df.empty:
        logger.error(f"Data for date {date} is empty, skipping")
        return {}, {}
    price_col = "close"
    if price_col not in df.columns:
        logger.error(f"Price column {price_col} not found in data")
        raise ValueError(f"Price column {price_col} not found in data")
    prices = df[[price_col]].dropna().groupby(df["symbol"])[price_col].first().to_dict()
    dividends = {}
    if "dividend" in df.columns:
        dividends = df[["dividend"]].fillna(0.0).groupby(df["symbol"])["dividend"].first().to_dict()
    prices = {k: float(v) for k, v in prices.items()}
    dividends = {k: float(v) for k, v in dividends.items()}
    return prices, dividends
