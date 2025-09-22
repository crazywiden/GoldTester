import unittest
import pandas as pd
from unittest.mock import Mock, MagicMock
from typing import Dict, Any

from backtest.backtest_types import Order, Fill
from backtest.orders import OrderGenerator
from backtest.execution import ExecutionSimulator
from backtest.data_loader import DataLoader
from backtest.accounting import Portfolio


class TestLimitOrderTypes(unittest.TestCase):
    """Test the updated data structures for limit orders"""
    
    def test_order_with_limit_price(self):
        """Test Order dataclass with limit order fields"""
        order = Order(
            date=pd.Timestamp("2023-01-01"),
            symbol="AAPL",
            side="BUY",
            qty=100,
            ref_price=150.0,
            order_type="LIMIT",
            limit_price=148.0
        )
        
        self.assertEqual(order.order_type, "LIMIT")
        self.assertEqual(order.limit_price, 148.0)
    
    def test_order_default_market_type(self):
        """Test Order dataclass defaults to MARKET type"""
        order = Order(
            date=pd.Timestamp("2023-01-01"),
            symbol="AAPL",
            side="BUY",
            qty=100,
            ref_price=150.0
        )
        
        self.assertEqual(order.order_type, "MARKET")
        self.assertIsNone(order.limit_price)
    
    def test_fill_with_order_type(self):
        """Test Fill dataclass includes order_type"""
        fill = Fill(
            order_id="test_001",
            date=pd.Timestamp("2023-01-01"),
            symbol="AAPL",
            side="BUY",
            qty=100,
            ref_price=150.0,
            fill_price=148.0,
            slippage=0.0,
            commission=5.0,
            order_type="LIMIT"
        )
        
        self.assertEqual(fill.order_type, "LIMIT")


class TestOrderGeneration(unittest.TestCase):
    """Test order generation with limit order specifications"""
    
    def setUp(self):
        self.cfg = {
            "execution": {
                "commission_model": {"per_share": 0.01, "min_per_order": 1.0}
            }
        }
        self.order_gen = OrderGenerator(self.cfg)
    
    def test_diff_to_orders_market_only(self):
        """Test order generation without order specs (market orders)"""
        cur_shares = {"AAPL": 0}
        target_shares = {"AAPL": 100}
        ref_prices = {"AAPL": 150.0}
        
        orders = self.order_gen.diff_to_orders(cur_shares, target_shares, ref_prices)
        
        self.assertEqual(len(orders), 1)
        order = orders[0]
        self.assertEqual(order.symbol, "AAPL")
        self.assertEqual(order.side, "BUY")
        self.assertEqual(order.qty, 100)
        self.assertEqual(order.order_type, "MARKET")
        self.assertIsNone(order.limit_price)
    
    def test_diff_to_orders_with_limit_specs(self):
        """Test order generation with limit order specifications"""
        cur_shares = {"AAPL": 0, "MSFT": 50}
        target_shares = {"AAPL": 100, "MSFT": 0}
        ref_prices = {"AAPL": 150.0, "MSFT": 200.0}
        order_specs = {
            "AAPL": {"order_type": "LIMIT", "limit_price": 148.0},
            "MSFT": {"order_type": "MARKET"}
        }
        
        orders = self.order_gen.diff_to_orders(
            cur_shares, target_shares, ref_prices, order_specs
        )
        
        self.assertEqual(len(orders), 2)
        
        # Find AAPL order
        aapl_order = next(o for o in orders if o.symbol == "AAPL")
        self.assertEqual(aapl_order.side, "BUY")
        self.assertEqual(aapl_order.qty, 100)
        self.assertEqual(aapl_order.order_type, "LIMIT")
        self.assertEqual(aapl_order.limit_price, 148.0)
        
        # Find MSFT order
        msft_order = next(o for o in orders if o.symbol == "MSFT")
        self.assertEqual(msft_order.side, "SELL")
        self.assertEqual(msft_order.qty, 50)
        self.assertEqual(msft_order.order_type, "MARKET")
        self.assertIsNone(msft_order.limit_price)


