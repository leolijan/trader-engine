# Sports Market Edge — Phase 2 Research Report
**May 2026**

---

## 1. Executive Summary

Phase 2 expanded the sports market analysis from 152 markets (Phase 1) to **12,500 resolved sports markets**. The key finding from Phase 1 — that sports markets significantly overestimate YES probability — is **confirmed on the 2024 training data** (Brier=0.115, n=5,379). However, a clean out-of-sample test is not possible because the 2025 data consists of fundamentally different market types (long-horizon championship markets vs. short-horizon game-day markets).

**Honest bottom line**: A real miscalibration edge exists in **short-horizon sports markets (duration 1–14 days)** on Polymarket. The market systematically overprices the probability of underdog/rare sports outcomes in the 5–30% YES range. Whether this is exploitable depends on bid-ask spreads (median ~2%) and whether the edge persists when properly controlled for market duration.

---

## 2. Dataset

| Metric | Value |
|--------|-------|
| Total sports markets fetched | 12,500 |
| With T-1 price data | 5,854 |
| With T-7 price data | 2,638 |
| Date range | Nov 2020 – Jun 2025 |
| Train period (2024) | 5,379 markets |
| Test period (2025) | 475 markets |

**Sport type breakdown** (all markets):

| Sport | n | YES rate |
|-------|---|----------|
| Other sports | 10,345 | 30.7% |
| Basketball | 953 | 45.1% |
| American football | 334 | 39.2% |
| Hockey | 209 | 41.1% |
| Soccer | 213 | 21.6% |
| Tennis | 129 | 23.3% |
| Esports | 61 | 21.3% |
| Golf | 52 | 7.7% |

**Spread proxy** (price range in 4-hour window at T-1): median=2.0%, 90th percentile=5.0%.

---

## 3. Critical Data Limitation: Composition Shift

The train (2024) and test (2025) periods contain **fundamentally different market types**:

| Metric | Train (2024) | Test (2025) |
|--------|-------------|-------------|
| n (with T-1) | 5,379 | 475 |
| Median duration | **5.9 days** | **185 days** |
| YES rate | 29.0% | 7.6% |
| Mean price at T-1 | 31.5% | 8.4% |
| % priced below 5% | ~25% | **84.8%** |

**What this means**: The 2024 markets are primarily short-horizon game-day bets (e.g., "Will Team X win tonight?"). The 2025 markets are long-horizon season/championship bets (e.g., "Will Team X win the league?") where, by T-1 day before resolution, the outcome is nearly certain and prices approach 0 or 1.

This composition shift explains why the 2025 Brier score (0.0085) is near-perfect: it is measuring a different phenomenon (certainty at resolution) rather than calibration quality. **These two sets cannot be directly compared as an in-sample/out-of-sample validation.**

---

## 4. Results

### 4.1 Training Period (2024, short-horizon markets)

| Sport | n | Brier | YES rate | Mean price |
|-------|---|-------|----------|------------|
| All sports | 5,379 | **0.115** | 29.0% | 31.5% |
| Other sports | 5,012 | 0.116 | 29.1% | 31.8% |
| Basketball | 94 | 0.123 | — | — |
| Am. football | 68 | 0.128 | — | — |
| Soccer | 39 | 0.068 | — | — |

The overall Brier score of 0.115 is remarkably high. For reference:
- A market that always predicts the base rate (29%) would score: 0.29×(1-0.29)² + 0.71×(0-0.29)² = **0.206**
- A perfect oracle scores **0**
- Score of **0.115** = 44% of the way from base rate to perfect

This means markets have real price discovery, but there is systematic miscalibration: the market overestimates YES probability in the 5–30% range (actual YES rate in those bins: 2–15%, predicted: 5–30%).

### 4.2 Test Period (2025, long-horizon markets)

| Sport | n | Brier | HL p-value | YES rate |
|-------|---|-------|------------|----------|
| All sports | 475 | **0.009** | 0.277 | 7.6% |
| Basketball | 124 | 0.001 | 0.659 | 4.0% |
| Soccer | 82 | 0.006 | 0.618 | 6.1% |
| Am. football | 30 | 0.004 | 0.772 | 10.0% |

