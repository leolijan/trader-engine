"""Fetch all resolved sports markets and cache to parquet."""

import logging
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from trader_engine.ingestion.sports import SportsClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

if __name__ == "__main__":
    client = SportsClient()
    df = client.fetch_and_cache()

    print("\nSports dataset summary:")
    print(f"  Total markets:   {len(df)}")
    print(f"  With T-1 price:  {df['price_t1'].drop_nulls().len()}")
    print(f"  With T-7 price:  {df['price_t7'].drop_nulls().len()}")
    print(f"  Resolved YES:    {df['resolved_yes'].sum()}")
    print(f"  Resolved NO:     {(~df['resolved_yes']).sum()}")
    print(f"  YES rate:        {df['resolved_yes'].mean():.3f}")
    print("\nBy sport type:")
    print(
        df.group_by("sport_type")
        .agg([pl.len().alias("n"), pl.col("resolved_yes").mean().alias("yes_rate")])
        .sort("n", descending=True)
    )
    print(f"\nDate range: {df['end_date'].min()} to {df['end_date'].max()}")