class TestLimitOrderExecution(unittest.TestCase):
    """Test limit order execution logic"""
    
    def setUp(self):
        self.cfg = {
            "execution": {
                "order_fill_method": "next_open",
                "commission_model": {"per_share": 0.01, "min_per_order": 1.0},
                "slippage_model": {"type": "bps_per_turnover", "bps_per_1x_turnover": 10}
            }
        }
        
        # Mock data loader
        self.data_loader = Mock(spec=DataLoader)
        self.execution_sim = ExecutionSimulator(self.cfg, self.data_loader)
        
        # Mock halts data
        self.data_loader.halts = pd.DataFrame()
    
    def test_limit_buy_order_fills_within_range(self):
        """Test limit buy order fills when limit price >= low"""
        # Setup mock data
        bar_data = pd.Series({
            "open": 149.0,
            "high": 152.0,
            "low": 147.0,  # limit price 148.0 >= low 147.0, should fill
            "close": 150.0,
            "volume": 1000000
        })
        
        self.data_loader.get_bar.return_value = bar_data
        self.data_loader.get_adv.return_value = 500000.0
        
        # Create limit buy order
        order = Order(
            date=pd.Timestamp("2023-01-02"),
            symbol="AAPL",
            side="BUY",
            qty=100,
            ref_price=150.0,
            order_type="LIMIT",
            limit_price=148.0
        )
        
        fills = self.execution_sim.fill_orders(pd.Timestamp("2023-01-02"), [order])
        
        self.assertEqual(len(fills), 1)
        fill = fills[0]
        self.assertEqual(fill.symbol, "AAPL")
        self.assertEqual(fill.side, "BUY")
        self.assertEqual(fill.qty, 100)
        self.assertEqual(fill.fill_price, 148.0)  # Should fill at limit price
        self.assertEqual(fill.slippage, 0.0)  # No slippage for limit orders
        self.assertEqual(fill.order_type, "LIMIT")
    
    def test_limit_buy_order_does_not_fill_outside_range(self):
        """Test limit buy order doesn't fill when limit price < low"""
        # Setup mock data
        bar_data = pd.Series({
            "open": 149.0,
            "high": 152.0,
            "low": 149.5,  # limit price 148.0 < low 149.5, should not fill
            "close": 150.0,
            "volume": 1000000
        })
        
        self.data_loader.get_bar.return_value = bar_data
        self.data_loader.get_adv.return_value = 500000.0
        
        # Create limit buy order
        order = Order(
            date=pd.Timestamp("2023-01-02"),
            symbol="AAPL",
            side="BUY",
            qty=100,
            ref_price=150.0,
            order_type="LIMIT",
            limit_price=148.0
        )
        
        fills = self.execution_sim.fill_orders(pd.Timestamp("2023-01-02"), [order])
        
        self.assertEqual(len(fills), 0)  # Order should not fill
    
    def test_limit_sell_order_fills_within_range(self):
        """Test limit sell order fills when limit price <= high"""
        # Setup mock data
        bar_data = pd.Series({
            "open": 149.0,
            "high": 152.0,  # limit price 151.0 <= high 152.0, should fill
            "low": 147.0,
            "close": 150.0,
            "volume": 1000000
        })
        
        self.data_loader.get_bar.return_value = bar_data
        self.data_loader.get_adv.return_value = 500000.0
        
        # Create limit sell order
        order = Order(
            date=pd.Timestamp("2023-01-02"),
            symbol="AAPL",
            side="SELL",
            qty=100,
            ref_price=150.0,
            order_type="LIMIT",
            limit_price=151.0
        )
        
        fills = self.execution_sim.fill_orders(pd.Timestamp("2023-01-02"), [order])
        
        self.assertEqual(len(fills), 1)
        fill = fills[0]
        self.assertEqual(fill.symbol, "AAPL")
        self.assertEqual(fill.side, "SELL")
        self.assertEqual(fill.qty, 100)
        self.assertEqual(fill.fill_price, 151.0)  # Should fill at limit price
        self.assertEqual(fill.slippage, 0.0)  # No slippage for limit orders
        self.assertEqual(fill.order_type, "LIMIT")
    
    def test_limit_sell_order_does_not_fill_outside_range(self):
        """Test limit sell order doesn't fill when limit price > high"""
        # Setup mock data
        bar_data = pd.Series({
            "open": 149.0,
            "high": 150.5,  # limit price 152.0 > high 150.5, should not fill
            "low": 147.0,
            "close": 150.0,
            "volume": 1000000
        })
        
        self.data_loader.get_bar.return_value = bar_data
        self.data_loader.get_adv.return_value = 500000.0
        
        # Create limit sell order
        order = Order(
            date=pd.Timestamp("2023-01-02"),
            symbol="AAPL",
            side="SELL",
            qty=100,
            ref_price=150.0,
            order_type="LIMIT",
            limit_price=152.0
        )
        
        fills = self.execution_sim.fill_orders(pd.Timestamp("2023-01-02"), [order])
        
        self.assertEqual(len(fills), 0)  # Order should not fill
    
    def test_market_order_still_works(self):
        """Test that market orders still work with existing logic"""
        # Setup mock data
        bar_data = pd.Series({
            "open": 149.0,
            "high": 152.0,
            "low": 147.0,
            "close": 150.0,
            "volume": 1000000
        })
        
        self.data_loader.get_bar.return_value = bar_data
        self.data_loader.get_adv.return_value = 500000.0
        
        # Create market order
        order = Order(
            date=pd.Timestamp("2023-01-02"),
            symbol="AAPL",
            side="BUY",
            qty=100,
            ref_price=150.0,
            order_type="MARKET"
        )
        
        fills = self.execution_sim.fill_orders(pd.Timestamp("2023-01-02"), [order])
        
        self.assertEqual(len(fills), 1)
        fill = fills[0]
        self.assertEqual(fill.symbol, "AAPL")
        self.assertEqual(fill.side, "BUY")
        self.assertEqual(fill.qty, 100)
        self.assertEqual(fill.order_type, "MARKET")
        # Market order should have slippage and use base fill price logic
        self.assertNotEqual(fill.slippage, 0.0)
    
    def test_mixed_order_types(self):
        """Test execution of both market and limit orders together"""
        # Setup mock data
        bar_data = pd.Series({
            "open": 149.0,
            "high": 152.0,
            "low": 147.0,
            "close": 150.0,
            "volume": 1000000
        })
        
        self.data_loader.get_bar.return_value = bar_data
        self.data_loader.get_adv.return_value = 500000.0
        
        # Create mixed orders
        market_order = Order(
            date=pd.Timestamp("2023-01-02"),
            symbol="AAPL",
            side="BUY",
            qty=100,
            ref_price=150.0,
            order_type="MARKET"
        )
        
        limit_order = Order(
            date=pd.Timestamp("2023-01-02"),
            symbol="MSFT",
            side="SELL",
            qty=50,
            ref_price=200.0,
            order_type="LIMIT",
            limit_price=201.0
        )
        
        # Mock different bars for different symbols
        def mock_get_bar(date, symbol):
            if symbol == "AAPL":
                return bar_data
            elif symbol == "MSFT":
                return pd.Series({
                    "open": 199.0,
                    "high": 202.0,  # limit 201.0 <= high 202.0, should fill
                    "low": 197.0,
                    "close": 200.0,
                    "volume": 800000
                })
        
        self.data_loader.get_bar.side_effect = mock_get_bar
        
        fills = self.execution_sim.fill_orders(pd.Timestamp("2023-01-02"), [market_order, limit_order])
        
        self.assertEqual(len(fills), 2)
        
        # Check market order fill
        market_fill = next(f for f in fills if f.symbol == "AAPL")
        self.assertEqual(market_fill.order_type, "MARKET")
        self.assertNotEqual(market_fill.slippage, 0.0)
        
        # Check limit order fill
        limit_fill = next(f for f in fills if f.symbol == "MSFT")
        self.assertEqual(limit_fill.order_type, "LIMIT")
        self.assertEqual(limit_fill.fill_price, 201.0)
        self.assertEqual(limit_fill.slippage, 0.0)


