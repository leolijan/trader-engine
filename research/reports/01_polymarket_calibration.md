# Polymarket Calibration Study
**Phase 1 Research Report — May 2026**

---

## 1. Executive Summary

Polymarket prediction markets exhibit **statistically significant miscalibration** across all three lookback windows (T−1 day, T−7 days, T−30 days before resolution). The miscalibration is largest and most tradeable in two regions: (1) the **5–20% YES-probability range**, where the market systematically overestimates YES probability by 5–14 percentage points, and (2) the **45–50% range**, where markets priced near 50/50 resolve YES only 12% of the time.

**Honest bottom line**: A gross edge of ~10% exists in specific probability bins, but after a realistic 2% bid-ask spread the net edge is 3–12%. Whether this constitutes a *sustainably tradeable* edge depends on factors not yet modelled: position sizing limits, liquidity constraints, adverse selection, and whether the pattern is stable over time. The data supports **proceeding to Phase 2** with cautious optimism.

---

## 2. Dataset

| Metric | Value |
|--------|-------|
| Total resolved markets | 1,789 |
| Date range | Nov 2021 – May 2026 |
| Total volume (USD) | $1.01 billion |
| Median market volume | $28,287 |
| Markets with T−1 data | 1,597 |
| Markets with T−7 data | 1,136 |
| Markets with T−30 data | 601 |
| Overall YES resolution rate | 28.8% |

**Categories**: other (65%), crypto (12%), politics (12%), sports (8%), weather (2%).

The 28.8% YES resolution rate reflects Polymarket's market composition: most markets are "Will unprecedented/difficult event X happen?" questions where NO is the modal correct answer.

**Data source**: Polymarket Gamma API (market metadata + resolution) and CLOB API (price history). Price snapshots extracted at exactly T−1, T−7, T−30 days before `closedTime` using binary search on the time-series.

---

## 3. Methodology

### 3.1 Market Selection
- Binary YES/NO markets only (two-outcome)
- Clearly resolved: `outcomePrices` shows exactly [1,0] or [0,1]
- Minimum duration: 24 hours (to have at least T−1 data)
- Minimum volume: $100 USD (to exclude trivial test markets)

### 3.2 Price Extraction
For each market, we extract the last available price at or before the lookback target timestamp using binary search on the chronological price history. Price history retrieved with adaptive fidelity (1440 → 60 → 1 minutes per point) to maximise historical coverage.

### 3.3 Calibration Metrics
- **Brier score**: Mean squared error between predicted probability and binary outcome. Lower is better. Perfect calibration with 50% base rate would yield ~0.25; a perfect oracle yields 0.
- **Log score**: Mean log-loss. Penalises confident wrong predictions more severely.
- **Reliability diagram**: Bins markets by predicted probability (20 bins of 5pp width), plots actual resolution rate per bin.
- **Hosmer-Lemeshow test**: Chi-squared test of whether actual and predicted rates differ significantly across bins.
- **Bootstrap CIs**: 2,000 bootstrap resamples for Brier score confidence intervals.

---

## 4. Results

### 4.1 Overall Calibration

| Lookback | n | Brier Score | 95% CI | Log Score | HL χ² | HL p-value |
|----------|---|-------------|--------|-----------|-------|------------|
| T−1 day | 1,597 | 0.0635 | [0.057, 0.070] | −0.206 | 85.2 | **<0.0001** |
| T−7 days | 1,136 | 0.0834 | [0.074, 0.093] | −0.271 | 73.1 | **<0.0001** |
| T−30 days | 601 | 0.0892 | [0.076, 0.104] | −0.294 | 32.7 | **0.018** |

All three lookbacks show **highly significant miscalibration** (HL p < 0.05). The Brier score improves as the lookback shortens (T−1 < T−7 < T−30), consistent with prices becoming more accurate as resolution approaches — but even at T−1 the miscalibration remains significant.

*See figures: `reliability_diagrams.png`, `miscalibration.png`*

### 4.2 Systematic Bias (Overconfidence in YES)

| Lookback | Mean error (actual − pred) | t-stat | p-value |
|----------|---------------------------|--------|---------|
| T−1 day | **−0.0127** | −2.01 | **0.044** |
| T−7 days | −0.0130 | −1.52 | 0.130 |
| T−30 days | −0.0108 | −0.88 | 0.377 |

At T−1, the market **significantly overestimates YES probability** by 1.27 pp on average (p = 0.044). This is weak but consistent: the market slightly over-assigns probability to YES outcomes.

### 4.3 Bin-Level Miscalibration (T−1 Day)

The reliability diagram reveals strong structure:

| Price bin | Pred | Actual | Miscal. | n |
|-----------|------|--------|---------|---|
| 0–5% | 0.010 | 0.008 | −0.002 | 747 |
| 5–10% | 0.073 | **0.022** | **−0.051** | 91 |
| 10–15% | 0.122 | **0.020** | **−0.101** | 49 |
| 15–20% | 0.176 | **0.032** | **−0.144** | 31 |
| 45–50% | 0.473 | **0.120** | **−0.352** | 83 |
| 50–55% | 0.513 | 0.506 | −0.006 | 77 |
| 65–70% | 0.674 | 0.933 | +0.259 | 15 |
| 90–95% | 0.932 | 1.000 | +0.068 | 40 |

**Key observations**:
1. **The 5–20% range severely overestimates YES** — markets priced at 10–15% resolve YES only 2% of the time (not 12%).
2. **The 45–50% anomaly is large**: 83 markets priced near-even resolve YES only 12% of the time. These appear to be "hard" uncertain questions with a strong NO base rate.
3. **High-probability markets (>65%) underestimate YES** — good events are even more likely than the market thinks.
4. **The 0–5% range is well-calibrated** (largest group, n=747) — near-certainty NO markets are correctly priced.

