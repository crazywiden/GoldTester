## GoldTester Backtest Platform

### Quickstart

1. Create and activate a Python 3.10+ virtual environment.
2. Install dependencies:
```bash
pip install -r requirements.txt
```
3. Prepare your CSV data files and config (see `backtest_config.yaml`).
4. Run a backtest:
```bash
python -m backtest.run --config backtest_config.yaml | cat
```

### Layout

- `backtest/`: core framework modules
- `strategies/`: user strategies; see `strategies/my_signal.py`
- `backtest.yaml`: example configuration
- `out/run_001/`: default output artifacts