class TestSignalFunctionInterface(unittest.TestCase):
    """Test the enhanced signal function interface"""
    
    def test_backward_compatibility_weights_only(self):
        """Test that old signal functions returning only weights still work"""
        def old_signal_function(date, df_today, df_prev, portfolio):
            return {"AAPL": 0.5, "MSFT": 0.5}
        
        # Mock the scenario from run.py
        signal_result = old_signal_function(None, None, None, None)
        
        # Test the interface detection logic from run.py
        if isinstance(signal_result, tuple) and len(signal_result) == 2:
            weights, order_specs = signal_result
        else:
            weights = signal_result
            order_specs = None
        
        self.assertEqual(weights, {"AAPL": 0.5, "MSFT": 0.5})
        self.assertIsNone(order_specs)
    
    def test_new_interface_with_order_specs(self):
        """Test new signal functions returning weights and order specs"""
        def new_signal_function(date, df_today, df_prev, portfolio):
            weights = {"AAPL": 0.6, "MSFT": 0.4}
            order_specs = {
                "AAPL": {"order_type": "LIMIT", "limit_price": 148.0},
                "MSFT": {"order_type": "MARKET"}
            }
            return weights, order_specs
        
        # Mock the scenario from run.py
        signal_result = new_signal_function(None, None, None, None)
        
        # Test the interface detection logic from run.py
        if isinstance(signal_result, tuple) and len(signal_result) == 2:
            weights, order_specs = signal_result
        else:
            weights = signal_result
            order_specs = None
        
        self.assertEqual(weights, {"AAPL": 0.6, "MSFT": 0.4})
        self.assertIsNotNone(order_specs)
        self.assertEqual(order_specs["AAPL"]["order_type"], "LIMIT")
        self.assertEqual(order_specs["AAPL"]["limit_price"], 148.0)
        self.assertEqual(order_specs["MSFT"]["order_type"], "MARKET")


if __name__ == "__main__":
    unittest.main()