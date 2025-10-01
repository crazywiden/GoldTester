import os
import pandas as pd
from typing import Optional



def get_date_range(
    input_path: str,
    output_path: str,
    start_date: str,
    end_date: str
):
    print(f"Reading from {input_path}...")
    df = pd.read_csv(input_path)

    print("Filtering data to be >= 2010")
    df['date'] = pd.to_datetime(
        df["date"],
        errors="coerce",
        utc=True,
    ).dt.tz_convert("America/New_York")
    df = df[df['date'] >= start_date]
    df = df[df['date'] <= end_date]
    df = df.rename(columns={'ticker': 'symbol'})

    print(f"Writing date range of shape {df.shape} to {output_path}...")
    df.to_csv(output_path, index=False)
    print("Done.")

if __name__ == "__main__":
    root_path = "/Users/widen/Documents/study/quant"
    input_path = os.path.join(root_path, "consolidated_raw_data_beyond_2b_enough_data.csv")
    output_path = os.path.join(root_path, "consolidated_raw_data_20250101_20251001.csv")

    start_date = "2025-01-01"
    end_date = "2025-10-01"
    get_date_range(
        input_path=input_path,
        output_path=output_path,
        start_date=start_date,
        end_date=end_date,
    )


