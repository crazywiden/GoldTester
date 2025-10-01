# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Running Backtests
```bash
python -m backtest.run --config backtest_config.yaml | cat
```

### Environment Setup
```bash
pip install -r requirements.txt
```

### Package Installation
```bash
pip install -e .
```

### Testing
```bash
# Run integration tests
python tests/integration_test.py

# Run unit tests (when available)
python -m pytest tests/unit/ -v
```

## Architecture Overview

GoldTester is a quantitative trading backtesting framework with a modular architecture:

### Core Components

- **`backtest/run.py`**: Main backtest orchestrator that coordinates all components in a time-series loop
- **`backtest/data_loader.py`**: Handles market data loading and time-series slicing from CSV files
- **`backtest/signals.py`**: Dynamic signal loading system that imports user-defined strategy modules
- **`backtest/orders.py`**: Order generation from target weights and portfolio differences
- **`backtest/execution.py`**: Order execution simulation with slippage and commission models
- **`backtest/accounting.py`**: Portfolio tracking, mark-to-market, and equity calculations
- **`backtest/metrics.py`**: Performance metrics computation (returns, drawdowns, etc.)
- **`backtest/reporting.py`**: Output artifact generation and persistence

### Strategy Development

User strategies are implemented in the `strategies/` directory as Python modules. The framework supports two signal function interfaces:

**Traditional Interface (Market Orders Only):**
```python
def compute_target_weights(
    date,
    df_today: pd.DataFrame,
    df_prev: pd.DataFrame, 
    portfolio: Portfolio,
) -> Dict[str, float]:
```

**Enhanced Interface (Market + Limit Orders):**
```python
def compute_target_weights_and_orders(
    date,
    df_today: pd.DataFrame,
    df_prev: pd.DataFrame, 
    portfolio: Portfolio,
) -> Tuple[Dict[str, float], Dict[str, Dict[str, Any]]]:
```

The enhanced interface returns both target weights and order specifications. Order specs format:
```python
order_specs = {
    "AAPL": {"order_type": "LIMIT", "limit_price": 148.0},
    "MSFT": {"order_type": "MARKET"}
}
```

The framework automatically detects which interface is used and maintains full backward compatibility. Limit orders are filled if the limit price falls within the [low, high] range of the execution day.

### Configuration System

All backtest parameters are specified in YAML configuration files. Example configurations can be found in `tests/test_runs/*/`:
- Run parameters (dates, seed, price column for valuation)
- Portfolio settings (initial cash, leverage limits, short selling)
- Execution models (order fill methods, slippage, commissions)
- Signal module specification
- Data file paths and output directories

### Data Flow

1. Market data loaded from CSV files specified in config
2. Strategy function called with current and historical data
3. Target weights converted to orders via portfolio differences
4. Orders executed with realistic slippage/commission simulation
5. Portfolio marked-to-market with new prices
6. Metrics computed and artifacts persisted

The main backtest loop iterates through trading days, calling the strategy function and updating portfolio state at each step.