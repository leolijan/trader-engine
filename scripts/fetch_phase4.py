"""Phase 4: Fetch resolved binary markets across all Polymarket categories.

Covers late 2025 – May 2026. Saves per-category parquet files to data/cache/.
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import polars as pl

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
CACHE = Path("data/cache")
CACHE.mkdir(parents=True, exist_ok=True)

T1 = 86_400  # seconds in a day

# ── Category definitions ────────────────────────────────────────────────────
# Each entry: (cache_name, fetch_params, min_volume, max_duration_days)
# fetch_params passed directly to /markets endpoint
CATEGORIES: list[dict[str, Any]] = [
    {
        "name": "sports_soccer",
        "params": {"closed": "true", "category": "Soccer"},
        "min_vol": 500,
        "max_dur": 14,
        "max_markets": 2000,
    },
    {
        "name": "sports_basketball",
        "params": {"closed": "true", "category": "Basketball"},
        "min_vol": 500,
        "max_dur": 14,
        "max_markets": 2000,
    },
    {
        "name": "sports_esports",
        "params": {"closed": "true", "category": "Esports"},
        "min_vol": 200,
        "max_dur": 14,
        "max_markets": 2000,
    },
    {
        "name": "sports_tennis",
        "params": {"closed": "true", "category": "Tennis"},
        "min_vol": 200,
        "max_dur": 14,
        "max_markets": 2000,
    },
    {
        "name": "sports_baseball",
        "params": {"closed": "true", "category": "Baseball"},
        "min_vol": 200,
        "max_dur": 7,
        "max_markets": 2000,
    },
    {
        "name": "sports_golf",
        "params": {"closed": "true", "category": "Golf"},
        "min_vol": 200,
        "max_dur": 30,
        "max_markets": 500,
    },
    {
        "name": "politics_elections",
        "params": {"closed": "true", "category": "Elections"},
        "min_vol": 500,
        "max_dur": 365,
        "max_markets": 1000,
    },
    {
        "name": "politics_us",
        "params": {"closed": "true", "category": "US politics"},
        "min_vol": 500,
        "max_dur": 365,
        "max_markets": 1000,
    },
    {
        "name": "politics_global",
        "params": {"closed": "true", "category": "Global Politics"},
        "min_vol": 500,
        "max_dur": 365,
        "max_markets": 1000,
    },
    {
        "name": "crypto",
        "params": {"closed": "true", "category": "Crypto"},
        "min_vol": 1000,
        "max_dur": 30,
        "max_markets": 2000,
    },
    {
        "name": "finance",
        "params": {"closed": "true", "category": "Finance"},
        "min_vol": 500,
        "max_dur": 60,
        "max_markets": 1000,
    },
    {
        "name": "ai_tech",
        "params": {"closed": "true", "category": "AI"},
        "min_vol": 200,
        "max_dur": 365,
        "max_markets": 500,
    },
    {
        "name": "pop_culture",
        "params": {"closed": "true", "category": "Pop Culture"},
        "min_vol": 200,
        "max_dur": 90,
        "max_markets": 500,
    },
    {
        "name": "science",
        "params": {"closed": "true", "category": "Science"},
        "min_vol": 200,
        "max_dur": 365,
        "max_markets": 500,
    },
]

CUTOFF_DATE = "2025-07-01"  # only markets closing after this


# ── Helpers ─────────────────────────────────────────────────────────────────


def parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    s = str(s).replace("Z", "+00:00").replace("+00:00:00", "+00:00")
    # Handle "+00" without seconds
    if s.endswith("+00") and len(s) == 22:
        s = s + ":00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def pick_price_at(history: list[dict[str, Any]], target_ts: int) -> float | None:
    lo, hi, result = 0, len(history) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if history[mid]["t"] <= target_ts:
            result = float(history[mid]["p"])
            lo = mid + 1
        else:
            hi = mid - 1
    return result


async def fetch_history(client: httpx.AsyncClient, token_id: str) -> list[dict[str, Any]]:
    for fidelity in ("60", "1"):
        try:
            r = await client.get(
                f"{CLOB}/prices-history",
                params={"market": token_id, "interval": "max", "fidelity": fidelity},
            )
            r.raise_for_status()
            hist: list[dict[str, Any]] = r.json().get("history", [])
            if hist:
                return hist
        except Exception:
            pass
    return []


async def process_market(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    raw: dict[str, Any],
    category_name: str,
) -> dict[str, Any] | None:
    try:
        prices_raw = json.loads(raw.get("outcomePrices", "[]"))
        clob_ids = json.loads(raw.get("clobTokenIds", "[]"))
        if len(prices_raw) != 2 or not clob_ids:
            return None
        p0, p1 = float(prices_raw[0]), float(prices_raw[1])
        if not ((p0 >= 0.99 and p1 <= 0.01) or (p0 <= 0.01 and p1 >= 0.99)):
            return None
        resolved_yes = p0 >= 0.99

        end_dt = parse_dt(raw.get("closedTime") or raw.get("endDate") or "")
        start_dt = parse_dt(raw.get("startDate") or raw.get("createdAt") or "")
        if end_dt is None:
            return None
        if start_dt is None:
            return None

        duration = (end_dt - start_dt).total_seconds() / 86400
        if duration < 0.25:
            return None

        close_ts = int(end_dt.timestamp())

        async with sem:
            history = await fetch_history(client, str(clob_ids[0]))

        price_t1 = pick_price_at(history, close_ts - T1)
        if price_t1 is None and history:
            price_t1 = float(history[0]["p"])

        return {
            "condition_id": str(raw.get("conditionId") or raw.get("id") or ""),
            "question": str(raw.get("question") or ""),
            "category": category_name,
            "volume_usd": float(raw.get("volumeNum") or 0),
            "duration_days": duration,
            "resolved_yes": resolved_yes,
            "price_t1": price_t1,
            "close_date": end_dt.date().isoformat(),
        }
    except Exception:
        return None


async def fetch_category(cat: dict[str, Any]) -> list[dict[str, Any]]:
    name = cat["name"]
    params_base = cat["params"]
    min_vol = cat["min_vol"]
    max_dur = cat["max_dur"]
    max_markets = cat["max_markets"]

    raw_markets: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30) as client:
        for offset in range(0, 500_000, 100):
            params = {
                **params_base,
                "limit": "100",
                "offset": str(offset),
                "order": "closedTime",
                "ascending": "false",
                "volumeNum_min": str(min_vol),
            }
            try:
                r = await client.get(f"{GAMMA}/markets", params=params)
                r.raise_for_status()
                batch: list[dict[str, Any]] = r.json()
            except Exception as e:
                logger.warning("%s: page error at offset=%d: %s", name, offset, e)
                break
            if not isinstance(batch, list) or not batch:
                break
            raw_markets.extend(batch)
            oldest = batch[-1].get("closedTime") or batch[-1].get("endDate") or ""
            if oldest < CUTOFF_DATE:
                logger.info(
                    "%s: reached cutoff at offset=%d (oldest=%s)", name, offset, oldest[:10]
                )
                break
            if len(raw_markets) >= max_markets * 5:
                logger.info("%s: hit fetch ceiling at %d raw markets", name, len(raw_markets))
                break

    # Filter by cutoff and duration
    filtered = []
    for m in raw_markets:
        ct = m.get("closedTime") or m.get("endDate") or ""
        if ct < CUTOFF_DATE:
            continue
        start_dt = parse_dt(m.get("startDate") or "")
        end_dt = parse_dt(ct)
        if start_dt is None or end_dt is None:
            continue
        dur = (end_dt - start_dt).total_seconds() / 86400
        if dur < 0.25 or dur > max_dur:
            continue
        filtered.append(m)

    # Deduplicate
    seen: set[str] = set()
    unique = []
    for m in filtered:
        key = str(m.get("conditionId") or m.get("id") or "")
        if key and key not in seen:
            seen.add(key)
            unique.append(m)

    # Sample if too many
    if len(unique) > max_markets:
        import random

        random.seed(42)
        unique = random.sample(unique, max_markets)

    logger.info("%s: %d unique markets after filter, fetching CLOB prices...", name, len(unique))

    sem = asyncio.Semaphore(25)
    async with httpx.AsyncClient(timeout=30) as client:
        tasks = [process_market(client, sem, m, name) for m in unique]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    rows = [r for r in results if isinstance(r, dict)]
    logger.info("%s: %d markets with T-1 price", name, len(rows))
    return rows


def save_category(rows: list[dict[str, Any]], name: str) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame()
    schema = {
        "condition_id": pl.String,
        "question": pl.String,
        "category": pl.String,
        "volume_usd": pl.Float64,
        "duration_days": pl.Float64,
        "resolved_yes": pl.Boolean,
        "price_t1": pl.Float64,
        "close_date": pl.String,
    }
    df = pl.DataFrame(rows, schema=schema)
    path = CACHE / f"phase4_{name}.parquet"
    df.write_parquet(path)
    logger.info("Saved %d rows to %s", len(df), path)
    return df


async def main() -> None:
    all_frames: list[pl.DataFrame] = []
    for cat in CATEGORIES:
        name = cat["name"]
        path = CACHE / f"phase4_{name}.parquet"
        if path.exists():
            logger.info("%s: loading from cache", name)
            df = pl.read_parquet(path)
        else:
            rows = await fetch_category(cat)
            df = save_category(rows, name)
        if len(df) > 0:
            all_frames.append(df)

    if all_frames:
        combined = pl.concat(all_frames, how="diagonal")
        combined.write_parquet(CACHE / "phase4_all.parquet")
        logger.info("Combined: %d total rows across %d categories", len(combined), len(all_frames))

        print("\n=== PHASE 4 DATA SUMMARY ===")
        summary = (
            combined.group_by("category")
            .agg(
                [
                    pl.len().alias("n"),
                    pl.col("price_t1").drop_nulls().len().alias("with_price"),
                    pl.col("resolved_yes").mean().alias("yes_rate"),
                    pl.col("volume_usd").median().alias("med_vol"),
                    pl.col("duration_days").median().alias("med_dur"),
                ]
            )
            .sort("n", descending=True)
        )
        print(summary)


if __name__ == "__main__":
    asyncio.run(main())
