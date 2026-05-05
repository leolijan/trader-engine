"""Sports market ingestion via Polymarket Events API."""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import polars as pl

logger = logging.getLogger(__name__)

GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"
CACHE_DIR = Path("data/cache")

T1 = 86_400
T7 = 7 * 86_400

SPORT_KEYWORDS: list[tuple[str, str]] = [
    ("nba", "basketball"),
    ("basketball", "basketball"),
    ("nfl", "american_football"),
    ("american football", "american_football"),
    ("nhl", "hockey"),
    ("hockey", "hockey"),
    ("mlb", "baseball"),
    ("baseball", "baseball"),
    ("soccer", "soccer"),
    ("football", "soccer"),
    ("premier league", "soccer"),
    ("la liga", "soccer"),
    ("serie a", "soccer"),
    ("bundesliga", "soccer"),
    ("champions league", "soccer"),
    ("world cup", "soccer"),
    ("tennis", "tennis"),
    ("atp", "tennis"),
    ("wta", "tennis"),
    ("wimbledon", "tennis"),
    ("us open", "tennis"),
    ("french open", "tennis"),
    ("ufc", "combat_sports"),
    ("mma", "combat_sports"),
    ("boxing", "combat_sports"),
    ("wrestl", "combat_sports"),
    ("esports", "esports"),
    ("cs:", "esports"),
    ("counter-strike", "esports"),
    ("dota", "esports"),
    ("league of legends", "esports"),
    ("valorant", "esports"),
    ("lol", "esports"),
    ("f1", "motorsport"),
    ("formula 1", "motorsport"),
    ("nascar", "motorsport"),
    ("golf", "golf"),
    ("pga", "golf"),
]


def classify_sport(question: str) -> str:
    q = question.lower()
    for kw, sport in SPORT_KEYWORDS:
        if kw in q:
            return sport
    return "other_sports"


def _pick_price_at(history: list[dict[str, Any]], target_ts: int) -> float | None:
    lo, hi = 0, len(history) - 1
    result: float | None = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if history[mid]["t"] <= target_ts:
            result = float(history[mid]["p"])
            lo = mid + 1
        else:
            hi = mid - 1
    return result