### 4.4 Category Breakdown (T−1 Day)

| Category | n | Brier | Mean pred | Actual rate |
|----------|---|-------|-----------|-------------|
| Sports | 125 | **0.116** | 0.338 | **0.152** |
| Other | 1,064 | 0.065 | 0.280 | 0.276 |
| Weather | 34 | 0.056 | 0.174 | 0.118 |
| Crypto | 167 | 0.056 | 0.492 | **0.545** |
| Politics | 203 | 0.031 | 0.200 | 0.197 |

**Sports** has by far the worst calibration (Brier 0.116): the market prices sports outcomes at 33.8% YES on average but they resolve YES only 15.2% of the time. This is a 18.6 pp systematic overestimation.

**Politics** is the best-calibrated category (Brier 0.031), with predicted and actual rates nearly identical (0.200 vs 0.197). The crowd is well-calibrated for political events.

**Crypto** slightly underestimates YES — actual rate (54.5%) exceeds mean prediction (49.2%).

*See figure: `category_brier.png`*

### 4.5 Market Efficiency Over Time

| Lookback | Spearman ρ | p-value | Trend |
|----------|-----------|---------|-------|
| T−1 day | +0.075 | 0.003 | Getting worse |
| T−7 days | +0.186 | <0.001 | Getting worse |
| T−30 days | −0.239 | <0.001 | **Getting better** |

Counterintuitively, short-term calibration (T−1, T−7) is getting *worse* over time, while long-term calibration (T−30) is improving. One interpretation: Polymarket has attracted more short-term sports/event markets (where calibration is poor) while long-horizon markets (politics, economics) have become more efficient as more sophisticated participants entered.

*See figures: `time_trend_price_t1.png`, `time_trend_price_t7.png`, `time_trend_price_t30.png`*

### 4.6 Edge Analysis (After 2% Bid-Ask Spread)

| Lookback | Bins with positive net edge | Mean gross edge | Mean net edge |
|----------|-----------------------------|-----------------|---------------|
| T−1 | 15 / 20 | 10.7% | **8.7%** |
| T−7 | 18 / 20 | 9.7% | **7.7%** |
| T−30 | 15 / 20 | 10.9% | **8.9%** |

These headline numbers look attractive but require important caveats (see §5).

---

## 5. Honest Assessment

### What the data shows

1. **Miscalibration is real and statistically significant** across all time horizons. This is not noise.

2. **The largest exploitable pattern** is sports markets priced 5–30%: the market overestimates YES probability by 5–18 pp, and a "sell YES" (= buy NO) strategy has 3–15% net edge per trade in these bins.

3. **The near-50% anomaly is large** (35 pp gross edge) but driven by a specific market structure: uncertain "will X happen?" questions with inherently low base rates. Once priced near 50%, these markets overwhelmingly resolve NO.

4. **Politics is well-calibrated** — no edge after costs.

### What the data does NOT show

1. **This is NOT a backtest.** The edge estimates above assume you can trade at the mid-price with a 2% spread. In practice, order book depth on Polymarket varies enormously. The 5–10% bin edge (3.1% net) would be eliminated by a wider spread or adverse selection.

2. **Sample sizes in key bins are small.** The 15–20% bin (n=31) and 45–50% bin (n=83) have wide confidence intervals. The edge estimates could be substantially wrong.

3. **The trend is partially negative.** Short-term calibration has been getting worse over time, partly because of composition effects (more sports markets). It is not clear the historical edge will persist.

4. **No position sizing or portfolio analysis.** A single trade with 8% edge is not valuable if you can only put $100 in it.

### Bottom line

**A tradeable edge is plausible but not proven.** The calibration anomalies are large enough to survive transaction costs in several bins, but the combination of small sample sizes, unknown liquidity constraints, and a negative efficiency trend for short-term markets means Phase 1 cannot definitively confirm a sustainable edge. Phase 2 is warranted.

---

## 6. Recommended Next Steps (Phase 2)

Based on the findings, Phase 2 should focus on:

### 6.1 Most Promising Direction: Sports Market NO-Bias
The sports category shows systematic YES overestimation (18.6 pp bias at T−1). Phase 2 should:
- Pull all available sports markets (not just top-volume)
- Segment by sport type, time-to-resolution, and market maker
- Build a base-rate model for sports outcomes to replace market prices

### 6.2 Order Book Analysis
The 2% spread assumption needs validation:
- Fetch actual bid-ask spreads for markets in each probability bin
- Estimate realistic fill costs by looking at order book depth
- Model slippage for different trade sizes

### 6.3 Walk-Forward Validation
To confirm the edge is not historical artefact:
- Split data: train on pre-2024, validate on 2024–2026
- Check if edge estimates hold out-of-sample

### 6.4 Kelly-Optimal Sizing
If edge survives the above:
- Estimate variance of the edge estimate per bin
- Compute Kelly fractions with half-Kelly safety margin
- Model a portfolio of simultaneous positions

---

## 7. Figures

- `reliability_diagrams.png` — Reliability diagrams at T−1, T−7, T−30
- `miscalibration.png` — Signed miscalibration per bin (actual − predicted)
- `category_brier.png` — Brier scores by category at T−1
- `resolution_bias.png` — Mean predicted vs actual resolution rate
- `time_trend_price_t1.png` — Rolling Brier score over time (T−1)
- `time_trend_price_t7.png` — Rolling Brier score over time (T−7)
- `time_trend_price_t30.png` — Rolling Brier score over time (T−30)
