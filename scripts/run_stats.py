"""Extended statistical tests: time-trend analysis and cross-category comparison."""

import logging
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

FIGURES_DIR = Path("research/reports/figures")
FIGURES_DIR.mkdir(parents=True, exist_ok=True)


def overconfidence_test(df: pl.DataFrame, col: str, label: str) -> dict[str, float]:
    """Test if the market is systematically over- or under-confident."""
    sub = df.drop_nulls(col)
    prices = sub[col].to_numpy()
    actuals = sub["resolved_yes"].cast(pl.Float64).to_numpy()

    # Signed error: positive = market underestimates probability of YES
    signed_error = actuals - prices
    t_stat, p_val = stats.ttest_1samp(signed_error, 0)
    mean_err = float(signed_error.mean())
    std_err = float(signed_error.std())
    n = len(signed_error)
    se = std_err / np.sqrt(n)

    print(f"\n{label} (n={n:,})")
    print(f"  Mean signed error (actual - predicted): {mean_err:+.4f} ± {se:.4f}")
    print(f"  t-statistic: {t_stat:.3f}, p-value: {p_val:.4f}")
    direction = (
        "OVERESTIMATES YES probability" if mean_err < 0 else "UNDERESTIMATES YES probability"
    )
    sig = "SIGNIFICANT" if p_val < 0.05 else "not significant"
    print(f"  Market {direction} ({sig})")

    return {
        "mean_error": mean_err,
        "t_stat": float(t_stat),
        "p_value": float(p_val),
        "n": float(n),
        "significant": float(p_val < 0.05),
    }


def time_trend_analysis(df: pl.DataFrame, col: str, label: str) -> None:
    """Check if calibration has improved over time (market efficiency over time)."""
    sub = df.drop_nulls(col).sort("end_date")
    if len(sub) < 60:
        print(f"\n{label}: insufficient data for time trend ({len(sub)} markets)")
        return

    prices = sub[col].to_numpy()
    actuals = sub["resolved_yes"].cast(pl.Float64).to_numpy()
    squared_errors = (prices - actuals) ** 2

    # Rolling 50-market window
    window = 50
    rolling_brier = [
        float(np.mean(squared_errors[max(0, i - window) : i + 1]))
        for i in range(len(squared_errors))
    ]

    # Spearman rank correlation: is Brier declining over time?
    indices = np.arange(len(rolling_brier))
    rho, p = stats.spearmanr(indices, rolling_brier)
    print(f"\nTime trend {label}: Spearman ρ={rho:.3f}, p={p:.4f}")
    trend = "IMPROVING (less miscalibrated)" if rho < 0 else "WORSENING or stable"
    sig = "(significant)" if p < 0.05 else "(not significant)"
    print(f"  Market efficiency trend: {trend} {sig}")

    # Plot
    dates_num = np.arange(len(rolling_brier))
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(dates_num, rolling_brier, color="#4575b4", lw=1.5, label=f"Rolling Brier (w={window})")
    z = np.polyfit(dates_num, rolling_brier, 1)
    trend_line = np.poly1d(z)
    ax.plot(dates_num, trend_line(dates_num), "r--", lw=1, label=f"Trend (ρ={rho:.2f}, p={p:.3f})")
    ax.set_xlabel("Market index (chronological)")
    ax.set_ylabel("Rolling Brier score")
    ax.set_title(f"Market Efficiency Over Time — {label}")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / f"time_trend_{col}.png", dpi=150, bbox_inches="tight")
    plt.close()
    logger.info("Saved time_trend_%s.png", col)


def edge_analysis(df: pl.DataFrame, col: str, label: str, spread_pct: float = 0.02) -> None:
    """Estimate tradeable edge assuming 2% bid-ask spread."""
    sub = df.drop_nulls(col)
    prices = sub[col].to_numpy()
    actuals = sub["resolved_yes"].cast(pl.Float64).to_numpy()

    # For each bin: if we could bet when predicted is far from actual
    bins = np.linspace(0, 1, 21)
    bin_idx = np.digitize(prices, bins) - 1
    bin_idx = np.clip(bin_idx, 0, len(bins) - 2)

    print(f"\nEdge analysis — {label} (spread={spread_pct*100:.0f}%)")
    print(
        f"  {'Bin':12s} {'Pred':>6s} {'Actual':>8s} {'Edge (gross)':>14s} "
        f"{'Edge (net)':>12s} {'n':>5s}"
    )

    total_gross_edge = []
    total_net_edge = []

    for i in range(len(bins) - 1):
        mask = bin_idx == i
        n = int(mask.sum())
        if n < 5:
            continue
        pred_mean = float(prices[mask].mean())
        actual_rate = float(actuals[mask].mean())
        # Gross edge: trade YES if actual > pred, NO if actual < pred
        gross_edge = abs(actual_rate - pred_mean)
        net_edge = gross_edge - spread_pct
        marker = " *" if net_edge > 0 else ""
        print(
            f"  {bins[i]:.2f}-{bins[i+1]:.2f}  {pred_mean:6.3f}  {actual_rate:8.3f}  "
            f"{gross_edge:+14.3f}  {net_edge:+12.3f}  {n:5d}{marker}"
        )
        total_gross_edge.append(gross_edge)
        total_net_edge.append(net_edge)

    n_positive = sum(1 for e in total_net_edge if e > 0)
    print(f"\n  Bins with positive net edge: {n_positive}/{len(total_net_edge)}")
    print(f"  Mean gross edge: {np.mean(total_gross_edge):.4f}")
    print(f"  Mean net edge (after {spread_pct*100:.0f}% spread): {np.mean(total_net_edge):.4f}")


if __name__ == "__main__":
    df = pl.read_parquet("data/cache/markets.parquet")
    logger.info("Loaded %d markets", len(df))

    print("\n" + "=" * 70)
    print("STATISTICAL TESTS: OVERCONFIDENCE / BIAS")
    print("=" * 70)

    overconf_results: dict[str, dict[str, float]] = {}
    for col, label in [
        ("price_t1", "T−1 day"),
        ("price_t7", "T−7 days"),
        ("price_t30", "T−30 days"),
    ]:
        overconf_results[col] = overconfidence_test(df, col, label)

    print("\n" + "=" * 70)
    print("STATISTICAL TESTS: MARKET EFFICIENCY OVER TIME")
    print("=" * 70)

    for col, label in [
        ("price_t1", "T−1 day"),
        ("price_t7", "T−7 days"),
        ("price_t30", "T−30 days"),
    ]:
        time_trend_analysis(df, col, label)

    print("\n" + "=" * 70)
    print("EDGE ANALYSIS: GROSS AND NET OF 2% SPREAD")
    print("=" * 70)

    for col, label in [
        ("price_t1", "T−1 day"),
        ("price_t7", "T−7 days"),
        ("price_t30", "T−30 days"),
    ]:
        edge_analysis(df, col, label)
