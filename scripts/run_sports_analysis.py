"""Phase 2: Sports market edge analysis — out-of-sample validation + Kelly sizing."""

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

TRAIN_CUTOFF = "2025-01-01"
BIN_EDGES = np.linspace(0, 1, 21)
N_BOOT = 2000
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
    "motorsport": "Motorsport",
    "baseball": "Baseball",
    "other_sports": "Other Sports",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def brier(prices: np.ndarray, actuals: np.ndarray) -> float:
    return float(np.mean((prices - actuals) ** 2))


def bootstrap_brier(prices: np.ndarray, actuals: np.ndarray) -> tuple[float, float]:
    n = len(prices)
    scores = np.array(
        [np.mean((prices[idx := RNG.integers(0, n, n)] - actuals[idx]) ** 2) for _ in range(N_BOOT)]
    )
    return float(np.percentile(scores, 2.5)), float(np.percentile(scores, 97.5))


def hl_test(prices: np.ndarray, actuals: np.ndarray) -> tuple[float, float]:
    bin_idx = np.clip(np.digitize(prices, BIN_EDGES) - 1, 0, len(BIN_EDGES) - 2)
    hl = 0.0
    df_used = 0
    for i in range(len(BIN_EDGES) - 1):
        m = bin_idx == i
        n = int(m.sum())
        if n < 5:
            continue
        exp_y = prices[m].mean() * n
        obs_y = actuals[m].sum()
        exp_n = n - exp_y
        obs_n = n - obs_y
        if exp_y > 0:
            hl += (obs_y - exp_y) ** 2 / exp_y
        if exp_n > 0:
            hl += (obs_n - exp_n) ** 2 / exp_n
        df_used += 1
    p = float(1 - stats.chi2.cdf(hl, max(1, df_used - 2)))
    return float(hl), p


def bin_stats(prices: np.ndarray, actuals: np.ndarray) -> pl.DataFrame:
    bin_idx = np.clip(np.digitize(prices, BIN_EDGES) - 1, 0, len(BIN_EDGES) - 2)
    rows = []
    for i in range(len(BIN_EDGES) - 1):
        m = bin_idx == i
        n = int(m.sum())
        if n == 0:
            continue
        pred = float(prices[m].mean())
        actual = float(actuals[m].mean())
        ci = proportion_confint(int(actuals[m].sum()), n, alpha=0.05, method="wilson")
        rows.append(
            {
                "bin_low": float(BIN_EDGES[i]),
                "bin_high": float(BIN_EDGES[i + 1]),
                "pred": pred,
                "actual": actual,
                "delta": actual - pred,
                "gross_edge": abs(actual - pred),
                "n": n,
                "ci_low": float(ci[0]),
                "ci_high": float(ci[1]),
            }
        )
    return pl.DataFrame(rows)


def net_edge(gross: float, spread: float = 0.02) -> float:
    return gross - spread


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------


def plot_reliability_split(train_bins: pl.DataFrame, test_bins: pl.DataFrame, sport: str) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    fig.suptitle(f"Reliability Diagram — {sport}", fontsize=13, fontweight="bold")
    for ax, df_b, period in [
        (axes[0], train_bins, "Train (pre-2024)"),
        (axes[1], test_bins, "Test (2024+)"),
    ]:
        if len(df_b) == 0:
            ax.text(0.5, 0.5, "Insufficient data", ha="center", va="center")
            ax.set_title(period)
            continue
        pred = df_b["pred"].to_numpy()
        actual = df_b["actual"].to_numpy()
        ci_lo = np.clip(actual - df_b["ci_low"].to_numpy(), 0, None)
        ci_hi = np.clip(df_b["ci_high"].to_numpy() - actual, 0, None)
        ns = df_b["n"].to_numpy()
        sizes = np.clip(ns * 3, 20, 300)
        ax.plot([0, 1], [0, 1], "k--", lw=1, label="Perfect")
        ax.scatter(
            pred,
            actual,
            s=sizes,
            zorder=3,
            edgecolors="black",
            linewidths=0.5,
            c=actual,
            cmap="RdYlGn",
            vmin=0,
            vmax=1,
        )
        ax.errorbar(pred, actual, yerr=[ci_lo, ci_hi], fmt="none", ecolor="gray", alpha=0.5)
        ax.set_xlim(-0.02, 1.02)
        ax.set_ylim(-0.02, 1.02)
        ax.set_xlabel("Predicted probability")
        if ax is axes[0]:
            ax.set_ylabel("Observed frequency")
        ax.set_title(f"{period}  (n={df_b['n'].sum():,})")
        ax.grid(True, alpha=0.3)
    plt.tight_layout()
    fname = sport.lower().replace(" ", "_").replace(".", "")
    plt.savefig(FIGURES / f"sports_{fname}_reliability.png", dpi=150, bbox_inches="tight")
    plt.close()


