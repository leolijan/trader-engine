"""Fetch resolved Polymarket markets and cache to parquet."""

import logging
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from trader_engine.ingestion.polymarket import PolymarketClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

if __name__ == "__main__":
    client = PolymarketClient()
    df = client.fetch_and_cache(target=600)
    print("\nDataset summary:")
    print(f"  Total markets: {len(df)}")
    print(f"  Resolved YES:  {df['resolved_yes'].sum()}")
    print(f"  Resolved NO:   {(~df['resolved_yes']).sum()}")
    print(f"  With T-1:      {df['price_t1'].drop_nulls().len()}")
    print(f"  With T-7:      {df['price_t7'].drop_nulls().len()}")
    print(f"  With T-30:     {df['price_t30'].drop_nulls().len()}")
    print("\nCategories:")
    print(df.group_by("category").agg(pl.len().alias("n")).sort("n", descending=True))
