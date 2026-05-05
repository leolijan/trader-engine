"""Run calibration analysis and produce figures."""

import logging
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from trader_engine.analysis.calibration import CalibrationAnalyzer, CalibrationResult

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

FIGURES_DIR = Path("research/reports/figures")
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

LOOKBACK_LABELS = {"t1": "T−1 day", "t7": "T−7 days", "t30": "T−30 days"}


def plot_reliability_diagram(results: dict[str, CalibrationResult]) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=True)
    fig.suptitle("Polymarket Calibration: Reliability Diagrams", fontsize=14, fontweight="bold")

    for ax, (lb, res) in zip(axes, results.items(), strict=False):
        bins = res.bins
        pred = [b.predicted_mean for b in bins]
        actual = [b.actual_rate for b in bins]
        ci_low = [b.ci_low for b in bins]
        ci_high = [b.ci_high for b in bins]
        ns = [b.n for b in bins]

        ax.plot([0, 1], [0, 1], "k--", lw=1, label="Perfect calibration", zorder=1)

        # Scatter sized by n
        sizes = [max(20, min(200, n * 2)) for n in ns]
        ax.scatter(
            pred,
            actual,
            s=sizes,
            c=actual,
            cmap="RdYlGn",
            vmin=0,
            vmax=1,
            zorder=3,
            edgecolors="black",
            linewidths=0.5,
        )
        err_low = np.clip(np.array(actual) - np.array(ci_low), 0, None)
        err_high = np.clip(np.array(ci_high) - np.array(actual), 0, None)
        ax.errorbar(
            pred, actual, yerr=[err_low, err_high], fmt="none", ecolor="gray", alpha=0.5, zorder=2
        )

        ax.set_xlim(-0.02, 1.02)
        ax.set_ylim(-0.02, 1.02)
        ax.set_xlabel("Predicted probability", fontsize=11)
        if ax is axes[0]:
            ax.set_ylabel("Observed frequency", fontsize=11)
        label = LOOKBACK_LABELS.get(lb, lb)
        ax.set_title(
            f"{label}\n"
            f"n={res.n_markets:,}  Brier={res.brier_score:.4f}  "
            f"HL p={res.hl_pvalue:.3f}",
            fontsize=10,
        )
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "reliability_diagrams.png", dpi=150, bbox_inches="tight")
    plt.close()
    logger.info("Saved reliability_diagrams.png")


def plot_miscalibration(results: dict[str, CalibrationResult]) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=True)
    fig.suptitle("Polymarket Miscalibration (Actual − Predicted)", fontsize=14, fontweight="bold")

    for ax, (lb, res) in zip(axes, results.items(), strict=False):
        bins = res.bins
        pred = np.array([b.predicted_mean for b in bins])
        actual = np.array([b.actual_rate for b in bins])
        ci_low = np.array([b.ci_low for b in bins])
        ci_high = np.array([b.ci_high for b in bins])
        delta = actual - pred

        colors = ["#d73027" if d < 0 else "#1a9850" for d in delta]
        ax.bar(pred, delta, width=0.04, color=colors, alpha=0.8, edgecolor="black", linewidth=0.5)
        err_lo = np.clip(actual - ci_low, 0, None)
        err_hi = np.clip(ci_high - actual, 0, None)
        ax.errorbar(
            pred, delta, yerr=[err_lo, err_hi], fmt="none", ecolor="black", alpha=0.6, capsize=3
        )
        ax.axhline(0, color="black", lw=1)
        ax.set_xlim(-0.02, 1.02)
        ax.set_xlabel("Predicted probability", fontsize=11)
        if ax is axes[0]:
            ax.set_ylabel("Actual rate − Predicted prob.", fontsize=11)
        label = LOOKBACK_LABELS.get(lb, lb)
        ax.set_title(f"{label}", fontsize=11)
        ax.grid(True, alpha=0.3, axis="y")
        ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1, decimals=0))

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "miscalibration.png", dpi=150, bbox_inches="tight")
    plt.close()
    logger.info("Saved miscalibration.png")