def plot_miscal_by_sport(results: dict[str, dict[str, Any]]) -> None:
    sports = [s for s, r in results.items() if r["test_n"] >= 30]
    if not sports:
        return

    fig, ax = plt.subplots(figsize=(12, 5))
    x = np.arange(len(sports))
    w = 0.35
    train_b = [results[s]["train_brier"] for s in sports]
    test_b = [results[s]["test_brier"] for s in sports]
    labels = [SPORT_LABELS.get(s, s) for s in sports]

    ax.bar(
        x - w / 2,
        train_b,
        w,
        label="Train (pre-2024)",
        color="#4575b4",
        alpha=0.8,
        edgecolor="black",
        linewidth=0.5,
    )
    ax.bar(
        x + w / 2,
        test_b,
        w,
        label="Test (2024+)",
        color="#d73027",
        alpha=0.8,
        edgecolor="black",
        linewidth=0.5,
    )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_ylabel("Brier score (lower = better)")
    ax.set_title("Brier Score by Sport: Train vs Out-of-Sample Test")
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()
    plt.savefig(FIGURES / "sports_brier_train_vs_test.png", dpi=150, bbox_inches="tight")
    plt.close()
    logger.info("Saved sports_brier_train_vs_test.png")


def plot_edge_heatmap(results: dict[str, dict[str, Any]]) -> None:
    sports = [s for s, r in results.items() if r["test_n"] >= 30]
    if not sports:
        return

    bin_centers = (BIN_EDGES[:-1] + BIN_EDGES[1:]) / 2
    matrix = np.full((len(sports), len(bin_centers)), np.nan)

    for i, sp in enumerate(sports):
        bins_df = results[sp]["test_bins"]
        if len(bins_df) == 0:
            continue
        for row in bins_df.iter_rows(named=True):
            j = int(round(row["bin_low"] / 0.05))
            if 0 <= j < len(bin_centers):
                matrix[i, j] = row["delta"]

    fig, ax = plt.subplots(figsize=(14, max(4, len(sports))))
    im = ax.imshow(matrix, cmap="RdYlGn", vmin=-0.3, vmax=0.3, aspect="auto")
    ax.set_xticks(np.arange(len(bin_centers)))
    ax.set_xticklabels([f"{c:.2f}" for c in bin_centers], rotation=90, fontsize=8)
    ax.set_yticks(np.arange(len(sports)))
    ax.set_yticklabels([SPORT_LABELS.get(s, s) for s in sports])
    ax.set_xlabel("Predicted probability bin")
    ax.set_title("Miscalibration (Actual − Predicted) by Sport × Bin (Out-of-Sample)")
    plt.colorbar(im, ax=ax, label="Actual − Predicted")
    plt.tight_layout()
    plt.savefig(FIGURES / "sports_miscal_heatmap.png", dpi=150, bbox_inches="tight")
    plt.close()
    logger.info("Saved sports_miscal_heatmap.png")


