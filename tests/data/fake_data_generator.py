import os
import datetime
import pandas as pd
import numpy as np

def generate_fake_stock_data(start_date, end_date, num_tickers, output_path):
    """
    Generates a DataFrame of fake stock data and saves it to a CSV file.

    Args:
        start_date (str): The start date in 'YYYY-MM-DD' format.
        end_date (str): The end date in 'YYYY-MM-DD' format.
        num_tickers (int): The number of stock tickers to generate.
        output_path (str): The path to save the output CSV file.
    """
    dates = pd.date_range(start=start_date, end=end_date)
    tickers = [f"TICKER_{i:03d}" for i in range(num_tickers)]

    all_data = []

    for ticker in tickers:
        # Simulate a random walk for the close price
        initial_price = np.random.uniform(20, 500)
        daily_returns = np.random.normal(0.0005, 0.02, len(dates))
        close_prices = initial_price * (1 + daily_returns).cumprod()

        # Generate open, high, low based on close
        open_prices = close_prices / (1 + np.random.normal(0, 0.01, len(dates)))
        
        # Ensure high is the highest and low is the lowest
        price_max = np.maximum(open_prices, close_prices)
        price_min = np.minimum(open_prices, close_prices)
        
        high_prices = price_max * (1 + np.random.uniform(0, 0.02, len(dates)))
        low_prices = price_min * (1 - np.random.uniform(0, 0.02, len(dates)))

        # Generate volume
        volumes = np.random.lognormal(mean=12, sigma=1.5, size=len(dates)).astype(int)

        ticker_df = pd.DataFrame({
            'date': dates,
            'symbol': ticker,
            'open': open_prices,
            'close': close_prices,
            'adjusted_close': close_prices,
            'high': high_prices,
            'low': low_prices,
            'volume': volumes
        })
        all_data.append(ticker_df)

    # Combine all ticker data into a single DataFrame
    df = pd.concat(all_data, ignore_index=True)

    # Save to CSV
    df.to_csv(output_path, index=False)
    print(f"Fake data generated and saved to {output_path}")


def generate_fake_halts_data(start_date, end_date, ticker_list, output_path, halt_prob=0.001):
    """
    Generates a DataFrame of fake halts data and
    saves it to a CSV file. Once a stock is halted, it cannot be relisted.

    Args:
        start_date (str): The start date in 'YYYY-MM-DD' format.
        end_date (str): The end date in 'YYYY-MM-DD' format.
        ticker_list (list): The list of stock tickers.
        output_path (str): The path to save the output CSV file.
        halt_prob (float): Daily probability of a stock being halted.
    """
    dates = pd.date_range(start=start_date, end=end_date)
    halt_data = []
    
    for ticker in ticker_list:
        halted = False
        for date in dates:
            if not halted and np.random.rand() < halt_prob:
                halted = True
            
            halt_data.append({'date': date, 'symbol': ticker, 'halt': halted})

    df = pd.DataFrame(halt_data)
    df.to_csv(output_path, index=False)
    print(f"Fake halts data generated and saved to {output_path}")


if __name__ == "__main__":
    start_date = "2024-01-01"
    end_date = "2024-06-01"
    num_tickers = 100
    folder_path = "tests/data"
    
    # Generate stock data
    output_csv_name = "fake_100_stock_20240101_20240601.csv"
    output_csv_path = os.path.join(folder_path, output_csv_name)
    generate_fake_stock_data(start_date, end_date, num_tickers, output_csv_path)

    # Generate halts data
    tickers = [f"TICKER_{i:03d}" for i in range(num_tickers)]
    halts_output_csv_name = "fake_100_halts_20240101_20240601.csv"
    halts_output_csv_path = os.path.join(folder_path, halts_output_csv_name)
    generate_fake_halts_data(start_date, end_date, tickers, halts_output_csv_path)
