"""Phase 3: Duration-controlled OOS validation of sports miscalibration edge.

Strategy: 2025 short-horizon sports markets are near-absent on Polymarket
(only 15 found vs 3,870 in 2024). Likely structural change in market offerings.

Fallback OOS design:
  - Filter to duration <= 14 days (short-horizon game-day markets)
  - Train: H1 2024 (Jan–Jun)
  - Test:  H2 2024 (Jul–Dec)
  - Secondary: 5-fold time-series cross-validation
  - 2025 (n=15) used as supplementary spot-check only
"""

import logging
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from scipy import stats
from statsmodels.stats.proportion import proportion_confint

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

FIGURES = Path("research/reports/figures")
FIGURES.mkdir(parents=True, exist_ok=True)

MAX_DURATION_DAYS = 14
BIN_EDGES = np.linspace(0, 1, 21)
N_BOOT = 3000
RNG = np.random.default_rng(42)

SPORT_LABELS = {
    "basketball": "Basketball",
    "soccer": "Soccer",
    "tennis": "Tennis",
    "american_football": "Am. Football",
    "hockey": "Hockey",
    "combat_sports": "Combat Sports",
    "esports": "Esports",
    "golf": "Golf",
    "other_sports": "Other Sports",
}


# ---------------------------------------------------------------------------
# Core metrics
# ---------------------------------------------------------------------------


def brier(p: np.ndarray, a: np.ndarray) -> float:
    return float(np.mean((p - a) ** 2))


def bootstrap_brier_ci(p: np.ndarray, a: np.ndarray) -> tuple[float, float]:
    n = len(p)
    scores = np.array([np.mean((p[i := RNG.integers(0, n, n)] - a[i]) ** 2) for _ in range(N_BOOT)])
    return float(np.percentile(scores, 2.5)), float(np.percentile(scores, 97.5))


def hl_pvalue(p: np.ndarray, a: np.ndarray) -> tuple[float, float]:
    idx = np.clip(np.digitize(p, BIN_EDGES) - 1, 0, len(BIN_EDGES) - 2)
    hl, dof = 0.0, 0
    for i in range(len(BIN_EDGES) - 1):
        m = idx == i
        n = int(m.sum())
        if n < 5:
            continue
        ey = p[m].mean() * n
        oy = a[m].sum()
        en = n - ey
        on = n - oy
        if ey > 0:
            hl += (oy - ey) ** 2 / ey
        if en > 0:
            hl += (on - en) ** 2 / en
        dof += 1
    pv = float(1 - stats.chi2.cdf(hl, max(1, dof - 2)))
    return float(hl), pv


def compute_bins(p: np.ndarray, a: np.ndarray) -> pl.DataFrame:
    idx = np.clip(np.digitize(p, BIN_EDGES) - 1, 0, len(BIN_EDGES) - 2)
    rows = []
    for i in range(len(BIN_EDGES) - 1):
        m = idx == i
        n = int(m.sum())
        if n == 0:
            continue
        pm = float(p[m].mean())
        am = float(a[m].mean())
        ci = proportion_confint(int(a[m].sum()), n, alpha=0.05, method="wilson")
        rows.append(
            {
                "bin": f"{BIN_EDGES[i]:.0%}–{BIN_EDGES[i+1]:.0%}",
                "pred": pm,
                "actual": am,
                "delta": am - pm,
                "gross_edge": abs(am - pm),
                "n": n,
                "ci_low": float(ci[0]),
                "ci_high": float(ci[1]),
            }
        )
    return pl.DataFrame(rows)


def summarise(df: pl.DataFrame, col: str = "price_t1") -> dict[str, Any]:
    sub = df.drop_nulls(col)
    if len(sub) < 20:
        return {
            "n": 0,
            "brier": float("nan"),
            "brier_ci": (float("nan"), float("nan")),
            "hl_p": float("nan"),
            "yes_rate": float("nan"),
            "bins": pl.DataFrame(),
        }
    p = sub[col].to_numpy()
    a = sub["resolved_yes"].cast(pl.Float64).to_numpy()
    bl, bh = bootstrap_brier_ci(p, a)
    _, hlp = hl_pvalue(p, a)
    return {
        "n": len(sub),
        "brier": brier(p, a),
        "brier_ci": (bl, bh),
        "hl_p": hlp,
        "yes_rate": float(a.mean()),
        "mean_price": float(p.mean()),
        "bins": compute_bins(p, a),
    }


# ---------------------------------------------------------------------------
# Bin persistence test
# ---------------------------------------------------------------------------


