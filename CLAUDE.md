Read CLAUDE.md first. Then execute the current phase autonomously.

GOAL: Prove or disprove that exploitable inefficiencies exist in prediction markets.
Specifically: the calibration arbitrage hypothesis on Polymarket historical data.

---

## PHASE 1: COMPLETE ✓

Key findings:
- 1,789 resolved binary markets analysed, $1B total volume
- Significant miscalibration: Hosmer-Lemeshow p < 0.0001
- Sports: worst calibrated (Brier 0.116), mean price 33.8%, actual rate 15.2%
- Politics: well calibrated (Brier 0.031), no edge after costs
- Gross edge ~10.7% at T-1; net ~8.7% after 2% spread (15/20 bins positive)
- Report: research/reports/01_polymarket_calibration.md

---

## PHASE 2: Sports Market Edge Validation (CURRENT)

GOAL: Prove or disprove that the sports miscalibration from Phase 1 is real,
stable, and tradeable after realistic costs.

PHASE 2 TASKS (do all of these autonomously):

1. Expanded sports data pull
   - Target: 1000+ resolved sports markets (Phase 1 had only 152)
   - Fetch ALL sports markets regardless of volume minimum
   - Classify by sport type using question text:
     soccer, tennis, basketball, american football, combat sports, esports, other
   - Cache to data/cache/sports_markets.parquet

2. Bid-ask spread analysis
   - For each market, fetch actual best_bid and best_ask at T-1 day before close
   - Use Polymarket CLOB API: GET /book?token_id=<id> at the relevant timestamp
   - If historical order book unavailable, use price_history spread proxy:
     estimate spread = (max_price - min_price) in last hour before T-1
   - Report: median spread, 90th percentile, spread by sport type
   - Recompute edge analysis with real spreads replacing the 2% assumption

3. Out-of-sample validation (CRITICAL — do not skip)
   - Train period: markets closing BEFORE 2024-01-01
   - Test period: markets closing ON OR AFTER 2024-01-01
   - Run full calibration analysis separately on each split
   - Report Brier score, HL p-value, and edge per period
   - If edge only appears in train: conclude NO tradeable edge

4. Sport-type breakdown
   - Run calibration analysis per sport type
   - Identify which sport(s) drive the anomaly
   - Check: is the edge concentrated in one sport or broad?

5. Kelly-optimal sizing (only if edge survives out-of-sample)
   - Compute Kelly fraction: f* = (bp - q) / b where b=odds, p=true prob, q=1-p
   - Use half-Kelly for safety
   - Estimate: expected monthly return at $10,000 bankroll
   - Estimate: number of qualifying trades per month at current market volume

6. Write research/reports/02_sports_edge.md with:
   - Methodology
   - Findings with plots (save to research/reports/figures/)
   - Out-of-sample results prominently
   - Honest assessment: tradeable edge or not?
   - If YES: Kelly sizing, estimated returns, risk of ruin
   - If NO: explain what drove the Phase 1 result (overfitting? category bias?)

CONSTRAINTS:
- No live trading code. Pure research.
- Use polars, not pandas.
- Every number in the report must come from data.
- Commit after each major step with conventional commits.
- If the edge disappears out-of-sample, SAY SO clearly.
- If data is insufficient for a conclusion, SAY SO.

When done, summarize findings and propose Phase 3 based on what you found.

---

## PHASE 3: Duration-Controlled OOS Test (CURRENT)

GOAL: Get a valid out-of-sample test by comparing like-for-like market types.
Phase 2 failed because train=short-horizon (5.9d) vs test=long-horizon (185d).
Fix: filter BOTH periods to short-horizon sports markets (duration 1–14 days).

PHASE 3 TASKS (do all autonomously):

1. Duration-stratified reanalysis
   - Filter sports_markets.parquet to duration_days <= 14
   - Check: how many 2024 vs 2025 short-horizon markets have T-1 price data?
   - If 2025 short-horizon is too sparse (<100 markets): fetch more via direct
     market API (not events API) using date filters on closedTime for 2025

2. If 2025 data is insufficient — targeted refetch
   - Use gamma-api.polymarket.com/markets?closed=true&category=Sports
     with date range filters to get markets closing in Jan–Apr 2025
   - Filter to duration <= 14 days after fetching
   - Merge with existing cache (deduplicate by condition_id)

