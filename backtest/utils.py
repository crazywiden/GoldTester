import os
import random
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Dict

import numpy as np
import pandas as pd
import yaml
from loguru import logger


def load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    # Ensure we always return a dict
    if data is None:
        return {}
    if isinstance(data, Mapping):
        return dict(data)
    raise TypeError("YAML root must be a mapping (dict)")


def ensure_dir(path: str) -> None:
    if os.path.exists(path):
        logger.info(f"Directory {path} already exists")
        return
    logger.info(f"Creating directory {path}")
    os.makedirs(path, exist_ok=True)


def write_csv(df: pd.DataFrame, path: str) -> None:
    """Write DataFrame to CSV at the given path."""
    base, ext = os.path.splitext(path)
    csv_path = path if ext.lower() == ".csv" else f"{base}.csv"
    df.to_csv(csv_path, index=False)


def parse_date(date_like: Any) -> pd.Timestamp:
    if isinstance(date_like, pd.Timestamp):
        return date_like.normalize()
    return pd.to_datetime(date_like).normalize()


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)


def next_trading_day(current: Any, dates: Sequence[pd.Timestamp]) -> Optional[pd.Timestamp]:
    cur = parse_date(current)
    for idx, d in enumerate(dates):
        if parse_date(d) == cur:
            if idx + 1 < len(dates):
                return parse_date(dates[idx + 1])
            return None
    later = [d for d in dates if parse_date(d) > cur]
    return parse_date(later[0]) if later else None


def typical_price(high: float, low: float, close: float) -> float:
    return (float(high) + float(low) + float(close)) / 3.0


def annual_to_daily_rate(annual_rate: float) -> float:
    return (1.0 + float(annual_rate)) ** (1.0 / 252.0) - 1.0


@dataclass
class ArtifactFlags:
    write_trades: bool
    write_positions: bool
    write_portfolio: bool
    write_metrics: bool


def get_artifact_flags(cfg: Dict[str, Any]) -> ArtifactFlags:
    io_cfg = cfg.get("io", {}) if isinstance(cfg, Mapping) else {}
    artifacts = io_cfg.get("artifacts", {}) if isinstance(io_cfg, Mapping) else {}
    return ArtifactFlags(
        write_trades=bool(artifacts.get("write_trades", True)),
        write_positions=bool(artifacts.get("write_positions", True)),
        write_portfolio=bool(artifacts.get("write_portfolio", True)),
        write_metrics=bool(artifacts.get("write_metrics", True)),
    )
