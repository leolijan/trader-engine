"""Polymarket data ingestion — resolves calibration data from the Gamma and CLOB APIs."""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import polars as pl
from pydantic import ValidationError

from trader_engine.schemas.market import Market, MarketOutcome

logger = logging.getLogger(__name__)

GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"
CACHE_DIR = Path("data/cache")

T1 = 86_400
T7 = 7 * 86_400
T30 = 30 * 86_400

# Minimum market duration to be included (seconds)
MIN_DURATION_T1 = T1
MIN_DURATION_T7 = T7
MIN_DURATION_T30 = T30


def _infer_category(raw: dict[str, Any]) -> str:
    cat = raw.get("category") or ""
    if cat:
        return cat.lower()
    events = raw.get("events") or []
    if events and isinstance(events, list):
        tag = events[0].get("category") or events[0].get("tag") or ""
        if tag:
            return str(tag).lower()
    q = (raw.get("question") or "").lower()
    for kw, label in [
        ("bitcoin", "crypto"),
        ("ethereum", "crypto"),
        ("btc", "crypto"),
        ("eth ", "crypto"),
        ("solana", "crypto"),
        ("doge", "crypto"),
        ("crypto", "crypto"),
        ("token", "crypto"),
        ("election", "politics"),
        ("president", "politics"),
        ("senate", "politics"),
        ("congress", "politics"),
        ("vote", "politics"),
        ("trump", "politics"),
        ("harris", "politics"),
        ("biden", "politics"),
        ("democrat", "politics"),
        ("republican", "politics"),
        ("poll", "politics"),
        ("nba", "sports"),
        ("nfl", "sports"),
        ("soccer", "sports"),
        ("tennis", "sports"),
        ("ufc", "sports"),
        ("game", "sports"),
        ("match", "sports"),
        ("league", "sports"),
        ("nhl", "sports"),
        ("mlb", "sports"),
        ("championship", "sports"),
        ("gdp", "economics"),
        ("inflation", "economics"),
        ("fed", "economics"),
        ("interest rate", "economics"),
        ("cpi", "economics"),
        ("jobs", "economics"),
        ("unemployment", "economics"),
        ("recession", "economics"),
        ("temperature", "weather"),
        ("rain", "weather"),
        ("weather", "weather"),
        ("celsius", "weather"),
        ("fahrenheit", "weather"),
    ]:
        if kw in q:
            return label
    return "other"


def _pick_price_at(history: list[dict[str, Any]], target_ts: int) -> float | None:
    """Binary search for last price at or before target_ts."""
    lo, hi = 0, len(history) - 1
    result: float | None = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if history[mid]["t"] <= target_ts:
            result = history[mid]["p"]
            lo = mid + 1
        else:
            hi = mid - 1
    return result