def _parse_timestamps(raw: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    closed_str = raw.get("closedTime") or raw.get("endDate") or ""
    start_str = raw.get("startDate") or raw.get("createdAt") or ""
    try:
        end_dt = datetime.fromisoformat(
            str(closed_str).replace("+00", "+00:00").replace("Z", "+00:00")
        )
    except ValueError:
        return None, None
    try:
        start_dt = datetime.fromisoformat(
            str(start_str).replace("Z", "+00:00").replace("+00", "+00:00")
        )
    except ValueError:
        start_dt = end_dt - timedelta(days=1)
    return start_dt, end_dt


def _parse_market(raw: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any] | None:
    try:
        prices_raw = json.loads(raw.get("outcomePrices", "[]"))
        clob_ids = json.loads(raw.get("clobTokenIds", "[]"))
        outcomes_raw = json.loads(raw.get("outcomes", "[]"))
    except (json.JSONDecodeError, TypeError):
        return None

    if len(prices_raw) != 2 or len(outcomes_raw) != 2 or not clob_ids:
        return None

    try:
        p0, p1 = float(prices_raw[0]), float(prices_raw[1])
    except (ValueError, TypeError):
        return None

    if not ((p0 >= 0.99 and p1 <= 0.01) or (p0 <= 0.01 and p1 >= 0.99)):
        return None

    resolved_yes = p0 >= 0.99
    start_dt, end_dt = _parse_timestamps(raw)
    if start_dt is None or end_dt is None:
        return None

    duration_days = (end_dt - start_dt).total_seconds() / 86400
    if duration_days < 1.0:
        return None

    close_ts = int(end_dt.timestamp())
    question = str(raw.get("question", ""))

    return {
        "condition_id": str(raw.get("conditionId", raw.get("id", ""))),
        "question": question,
        "sport_type": classify_sport(question),
        "start_date": start_dt,
        "end_date": end_dt,
        "duration_days": duration_days,
        "volume_usd": float(raw.get("volumeNum", 0)),
        "resolved_yes": resolved_yes,
        "price_t1": _pick_price_at(history, close_ts - T1),
        "price_t7": _pick_price_at(history, close_ts - T7),
        "spread_proxy": _spread_proxy(history, close_ts - T1),
    }


def _spread_proxy(history: list[dict[str, Any]], around_ts: int) -> float | None:
    """Estimate spread as price range in the 4-hour window before target_ts."""
    window = 4 * 3600
    pts = [p["p"] for p in history if around_ts - window <= p["t"] <= around_ts + 3600]
    if len(pts) < 2:
        return None
    return float(max(pts) - min(pts))


class SportsClient:
    def __init__(self, cache_dir: Path = CACHE_DIR) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_and_cache(self, force: bool = False) -> pl.DataFrame:
        parquet_path = self.cache_dir / "sports_markets.parquet"
        if parquet_path.exists() and not force:
            logger.info("Loading cached sports markets from %s", parquet_path)
            return pl.read_parquet(parquet_path)

        rows = asyncio.run(self._collect())
        schema = {
            "condition_id": pl.String,
            "question": pl.String,
            "sport_type": pl.String,
            "start_date": pl.Datetime(time_zone="UTC"),
            "end_date": pl.Datetime(time_zone="UTC"),
            "duration_days": pl.Float64,
            "volume_usd": pl.Float64,
            "resolved_yes": pl.Boolean,
            "price_t1": pl.Float64,
            "price_t7": pl.Float64,
            "spread_proxy": pl.Float64,
        }
        df = pl.DataFrame(rows, schema=schema)
        df.write_parquet(parquet_path)
        logger.info("Cached %d sports markets to %s", len(df), parquet_path)
        return df

    async def _collect(self) -> list[dict[str, Any]]:
        raw_markets: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for offset in range(0, 10000, 100):
                batch = await self._fetch_events_page(client, offset)
                if not batch:
                    logger.info("Events exhausted at offset %d", offset)
                    break
                raw_markets.extend(batch)
                if len(raw_markets) > 15000:
                    break

        # Deduplicate
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for m in raw_markets:
            key = str(m.get("conditionId") or m.get("id") or "")
            if key and key not in seen:
                seen.add(key)
                unique.append(m)

        logger.info("Fetched %d unique sports market records", len(unique))

        sem = asyncio.Semaphore(30)
        async with httpx.AsyncClient(timeout=30) as client:
            tasks = [self._process(client, sem, m) for m in unique]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        rows = [r for r in results if isinstance(r, dict)]
        logger.info("Parsed %d valid sports markets", len(rows))
        return rows

    async def _fetch_events_page(
        self, client: httpx.AsyncClient, offset: int
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {
            "closed": "true",
            "category": "Sports",
            "limit": "100",
            "offset": str(offset),
        }
        try:
            r = await client.get(f"{GAMMA_URL}/events", params=params)
            r.raise_for_status()
            events = r.json()
            markets: list[dict[str, Any]] = []
            for ev in events:
                for m in ev.get("markets", []):
                    m["_event_title"] = ev.get("title", "")
                    markets.append(m)
            return markets
        except Exception as e:
            logger.warning("Events page offset=%d failed: %s", offset, e)
            return []

    async def _process(
        self, client: httpx.AsyncClient, sem: asyncio.Semaphore, raw: dict[str, Any]
    ) -> dict[str, Any] | None:
        try:
            clob_ids = json.loads(raw.get("clobTokenIds", "[]"))
        except (json.JSONDecodeError, TypeError):
            return None
        if not clob_ids:
            return None

        start_dt, end_dt = _parse_timestamps(raw)
        if start_dt is None or end_dt is None:
            return None
        if (end_dt - start_dt).total_seconds() < T1:
            return None

        async with sem:
            history = await self._fetch_history(client, str(clob_ids[0]))

        return _parse_market(raw, history)

    async def _fetch_history(
        self, client: httpx.AsyncClient, token_id: str
    ) -> list[dict[str, Any]]:
        for fidelity in ("1440", "60", "1"):
            params: dict[str, str] = {
                "market": token_id,
                "interval": "max",
                "fidelity": fidelity,
            }
            try:
                r = await client.get(f"{CLOB_URL}/prices-history", params=params)
                r.raise_for_status()
                hist: list[dict[str, Any]] = r.json().get("history", [])
                if hist:
                    return hist
            except Exception:
                pass
        return []
