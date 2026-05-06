# Phase 3: Duration-Controlled OOS Validation
**May 2026**

---

## 1. Executive Summary

Phase 3 addresses the core failure of Phase 2: the train/test split compared structurally different market types (short-horizon 2024 vs. long-horizon 2025). The fix was to filter both periods to short-horizon markets (duration ≤ 14 days) and use a clean **H1 2024 (train) vs. H2 2024 (test)** temporal split.

**Definitive verdict**: The sports miscalibration **persists out-of-sample** — HL p=0.0002 in the H2 2024 test set with n=3,299. However, **bin-level persistence is weak** (10/20 bins, 50%), and the edge is concentrated in the 10–50% YES range with high noise. The Kelly EV estimates are mathematically valid but operationally unrealistic at the computed sizes.

**Bottom line**: There is a real, statistically significant miscalibration in short-horizon Polymarket sports markets. The edge survives OOS on aggregate. However, individual bin reliability is insufficient to size confidently into specific price buckets. A live monitoring period (Phase 4) is required before deploying capital.

---

## 2. Dataset and Study Design

### 2.1 Data availability

| Stratum | Total markets | With T-1 price |
|---------|--------------|----------------|
| All short-horizon (≤14d) | 8,403 | 3,873 |
| H1 2024 (Jan–Jun) | 3,073 | 574 |
| H2 2024 (Jul–Dec) | 5,330 | 3,299 |
| 2025 (OOS attempt) | 0 | 0 |

**2025 note**: Zero short-horizon sports markets found despite exhaustive search of both the Events API and Gamma markets API. Polymarket appears to have restructured sports offerings in 2025, shifting toward long-horizon championship markets. The 2025 OOS test is flagged as **UNDERPOWERED** (n=0, below the 100-market threshold specified in the study protocol).

### 2.2 Design pivot

Because the 2025 short-horizon data is absent, the primary OOS design uses a **within-2024 temporal split**:

- **Train**: H1 2024 (January–June), n=574 with T-1 price
- **Test**: H2 2024 (July–December), n=3,299 with T-1 price
- **Supplementary**: 5-fold expanding-window time-series cross-validation across all 2024 data

This design is **pre-specified**: H1 was designated train before any H2 results were inspected.

---

## 3. Primary OOS Results

### 3.1 Aggregate calibration

| Period | n | Brier | 95% CI | HL p | YES rate | Mean price |
|--------|---|-------|--------|------|----------|------------|
| H1 2024 (train) | 574 | 0.1128 | [0.0985, 0.1277] | 0.0254* | 28.9% | 30.2% |
| H2 2024 (test) | 3,299 | **0.1508** | [0.1450, 0.1569] | **0.0002*** | 34.3% | 37.2% |

Miscalibration is **statistically significant in both periods**. The Brier score is *higher* (worse) in H2 (0.1508 vs. 0.1128), which at first seems counterintuitive — markets should price in more information over time, not less. The explanation is a within-year composition shift: H2 has a higher YES rate (34.3% vs. 28.9%) and higher mean price (37.2% vs. 30.2%), consistent with more competitive game-day markets or different sport mix in summer/fall.

Key point: the miscalibration does **not disappear** in the OOS period. The edge is real on aggregate.

### 3.2 Bin-level OOS results (H2 2024 test set)

