from typing import Dict, List, Optional, Mapping, Any

import pandas as pd
import json
from pathlib import Path
import webbrowser

from backtest.utils import ensure_dir, write_csv
from backtest.html_templates import render_positions_html



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

        # Write an interactive HTML chart of total position value (market_value) over time
        # and the number of positions held. Uses Plotly via CDN (no extra Python deps).
        try:
            dates_str: List[str] = []
            market_values: List[float] = []
            position_counts: List[int] = []

            if self.portfolio_rows:
                pf_df = pd.DataFrame(self.portfolio_rows)
                if "date" in pf_df.columns and "market_value" in pf_df.columns:
                    pf_df = pf_df.sort_values("date")
                    dates_str = pf_df["date"].astype(str).tolist()
                    market_values = pf_df["market_value"].astype(float).tolist()

            if self.positions_rows and dates_str:
                pos_df = pd.DataFrame(self.positions_rows)
                if "date" in pos_df.columns and "shares" in pos_df.columns:
                    pos_df = pos_df.sort_values("date")
                    pos_counts_map: Dict[str, int] = (
                        pos_df.assign(date_str=pos_df["date"].astype(str))
                        .groupby("date_str")["shares"]
                        .apply(lambda s: int((pd.Series(s).astype(int) != 0).sum()))
                        .to_dict()
                    )
                    position_counts = [int(pos_counts_map.get(d, 0)) for d in dates_str]

            # Build Filled Orders HTML table with FIFO cost basis/positions and total equity
            orders_html = "<p>No filled orders.</p>"
            if self.trades_rows:
                try:
                    trades_df = pd.DataFrame(self.trades_rows)
                    # Ensure required columns
                    required_cols = {"date", "symbol", "side", "qty", "fill_price"}
                    if required_cols.issubset(set(trades_df.columns)):
                        trades_df = trades_df.sort_values(["date", "symbol"]).reset_index(drop=True)
                        # Map date -> total equity at end of day
                        equity_map: Dict[str, float] = {}
                        if self.portfolio_rows:
                            pf_df2 = pd.DataFrame(self.portfolio_rows)
                            if "date" in pf_df2.columns and "equity" in pf_df2.columns:
                                pf_df2 = pf_df2.sort_values("date")
                                equity_map = (
                                    pf_df2.assign(date_str=pf_df2["date"].astype(str))
                                    .groupby("date_str")["equity"].last().astype(float).to_dict()
                                )
                        # FIFO lots per symbol
                        lots_map: Dict[str, List[Dict[str, float]]] = {}
                        out_rows: List[Dict[str, Any]] = []
                        for _, row in trades_df.iterrows():
                            date_val = row["date"]
                            date_str = str(date_val)
                            symbol = str(row["symbol"])  # type: ignore
                            side = str(row["side"]).upper()  # type: ignore
                            qty = int(row["qty"])  # type: ignore
                            price = float(row["fill_price"])  # type: ignore
                            lots = lots_map.setdefault(symbol, [])
                            if side == "BUY":
                                lots.append({"qty": int(qty), "price": float(price)})
                            else:
                                remaining = int(qty)
                                new_lots: List[Dict[str, float]] = []
                                for lot in lots:
                                    if remaining <= 0:
                                        new_lots.append(lot)
                                        continue
                                    lot_qty = int(lot["qty"])  # type: ignore
                                    if lot_qty <= remaining:
                                        remaining -= lot_qty
                                        continue
                                    # partial reduce
                                    new_lots.append({"qty": int(lot_qty - remaining), "price": float(lot["price"])})
                                    remaining = 0
                                lots_map[symbol] = new_lots
                                lots = new_lots
                            total_qty = int(sum(int(l["qty"]) for l in lots))
                            if total_qty > 0:
                                total_cost = float(sum(int(l["qty"]) * float(l["price"]) for l in lots))
                                avg_cost = float(total_cost) / float(total_qty)
                            else:
                                avg_cost = 0.0
                            out_rows.append({
                                "date": date_str,
                                "symbol": symbol,
                                "side": side,
                                "price": float(price),
                                "cost_basis": float(avg_cost),
                                "positions": int(total_qty),
                                "total_equity": float(equity_map.get(date_str, float("nan"))),
                            })
                        if out_rows:
                            out_df = pd.DataFrame(out_rows)
                            # Render compact HTML table
                            def fmt_money(x: Any) -> str:
                                try:
                                    return f"{float(x):,.2f}"
                                except Exception:
                                    return ""
                            def fmt_int(x: Any) -> str:
                                try:
                                    return f"{int(x):,}"
                                except Exception:
                                    return "0"
                            headers = ["date", "symbol", "side", "price", "cost_basis", "positions", "total_equity"]
                            header_html = "".join(f"<th>{h}</th>" for h in headers)
                            rows_html_parts: List[str] = []
                            for _, r in out_df.iterrows():
                                row_cells: List[str] = []
                                row_cells.append(f"<td>{r['date']}</td>")
                                row_cells.append(f"<td>{r['symbol']}</td>")
                                row_cells.append(f"<td>{r['side']}</td>")
                                row_cells.append(f"<td>{fmt_money(r['price'])}</td>")
                                row_cells.append(f"<td>{fmt_money(r['cost_basis'])}</td>")
                                row_cells.append(f"<td>{fmt_int(r['positions'])}</td>")
                                row_cells.append(f"<td>{fmt_money(r['total_equity'])}</td>")
                                rows_html_parts.append("<tr>" + "".join(row_cells) + "</tr>")
                            body_html = "".join(rows_html_parts)
                            orders_html = (
                                "<table class=\"orders\">"
                                "<thead><tr>" + header_html + "</tr></thead>"
                                "<tbody>" + body_html + "</tbody>"
                                "</table>"
                            )
                except Exception:
                    orders_html = "<p>Failed to build Filled Orders table.</p>"

            if dates_str and market_values:
                html_out = f"{outdir}/positions.html"
                plotly_cdn = "https://cdn.plot.ly/plotly-2.30.0.min.js"
                chart_title = "Total Position Value Over Time"
                x_json = json.dumps(dates_str)
                y_json = json.dumps([float(v) for v in market_values])
                y2_json = json.dumps([int(v) for v in position_counts]) if position_counts else "null"
                has_y2_bool = bool(position_counts)
                # Prepare metrics summary (Sharpe, total return, max drawdown, variance)
                stats_html = ""
                if self.metrics_rows:
                    try:
                        mdf = pd.DataFrame(self.metrics_rows)
                        # Expect columns from MetricsEngine.update
                        sharpe_itd = float(mdf["sharpe_itd"].iloc[-1]) if "sharpe_itd" in mdf.columns and not mdf.empty else 0.0
                        total_return = float(mdf["cumulative_return"].iloc[-1]) if "cumulative_return" in mdf.columns and not mdf.empty else 0.0
                        max_dd = float(mdf["max_drawdown"].min()) if "max_drawdown" in mdf.columns and not mdf.empty else 0.0
                        # daily return variance
                        variance_ret = float(pd.Series(mdf.get("daily_return", pd.Series([], dtype=float))).astype(float).var(ddof=1)) if "daily_return" in mdf.columns and len(mdf["daily_return"]) > 1 else 0.0
                        # Build HTML table
                        stats_html = (
                            "<table class=\"stats\">"
                            "<thead><tr><th>Metric</th><th>Value</th></tr></thead>"
                            "<tbody>"
                            f"<tr><td>Sharpe Ratio (ITD)</td><td>{sharpe_itd:.3f}</td></tr>"
                            f"<tr><td>Total Return</td><td>{total_return:.2%}</td></tr>"
                            f"<tr><td>Max Drawdown</td><td>{max_dd:.2%}</td></tr>"
                            f"<tr><td>Return Variance (daily)</td><td>{variance_ret:.6f}</td></tr>"
                            "</tbody></table>"
                        )
                    except Exception:
                        stats_html = ""

                # Prepare daily returns series
                ret_dates_str: List[str] = []
                ret_values: List[float] = []
                if self.metrics_rows:
                    try:
                        mdf = pd.DataFrame(self.metrics_rows)
                        if "date" in mdf.columns and "daily_return" in mdf.columns and not mdf.empty:
                            mdf = mdf.sort_values("date")
                            ret_dates_str = mdf["date"].astype(str).tolist()
                            ret_values = mdf["daily_return"].astype(float).tolist()
                    except Exception:
                        ret_dates_str = []
                        ret_values = []

                html = render_positions_html(
                    chart_title=chart_title,
                    plotly_cdn=plotly_cdn,
                    x_json=x_json,
                    y_json=y_json,
                    y2_json=y2_json,
                    has_y2=has_y2_bool,
                    stats_html=stats_html,
                    ret_x_json=json.dumps(ret_dates_str) if ret_dates_str else "[]",
                    ret_y_json=json.dumps([float(v) for v in ret_values]) if ret_values else "[]",
                    has_returns=bool(ret_values),
                    orders_html=orders_html,
                )
                with open(html_out, "w", encoding="utf-8") as f:
                    f.write(html)
                # Optionally open in default browser
                if bool(self.cfg["io"].get("open_positions_html", True)):
                    url = Path(html_out).resolve().as_uri()
                    webbrowser.open(url, new=2)
        except Exception:
            # Chart creation failures should not block CSV outputs
            pass


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
            "order_type": getattr(f, "order_type", "MARKET"),
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
