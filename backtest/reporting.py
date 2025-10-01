from typing import Dict, List, Optional, Mapping, Any, Tuple

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
        outdir = self._output_dir()
        ensure_dir(outdir)
        self._write_artifacts(outdir)

        # Build interactive HTML dashboard
        try:
            dates_str, equity_values = self._build_equity_series()
            if not (dates_str and equity_values):
                return
            position_counts = self._build_position_count_series(dates_str)
            equity_map = self._build_equity_map()

            orders_html = self._build_orders_html(equity_map)
            stats_html = self._build_stats_html()
            ret_dates_str, ret_values = self._build_returns_series()

            html_out = f"{outdir}/positions.html"
            html = self._render_positions_dashboard(
                dates_str=dates_str,
                equity_values=equity_values,
                position_counts=position_counts,
                stats_html=stats_html,
                ret_dates_str=ret_dates_str,
                ret_values=ret_values,
                orders_html=orders_html,
                extra_sections_html="",
            )
            with open(html_out, "w", encoding="utf-8") as f:
                f.write(html)
            if bool(self.cfg.get("io", {}).get("open_positions_html", True)):
                url = Path(html_out).resolve().as_uri()
                webbrowser.open(url, new=2)
        except Exception:
            # Chart creation failures should not block CSV outputs
            pass

    # -------------------- Helpers: configuration & artifacts --------------------
    def _output_dir(self) -> str:
        return self.cfg.get("io", {}).get("output_dir", "./output")

    def _artifact_flags(self) -> Dict[str, Any]:
        return dict(self.cfg.get("io", {}).get("artifacts", {}))

    def _write_artifacts(self, outdir: str) -> None:
        flags = self._artifact_flags()
        if bool(flags.get("write_trades", True)) and self.trades_rows:
            write_csv(pd.DataFrame(self.trades_rows), f"{outdir}/trades.csv")
        if bool(flags.get("write_positions", True)) and self.positions_rows:
            write_csv(pd.DataFrame(self.positions_rows), f"{outdir}/positions.csv")
        if bool(flags.get("write_portfolio", True)) and self.portfolio_rows:
            write_csv(pd.DataFrame(self.portfolio_rows), f"{outdir}/portfolio.csv")
        if bool(flags.get("write_metrics", True)) and self.metrics_rows:
            write_csv(pd.DataFrame(self.metrics_rows), f"{outdir}/metrics.csv")

    # -------------------- Helpers: series builders --------------------
    def _build_equity_series(self) -> Tuple[List[str], List[float]]:
        if not self.portfolio_rows:
            return [], []
        pf_df = pd.DataFrame(self.portfolio_rows)
        pf_df = pf_df.sort_values("date")
        dates_str = pf_df["date"].astype(str).tolist()
        equity_values = pf_df["equity"].astype(float).tolist()
        return dates_str, equity_values

    def _build_position_count_series(self, dates_str: List[str]) -> List[int]:
        if not (self.positions_rows and dates_str):
            return []
        pos_df = pd.DataFrame(self.positions_rows)
        if "date" not in pos_df.columns or "shares" not in pos_df.columns:
            return []
        pos_df = pos_df.sort_values("date")
        pos_counts_map: Dict[str, int] = (
            pos_df.assign(date_str=pos_df["date"].astype(str))
            .groupby("date_str")["shares"]
            .apply(lambda s: int((pd.Series(s).astype(int) != 0).sum()))
            .to_dict()
        )
        return [int(pos_counts_map.get(d, 0)) for d in dates_str]

    def _build_equity_map(self) -> Dict[str, float]:
        if not self.portfolio_rows:
            return {}
        pf_df2 = pd.DataFrame(self.portfolio_rows)
        if "date" not in pf_df2.columns or "equity" not in pf_df2.columns:
            return {}
        pf_df2 = pf_df2.sort_values("date")
        return (
            pf_df2.assign(date_str=pf_df2["date"].astype(str))
            .groupby("date_str")["equity"].last().astype(float).to_dict()
        )

    # -------------------- Helpers: HTML builders --------------------
    def _build_orders_html(self, equity_map: Dict[str, float]) -> str:
        if not self.trades_rows:
            return "<p>No filled orders.</p>"
        try:
            trades_df = pd.DataFrame(self.trades_rows)
            required_cols = {"date", "symbol", "side", "qty", "fill_price"}
            if not required_cols.issubset(set(trades_df.columns)):
                return "<p>No filled orders.</p>"

            # Ensure base_price column exists
            if "base_price" not in trades_df.columns:
                trades_df["base_price"] = None
            trades_df = trades_df.sort_values(["date", "symbol"]).reset_index(drop=True)

            lots_map: Dict[str, List[Dict[str, float]]] = {}
            out_rows: List[Dict[str, Any]] = []
            for _, row in trades_df.iterrows():
                date_str = str(row["date"])
                symbol = str(row["symbol"])
                side = str(row["side"]).upper()
                qty = int(row["qty"])
                fill_price = float(row["fill_price"])
                base_price = row.get("base_price", None)
                if base_price is not None:
                    base_price = float(base_price)
                lots = lots_map.setdefault(symbol, [])
                if side == "BUY":
                    lots.append({
                        "qty": int(qty),
                        "price": float(fill_price),
                    })
                elif side == "SELL":
                    total_sell_qty = int(qty)
                    new_lots: List[Dict[str, float]] = []
                    for lot in lots:
                        if total_sell_qty <= 0:
                            new_lots.append(lot)
                            continue
                        lot_qty = int(lot["qty"])
                        if lot_qty <= total_sell_qty:
                            total_sell_qty -= lot_qty
                            continue
                        new_lots.append({
                            "qty": int(lot_qty - total_sell_qty),
                            "price": float(lot["price"]),
                        })
                        total_sell_qty = 0
                    lots_map[symbol] = new_lots
                    lots = new_lots
                total_qty = sum(l["qty"] for l in lots)
                if total_qty > 0:
                    total_cost = float(sum(l["qty"] * float(l["price"]) for l in lots))
                    avg_cost = float(total_cost) / float(total_qty)
                else:
                    avg_cost = 0.0

                # Calculate P&L for this trade
                pnl = 0.0
                if side == "SELL" and base_price is not None:
                    pnl = (fill_price - base_price) * qty

                out_rows.append({
                    "date": date_str,
                    "symbol": symbol,
                    "side": side,
                    "price": float(fill_price),
                    "cost_basis": float(avg_cost),
                    "base_price": base_price if base_price is not None else float("nan"),
                    "pnl": float(pnl),
                    "positions": int(total_qty),
                    "total_equity": float(equity_map.get(date_str, float("nan"))),
                })
            if not out_rows:
                return "<p>No filled orders.</p>"
            out_df = pd.DataFrame(out_rows)

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

            headers = ["date", "symbol", "side", "price", "base_price", "pnl", "positions", "total_equity"]
            header_html = "".join(f"<th>{h}</th>" for h in headers)
            rows_html_parts: List[str] = []
            for _, r in out_df.iterrows():
                row_cells: List[str] = []
                row_cells.append(f"<td>{r['date']}</td>")
                row_cells.append(f"<td>{r['symbol']}</td>")
                row_cells.append(f"<td>{r['side']}</td>")
                row_cells.append(f"<td>{fmt_money(r['price'])}</td>")
                base_price_str = fmt_money(r['base_price']) if r['base_price'] != float("nan") else "N/A"
                row_cells.append(f"<td>{base_price_str}</td>")
                pnl_str = fmt_money(r['pnl']) if r['pnl'] != 0.0 else "0.00"
                pnl_class = "profit" if r['pnl'] > 0 else ("loss" if r['pnl'] < 0 else "")
                row_cells.append(f"<td class='{pnl_class}'>{pnl_str}</td>")
                row_cells.append(f"<td>{fmt_int(r['positions'])}</td>")
                row_cells.append(f"<td>{fmt_money(r['total_equity'])}</td>")
                rows_html_parts.append("<tr>" + "".join(row_cells) + "</tr>")
            body_html = "".join(rows_html_parts)
            return (
                "<table class=\"orders\">"
                "<thead><tr>" + header_html + "</tr></thead>"
                "<tbody>" + body_html + "</tbody>"
                "</table>"
            )
        except Exception:
            return "<p>Failed to build Filled Orders table.</p>"

    def _build_stats_html(self) -> str:
        if not self.metrics_rows:
            return ""
        mdf = pd.DataFrame(self.metrics_rows)
        if mdf.empty:
            return ""
        sharpe_itd = float(mdf["sharpe_itd"].iloc[-1]) if "sharpe_itd" in mdf.columns else 0.0
        total_return = float(mdf["cumulative_return"].iloc[-1]) if "cumulative_return" in mdf.columns else 0.0
        max_dd = float(mdf["max_drawdown"].min()) if "max_drawdown" in mdf.columns else 0.0
        variance_ret = (
            float(pd.Series(mdf.get("daily_return", pd.Series([], dtype=float))).astype(float).var(ddof=1))
            if "daily_return" in mdf.columns and len(mdf.get("daily_return", [])) > 1
            else 0.0
        )
        return (
            "<table class=\"stats\">"
            "<thead><tr><th>Metric</th><th>Value</th></tr></thead>"
            "<tbody>"
            f"<tr><td>Sharpe Ratio (ITD)</td><td>{sharpe_itd:.3f}</td></tr>"
            f"<tr><td>Total Return</td><td>{total_return:.2%}</td></tr>"
            f"<tr><td>Max Drawdown</td><td>{max_dd:.2%}</td></tr>"
            f"<tr><td>Return Variance (daily)</td><td>{variance_ret:.6f}</td></tr>"
            "</tbody></table>"
        )

    def _build_returns_series(self) -> Tuple[List[str], List[float]]:
        if not self.metrics_rows:
            return [], []
        mdf = pd.DataFrame(self.metrics_rows)
        mdf = mdf.sort_values("date")
        return mdf["date"].astype(str).tolist(), mdf["daily_return"].astype(float).tolist()

    # -------------------- Helpers: dashboard rendering --------------------
    def _render_positions_dashboard(
        self,
        *,
        dates_str: List[str],
        equity_values: List[float],
        position_counts: List[int],
        stats_html: str,
        ret_dates_str: List[str],
        ret_values: List[float],
        orders_html: str,
        extra_sections_html: str,
    ) -> str:
        plotly_cdn = "https://cdn.plot.ly/plotly-2.30.0.min.js"
        chart_title = "Total Position Value Over Time"
        x_json = json.dumps(dates_str)
        y_json = json.dumps([float(v) for v in equity_values])
        y2_json = json.dumps([int(v) for v in position_counts]) if position_counts else "null"
        has_y2_bool = bool(position_counts)
        return render_positions_html(
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
            extra_sections_html=extra_sections_html,
        )


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
            "base_price": getattr(f, "base_price", None),
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
