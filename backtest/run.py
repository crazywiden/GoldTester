import time
import argparse

from loguru import logger
from backtest.utils import load_yaml, seed_everything, ensure_dir
from backtest.data_loader import DataLoader, choose_ref_prices_for_next_fill, get_marking_series
from backtest.signals import load_user_signal
from backtest.orders import OrderGenerator
from backtest.execution import ExecutionSimulator
from backtest.accounting import Portfolio
from backtest.metrics import MetricsEngine
from backtest import reporting
from backtest.utils import next_trading_day
from backtest.risk import evaluate_stop_levels


def run(cfg_path: str) -> None:
    cfg = load_yaml(cfg_path)
    logger.info(f"Config: {cfg}")
    seed_everything(int(cfg.get("run", {}).get("seed", 42)))
    ensure_dir(cfg.get("io", {}).get("output_dir", "./output"))
    reporting.init_reporting(cfg)
    data_loader = DataLoader(cfg)
    signals_cfg = cfg.get("signals", {})
    signal_function = load_user_signal(
        signals_cfg.get("module"),
        signals_cfg.get("function"),
    )
    order_generator = OrderGenerator(cfg)
    execution_simulator = ExecutionSimulator(cfg, data_loader)
    portfolio = Portfolio(cfg.get("portfolio", {}).get("initial_cash", 1_000_000))
    metrics_engine = MetricsEngine(cfg)

    date_list = sorted(data_loader.market["date"].unique())
    if len(date_list) < 2:
        logger.error("Not enough dates to run backtest")
        return

    if reporting.REPORTER is None:
        logger.warning("No reporter found, skipping logging")
        return
    start_date = cfg.get("run", {}).get("start_date")
    end_date = cfg.get("run", {}).get("end_date")
    logger.info(f"Start running backtest, start date: {start_date}, end date: {end_date}")
    start_time = time.perf_counter()
    for t0 in date_list[:-1]:
        logger.info(f"Running backtest for date {t0}")
        data_t0 = data_loader.get_slice(t0)
        all_prev_data = data_loader.get_market_data_before(t0)
        if data_t0.empty:
            logger.warning(f"Data for date {t0} is empty, skipping")
            continue

        weights, order_specs = signal_function(
            t0, data_t0, all_prev_data, portfolio
        )

        t1 = next_trading_day(t0, date_list)
        if t1 is None:
            logger.warning(f"No next trading day found for date {t0}, skipping")
            break
        # Risk overlay: compute stop-loss / take-profit effect on current holdings using t1 intraday extremes
        try:
            data_t1 = data_loader.get_slice(t1)
        except KeyError:
            data_t1 = None

        prices_for_risk = {}
        intraday_high = {}
        intraday_low = {}
        if data_t1 is not None and not data_t1.empty:
            price_col = cfg.get("run", {}).get("price_column_for_valuation", "close")
            if price_col in data_t1.columns:
                prices_for_risk = data_t1[["symbol", price_col]].dropna().groupby("symbol")[price_col].first().to_dict()
            if "high" in data_t1.columns and "low" in data_t1.columns:
                intraday_high = data_t1[["symbol", "high"]].dropna().groupby("symbol")["high"].first().to_dict()
                intraday_low = data_t1[["symbol", "low"]].dropna().groupby("symbol")["low"].first().to_dict()

        # Compute signal-driven target shares
        ref_prices = choose_ref_prices_for_next_fill(t0, data_loader, cfg, order_specs)
        target_shares_by_signal = order_generator.weights_to_target_shares(
            weights, portfolio.equity, ref_prices
        )

        # Apply risk overlay to current holdings, then cap signal targets accordingly
        target_after_risk_current = evaluate_stop_levels(
            t1, cfg, portfolio, prices_for_risk, intraday_high or None, intraday_low or None
        )
        final_target_shares = dict(target_shares_by_signal)
        for sym, cur_risk_target in target_after_risk_current.items():
            desired = int(final_target_shares.get(sym, 0))
            # do not exceed risk-capped target for currently held symbols
            final_target_shares[sym] = min(desired, int(cur_risk_target))

        orders_t1 = order_generator.diff_to_orders(
            portfolio.get_total_shares_map(), final_target_shares, ref_prices, order_specs
        )
        fills = execution_simulator.fill_orders(t1, orders_t1)
        portfolio.apply_fills(fills)
        prices_t1, dividends_t1 = get_marking_series(t1, data_loader, cfg)
        prev_equity = float(portfolio.equity)
        portfolio.mark_to_market(prices_t1, dividends_t1)
        metrics = metrics_engine.update(t1, portfolio.equity, prev_equity)
        reporting.persist_snapshots(t1, portfolio, fills, metrics)
        
    time_used = time.perf_counter() - start_time
    logger.info(f"Backtest finished, time used: {time_used} seconds")

    if reporting.REPORTER is not None:
        logger.info("Finalizing Reports...")
        reporting.REPORTER.finalize()


def main() -> None:
    parser = argparse.ArgumentParser(description="GoldTester Backtest Runner")
    parser.add_argument("--config", "-c", required=True, help="Path to backtest.yaml")
    args = parser.parse_args()
    run(args.config)


if __name__ == "__main__":
    main()