def plot_category_brier(results: dict[str, CalibrationResult]) -> None:
    lb = "t1"
    if lb not in results:
        return
    res = results[lb]
    cats = sorted(res.by_category.items(), key=lambda x: -x[1]["n"])

    fig, ax = plt.subplots(figsize=(10, 5))
    labels = [c for c, _ in cats]
    briers = [d["brier"] for _, d in cats]
    ns = [int(d["n"]) for _, d in cats]
    colors = plt.colormaps["tab10"](np.linspace(0, 1, len(labels)))

    bars = ax.barh(labels, briers, color=colors, edgecolor="black", linewidth=0.5)
    for bar, n in zip(bars, ns, strict=False):
        ax.text(
            bar.get_width() + 0.001,
            bar.get_y() + bar.get_height() / 2,
            f"n={n}",
            va="center",
            fontsize=9,
        )

    perfect = 0.25  # random predictor Brier score for 50% base rate
    ax.axvline(perfect, color="gray", linestyle="--", lw=1, label="Random (0.25)")
    ax.set_xlabel("Brier Score (lower = better calibrated)", fontsize=11)
    ax.set_title("Brier Score by Category (T−1 day before resolution)", fontsize=12)
    ax.legend()
    ax.grid(True, alpha=0.3, axis="x")
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "category_brier.png", dpi=150, bbox_inches="tight")
    plt.close()
    logger.info("Saved category_brier.png")


def plot_resolution_bias(df: pl.DataFrame) -> None:
    """Plot the overall YES resolution rate vs. mean predicted probability."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    fig.suptitle("Resolution Rate vs. Mean Predicted Probability", fontsize=13)

    for ax, (col, label) in zip(
        axes,
        [("price_t1", "T−1 day"), ("price_t7", "T−7 days"), ("price_t30", "T−30 days")],
        strict=False,
    ):
        sub = df.drop_nulls(col)
        if len(sub) == 0:
            continue
        mean_pred = sub[col].mean()
        actual_rate = sub["resolved_yes"].mean()
        ax.bar(
            ["Predicted\nprob.", "Actual\nresolution"],
            [mean_pred, actual_rate],
            color=["#4575b4", "#d73027"],
            edgecolor="black",
            linewidth=0.8,
        )
        ax.set_ylim(0, 1)
        ax.set_title(f"{label}\nn={len(sub):,}", fontsize=10)
        ax.set_ylabel("Rate / Probability")
        for i, v in enumerate([mean_pred, actual_rate]):
            ax.text(i, v + 0.02, f"{v:.3f}", ha="center", fontsize=11)
        ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "resolution_bias.png", dpi=150, bbox_inches="tight")
    plt.close()
    logger.info("Saved resolution_bias.png")


def print_summary(results: dict[str, CalibrationResult]) -> None:
    print("\n" + "=" * 70)
    print("CALIBRATION ANALYSIS SUMMARY")
    print("=" * 70)
    for lb, res in results.items():
        label = LOOKBACK_LABELS.get(lb, lb)
        print(f"\n{label}  (n={res.n_markets:,})")
        print(
            f"  Brier score:  {res.brier_score:.5f}  "
            f"95% CI [{res.brier_ci[0]:.5f}, {res.brier_ci[1]:.5f}]"
        )
        print(f"  Log score:    {res.log_score:.5f}")
        print(
            f"  HL chi²:      {res.hl_stat:.2f}  p={res.hl_pvalue:.4f}"
            f"  ({'SIGNIFICANT miscalibration' if res.hl_pvalue < 0.05 else 'Not significant'})"
        )
        if res.by_category:
            print("  By category:")
            for cat, d in sorted(res.by_category.items(), key=lambda x: -x[1]["n"]):
                print(
                    f"    {cat:15s}  n={int(d['n']):4d}  "
                    f"brier={d['brier']:.4f}  "
                    f"pred={d['mean_price']:.3f}  actual={d['actual_rate']:.3f}"
                )
    print("=" * 70)


if __name__ == "__main__":
    df = pl.read_parquet("data/cache/markets.parquet")
    logger.info("Loaded %d markets", len(df))

    analyzer = CalibrationAnalyzer(df)
    results = analyzer.run_all()

    print_summary(results)
    plot_reliability_diagram(results)
    plot_miscalibration(results)
    plot_category_brier(results)
    plot_resolution_bias(df)

    logger.info("All figures saved to %s", FIGURES_DIR)
