# Forward-Decision Methodology Review — V2 implementation and validation

Date: 2026-07-13

Scope: `scripts/fund_forward_decision.py`, `scripts/validate_forward_decision_methodology.py`, `scripts/operate.py`, `scripts/technical_signal_review.py`, and their report consumers.

Status: `dual_relative_v2` is implemented and is the default. The legacy method remains callable only for comparison.

All ratings are general research support, not personalized financial advice.

## 1. Why the legacy method was replaced

The legacy model selected up to 150 highly overlapping daily rows for a six-month outcome. Those rows often represented only a handful of independent market episodes, so raw frequencies looked much more precise than the evidence allowed. Fixed +15%/-8% decision targets also made high-volatility funds mechanically more likely to show upside, while weak recent momentum could dominate a recovery setup.

V2 corrects those problems without treating a drawdown as valuation or “cheapness”:

- exact forward intervals use each row's actual `Start Date` and `End Date`;
- intervals are half-open `[start, end)`, so touching endpoints are independent but intersections are rejected;
- relative P75/P25 events determine decisions; fixed absolute targets remain descriptive;
- probabilities and expected returns are stabilized against independent fund-specific baselines;
- current conditions are compared with the fund's own historical momentum distribution;
- trend and recovery BUY paths have different momentum confirmation requirements;
- cross-fund momentum is contextual reporting only.

The callable comparison modes are:

```text
--forward-method dual-relative-v2   # default and authoritative
--forward-method legacy             # overlapping-150/fixed-target comparison only
```

Every dashboard/detail row is tagged with `Forward Method Version`.

## 2. V2 calculation

### Training and independent evidence

For a decision date, every eligible forward-return row used to estimate P25/P75 must have its actual `End Date < decision date`. All such known returns may estimate the quantiles. Evidence counts and event probabilities use only exact non-overlapping periods selected by the shared interval helper.

The same interval logic is used for analogs, baselines, output validation, and walk-forward evaluation. No horizon end is reconstructed from `start + days`.

Confidence requires both analog and baseline evidence:

- `LOW`: either count is below 6;
- `MEDIUM`: both are at least 6 but either is below 12;
- `NORMAL`: both are at least 12.

BUY and SELL require at least MEDIUM confidence. With five years of history, 1Y normally has only about four independent outcomes and is therefore HOLD by construction. Six-month signals are expected to be rare.

### Two-stage probability stabilization

Prior strength 4 is pre-registered in both `fund_forward_decision.py` and `operate.py`.

1. The independent baseline P75 and P25 event probabilities are shrunk toward their nominal 25% event rates with strength 4.
2. Conditional analog probabilities are then shrunk toward those stabilized baseline probabilities with strength 4.
3. Decision lifts are the shrunk conditional probability minus the shrunk baseline probability. Raw probabilities remain diagnostics only.

Sensitivity values 2/4/8 are reported only on the calibration segment. They do not change the locked production value and are not evaluated or selected from holdout results.

### Dimensionless evidence score

`Conditional Expected Edge = shrunk conditional expected return - independent baseline expected return`.

The score denominator is:

```text
max(
  independent baseline forward-return standard deviation,
  current annualized 3M volatility * sqrt(horizon_days / 252),
  0.01
)
```

NaN candidates are ignored. If neither empirical standard deviation nor current volatility is valid, the score is unavailable and the decision is forced to HOLD. Otherwise:

```text
Decision Score = clip(Conditional Expected Edge / score_sigma, -3, 3)
```

### Momentum and decision paths

Risk-adjusted momentum uses 40% annualized 3M return plus 60% annualized 6M return, divided by annualized 3M volatility floored at 5%. It is ranked against that fund's prior history only. The value from 21 trading days earlier is retained to identify direction.

Trend BUY requires the confirmed positive 6M return, EMA50/200 gap, and EMA200 slope setup plus self-relative momentum at or above the 55th percentile.

Recovery BUY requires:

- `recovering / mixed` trend state;
- positive 1M and 3M returns;
- positive EMA200 slope;
- at least 5% rebound from the 3M low;
- self-relative momentum at or above the 40th percentile and rising versus 21 trading days earlier.

Both BUY paths also require positive absolute expected return, positive conditional edge, shrunk relative-upside lift of at least 5 percentage points, and relative-downside lift no greater than zero.

SELL requires at least two broken-trend indicators, self-relative momentum no higher than the 45th percentile, negative conditional edge, relative-downside lift of at least 5 percentage points, relative-upside lift no greater than zero, and at least MEDIUM confidence.

Everything else is `HOLD / WATCH`.

## 3. Integration and reporting

`operate.py` now treats the V2 decision as authoritative. It does not calculate a second Buy/Sell conclusion. The GA strategy is reported only as `CONFIRM`, `CONFLICT`, or `NEUTRAL`, alongside:

- forward decision and method version;
- standardized evidence score;
- shrunk relative upside/downside lifts;
- independent analog and baseline counts;
- evidence reliability and data status.

Technical likelihoods are explicitly separate. New columns use the `Technical Absolute ...` prefix and the report labels them “absolute-threshold technical likelihood—separate model and not a V2 decision input.” Old technical column names remain aliases for one compatibility cycle.

The dashboard explains absolute versus relative metrics, raw versus shrunk probabilities, the 1Y evidence limit, and expected 6M signal rarity. If more activity is required, use a 3M primary horizon or obtain longer NAV history; do not weaken independence or reintroduce overlapping evidence.

