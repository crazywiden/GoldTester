from typing import Dict, List, Optional, Mapping, Any

import pandas as pd

from backtest.utils import ensure_dir, write_csv



class _ReportWriter:
    def __init__(self, cfg: Mapping[str, Any]):
        self.cfg = dict(cfg)
        self.position_map_rows: List[Dict] = []
        self.trades_rows: List[Dict] = []
        self.positions_rows: List[Dict] = []
        self.portfolio_rows: List[Dict] = []
        self.metrics_rows: List[Dict] = []

    def add_position_map(self, rows: List[Dict]) -> None:
        self.position_map_rows.extend(rows)

    def add_trades(self, rows: List[Dict]) -> None:
        self.trades_rows.extend(rows)

    def add_positions(self, rows: List[Dict]) -> None:
        self.positions_rows.extend(rows)

    def add_portfolio(self, row: Dict) -> None:
        self.portfolio_rows.append(row)

    def add_metrics(self, row: Dict) -> None:
        self.metrics_rows.append(row)

    def finalize(self) -> None:
        outdir = self.cfg.get("io", {}).get("output_dir", "./output")
        ensure_dir(outdir)
        flags = self.cfg.get("io", {}).get("artifacts", {})
        if bool(flags.get("write_trades", True)) and self.trades_rows:
            df = pd.DataFrame(self.trades_rows)
            write_csv(df, f"{outdir}/trades.csv")
        if bool(flags.get("write_positions", True)) and self.positions_rows:
            df = pd.DataFrame(self.positions_rows)
            write_csv(df, f"{outdir}/positions.csv")
        if bool(flags.get("write_portfolio", True)) and self.portfolio_rows:
            df = pd.DataFrame(self.portfolio_rows)
            write_csv(df, f"{outdir}/portfolio.csv")
        if bool(flags.get("write_metrics", True)) and self.metrics_rows:
            df = pd.DataFrame(self.metrics_rows)
            write_csv(df, f"{outdir}/metrics.csv")


REPORTER: Optional[_ReportWriter] = None


def init_reporting(cfg) -> None:
    global REPORTER
    REPORTER = _ReportWriter(cfg)


def persist_snapshots(date, portfolio, fills, metrics) -> None:
    if REPORTER is None:
        return
    # trades
    trade_rows = []
    for f in fills:
        trade_rows.append({
            "datetime": date,
            "date": date,
            "symbol": f.symbol,
            "side": f.side,
            "qty": int(f.qty),
            "ref_price": float(f.ref_price),
            "fill_price": float(f.fill_price),
            "slippage": float(f.slippage),
            "commission": float(f.commission),
            "notional": float(f.qty) * float(f.fill_price),
            "order_id": f.order_id,
        })
    REPORTER.add_trades(trade_rows)
    pos_rows = []
    for sym in portfolio.shares.keys():
        qty = portfolio.get_total_shares(sym)
        pos_rows.append({
            "date": date,
            "symbol": sym,
            "shares": int(qty),
        })
    REPORTER.add_positions(pos_rows)
    REPORTER.add_portfolio(portfolio.snapshot(date))
    REPORTER.add_metrics(metrics)