def plot_spread_analysis(df: pl.DataFrame) -> None:
    spreads = df.filter(pl.col("spread_proxy").is_not_null())["spread_proxy"].to_numpy()
    if len(spreads) < 10:
        return
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    fig.suptitle("Bid-Ask Spread Proxy Distribution (Sports Markets)", fontsize=13)
    axes[0].hist(
        np.clip(spreads, 0, 0.2), bins=40, color="#4575b4", edgecolor="black", linewidth=0.4
    )
    axes[0].axvline(
        float(np.median(spreads)), color="red", lw=2, label=f"Median={np.median(spreads):.3f}"
    )
    axes[0].axvline(
        float(np.percentile(spreads, 90)),
        color="orange",
        lw=2,
        label=f"90th pct={np.percentile(spreads, 90):.3f}",
    )
    axes[0].set_xlabel("Spread proxy (price range near T-1)")
    axes[0].set_ylabel("Count")
    axes[0].legend()

    by_sport = (
        df.filter(pl.col("spread_proxy").is_not_null())
        .group_by("sport_type")
        .agg(pl.col("spread_proxy").median().alias("med_spread"), pl.len().alias("n"))
        .filter(pl.col("n") >= 10)
        .sort("med_spread")
    )
    labels = [SPORT_LABELS.get(s, s) for s in by_sport["sport_type"].to_list()]
    axes[1].barh(
        labels, by_sport["med_spread"].to_numpy(), color="#4575b4", edgecolor="black", linewidth=0.4
    )
    axes[1].set_xlabel("Median spread proxy")
    axes[1].set_title("By Sport Type")
    axes[1].grid(True, alpha=0.3, axis="x")
    plt.tight_layout()
    plt.savefig(FIGURES / "sports_spread_analysis.png", dpi=150, bbox_inches="tight")
    plt.close()
    logger.info("Saved sports_spread_analysis.png")


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

_EMPTY_RESULT: dict[str, Any] = {
    "train_brier": np.nan,
    "train_hl_p": np.nan,
    "train_n": 0,
    "test_brier": np.nan,
    "test_brier_ci": (np.nan, np.nan),
    "test_hl_p": np.nan,
    "test_n": 0,
    "test_yes_rate": np.nan,
    "test_mean_price": np.nan,
    "test_bins": pl.DataFrame(),
    "train_bins": pl.DataFrame(),
}


def analyse_sport(df: pl.DataFrame, col: str = "price_t1") -> dict[str, Any]:
    sub = df.drop_nulls(col)
    if len(sub) < 20:
        return _EMPTY_RESULT.copy()

    cutoff = pl.lit(TRAIN_CUTOFF).str.to_datetime().dt.replace_time_zone("UTC")
    train = sub.filter(pl.col("end_date") < cutoff)
    test = sub.filter(pl.col("end_date") >= cutoff)

    def _metrics(split: pl.DataFrame) -> dict[str, Any]:
        if len(split) < 10:
            return {
                "brier": np.nan,
                "hl_p": np.nan,
                "n": 0,
                "yes_rate": np.nan,
                "mean_price": np.nan,
                "bins": pl.DataFrame(),
            }
        p = split[col].to_numpy()
        a = split["resolved_yes"].cast(pl.Float64).to_numpy()
        bl, bh = bootstrap_brier(p, a)
        hl_s, hl_p = hl_test(p, a)
        return {
            "brier": brier(p, a),
            "brier_ci": (bl, bh),
            "hl_stat": hl_s,
            "hl_p": hl_p,
            "n": len(split),
            "yes_rate": float(a.mean()),
            "mean_price": float(p.mean()),
            "bins": bin_stats(p, a),
        }

    return {
        "train_brier": _metrics(train)["brier"],
        "train_hl_p": _metrics(train)["hl_p"],
        "train_n": _metrics(train)["n"],
        "test_brier": _metrics(test)["brier"],
        "test_brier_ci": _metrics(test).get("brier_ci", (np.nan, np.nan)),
        "test_hl_p": _metrics(test)["hl_p"],
        "test_n": _metrics(test)["n"],
        "test_yes_rate": _metrics(test)["yes_rate"],
        "test_mean_price": _metrics(test)["mean_price"],
        "test_bins": _metrics(test)["bins"],
        "train_bins": _metrics(train)["bins"],
    }


def kelly_analysis(bins_df: pl.DataFrame, spread: float) -> pl.DataFrame:
    """Compute Kelly fraction and expected value for each bin with positive net edge."""
    rows = []
    for row in bins_df.iter_rows(named=True):
        gross = row["gross_edge"]
        ne = net_edge(gross, spread)
        if ne <= 0 or row["n"] < 10:
            continue
        p_true = row["actual"]
        p_market = row["pred"]
        # Bet NO if actual < pred (market overestimates YES)
        if p_true < p_market:
            # Buying NO at price (1 - p_market), true prob of winning = 1 - p_true
            b = (1.0 - p_market) / p_market  # odds in decimal
            p_win = 1.0 - p_true
        else:
            # Buying YES at price p_market, true prob of winning = p_true
            b = p_market / (1.0 - p_market)
            p_win = p_true
        kelly_f = max(0.0, (b * p_win - (1 - p_win)) / b)
        half_kelly = kelly_f / 2
        ev_per_unit = b * p_win - (1 - p_win) - spread
        rows.append(
            {
                "bin": f"{row['bin_low']:.2f}–{row['bin_high']:.2f}",
                "pred": row["pred"],
                "actual": row["actual"],
                "gross_edge": gross,
                "net_edge": ne,
                "kelly_f": kelly_f,
                "half_kelly": half_kelly,
                "ev_per_unit": ev_per_unit,
                "n_test": row["n"],
            }
        )
    return pl.DataFrame(rows) if rows else pl.DataFrame()


