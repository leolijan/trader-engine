"""Phase 4: Cross-category calibration analysis → figures + LaTeX stats.

Outputs:
  research/reports/figures/p4_reliability_{cat}.png  (one per category)
  research/reports/figures/p4_brier_comparison.png
  research/reports/figures/p4_edge_heatmap.png
  data/cache/phase4_results.json   (all numbers used in LaTeX report)
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from scipy import stats

matplotlib.use("Agg")
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

FIGURES = Path("research/reports/figures")
FIGURES.mkdir(parents=True, exist_ok=True)
CACHE = Path("data/cache")

RNG = np.random.default_rng(42)
N_BOOT = 3000
BIN_EDGES = np.linspace(0, 1, 11)  # 10 bins of 10pp each
SPREAD = 0.02  # assumed round-trip cost

# Prettier names for the report
PRETTY = {
    "sports_soccer": "Soccer",
    "sports_basketball": "Basketball",
    "sports_esports": "Esports",
    "sports_tennis": "Tennis",
    "sports_baseball": "Baseball",
    "sports_golf": "Golf",
    "politics_elections": "Elections",
    "politics_us": "US Politics",
    "politics_global": "Global Politics",
    "crypto": "Crypto",
    "finance": "Finance",
    "ai_tech": "AI / Tech",
    "pop_culture": "Pop Culture",
    "science": "Science",
}

GROUP = {
    "sports_soccer": "Sports",
    "sports_basketball": "Sports",
    "sports_esports": "Sports",
    "sports_tennis": "Sports",
    "sports_baseball": "Sports",
    "sports_golf": "Sports",
    "politics_elections": "Politics",
    "politics_us": "Politics",
    "politics_global": "Politics",
    "crypto": "Crypto/Finance",
    "finance": "Crypto/Finance",
    "ai_tech": "Tech/Culture",
    "pop_culture": "Tech/Culture",
    "science": "Tech/Culture",
}


# ── Stats helpers ────────────────────────────────────────────────────────────


def brier(p: np.ndarray, a: np.ndarray) -> float:
    return float(np.mean((p - a) ** 2))


def brier_ci(p: np.ndarray, a: np.ndarray) -> tuple[float, float]:
    n = len(p)
    bs = np.array([np.mean((p[idx := RNG.integers(0, n, n)] - a[idx]) ** 2) for _ in range(N_BOOT)])
    return float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def hosmer_lemeshow(p: np.ndarray, a: np.ndarray, bins: int = 10) -> float:
    edges = np.percentile(p, np.linspace(0, 100, bins + 1))
    edges[-1] += 1e-9
    chi2 = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (p >= lo) & (p < hi)
        n = mask.sum()
        if n == 0:
            continue
        o1 = a[mask].sum()
        e1 = p[mask].sum()
        o0, e0 = n - o1, n - e1
        if e1 > 0:
            chi2 += (o1 - e1) ** 2 / e1
        if e0 > 0:
            chi2 += (o0 - e0) ** 2 / e0
    p_val = 1 - stats.chi2.cdf(chi2, df=bins - 2)
    return float(p_val)


def bin_stats(p: np.ndarray, a: np.ndarray) -> list[dict[str, Any]]:
    rows = []
    for i in range(len(BIN_EDGES) - 1):
        lo, hi = BIN_EDGES[i], BIN_EDGES[i + 1]
        mask = (p >= lo) & (p < hi)
        n = int(mask.sum())
        if n < 3:
            rows.append(
                {
                    "lo": lo,
                    "hi": hi,
                    "n": n,
                    "pred": None,
                    "actual": None,
                    "delta": None,
                    "net_edge": None,
                }
            )
            continue
        pred = float(p[mask].mean())
        actual = float(a[mask].mean())
        delta = pred - actual
        net_edge = abs(delta) - SPREAD
        rows.append(
            {
                "lo": lo,
                "hi": hi,
                "n": n,
                "pred": pred,
                "actual": actual,
                "delta": delta,
                "net_edge": net_edge,
            }
        )
    return rows


def kelly_half(pred: float, actual: float) -> float:
    """Half-Kelly fraction for a NO bet when market overprices YES."""
    if actual >= pred:
        return 0.0
    b = (1 - pred) / pred  # odds of NO at market price
    f = (b * (1 - actual) - actual) / b
    return max(0.0, f / 2)


# ── Per-category analysis ────────────────────────────────────────────────────


def analyse_category(df: pl.DataFrame, name: str) -> dict[str, Any]:
    sub = df.filter((pl.col("category") == name) & pl.col("price_t1").is_not_null())
    if len(sub) < 20:
        return {"name": name, "n": len(sub), "underpowered": True}

    p = sub["price_t1"].to_numpy().astype(float)
    a = sub["resolved_yes"].cast(pl.Float64).to_numpy()

    br = brier(p, a)
    ci_lo, ci_hi = brier_ci(p, a)
    hl_p = hosmer_lemeshow(p, a)
    bins = bin_stats(p, a)

    # Best edge bins (net_edge > 0)
    edge_bins = [b for b in bins if b["net_edge"] is not None and b["net_edge"] > 0.03]

    return {
        "name": name,
        "pretty": PRETTY.get(name, name),
        "group": GROUP.get(name, "Other"),
        "n": len(sub),
        "underpowered": len(sub) < 100,
        "brier": br,
        "brier_ci": [ci_lo, ci_hi],
        "hl_p": hl_p,
        "yes_rate": float(a.mean()),
        "mean_price": float(p.mean()),
        "med_vol": float(sub["volume_usd"].median()),
        "bins": bins,
        "edge_bins": edge_bins,
    }


# ── Figures ──────────────────────────────────────────────────────────────────


def plot_reliability(p: np.ndarray, a: np.ndarray, name: str, n: int) -> None:
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], "k--", lw=0.8, alpha=0.5, label="Perfect calibration")

    bin_centers, bin_actual, bin_n = [], [], []
    for i in range(len(BIN_EDGES) - 1):
        lo, hi = BIN_EDGES[i], BIN_EDGES[i + 1]
        mask = (p >= lo) & (p < hi)
        if mask.sum() < 5:
            continue
        bin_centers.append(float(p[mask].mean()))
        bin_actual.append(float(a[mask].mean()))
        bin_n.append(int(mask.sum()))

    sizes = [max(20, min(300, n_i / 2)) for n_i in bin_n]
    ax.scatter(bin_centers, bin_actual, s=sizes, zorder=5, color="#2563eb", alpha=0.85)
    ax.plot(bin_centers, bin_actual, color="#2563eb", lw=1.2, alpha=0.6)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Predicted probability (T-1)", fontsize=10)
    ax.set_ylabel("Observed YES rate", fontsize=10)
    ax.set_title(f"{PRETTY.get(name, name)} (n={n:,})", fontsize=11)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIGURES / f"p4_reliability_{name}.png", dpi=150)
    plt.close(fig)


def plot_brier_comparison(results: list[dict[str, Any]]) -> None:
    valid = [r for r in results if not r.get("underpowered") and "brier" in r]
    valid.sort(key=lambda r: r["brier"], reverse=True)

    labels = [r["pretty"] for r in valid]
    briers = [r["brier"] for r in valid]
    ci_lo = [r["brier"] - r["brier_ci"][0] for r in valid]
    ci_hi = [r["brier_ci"][1] - r["brier"] for r in valid]
    colors = ["#ef4444" if r["hl_p"] < 0.05 else "#6b7280" for r in valid]

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(
        labels, briers, xerr=[ci_lo, ci_hi], color=colors, capsize=3, alpha=0.85, ecolor="#374151"
    )
    ax.axvline(0, color="black", lw=0.6)
    ax.set_xlabel("Brier Score (lower = better calibrated)", fontsize=10)
    ax.set_title(
        "Calibration by Category — Polymarket 2025–2026\n"
        "(red = HL p < 0.05; error bars = 95% bootstrap CI)",
        fontsize=10,
    )
    ax.grid(axis="x", alpha=0.3)

    # Reference lines
    ax.axvline(0.25, color="#9ca3af", lw=0.8, ls="--", alpha=0.7)
    ax.text(0.251, -0.6, "random", fontsize=7, color="#9ca3af")

    fig.tight_layout()
    fig.savefig(FIGURES / "p4_brier_comparison.png", dpi=150)
    plt.close(fig)


def plot_edge_heatmap(results: list[dict[str, Any]]) -> None:
    valid = [r for r in results if not r.get("underpowered") and "bins" in r]
    valid.sort(key=lambda r: r["pretty"])

    bin_labels = [f"{int(b['lo']*100)}–{int(b['hi']*100)}%" for b in valid[0]["bins"]]
    matrix = np.full((len(valid), len(bin_labels)), np.nan)

    for i, r in enumerate(valid):
        for j, b in enumerate(r["bins"]):
            if b["delta"] is not None:
                matrix[i, j] = b["delta"]

    fig, ax = plt.subplots(figsize=(12, 6))
    im = ax.imshow(matrix, cmap="RdBu_r", vmin=-0.20, vmax=0.20, aspect="auto")
    ax.set_xticks(range(len(bin_labels)))
    ax.set_xticklabels(bin_labels, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(valid)))
    ax.set_yticklabels([r["pretty"] for r in valid], fontsize=9)

    # Annotate
    for i in range(len(valid)):
        for j in range(len(bin_labels)):
            v = matrix[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:+.2f}", ha="center", va="center", fontsize=6.5, color="black")

    plt.colorbar(im, ax=ax, label="Pred − Actual (positive = market overestimates YES)")
    ax.set_title(
        "Calibration Delta by Category × Price Bin\n"
        "Polymarket 2025–2026 (red = market overprices YES, blue = underprices)",
        fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(FIGURES / "p4_edge_heatmap.png", dpi=150)
    plt.close(fig)


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    df = pl.read_parquet(CACHE / "phase4_all.parquet")
    logger.info("Loaded %d rows", len(df))

    categories = df["category"].unique().to_list()
    results: list[dict[str, Any]] = []

    for cat in sorted(categories):
        r = analyse_category(df, cat)
        results.append(r)
        if r.get("underpowered"):
            logger.info("%-25s  n=%d  UNDERPOWERED", cat, r["n"])
        else:
            logger.info(
                "%-25s  n=%d  Brier=%.4f  HL_p=%.4f",
                cat,
                r["n"],
                r.get("brier", 0),
                r.get("hl_p", 1),
            )

        # Reliability plot
        sub = df.filter((pl.col("category") == cat) & pl.col("price_t1").is_not_null())
        if len(sub) >= 20:
            p = sub["price_t1"].to_numpy().astype(float)
            a = sub["resolved_yes"].cast(pl.Float64).to_numpy()
            plot_reliability(p, a, cat, len(sub))

    # Aggregate plots
    plot_brier_comparison(results)
    plot_edge_heatmap(results)
    logger.info("Saved all figures to %s", FIGURES)

    # Save numeric results for LaTeX
    with open(CACHE / "phase4_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info("Saved phase4_results.json")

    # Print summary table
    print("\n" + "=" * 80)
    print("CROSS-CATEGORY CALIBRATION SUMMARY — POLYMARKET 2025–2026")
    print("=" * 80)
    print(f"{'Category':22} {'n':>6} {'Brier':>7} {'HL p':>8} {'YES%':>6} " f"{'Edge bins':>12}")
    print("-" * 80)
    for r in sorted(results, key=lambda x: x.get("brier", 99)):
        if r.get("underpowered"):
            print(f"{r['pretty']:22} {r['n']:>6}   UNDERPOWERED")
            continue
        edge_summary = (
            ", ".join(
                f"{int(b['lo']*100)}-{int(b['hi']*100)}% ({b['net_edge']:+.2f})"
                for b in r.get("edge_bins", [])[:3]
            )
            or "none"
        )
        sig = "*" if r["hl_p"] < 0.05 else " "
        print(
            f"{r['pretty']:22} {r['n']:>6} {r['brier']:>7.4f} {r['hl_p']:>7.4f}{sig} "
            f"{r['yes_rate']:>5.1%}  {edge_summary}"
        )


if __name__ == "__main__":
    main()