def _parse_timestamps(raw: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    closed_str = raw.get("closedTime") or raw.get("endDate") or ""
    start_str = raw.get("startDate") or raw.get("createdAt") or ""
    try:
        end_dt = datetime.fromisoformat(closed_str.replace("+00", "+00:00").replace("Z", "+00:00"))
    except ValueError:
        return None, None
    try:
        start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00").replace("+00", "+00:00"))
    except ValueError:
        start_dt = end_dt - timedelta(days=1)
    return start_dt, end_dt


def _parse_market(raw: dict[str, Any], history: list[dict[str, Any]]) -> Market | None:
    try:
        outcomes_raw = json.loads(raw.get("outcomes", "[]"))
        prices_raw = json.loads(raw.get("outcomePrices", "[]"))
        clob_ids = json.loads(raw.get("clobTokenIds", "[]"))
    except (json.JSONDecodeError, TypeError):
        return None

    if len(outcomes_raw) != 2 or len(prices_raw) != 2 or not clob_ids:
        return None

    try:
        p0, p1 = float(prices_raw[0]), float(prices_raw[1])
    except (ValueError, TypeError):
        return None

    if not ((p0 >= 0.99 and p1 <= 0.01) or (p0 <= 0.01 and p1 >= 0.99)):
        return None

    outcome = MarketOutcome.YES if p0 >= 0.99 else MarketOutcome.NO

    start_dt, end_dt = _parse_timestamps(raw)
    if start_dt is None or end_dt is None:
        return None

    close_ts = int(end_dt.timestamp())
    price_t1 = _pick_price_at(history, close_ts - T1)
    price_t7 = _pick_price_at(history, close_ts - T7)
    price_t30 = _pick_price_at(history, close_ts - T30)

    try:
        return Market(
            condition_id=raw.get("conditionId", raw.get("id", "")),
            question=raw.get("question", ""),
            category=_infer_category(raw),
            start_date=start_dt,
            end_date=end_dt,
            volume_usd=float(raw.get("volumeNum", 0)),
            outcome=outcome,
            price_t1=price_t1,
            price_t7=price_t7,
            price_t30=price_t30,
        )
    except ValidationError:
        return None


class PolymarketClient:
    def __init__(self, cache_dir: Path = CACHE_DIR) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_and_cache(self, target: int = 600) -> pl.DataFrame:
        parquet_path = self.cache_dir / "markets.parquet"
        if parquet_path.exists():
            logger.info("Loading cached markets from %s", parquet_path)
            return pl.read_parquet(parquet_path)

        markets = asyncio.run(self._collect(target))
        df = self._to_dataframe(markets)
        df.write_parquet(parquet_path)
        logger.info("Cached %d markets to %s", len(df), parquet_path)
        return df

    async def _collect(self, target: int) -> list[Market]:
        # Fetch raw markets in multiple passes with different strategies
        raws: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30) as client:
            # Pass 1: high-volume markets (any duration)
            for offset in range(0, 2000, 500):
                batch = await self._fetch_page(client, limit=500, offset=offset, min_vol=500)
                raws.extend(batch)

            # Pass 2: older markets sorted by end date (more likely long-running)
            for offset in range(0, 2000, 500):
                batch = await self._fetch_page(
                    client, limit=500, offset=offset, min_vol=100, order="endDate", ascending=False
                )
                raws.extend(batch)

        # Deduplicate by conditionId
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for r in raws:
            key = r.get("conditionId") or r.get("id") or ""
            if key and key not in seen:
                seen.add(key)
                unique.append(r)

        logger.info("Fetched %d unique raw markets", len(unique))

        # Process concurrently
        sem = asyncio.Semaphore(25)
        async with httpx.AsyncClient(timeout=30) as client:
            tasks = [self._process_market(client, sem, raw) for raw in unique]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        markets = [r for r in results if isinstance(r, Market)]
        logger.info("Parsed %d valid markets", len(markets))
        return markets

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        limit: int,
        offset: int,
        min_vol: float,
        order: str = "volume",
        ascending: bool = False,
    ) -> list[dict[str, Any]]:
        str_params: dict[str, str] = {
            "closed": "true",
            "limit": str(limit),
            "offset": str(offset),
            "order": order,
            "ascending": str(ascending).lower(),
        }
        try:
            r = await client.get(f"{GAMMA_URL}/markets", params=str_params)
            r.raise_for_status()
            return [m for m in r.json() if float(m.get("volumeNum", 0)) >= min_vol]
        except Exception as e:
            logger.warning("Page fetch failed offset=%d: %s", offset, e)
            return []

    async def _process_market(
        self, client: httpx.AsyncClient, sem: asyncio.Semaphore, raw: dict[str, Any]
    ) -> Market | None:
        try:
            clob_ids = json.loads(raw.get("clobTokenIds", "[]"))
        except (json.JSONDecodeError, TypeError):
            return None
        if not clob_ids:
            return None

        # Skip markets that were clearly too short for any useful data
        start_dt, end_dt = _parse_timestamps(raw)
        if start_dt is None or end_dt is None:
            return None
        duration = (end_dt - start_dt).total_seconds()
        if duration < T1:
            return None  # shorter than 1 day — not useful

        async with sem:
            history = await self._fetch_history(client, clob_ids[0])

        return _parse_market(raw, history)

    async def _fetch_history(
        self, client: httpx.AsyncClient, token_id: str
    ) -> list[dict[str, Any]]:
        # Try fidelity levels from coarse to fine; coarse covers long markets, fine covers short
        for fidelity in ("1440", "60", "1"):
            params = {"market": token_id, "interval": "max", "fidelity": fidelity}
            try:
                r = await client.get(f"{CLOB_URL}/prices-history", params=params)
                r.raise_for_status()
                hist: list[dict[str, Any]] = r.json().get("history", [])
                if hist:
                    return hist
            except Exception as e:
                logger.debug(
                    "Price history fidelity=%s failed for %s: %s", fidelity, token_id[:20], e
                )
        return []

    @staticmethod
    def _to_dataframe(markets: list[Market]) -> pl.DataFrame:
        rows = [
            {
                "condition_id": m.condition_id,
                "question": m.question,
                "category": m.category,
                "start_date": m.start_date,
                "end_date": m.end_date,
                "volume_usd": m.volume_usd,
                "resolved_yes": m.resolved_yes,
                "price_t1": m.price_t1,
                "price_t7": m.price_t7,
                "price_t30": m.price_t30,
            }
            for m in markets
        ]
        return pl.DataFrame(rows)