def print_summary(results: dict[str, dict[str, Any]]) -> None:
    print("\n" + "=" * 80)
    print("SPORTS CALIBRATION — TRAIN vs OUT-OF-SAMPLE TEST")
    print("=" * 80)
    print(
        f"{'Sport':<20} {'Train n':>8} {'Train Brier':>12} {'Test n':>8} "
        f"{'Test Brier':>11} {'HL p':>8} {'YES%':>6}"
    )
    print("-" * 80)
    for sp, r in sorted(results.items(), key=lambda x: -x[1].get("test_n", 0)):
        if r.get("test_n", 0) < 10:
            continue
        label = SPORT_LABELS.get(sp, sp)
        sig = "*" if (r.get("test_hl_p", 1) or 1) < 0.05 else " "
        print(
            f"{label:<20} {r.get('train_n', 0):>8,} "
            f"{r.get('train_brier', np.nan):>12.4f} "
            f"{r.get('test_n', 0):>8,} "
            f"{r.get('test_brier', np.nan):>10.4f}{sig} "
            f"{r.get('test_hl_p', np.nan):>8.4f} "
            f"{r.get('test_yes_rate', np.nan)*100:>5.1f}%"
        )
    print("* = HL p < 0.05 (significant miscalibration)")


if __name__ == "__main__":
    df = pl.read_parquet("data/cache/sports_markets.parquet")
    logger.info("Loaded %d sports markets", len(df))

    # --- Spread analysis ---
    median_spread = float(df["spread_proxy"].drop_nulls().median() or 0.02)
    p90_spread = float(df["spread_proxy"].drop_nulls().quantile(0.9) or 0.05)
    print(f"\nSpread proxy: median={median_spread:.4f}, 90th pct={p90_spread:.4f}")
    effective_spread = max(median_spread, 0.01)
    plot_spread_analysis(df)

    # --- Per-sport analysis ---
    results: dict[str, dict[str, Any]] = {}
    sport_types = df["sport_type"].unique().to_list()
    for sp in sport_types:
        sport_df = df.filter(pl.col("sport_type") == sp)
        results[sp] = analyse_sport(sport_df)

    # Also run on all sports combined
    results["ALL_SPORTS"] = analyse_sport(df)

    print_summary(results)

    # --- Plots ---
    plot_miscal_by_sport(results)
    plot_edge_heatmap(results)

    # Reliability diagrams for top sports
    top_sports = sorted(
        [(sp, r) for sp, r in results.items() if r.get("test_n", 0) >= 30],
        key=lambda x: -x[1]["test_n"],
    )[:5]
    for sp, r in top_sports:
        plot_reliability_split(r["train_bins"], r["test_bins"], SPORT_LABELS.get(sp, sp))

    # --- Kelly analysis for ALL_SPORTS test bins ---
    print("\n" + "=" * 80)
    print("KELLY ANALYSIS — ALL SPORTS (OUT-OF-SAMPLE, T-1 DAY)")
    print(f"Effective spread used: {effective_spread:.4f}")
    print("=" * 80)
    kelly_df = kelly_analysis(results["ALL_SPORTS"]["test_bins"], effective_spread)
    if len(kelly_df) > 0:
        print(kelly_df)
        total_ev = kelly_df["ev_per_unit"].sum()
        mean_hk = kelly_df["half_kelly"].mean()
        print(f"\nSummary: {len(kelly_df)} bins with positive net edge")
        print(f"Mean half-Kelly fraction: {mean_hk:.4f} ({mean_hk*100:.1f}% of bankroll per trade)")
        print(f"Mean EV per unit staked: {kelly_df['ev_per_unit'].mean():.4f}")
    else:
        print("No bins with positive net edge after costs in test period.")

    logger.info("All figures saved to %s", FIGURES)