def bin_persistence(train_bins: pl.DataFrame, test_bins: pl.DataFrame) -> dict[str, Any]:
    """For each bin present in both splits, check if the edge direction is the same."""
    if len(train_bins) == 0 or len(test_bins) == 0:
        return {"n_shared": 0, "same_direction": 0, "pct_same": float("nan")}

    t_map = {r["bin"]: r["delta"] for r in train_bins.iter_rows(named=True)}
    same, total = 0, 0
    for row in test_bins.iter_rows(named=True):
        b = row["bin"]
        if b not in t_map or row["n"] < 5:
            continue
        total += 1
        if (t_map[b] < 0) == (row["delta"] < 0):
            same += 1
    return {
        "n_shared": total,
        "same_direction": same,
        "pct_same": same / total if total > 0 else float("nan"),
    }


# ---------------------------------------------------------------------------
# Time-series cross-validation
# ---------------------------------------------------------------------------


def ts_crossval(df: pl.DataFrame, col: str = "price_t1", n_folds: int = 5) -> pl.DataFrame:
    """Expanding-window time-series CV: train on first k/n, test on (k+1)/n."""
    sub = df.drop_nulls(col).sort("end_date")
    n = len(sub)
    step = n // (n_folds + 1)
    rows = []
    for fold in range(1, n_folds + 1):
        cutoff_idx = fold * step
        train_fold = sub[:cutoff_idx]
        test_fold = sub[cutoff_idx : cutoff_idx + step]
        if len(test_fold) < 20:
            continue
        tr = summarise(train_fold, col)
        te = summarise(test_fold, col)
        rows.append(
            {
                "fold": fold,
                "train_n": tr["n"],
                "train_brier": tr["brier"],
                "test_n": te["n"],
                "test_brier": te["brier"],
                "test_hl_p": te["hl_p"],
                "test_yes_rate": te["yes_rate"],
            }
        )
    return pl.DataFrame(rows)


# ---------------------------------------------------------------------------
# Kelly sizing
# ---------------------------------------------------------------------------


def kelly_sizing(
    bins: pl.DataFrame, spread: float = 0.02, bankroll: float = 10_000, trades_per_month: int = 50
) -> None:
    print(
        f"\n{'Bin':<12} {'Pred':>6} {'Act':>6} {'NetEdge':>9} "
        f"{'HalfKelly':>10} {'$/trade':>9} {'EV/mo':>9} {'n':>5}"
    )
    print("-" * 70)
    total_ev_month = 0.0
    for row in bins.iter_rows(named=True):
        ge = row["gross_edge"]
        ne = ge - spread
        if ne <= 0 or row["n"] < 10:
            continue
        p_t = row["actual"]
        p_m = row["pred"]
        if p_t < p_m:
            b = (1 - p_m) / p_m
            p_win = 1 - p_t
        else:
            b = p_m / (1 - p_m)
            p_win = p_t
        kf = max(0.0, (b * p_win - (1 - p_win)) / b)
        hk = kf / 2
        dollars = hk * bankroll
        ev_trade = ne * dollars
        ev_month = ev_trade * trades_per_month
        total_ev_month += ev_month
        print(
            f"{row['bin']:<12} {p_m:>6.3f} {p_t:>6.3f} "
            f"{ne:>+9.3f} {hk:>10.3f} {dollars:>9.0f} {ev_month:>+9.0f}"
        )
    print(
        f"\n  Estimated monthly EV at ${bankroll:,.0f} bankroll, "
        f"{trades_per_month} trades/mo: ${total_ev_month:+,.0f}"
    )


# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------


