Read CLAUDE.md first. Then execute Phase 1: Research & Validation.

GOAL: Before writing any execution code, prove that exploitable inefficiencies actually exist in prediction markets. Specifically, prove or disprove the calibration arbitrage hypothesis on Polymarket historical data.

PHASE 1 TASKS (do all of these autonomously):

1. Set up the project skeleton per CLAUDE.md's project structure. Use uv for deps. Initialize git, set up pre-commit hooks for ruff and mypy.

2. Build the data ingestion layer for Polymarket:
   - Pull resolved (closed) markets via their public API
   - Get the full price history for each market
   - Cache to parquet files in data/cache/
   - Schema with Pydantic, stored efficiently
   - Target: at least 500 resolved binary markets across categories (politics, sports, crypto, economics)

3. Build the calibration analysis pipeline:
   - For each market, take the price at T-1 day, T-7 days, T-30 days before resolution
   - Bin markets by predicted probability (e.g., 0-5%, 5-10%, ..., 95-100%)
   - Compute: actual resolution rate per bin, Brier score, log score, reliability diagram
   - Compare to perfect calibration

4. Statistical tests:
   - Is miscalibration statistically significant? (Hosmer-Lemeshow test)
   - Is it consistent across categories or category-specific?
   - Does it persist over time or has the market gotten more efficient?
   - Bootstrap confidence intervals on all metrics

5. Write a research report at research/reports/01_polymarket_calibration.md with:
   - Methodology
   - Findings with plots (use matplotlib, save to research/reports/figures/)
   - Honest assessment: is there a tradeable edge or not?
   - If yes, estimated edge size after realistic transaction costs (assume 2% bid-ask spread)
   - Recommended next steps

CONSTRAINTS:
- No live trading code in this phase. Pure research.
- Every claim in the report must be backed by a number from the data.
- If the data doesn't support a tradeable edge, SAY SO. Don't manufacture a positive result.
- Use polars, not pandas.
- Commit after each major step with conventional commits.

When done, summarize findings and propose Phase 2 based on what you found.