3. Run proper OOS calibration analysis
   - Train: 2024 short-horizon sports (duration 1–14 days)
   - Test: 2025 short-horizon sports (duration 1–14 days)
   - Same CalibrationAnalyzer as before: Brier, HL test, bin-level edge
   - Report BOTH periods with 95% bootstrap CIs

4. Bin-level persistence test
   - For each bin (5–10%, 10–15%, ..., 25–30%): does the edge direction persist?
   - A bin where train shows -15pp miscal should also show negative in test
   - Count: how many bins show same sign in both periods?

5. If edge persists OOS:
   - Kelly sizing with actual median spread (2% confirmed)
   - Estimated trades/month at current Polymarket sports volume
   - Expected monthly P&L at $10k bankroll (half-Kelly)

6. Write research/reports/03_oos_validation.md
   - This is the definitive verdict on whether the edge is real
   - If OOS edge confirmed: "YES, proceed to live monitoring"
   - If OOS edge absent: "NO tradeable edge found, stop here"

CONSTRAINTS:
- Duration filter is STRICT: <= 14 days only, both periods
- If 2025 short-horizon n < 100, explicitly flag as "underpowered"
- No live trading code
- Commit after each major step

---

## PHASE 4: Cross-Category Market Efficiency Analysis (CURRENT)

GOAL: Identify which Polymarket niches have exploitable inefficiencies in 2025–2026.
Produce a professional LaTeX research report suitable for quant finance applications.

CONTEXT:
- Phase 3 confirmed sports edge (10–30% YES bins, net ~10% OOS) but only used 2024 data.
- Phase 4 pivots to CURRENT data: late 2025 and 2026 (API fetches live/recent markets).
- Key 2026 API discovery: tag_slug=sports includes weather and crypto — must filter carefully.
- Sports markets now ~4,600/day (esports props, soccer spreads, O/U) via tag_slug=sports.

CATEGORIES TO ANALYSE (use Polymarket category= or tag_slug= filters):
  1. Sports — pure game outcomes: Soccer, Basketball, Esports, Tennis, Baseball, Golf
  2. Politics — Elections, US politics, Global Politics (Trump, Congress, etc.)
  3. Crypto/Finance — Crypto price movements, ETF, Fed rates, Commodities
  4. AI/Tech — AI model predictions, Tech milestone markets
  5. Pop Culture — Film & TV, Celebrities, Music
  6. Climate & Weather — temperature/rainfall specific-value markets
  7. Science/Space — scientific milestone markets

DATA REQUIREMENTS (per category):
  - Focus period: 2025-10-01 to 2026-05-06 (last ~7 months)
  - Min volume: $500 per market (real price discovery)
  - Binary markets only (2 outcomes, cleanly resolved)
  - Duration: 1–30 days (exclude >30d long-horizon markets)
  - T-1 price from CLOB price history (fidelity=60 first, then 1)
  - Min 100 markets per category for inference; flag <50 as underpowered

FETCH STRATEGY (pagination problem):
  - Categories with few markets (AI, Science, Chess): paginate back to 2025-10-01
  - High-volume categories (Sports): use volumeNum_min=1000 or random sample 2000
  - Save each category to data/cache/phase4_{category}.parquet
  - Deduplicate by condition_id

ANALYSIS PER CATEGORY:
  - Brier score + 95% bootstrap CI (N=3000)
  - Hosmer-Lemeshow χ² test
  - Bin-level calibration table (10 bins, 0–100%)
  - Wilson CIs on actual YES rate per bin
  - Net edge = |pred - actual| - 2% spread
  - Kelly half-fraction and EV/month at $10k bankroll

LATEX REPORT: research/reports/04_cross_category_efficiency.tex
  - Professional format: 12pt article, booktabs tables, reliability diagram figures
  - Abstract, Introduction, Methodology, Results (per category), Summary table, Conclusion
  - Mathematical notation for Brier, HL, Kelly
  - Every number from data — NO invented statistics
  - Tone: SIG/Jane Street internal research memo — precise, rigorous, honest about limitations
  - Include: "which niche to trade" recommendation with supporting evidence

CONSTRAINTS:
  - Pure research, no live trading code
  - Use polars for data, numpy/scipy for stats
  - Every claim backed by numbers from the actual fetch
  - Flag underpowered categories clearly (n < 100)
  - Commit data fetch, analysis script, and LaTeX separately
  - The sports result from Phase 3 (2024 data) feeds into context — Phase 4 uses 2026 data
