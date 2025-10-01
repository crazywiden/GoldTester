from backtest.utils import get_all_trading_days

def test_get_all_trading_days():
    start_date = "2025-09-01"
    end_date = "2025-10-05"
    print(get_all_trading_days(start_date, end_date))
    
    
if __name__ == "__main__":
    test_get_all_trading_days()