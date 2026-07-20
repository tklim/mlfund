Forward-Decision Methodology V2 — Corrected Implementation Plan

Summary

Implement dual\_relative\_v2 as the default while retaining a callable legacy model for comparison. Absolute +15%/−8% probabilities remain descriptive; decisions use shrunk P75/P25 probability lifts, path-specific momentum confirmation, conditional return edge, and exact independent intervals.

Live verification shows both fund\_forward\_decision.py and operate.py currently default to prior strength 4.0; keep 4 pre-registered. Sensitivity testing must not choose a different value from holdout results.

Core Model

Add --forward-method {legacy,dual-relative-v2}, defaulting to V2.legacy faithfully preserves the original overlapping-150/fixed-target methodology for validation only.

Every output includes Forward Method Version.



Determine independence from each row’s actual Start Date and End Date; never reconstruct the end from horizon length.Treat intervals as \[start, end), allowing touching endpoints.

Use the same helper in analog selection, baseline selection, validation, and walk-forward evaluation.



Derive V2 thresholds from training data only:Relative upside threshold = training-return P75.

Relative downside threshold = training-return P25.

During walk-forward evaluation, require every threshold-estimation row to have End Date < decision date.

All eligible training returns may estimate the quantile, but only exact non-overlapping periods contribute evidence counts and probabilities.



Stabilize relative probabilities in two stages:Shrink the independent baseline P75/P25 event probabilities toward their nominal 25% rates with prior strength 4.

Shrink conditional analog probabilities toward those stabilized baseline probabilities with prior strength 4.

Compute all decision lifts from shrunk conditional probability minus shrunk baseline probability; retain raw probabilities for diagnostics only.



Replace the mixed-unit score with:score\_sigma = max(independent baseline forward-return std, current annualized 3M volatility × sqrt(horizon\_days/252), 0.01).

Ignore NaN candidates; if neither volatility estimate is valid, set score unavailable and force HOLD.

Decision Score = clip(Conditional Expected Edge / score\_sigma, -3, 3).



Confidence requires both independent analog count and independent baseline count:LOW if either is below 6.

MEDIUM from 6–11.

NORMAL from 12 upward.

BUY and SELL both require at least MEDIUM confidence.

Consequently, 1Y decisions are HOLD by construction with five years of history; 6M decisions will remain deliberately rare.



Decision Paths and Momentum

Compute self-relative risk-adjusted momentum from annualized 3M/6M returns weighted 40%/60%, divided by annualized 3M volatility with a 5% floor.

Rank it against that fund’s own prior history. Also retain its value from 21 trading days earlier to detect direction.

Trend BUY path:Existing confirmed-trend conditions.

Self-relative momentum percentile ≥55%.



Recovery BUY path:recovering / mixed state.

Positive 1M and 3M returns, positive EMA200 slope, and rebound from 3M low ≥5%.

Self-relative momentum percentile ≥40%.

Current momentum percentile greater than its value 21 trading days earlier.



Both BUY paths additionally require:Positive absolute expected return and conditional expected edge.

Shrunk relative-upside lift ≥5 percentage points.

Shrunk relative-downside lift ≤0.



SELL requires:At least two broken-trend indicators.

Self-relative momentum percentile ≤45%.

Negative conditional expected edge.

Shrunk relative-downside lift ≥5 percentage points.

Shrunk relative-upside lift ≤0.



Otherwise return HOLD / WATCH. Drawdown is described only as a depressed-price state, never “cheapness” or valuation.

Keep cross-fund momentum as contextual reporting only; it cannot qualify or disqualify a decision.

Centralize decision creation after all metrics are assembled so CLI, programmatic, chart, and single-fund paths use identical rules.

Integration and Reporting

Make the V2 forward decision authoritative in operate.py.Remove the independently thresholded Buy/Sell conclusion.

Present GA as CONFIRM, CONFLICT, or NEUTRAL.

Replace old Buy/Sell score fields with forward decision, standardized evidence score, shrunk relative lifts, reliability, GA signal, agreement, and data status.

Update all repository CSV/Markdown/HTML consumers with the new schema.



Keep technical likelihoods separate:Rename/alias fields as Technical Absolute Probability >= Upside Target and corresponding downside/return fields.

Label the section “absolute-threshold technical likelihood—separate model and not a V2 decision input.”

Preserve legacy column aliases for one compatibility cycle.



Add dashboard explanations for:Absolute versus relative metrics.

Shrunk versus raw probabilities.

Why 1Y is evidence-limited.

Why rare 6M signals are expected.

If more activity is needed, recommend a 3M primary horizon or longer NAV history—not overlapping windows or weaker independence rules.



Walk-Forward Validation, Tests, and Documentation

Add a reproducible rolling-origin validator that invokes both legacy and dual-relative-v2 without git archaeology.

For every evaluation:Train only on rows with actual End Date < decision date.

Calculate features, P25/P75 thresholds, momentum percentiles, priors, and analogs solely from that training slice.

Space evaluation decisions by at least the evaluated horizon.

Use the earliest 70% of evaluation dates for diagnostics and the latest 30% as untouched holdout.



Prior 4 remains pre-registered. Report 2/4/8 sensitivity on calibration data only; do not switch automatically.

Report MAE, signed bias, absolute-event Brier scores, relative-event Brier scores, label frequency, realized outcomes by label, and results by trend state and volatility tertile.

Rollout acceptance:Accept when holdout MAE and average Brier improve, or one improves while the other worsens by no more than 5%.

Stop for review if both worsen or a subgroup with at least ten observations develops over five percentage points of additional signed bias.

Report “insufficient decisions” rather than relaxing rules when BUY/SELL samples are too small.



Add tests for actual interval intersections, boundary-touching intervals, training cutoffs for quantiles, shrunk-lift calculations, trend and recovery paths, low-confidence SELL suppression, single-fund behavior, score denominator fallback, legacy reproducibility, downstream authority, and look-ahead prevention.

Update FORWARD\_DECISION\_METHODOLOGY\_REVIEW.md with prior 4, regenerated results, feasibility limits, recovery-specific momentum rules, V2 schema, and walk-forward findings.

Replace secondary sources with the specified canonical literature: Hansen–Hodrick, Newey–West, Jegadeesh–Titman, Daniel–Moskowitz, Moreira–Muir, De Bondt–Thaler, Carhart, and Bailey–López de Prado.

Treat all ratings as general research support, not personalized financial advice.