| Bin | Predicted | Actual | Delta | n | Edge? |
|-----|-----------|--------|-------|---|-------|
| 0%–5% | 1.7% | 0.6% | −1.2% | 527 | |
| 5%–10% | 7.0% | 6.6% | −0.4% | 243 | |
| **10%–15%** | **12.2%** | **6.7%** | **−5.6%** | 180 | YES |
| 15%–20% | 17.6% | 16.0% | −1.6% | 163 | |
| **20%–25%** | **22.3%** | **16.8%** | **−5.6%** | 173 | YES |
| 25%–30% | 27.3% | 27.2% | −0.1% | 206 | |
| 30%–35% | 32.7% | 31.4% | −1.2% | 140 | |
| **35%–40%** | **37.5%** | **29.9%** | **−7.6%** | 107 | YES |
| **40%–45%** | **42.3%** | **33.6%** | **−8.7%** | 131 | YES |
| **45%–50%** | **47.7%** | **34.2%** | **−13.5%** | 260 | YES |
| 50%–55% | 51.2% | 52.0% | +0.9% | 346 | |
| 55%–60% | 57.5% | 57.9% | +0.5% | 145 | |
| 60%–65% | 62.4% | 61.8% | −0.6% | 89 | |
| **65%–70%** | **67.4%** | **63.3%** | **−4.1%** | 109 | |
| **70%–75%** | **72.3%** | **64.4%** | **−7.9%** | 87 | |
| **75%–80%** | **77.0%** | **68.9%** | **−8.1%** | 90 | |
| 80%–85% | 82.7% | 82.5% | −0.1% | 103 | |
| 85%–90% | 87.7% | 89.6% | +1.9% | 77 | |
| 90%–95% | 92.4% | 94.1% | +1.7% | 68 | |
| 95%–100% | 98.5% | 100.0% | +1.5% | 55 | |

**Pattern**: Markets systematically overestimate YES probability in the 10–50% range and also in the 65–80% range. The 50–65% range is nearly perfectly calibrated.

### 3.3 Bin persistence

- Bins with same direction (train vs. test): **10 of 20 (50%)**
- This is equivalent to a coin flip — no reliable bin-level directional persistence
- The aggregate effect persists, but targeting specific bins based on training data is **not justified**

---

## 4. Time-Series Cross-Validation

5-fold expanding-window cross-validation on all 2024 short-horizon markets (n=3,870 with T-1 price, ~645 per fold):

| Fold | Train n | Train Brier | Test n | Test Brier | HL p | Test YES% |
|------|---------|-------------|--------|------------|------|-----------|
| 1 | 645 | 0.1126 | 645 | 0.1243 | <0.001*** | 23.1% |
| 2 | 1,290 | 0.1184 | 645 | 0.1423 | 0.247 | 33.3% |
| 3 | 1,935 | 0.1264 | 645 | 0.1532 | 0.837 | 37.1% |
| 4 | 2,580 | 0.1331 | 645 | 0.1819 | 0.901 | 43.4% |
| 5 | 3,225 | 0.1429 | 645 | 0.1569 | 0.080 | 35.7% |

**Mean OOS Brier: 0.1517**. Folds with significant HL miscalibration (p<0.05): 1/5 (20%).

**Interpretation**: The aggregate Brier score is consistently above what a random model would achieve, but HL significance is intermittent — suggesting the miscalibration is real but varies in strength across time windows. The edge is not a stable, stationary phenomenon.

---

## 5. Sport-Type Breakdown (H2 2024 OOS)

| Sport | n | Brier | YES% | HL p |
|-------|---|-------|------|------|
| Other sports | 3,145 | 0.1517 | 34.2% | 0.0002*** |
| Am. football | 44 | 0.1264 | 29.5% | 0.286 |
| Combat sports | 37 | 0.2256 | 40.5% | 0.031* |
| Esports | 28 | 0.0932 | 10.7% | 0.370 |
| Tennis | 25 | 0.0569 | 28.0% | 0.777 |

The edge is **driven entirely by "other sports"** (n=3,145, HL p=0.0002). Named sport categories have insufficient sample sizes for reliable inference (n=25–44). Combat sports show a significant HL p but with only 37 markets the Wilson CI is wide. Tennis appears closest to efficient pricing.

---

## 6. Kelly Sizing (OOS Bins with Edge)

Applied to H2 2024 bins showing edge (≥3% net), assuming 2% spread cost:

| Bin | Pred | Actual | Net Edge | Half-Kelly | $/trade | Est. EV/mo |
|-----|------|--------|----------|------------|---------|------------|
| 10–15% | 12.2% | 6.7% | +3.6% | 46.2% | $4,620 | $8,226 |
| 20–25% | 22.3% | 16.8% | +3.6% | 39.2% | $3,921 | $6,985 |
| 35–40% | 37.5% | 29.9% | +5.6% | 26.1% | $2,607 | $7,298 |
| 40–45% | 42.3% | 33.6% | +6.7% | 20.9% | $2,089 | $7,016 |
| 45–50% | 47.7% | 34.2% | +11.5% | 17.3% | $1,725 | $9,924 |