def plot_reliability_halves(h1: dict[str, Any], h2: dict[str, Any]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    fig.suptitle(
        "Short-Horizon Sports Markets — Reliability Diagram", fontsize=13, fontweight="bold"
    )
    for ax, d, label in [
        (axes[0], h1, "Train: H1 2024 (Jan–Jun)"),
        (axes[1], h2, "Test: H2 2024 (Jul–Dec)"),
    ]:
        bins_df = d["bins"]
        if len(bins_df) == 0:
            ax.text(0.5, 0.5, "No data", ha="center", va="center")
            continue
        pred = bins_df["pred"].to_numpy()
        actual = bins_df["actual"].to_numpy()
        ci_lo = np.clip(actual - bins_df["ci_low"].to_numpy(), 0, None)
        ci_hi = np.clip(bins_df["ci_high"].to_numpy() - actual, 0, None)
        ns = bins_df["n"].to_numpy()
        ax.plot([0, 1], [0, 1], "k--", lw=1, label="Perfect", zorder=1)
        ax.scatter(
            pred,
            actual,
            s=np.clip(ns * 3, 20, 300),
            c=actual,
            cmap="RdYlGn",
            vmin=0,
            vmax=1,
            zorder=3,
            edgecolors="black",
            linewidths=0.5,
        )
        ax.errorbar(
            pred, actual, yerr=[ci_lo, ci_hi], fmt="none", ecolor="gray", alpha=0.5, zorder=2
        )
        b = d["brier"]
        bl, bh = d["brier_ci"]
        ax.set_title(
            f"{label}\nn={d['n']:,}  Brier={b:.4f} [{bl:.4f},{bh:.4f}]  " f"HL p={d['hl_p']:.3f}",
            fontsize=9,
        )
        ax.set_xlim(-0.02, 1.02)
        ax.set_ylim(-0.02, 1.02)
        ax.set_xlabel("Predicted probability")
        if ax is axes[0]:
            ax.set_ylabel("Observed frequency")
        ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(FIGURES / "oos_reliability_h1_vs_h2.png", dpi=150, bbox_inches="tight")
    plt.close()
    logger.info("Saved oos_reliability_h1_vs_h2.png")


def plot_edge_persistence(train_bins: pl.DataFrame, test_bins: pl.DataFrame) -> None:
    if len(train_bins) == 0 or len(test_bins) == 0:
        return
    t_map = {r["bin"]: r for r in train_bins.iter_rows(named=True)}
    shared = [r for r in test_bins.iter_rows(named=True) if r["bin"] in t_map and r["n"] >= 5]
    if not shared:
        return
    labels = [r["bin"] for r in shared]
    train_d = [t_map[r["bin"]]["delta"] for r in shared]
    test_d = [r["delta"] for r in shared]
    x = np.arange(len(labels))
    w = 0.35
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.bar(
        x - w / 2,
        train_d,
        w,
        label="Train H1 2024",
        color="#4575b4",
        alpha=0.8,
        edgecolor="black",
        linewidth=0.4,
    )
    ax.bar(
        x + w / 2,
        test_d,
        w,
        label="Test H2 2024",
        color="#d73027",
        alpha=0.8,
        edgecolor="black",
        linewidth=0.4,
    )
    ax.axhline(0, color="black", lw=1)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=60, ha="right", fontsize=8)
    ax.set_ylabel("Actual − Predicted (miscalibration)")
    ax.set_title("Bin-Level Edge Persistence: H1 2024 (train) vs H2 2024 (test)")
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()
    plt.savefig(FIGURES / "oos_edge_persistence.png", dpi=150, bbox_inches="tight")
    plt.close()
    logger.info("Saved oos_edge_persistence.png")


