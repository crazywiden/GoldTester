import time
import argparse


from loguru import logger
from backtest.utils import load_yaml, seed_everything, ensure_dir
from backtest.data_loader import DataLoader, choose_target_prices_for_next_fill, get_marking_series
from backtest.signals import load_user_signal
from backtest.orders import OrderGenerator
from backtest.execution import ExecutionSimulator
from backtest.accounting import Portfolio
from backtest.metrics import MetricsEngine
from backtest import reporting
import backtest.utils as utils


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
    all_trading_days = utils.get_all_trading_days(start_date, end_date)
    pending_orders = []
    for t0 in all_trading_days:
        """
        for every trading day, the simulation will do:
        
        1. review the order specs from the previous day, and try to execute the orders
          a) for limit orders, we will use the limit price as the target price
          b) for market orders, we will update the target price first, then execute the orders
        2. update the positions map
        3. calculate the target shares for the next day
        4. update the order specs for the next day
        """
        logger.info(f"Running backtest for date {t0}")
        data_t0 = data_loader.get_slice(t0)
        if data_t0.empty:
            logger.warning(f"Data for date {t0} is empty, skipping")
            continue

        # 1) Execute orders staged from the previous day on today's market
        fills = execution_simulator.fill_orders(t0, pending_orders)
        logger.info(f"Executed {len(fills)} orders on {t0}")
        portfolio.apply_fills(fills)

        # 2) Mark portfolio to market using today's prices and persist snapshots
        close_prices_t0, dividends_t0 = get_marking_series(t0, data_loader)
        portfolio.update_equity(close_prices_t0, dividends_t0)
        logger.info(f"Equity after fills and marking to market: {portfolio.equity} on {t0}")
        metrics = metrics_engine.update(t0, portfolio.equity)
        reporting.persist_snapshots(t0, portfolio, fills, metrics)

        # 3) Compute target shares for the next trading day
        all_prev_data = data_loader.get_market_data_before(t0)
        weights, order_specs = signal_function(
            t0, data_t0, all_prev_data, portfolio
        )
        logger.info(f"t0 Date: {t0}, weights: {weights}, order_specs: {order_specs}")

        t1 = utils.next_trading_day(t0, all_trading_days)
        if t1 is None:
            logger.warning(f"No next trading day found for date {t0}, ending run loop")
            break

        data_t1 = data_loader.get_slice(t1)
        if data_t1 is None or data_t1.empty:
            err_msg = f"trading day {t1} data not found in source data!!"
            logger.error(err_msg)
            raise ValueError(err_msg)

        # for market order, use next day's information to choose the target price
        # if no next day's information, use today's information
        if data_t1.empty:
            logger.warning(f"No next day's data found for {t1}, using {t0} data")
            target_prices = choose_target_prices_for_next_fill(t0, data_loader, cfg, order_specs)
        else:
            target_prices = choose_target_prices_for_next_fill(t1, data_loader, cfg, order_specs)
        logger.info(f"target_price for {order_specs} is {target_prices}, current date: {t0}, next date: {t1}")
        target_shares = order_generator.weights_to_target_shares(
            weights, portfolio.equity, target_prices
        )
        logger.info(f"target_shares for {order_specs} is {target_shares}")

        # 4) Stage orders for the next trading day
        pending_orders = order_generator.diff_to_orders(
            portfolio.get_total_shares_map(), target_shares, target_prices, order_specs, portfolio
        )
        if pending_orders:
            logger.info(f"Staged {len(pending_orders)} orders for next day {t1}")
        else:
            logger.info(f"No orders staged for next day {t1}")
        
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