**Estimated total EV: ~$39,448/month at $10,000 bankroll, 50 trades/month**

### Critical caveats on Kelly estimates

These numbers are **mathematically correct but operationally unrealistic**:

1. **Bin-level estimates assume you know the "true" probability.** You don't. The OOS actual rate (e.g., 6.7% for 10–15% bin) has a wide Wilson CI at n=180. The true rate could be anywhere from ~3% to ~12%.

2. **Half-Kelly fractions of 40–46% are extremely aggressive.** At 46% of bankroll per trade, a single losing run of 3 trades (not unlikely with 6.7% true prob) costs 82% of capital.

3. **Market capacity**: At $10k position sizes, you will move thin sports markets significantly. Most short-horizon sports markets on Polymarket have $5k–$50k total volume.

4. **Bin persistence = 50%**: Using bin-specific estimates from H1 to predict H2 beat a coin flip by zero. Do not size differently across bins based on historical bin estimates.

**Realistic estimate**: A conservative strategy buying NO in the 10–50% YES range, 0.5–2% of bankroll per trade, 30–50 trades/month = **$300–$2,000/month EV** at $10k bankroll. This is meaningful but not the mathematical maximum.

---

## 7. Honest Assessment

### What Phase 3 confirms

1. **The miscalibration is real and statistically significant OOS** (HL p=0.0002, n=3,299). This is the strongest evidence yet — it is not a training-set artifact.

2. **The edge is directionally correct in aggregate**: markets consistently overestimate YES probability in short-horizon sports markets.

3. **A NO-buying strategy in the 10–50% YES range survives OOS** on aggregate. Net edge after 2% spread: +3–12% depending on bin.

4. **The most miscalibrated area is 35–50%** (delta −7.6 to −13.5pp), suggesting bettors are irrationally attracted to near-50/50 propositions.

### What Phase 3 does not confirm

1. **Bin-level persistence**: 10/20 bins (50%) show the same direction train vs. test. This is a coin flip. Do not overfit to specific bin estimates.

2. **2025 validation is impossible**: Zero short-horizon sports markets found in 2025. Polymarket restructured offerings. The edge may or may not persist in the current market structure.

3. **Temporal stability**: The 5-fold CV shows HL significance in only 1/5 windows. The miscalibration may be stronger in certain time periods (e.g., NFL season) than others.

4. **Liquidity**: Position sizing at Kelly-implied levels ($1,700–$4,600/trade) would face bid-ask spreads significantly above 2% in thin markets.

### The residual risk

Even if calibration statistics are correct, **adverse selection** is the key unknown. When you buy NO at 12% YES in a soccer match, you are trading against someone who may have watched recent tape, knows an injury report, or has sports betting expertise far exceeding the base rate calibration signal. The statistical edge measures aggregate miscalibration — not your edge vs. informed traders at the margin.

---

## 8. Conclusion and Phase 4 Recommendation

**Phase 3 verdict**: YES, the edge is real on historical data. No, it is not yet confirmed for current market structure (2025 data absent).

The research program has reached the limits of what historical data can tell us. A prospective live monitoring period is the only valid next step.

### Recommended Phase 4: Live Monitoring

1. **Track current open short-horizon sports markets** (duration ≤14 days, priced 10–50% YES)
2. **Record predicted vs. actual resolution** over 3 months minimum
3. **Do not deploy capital** until 100+ prospective resolutions confirm the edge direction
4. **Monitor bid-ask spread** on actual order book (not proxy) at intended entry time
5. **If edge confirms prospectively**: begin paper trading, then deploy at ≤1% Kelly

The calibration arbitrage hypothesis in Polymarket short-horizon sports markets is **supported by the evidence but not yet actionable**. Phase 4 converts it from a historical finding to a live trading signal.

---

## 9. Figures

- `oos_reliability_h1_vs_h2.png` — Reliability diagram comparing H1 (train) vs H2 (test) bin-level calibration
- `oos_edge_persistence.png` — Bin-level delta in train vs test, showing which bins flip direction
- `oos_ts_crossval.png` — 5-fold time-series CV: train Brier vs. test Brier per fold