## 4. Rolling-origin validation

Reproducible command:

```text
python scripts/validate_forward_decision_methodology.py --all --output-dir outputs/reports
```

The validator calls both production methods directly. Each fund's evaluation decisions are spaced by their actual forward intervals. At every origin, features, analogs, baselines, thresholds, and priors use only past-known data. The earliest 70% of decision dates are calibration diagnostics; the latest 30% are untouched holdout.

Generated artifacts:

- `outputs/reports/forward_decision_walk_forward.csv`
- `outputs/reports/forward_decision_walk_forward_metrics.csv`
- `outputs/reports/forward_decision_walk_forward.md`

### Regenerated 6M results

Ten funds supplied eligible walk-forward periods; `MGPRH_GlobalPerspective` did not have enough prior independent outcomes. At locked prior 4 there were 20 calibration and 10 holdout observations.

| Split | Method | N | MAE | Signed bias | Average Brier* |
|---|---|---:|---:|---:|---:|
| Calibration | Legacy | 20 | 10.50% | +8.31% | 20.37% |
| Calibration | V2, prior 4 | 20 | 7.01% | +3.73% | 14.24% |
| Holdout | Legacy | 10 | 10.40% | -6.05% | 22.36% |
| Holdout | V2, prior 4 | 10 | 9.34% | -7.27% | 18.27% |

\*Average of absolute-upside, absolute-downside, relative-upside, and relative-downside Brier scores.

V2 improved holdout MAE by about 1.06 percentage points and average Brier by about 4.09 percentage points, so it meets the pre-registered acceptance rule. Signed bias was about 1.22 percentage points more negative, well below the 5-point subgroup stop threshold; no holdout subgroup had the required ten observations for a subgroup stop.

The validation signal sample is still insufficient: V2 produced only HOLD/WATCH labels in the spaced historical evaluations. This is reported as insufficient decisions; the model rules were not relaxed. The holdout contains only ten observations, so acceptance is provisional evidence rather than proof of predictive skill.

Calibration-only sensitivity improved gradually from prior 2 to 8 in this small sample, but production remains at pre-registered prior 4. The holdout was not used to select a prior.

## 5. Current regenerated dashboard

Command:

```text
python scripts/fund_forward_decision.py --all --charts --all-horizon-chart --validate
```

The 2026-07-13 V2 dashboard analyzed 11 funds and passed validation:

- 1 BUY: `HWFL_HWFlexi`;
- 10 HOLD/WATCH;
- 0 SELL/AVOID.

The HWFL trend-path BUY has 7 independent analogs and 9 independent baseline periods (MEDIUM confidence), +12.5 percentage points shrunk relative-upside lift, -4.2 points relative-downside lift, positive 1.7% conditional edge, and self-relative momentum at the 81st percentile. It is not a drawdown-based valuation call.

The latest final GA replay ends in `SELL/CASH`, so `operate.py` reports `CONFLICT` for HWFL while preserving the authoritative V2 `BUY` conclusion.

## 6. Tests and limitations

The automated suite covers actual interval intersections, endpoint touching, strict training cutoffs, two-stage shrunk lifts, trend and recovery paths, low-confidence SELL suppression, single-fund context, score unavailability, legacy behavior, authoritative downstream integration, technical aliases, and look-ahead prevention.

Remaining limitations:

- the holdout is small and one fund had no eligible evaluations;
- no historical V2 BUY/SELL sample was large enough for outcome analysis by active label;
- the method models each fund from its own short history and does not establish alpha versus a benchmark;
- current technical backtest parameters are unavailable for the new reinvested-total-return method until they are regenerated; this is surfaced as unavailable rather than silently mixing methods.

## Canonical research basis

- [Hansen and Hodrick (1980), *Forward Exchange Rates as Optimal Predictors of Future Spot Rates*](https://doi.org/10.1086/260910) — overlapping multi-step outcomes.
- [Newey and West (1987), *A Simple, Positive Semi-Definite, Heteroskedasticity and Autocorrelation Consistent Covariance Matrix*](https://www.jstor.org/stable/1913610) — autocorrelation-robust inference.
- [Jegadeesh and Titman (1993), *Returns to Buying Winners and Selling Losers*](https://doi.org/10.1111/j.1540-6261.1993.tb04702.x) and [Jegadeesh and Titman (2001), *Profitability of Momentum Strategies*](https://doi.org/10.1111/0022-1082.00342) — momentum persistence and out-of-sample continuation.
- [Daniel and Moskowitz (2016), *Momentum Crashes*](https://www.nber.org/papers/w20439) — rebound-state momentum crash risk.
- [Moreira and Muir (2017), *Volatility-Managed Portfolios*](https://doi.org/10.1111/jofi.12513) — volatility-aware scaling.
- [De Bondt and Thaler (1985), *Does the Stock Market Overreact?*](https://doi.org/10.1111/j.1540-6261.1985.tb05004.x) — long-horizon reversal evidence.
- [Carhart (1997), *On Persistence in Mutual Fund Performance*](https://doi.org/10.1111/j.1540-6261.1997.tb03808.x) — common-factor and cost explanations for fund persistence.
- [Bailey and López de Prado (2014), *The Deflated Sharpe Ratio*](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551) — selection bias and backtest overfitting.