def plot_ts_cv(cv_df: pl.DataFrame) -> None:
    if len(cv_df) == 0:
        return
    fig, ax = plt.subplots(figsize=(9, 4))
    x = cv_df["fold"].to_numpy()
    ax.plot(
        x,
        cv_df["test_brier"].to_numpy(),
        "o-",
        color="#d73027",
        lw=2,
        label="Test Brier (OOS fold)",
    )
    ax.plot(x, cv_df["train_brier"].to_numpy(), "s--", color="#4575b4", lw=1.5, label="Train Brier")
    ax.set_xlabel("CV Fold (expanding window)")
    ax.set_ylabel("Brier score")
    ax.set_title("Time-Series Cross-Validation — Short-Horizon Sports (2024)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(FIGURES / "oos_ts_crossval.png", dpi=150, bbox_inches="tight")
    plt.close()
    logger.info("Saved oos_ts_crossval.png")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    df_all = pl.read_parquet("data/cache/sports_markets.parquet")
    logger.info("Total sports markets: %d", len(df_all))

    # ---- Duration filter ----
    short = df_all.filter(pl.col("duration_days") <= MAX_DURATION_DAYS)
    logger.info("Short-horizon (<=14d): %d", len(short))

    # ---- OOS data availability ----
    cutoff_2025 = pl.lit("2025-01-01").str.to_datetime().dt.replace_time_zone("UTC")
    cutoff_h2 = pl.lit("2024-07-01").str.to_datetime().dt.replace_time_zone("UTC")

    s2024 = short.filter(pl.col("end_date") < cutoff_2025)
    s2025 = short.filter(pl.col("end_date") >= cutoff_2025)
    h1_2024 = s2024.filter(pl.col("end_date") < cutoff_h2)
    h2_2024 = s2024.filter(pl.col("end_date") >= cutoff_h2)

    print("\n" + "=" * 70)
    print("DATA AVAILABILITY — SHORT-HORIZON SPORTS (duration ≤ 14 days)")
    print("=" * 70)
    for label, sub in [
        ("2024 total", s2024),
        ("H1 2024 (train)", h1_2024),
        ("H2 2024 (test)", h2_2024),
        ("2025 (OOS attempt)", s2025),
    ]:
        t1 = sub["price_t1"].drop_nulls().len()
        print(f"  {label:<22}: n={len(sub):5,}  with T-1 price: {t1:4,}")

    if s2025["price_t1"].drop_nulls().len() < 100:
        print("\n  *** 2025 short-horizon data UNDERPOWERED (<100 markets) ***")
        print("  Using H1/H2 2024 temporal split as primary OOS test.")

    # ---- Primary OOS: H1 2024 (train) vs H2 2024 (test) ----
    print("\n" + "=" * 70)
    print("PRIMARY OOS: H1 2024 (TRAIN) vs H2 2024 (TEST)")
    print("=" * 70)

    h1_stats = summarise(h1_2024)
    h2_stats = summarise(h2_2024)

    for label, st in [("H1 2024 — train", h1_stats), ("H2 2024 — test", h2_stats)]:
        bl, bh = st["brier_ci"]
        sig = "SIGNIFICANT" if (st["hl_p"] or 1) < 0.05 else "not significant"
        print(f"\n  {label}  (n={st['n']:,})")
        print(f"    Brier: {st['brier']:.5f}  95% CI [{bl:.5f}, {bh:.5f}]")
        print(f"    HL p:  {st['hl_p']:.4f}  ({sig})")
        print(f"    YES rate: {st['yes_rate']:.3f}  |  mean price: {st.get('mean_price',0):.3f}")

    persist = bin_persistence(h1_stats["bins"], h2_stats["bins"])
    print(
        f"\n  Bin persistence: {persist['same_direction']}/{persist['n_shared']} "
        f"bins same direction ({persist['pct_same']:.0%})"
    )

    # ---- Bin-level detail ----
    print("\n" + "=" * 70)
    print("BIN-LEVEL EDGE — H2 2024 (OUT-OF-SAMPLE)")
    print("=" * 70)
    print(f"  {'Bin':<12} {'Pred':>6} {'Actual':>8} {'Delta':>8} {'n':>6}")
    for row in h2_stats["bins"].iter_rows(named=True):
        marker = " <-- EDGE" if abs(row["delta"]) > 0.05 and row["n"] >= 10 else ""
        print(
            f"  {row['bin']:<12} {row['pred']:>6.3f} {row['actual']:>8.3f} "
            f"{row['delta']:>+8.3f} {row['n']:>6}{marker}"
        )

    # ---- Time-series cross-validation ----
    print("\n" + "=" * 70)
    print("TIME-SERIES CROSS-VALIDATION (5-fold, expanding window, 2024)")
    print("=" * 70)
    cv_df = ts_crossval(s2024)
    if len(cv_df) > 0:
        print(cv_df)
        mean_test_brier = cv_df["test_brier"].mean()
        print(f"\n  Mean OOS Brier across folds: {mean_test_brier:.5f}")
        frac_sig = cv_df.filter(pl.col("test_hl_p") < 0.05).shape[0] / len(cv_df)
        print(f"  Folds with significant miscalibration (HL p<0.05): {frac_sig:.0%}")

    # ---- Supplementary: 2025 spot-check ----
    s25_t1 = s2025["price_t1"].drop_nulls().len()
    print(f"\n  [SUPPLEMENTARY] 2025 short-horizon n={s25_t1} — too small for inference")
    if s25_t1 >= 10:
        s25_stats = summarise(s2025)
        print(f"  Brier: {s25_stats['brier']:.4f}  HL p: {s25_stats['hl_p']:.4f}")

    # ---- Kelly sizing (based on H2 test bins) ----
    print("\n" + "=" * 70)
    print("KELLY SIZING — H2 2024 OOS BINS (spread=2%, bankroll=$10,000)")
    print("=" * 70)
    kelly_sizing(h2_stats["bins"], spread=0.02, bankroll=10_000, trades_per_month=50)

    # ---- Sport breakdown OOS ----
    print("\n" + "=" * 70)
    print("OOS BRIER BY SPORT TYPE — H2 2024")
    print("=" * 70)
    print(f"  {'Sport':<20} {'n':>5} {'Brier':>8} {'YES%':>7} {'HL p':>8}")
    for sp in h2_2024["sport_type"].unique().sort().to_list():
        sub_sp = h2_2024.filter(pl.col("sport_type") == sp)
        st = summarise(sub_sp)
        if st["n"] < 10:
            continue
        label = SPORT_LABELS.get(sp, sp)
        sig = "*" if (st["hl_p"] or 1) < 0.05 else " "
        print(
            f"  {label:<20} {st['n']:>5,} {st['brier']:>8.4f} "
            f"{st['yes_rate']*100:>6.1f}% {st['hl_p']:>8.4f}{sig}"
        )

    # ---- Plots ----
    plot_reliability_halves(h1_stats, h2_stats)
    plot_edge_persistence(h1_stats["bins"], h2_stats["bins"])
    plot_ts_cv(cv_df)

    logger.info("Done — all figures saved to %s", FIGURES)
