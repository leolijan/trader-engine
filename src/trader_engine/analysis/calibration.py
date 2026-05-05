"""Calibration analysis: bins, Brier scores, Hosmer-Lemeshow test, bootstrap CIs."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import polars as pl
from numpy.typing import NDArray
from scipy import stats

logger = logging.getLogger(__name__)

LOOKBACKS: list[Literal["t1", "t7", "t30"]] = ["t1", "t7", "t30"]
BIN_EDGES = np.linspace(0, 1, 21)  # 20 bins of width 0.05
BIN_CENTERS = (BIN_EDGES[:-1] + BIN_EDGES[1:]) / 2
N_BOOTSTRAP = 2_000
RNG = np.random.default_rng(42)


@dataclass
class BinStats:
    center: float
    predicted_mean: float
    actual_rate: float
    n: int
    ci_low: float
    ci_high: float


@dataclass
class CalibrationResult:
    lookback: str
    n_markets: int
    brier_score: float
    brier_ci: tuple[float, float]
    log_score: float
    hl_stat: float
    hl_pvalue: float
    bins: list[BinStats]
    by_category: dict[str, dict[str, float]] = field(default_factory=dict)


class CalibrationAnalyzer:
    def __init__(self, df: pl.DataFrame) -> None:
        self.df = df

    def run_all(self) -> dict[str, CalibrationResult]:
        results: dict[str, CalibrationResult] = {}
        for lb in LOOKBACKS:
            col = f"price_{lb}"
            if col not in self.df.columns:
                continue
            sub = self.df.drop_nulls(col)
            if len(sub) < 30:
                logger.warning("Too few markets for lookback %s (%d)", lb, len(sub))
                continue
            results[lb] = self._analyze(sub, col, lb)
        return results

    # ------------------------------------------------------------------

    def _analyze(self, df: pl.DataFrame, col: str, lb: str) -> CalibrationResult:
        prices = df[col].to_numpy()
        actuals = df["resolved_yes"].cast(pl.Float64).to_numpy()

        brier = float(np.mean((prices - actuals) ** 2))
        brier_ci = self._bootstrap_brier(prices, actuals)
        log_sc = self._log_score(prices, actuals)

        bin_stats = self._bin_stats(prices, actuals)
        hl_stat, hl_p = self._hosmer_lemeshow(bin_stats)

        by_cat: dict[str, dict[str, float]] = {}
        if "category" in df.columns:
            for cat in df["category"].unique().to_list():
                sub = df.filter(pl.col("category") == cat)
                if len(sub) < 10:
                    continue
                p = sub[col].to_numpy()
                a = sub["resolved_yes"].cast(pl.Float64).to_numpy()
                by_cat[cat] = {
                    "n": float(len(sub)),
                    "brier": float(np.mean((p - a) ** 2)),
                    "mean_price": float(np.mean(p)),
                    "actual_rate": float(np.mean(a)),
                }

        return CalibrationResult(
            lookback=lb,
            n_markets=len(df),
            brier_score=brier,
            brier_ci=brier_ci,
            log_score=log_sc,
            hl_stat=hl_stat,
            hl_pvalue=hl_p,
            bins=bin_stats,
            by_category=by_cat,
        )

    def _bin_stats(self, prices: NDArray[Any], actuals: NDArray[Any]) -> list[BinStats]:
        bin_indices = np.digitize(prices, BIN_EDGES) - 1
        bin_indices = np.clip(bin_indices, 0, len(BIN_CENTERS) - 1)
        result = []
        for i, center in enumerate(BIN_CENTERS):
            mask = bin_indices == i
            n = int(mask.sum())
            if n == 0:
                continue
            pred_mean = float(prices[mask].mean())
            actual_rate = float(actuals[mask].mean())
            # Wilson confidence interval for actual rate
            ci = stats.proportion_confint(int(actuals[mask].sum()), n, alpha=0.05, method="wilson")
            result.append(
                BinStats(
                    center=center,
                    predicted_mean=pred_mean,
                    actual_rate=actual_rate,
                    n=n,
                    ci_low=float(ci[0]),
                    ci_high=float(ci[1]),
                )
            )
        return result

    def _hosmer_lemeshow(self, bins: list[BinStats]) -> tuple[float, float]:
        """Hosmer-Lemeshow chi-squared test across calibration bins."""
        hl = 0.0
        for b in bins:
            if b.n == 0:
                continue
            obs_yes = b.actual_rate * b.n
            obs_no = b.n - obs_yes
            exp_yes = b.predicted_mean * b.n
            exp_no = b.n - exp_yes
            if exp_yes > 0:
                hl += (obs_yes - exp_yes) ** 2 / exp_yes
            if exp_no > 0:
                hl += (obs_no - exp_no) ** 2 / exp_no
        df_hl = max(1, len(bins) - 2)
        p = float(1 - stats.chi2.cdf(hl, df_hl))
        return float(hl), p

    def _bootstrap_brier(self, prices: NDArray[Any], actuals: NDArray[Any]) -> tuple[float, float]:
        n = len(prices)
        scores = np.empty(N_BOOTSTRAP)
        for i in range(N_BOOTSTRAP):
            idx = RNG.integers(0, n, size=n)
            scores[i] = np.mean((prices[idx] - actuals[idx]) ** 2)
        return (float(np.percentile(scores, 2.5)), float(np.percentile(scores, 97.5)))

    @staticmethod
    def _log_score(prices: NDArray[Any], actuals: NDArray[Any]) -> float:
        eps = 1e-6
        p = np.clip(prices, eps, 1 - eps)
        return float(np.mean(actuals * np.log(p) + (1 - actuals) * np.log(1 - p)))
