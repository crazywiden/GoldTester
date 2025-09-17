from __future__ import annotations

from typing import Dict, Optional, Tuple, Any, Mapping

import os
import pandas as pd
from loguru import logger

from backtest.utils import parse_date


REQUIRED_COLS = ["open", "high", "low", "close", "adjusted_close", "volume"]


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
        
        date, symbol, open, high, low, close, adjusted_close, volume
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

        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        if "delisting_date" in df.columns:
            df["delisting_date"] = pd.to_datetime(df["delisting_date"]).dt.normalize()
        df = df.sort_values(["date", "symbol"]).set_index(["date", "symbol"], drop=False)
        return df

    def load_halts(self) -> pd.DataFrame:
        path = self.cfg.get("io", {}).get("halts_path")
        if not path or not os.path.exists(path):
            logger.error(f"Halts data not found: {path}")
            raise FileNotFoundError(f"Halts data not found: {path}")
        df = pd.read_csv(path)
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        df = df.sort_values(["date", "symbol"]).set_index(["date", "symbol"], drop=False)
        return df

    def get_slice(self, date: pd.Timestamp) -> pd.DataFrame:
        d = parse_date(date)
        return self.market.loc[(d,), :]

    def get_bar(self, date: pd.Timestamp, symbol: str) -> Optional[pd.Series]:
        d = parse_date(date)
        return self.market.loc[(d, symbol)]

    def get_adv(self, symbol: str, date: pd.Timestamp, lookback: int = 20) -> float:
        d = parse_date(date)
        start = d - pd.tseries.offsets.BDay(lookback)
        df = self.market
        panel = df.loc[(slice(pd.Timestamp(start, tz=None), d - pd.Timedelta(days=1)), symbol), :]
        if panel.empty or "volume" not in panel.columns:
            return 0.0
        return float(panel["volume"].tail(lookback).mean())


def choose_ref_prices_for_next_fill(date: pd.Timestamp, data_loader: DataLoader, cfg: Mapping[str, Any]) -> Dict[str, float]:
    method = cfg.get("execution", {}).get("order_fill_method", "next_close")
    df = data_loader.get_slice(date)
    if df.empty:
        return {}
    if method in ("next_open", "next_close"):
        base = df["close"]
    elif method == "vwap_proxy":
        base = (df["high"] + df["low"] + df["close"]) / 3.0
    else:
        base = df["close"]
    return {sym: float(p) for sym, p in base.groupby(df["symbol"]).first().items()}


def get_marking_series(
    date: pd.Timestamp,
    data_loader: DataLoader,
    cfg: Mapping[str, Any],
) -> Tuple[Dict[str, float], Dict[str, float]]:
    df = data_loader.get_slice(date)
    if df.empty:
        return {}, {}
    price_col = cfg.get("run", {}).get("price_column_for_valuation", "close")
    if price_col not in df.columns:
        logger.error(f"Price column {price_col} not found in data")
        raise ValueError(f"Price column {price_col} not found in data")
    prices = df[["symbol", price_col]].dropna().groupby("symbol")[price_col].first().to_dict()
    dividends = {}
    if "dividend" in df.columns:
        dividends = df[["symbol", "dividend"]].fillna(0.0).groupby("symbol")["dividend"].first().to_dict()
    prices = {k: float(v) for k, v in prices.items()}
    dividends = {k: float(v) for k, v in dividends.items()}
    return prices, dividends