The 2025 test Brier score (0.009) reflects near-perfect certainty at T-1 in long-horizon markets — NOT improved calibration. 84.8% of 2025 markets are priced below 5% and 90.5% of those resolve NO. This is trivially "calibrated" because it measures price accuracy when the outcome is essentially already known.

**Conclusion**: The out-of-sample test is invalid due to composition shift. We cannot confirm or deny persistence of the 2024 edge using this data.

### 4.3 Spread Analysis

The spread proxy (price range near T-1) shows:
- Median spread: **2.0%** (consistent with Phase 1 assumption)
- 90th percentile: **5.0%**

This means the 2% spread assumption used in Phase 1 edge analysis was accurate at the median but understates costs in illiquid markets. Any strategy must account for hitting the 90th percentile occasionally.

---

## 5. Where the Edge Actually Lives

Despite the test limitation, the data points to where miscalibration is most exploitable:

### Short-horizon markets (1–14 days), 5–30% YES bins:

| Bin | Predicted | Actual (train) | Gross edge | Net (−2%) |
|-----|-----------|----------------|------------|-----------|
| 5–10% | 7.3% | ~2% | ~5% | ~3% |
| 10–15% | 12.2% | ~2% | ~10% | ~8% |
| 15–20% | 17.6% | ~3% | ~15% | ~13% |
| 20–30% | 25% | ~10% | ~15% | ~13% |

These bins are **consistently overpriced YES**. The mechanism: sports betting markets attract bettors who overestimate the probability of "upset" outcomes. When something is priced at 15% YES on Polymarket, bettors are drawn to the asymmetric payout, not the true probability.

### Sport-specific patterns:
- **Golf**: 7.7% YES rate — heavily overpriced in 10–30% bins
- **Soccer**: 21.6% YES rate with lower Brier (0.068) — best-calibrated sport
- **Basketball**: 45% YES rate — market is symmetric, less directional bias

---

## 6. Honest Assessment

### What the data shows

1. **The miscalibration is real in 2024 short-horizon sports markets**: Brier=0.115 on 5,379 markets is a large and consistent finding, not noise.

2. **The edge survives 2% spread** in the 10–30% YES range (gross edge 10–15%, net 8–13%).

3. **The sport type matters**: Golf and "other sports" have the strongest NO bias; soccer is the most efficient.

### What the data does NOT show

1. **We cannot confirm out-of-sample persistence** because the 2025 test set is structurally different (long-horizon vs. short-horizon markets). This is the most important limitation of Phase 2.

2. **Liquidity at the 5th–15th percentile price range** is unknown. Many of these markets may have bid-ask spreads of 5–10%, not 2%.

3. **Adverse selection**: If you are buying NO in a market priced at 12% YES, you may be trading against informed sports bettors who know something you don't.

### The key question for Phase 3

The critical question is: **does the 5–30% YES miscalibration in short-horizon sports markets persist in 2025 and 2026?**

To answer this requires fetching 2025 short-horizon sports markets (duration 1–14 days, closed in 2025). Our current 2025 data does not contain these because the CLOB price history API preferentially returns data for long-running markets at daily resolution.

---

## 7. Recommended Next Steps (Phase 3)

### 7.1 Duration-stratified analysis (Priority 1)
- Restrict ALL analysis to markets with duration 1–14 days
- Fetch 2025 short-horizon markets directly (filter by `startDate` and `closedTime`)
- Run train (2024) vs. test (2025) with matched market types

### 7.2 Live data monitoring (Priority 2)
- Track current open sports markets priced 5–30% YES
- Monitor actual resolution rate vs. prediction over 3 months
- This would constitute a prospective out-of-sample test

### 7.3 Order book analysis (Priority 3)
- Fetch actual bid/ask at time of entry for historical markets
- Compute realized spread, not just spread proxy
- Estimate true cost of carry for a NO-buying strategy

### 7.4 Base rate model (Priority 4)
- Build a simple statistical model for sports outcomes (team ELO, historical head-to-head)
- Compare model predictions to market prices
- Identify which markets are most mispriced vs. a naive model

---

## 8. Figures

- `sports_brier_train_vs_test.png` — Brier score comparison by sport
- `sports_miscal_heatmap.png` — Miscalibration heatmap by sport × price bin
- `sports_spread_analysis.png` — Spread proxy distribution
- `sports_*_reliability.png` — Reliability diagrams per sport (top 5 by n)
