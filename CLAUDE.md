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
