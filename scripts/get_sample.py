import os
import pandas as pd
from typing import Optional



def sample_csv(
    input_path: str,
    output_path: str,
    sample_ratio: float,
    seed: int = 42,
    sample_by_column: Optional[str] = None
):
    print(f"Reading from {input_path}...")
    df = pd.read_csv(input_path)

    if sample_by_column:
        unique_values = df[sample_by_column].unique()
        n_unique = len(unique_values)
        n_to_sample = int(n_unique * sample_ratio)

        if n_to_sample == 0 and n_unique > 0:
            n_to_sample = 1

        print(f"Found {n_unique} unique values in column '{sample_by_column}'.")
        print(f"Sampling {n_to_sample} unique values (ratio: {sample_ratio})...")

        # Sample the unique values
        sampled_keys = pd.Series(unique_values).sample(n=n_to_sample, random_state=seed)

        # Filter the dataframe
        sample_df = df[df[sample_by_column].isin(sampled_keys)]
    else:
        n = int(len(df) * sample_ratio)
        print(f"Sampling {n} rows, sample ratio: {sample_ratio}")
        sample_df = df.sample(n=n, random_state=seed)
    
    print(f"Writing sample of shape {sample_df.shape} to {output_path}...")
    sample_df.dropna(subset=['date'], inplace=True)
    sample_df.to_csv(output_path, index=False)
    print("Done.")


if __name__ == "__main__":
    input_path = "/Users/widen/Documents/study/quant/consolidated_raw_data_beyond_2b_enough_data.csv"
    output_path = "/Users/widen/Documents/study/quant/consolidated_raw_data_0_01_sample_by_ticker.csv"

    sample_csv(
        input_path=input_path,
        output_path=output_path,
        sample_ratio=0.01,
        seed=42,
        sample_by_column="ticker"
    )


