import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

import matplotlib.image as mpimg
import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fund_forward_decision import (
    DEFAULT_FORWARD_METHOD,
    add_cross_fund_context,
    confidence_level,
    create_all_horizon_chart,
    decide,
    decide_legacy,
    decision_score,
    deduplicate_csv_paths,
    intervals_overlap,
    scaled_return_threshold,
    select_non_overlapping_rows,
    shrunk_binomial_estimate,
    summarize_analogs,
)


class FundPathDeduplicationTests(unittest.TestCase):
    def test_keeps_newest_file_for_normalized_fund_label(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            older = root / "APCR_AsiaPacificREIT_nav_5Y.csv"
            newer = root / "APCR_AsiaPacificREIT_nav_5Y_20260713_010000.csv"
            older.write_text("Date,TotalReturn\n2026-01-01,1\n", encoding="utf-8")
            newer.write_text("Date,TotalReturn\n2026-01-02,2\n", encoding="utf-8")
            os.utime(older, (1, 1))
            os.utime(newer, (2, 2))

            selected = deduplicate_csv_paths([older, newer])

        self.assertEqual(selected, [newer])

    def test_collapses_repeated_identical_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "APCR_AsiaPacificREIT_nav_5Y.csv"
            path.write_text("Date,TotalReturn\n2026-01-01,1\n", encoding="utf-8")

            selected = deduplicate_csv_paths([path, path])

        self.assertEqual(selected, [path])


class AllHorizonChartTests(unittest.TestCase):
    def test_duplicate_rows_do_not_crash_chart_pivot(self):
        base = {
            "Fund Label": "APCR_AsiaPacificREIT",
            "Horizon": "6M",
            "Expected Forward Return": 0.10,
            "Probability >= Upside Target": 0.50,
            "Probability <= Downside Risk": 0.10,
            "Expected Shortfall 10%": -0.05,
            "Confidence Level": "NORMAL",
            "Analog Count": 100,
            "Upside Target": 0.15,
            "Downside Risk": -0.08,
        }
        details = pd.DataFrame(
            [
                {**base, "Decision Score": 0.40},
                {**base, "Decision Score": 0.30},
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            chart_dir = Path(temp_dir)
            path = create_all_horizon_chart(details, chart_dir, ["6M"])

            self.assertTrue(path.exists())
            image = mpimg.imread(path)
            self.assertGreaterEqual(image.shape[1], 4000)
            self.assertGreaterEqual(image.shape[0], 1800)


class MethodologyTests(unittest.TestCase):
    def test_compounded_thresholds_are_horizon_consistent(self):
        one_month_target = scaled_return_threshold(0.15, 21, 126)
        one_year_target = scaled_return_threshold(0.15, 252, 126)

        self.assertAlmostEqual(one_month_target, (1.15 ** (1 / 6)) - 1)
        self.assertAlmostEqual(one_year_target, 1.15**2 - 1)

    def test_analog_selection_removes_overlapping_holding_periods(self):
        frame = pd.DataFrame(
            {
                "Start Date": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-08-01"]),
                # Actual end dates, not reconstructed horizon offsets.
                "End Date": pd.to_datetime(["2024-07-01", "2024-08-01", "2025-02-01"]),
                "Analog Distance": [0.1, 0.2, 0.3],
            }
        )

        selected = select_non_overlapping_rows(
            frame,
            horizon_days=126,
            max_rows=20,
            sort_columns=["Analog Distance", "Start Date"],
        )

        self.assertEqual(selected["Start Date"].dt.strftime("%Y-%m-%d").tolist(), ["2024-01-01", "2024-08-01"])

    def test_actual_long_interval_intersection_is_detected(self):
        self.assertTrue(intervals_overlap("2024-01-01", "2024-08-15", "2024-08-01", "2025-02-01"))

    def test_boundary_touching_intervals_are_independent(self):
        self.assertFalse(intervals_overlap("2024-01-01", "2024-07-01", "2024-07-01", "2025-01-01"))

    def test_small_analog_sample_is_shrunk_toward_base_rate(self):
        probability, _, _ = shrunk_binomial_estimate(4, 4, base_probability=0.20, prior_strength=8)

        self.assertGreater(probability, 0.20)
        self.assertLess(probability, 1.0)

    def test_legacy_decision_rule_remains_callable_for_reproducibility(self):
        row = pd.Series(
            {
                "Probability >= Upside Target": 0.30,
                "Probability <= Downside Risk": 0.10,
                "Expected Forward Return": 0.05,
                "Confidence Level": "NORMAL",
            }
        )
        self.assertEqual(decide_legacy(row)[0], "BUY")

    def test_favorable_rebound_statistics_cannot_buy_without_trend_confirmation(self):
        row = pd.Series(
            {
                "Probability >= Upside Target": 0.60,
                "Probability <= Downside Risk": 0.05,
                "Probability > 0": 0.75,
                "Expected Forward Return": 0.20,
                "Conditional Expected Edge": 0.10,
                "Relative Upside Probability Lift": 0.08,
                "Relative Downside Probability Lift": -0.03,
                "Decision Score": 0.8,
                "Forward Method Version": DEFAULT_FORWARD_METHOD,
                "Confidence Level": "NORMAL",
                "Horizon": "6M",
                "Analog Count": 10,
                "Base Observations": 10,
                "Candidate Analog Count": 500,
                "Upside Target": 0.15,
                "Downside Risk": -0.08,
                "Base Probability >= Upside Target": 0.30,
                "Base Probability <= Downside Risk": 0.10,
                "Upside Probability CI Low": 0.20,
                "Current Trailing Return 6M": -0.10,
                "Current EMA 50/200 Gap": -0.05,
                "Current EMA 200 Slope 1M": -0.01,
                "Cross-Fund Momentum Percentile": 0.90,
            }
        )

        action, _ = decide(row)

        self.assertNotEqual(action, "BUY")

    def test_confirmed_recovery_can_buy_without_being_above_long_term_average(self):
        row = pd.Series(
            {
                "Probability >= Upside Target": 0.45,
                "Probability <= Downside Risk": 0.05,
                "Probability > 0": 0.75,
                "Expected Forward Return": 0.18,
                "Conditional Expected Edge": 0.08,
                "Relative Upside Probability Lift": 0.08,
                "Relative Downside Probability Lift": -0.03,
                "Decision Score": 0.8,
                "Forward Method Version": DEFAULT_FORWARD_METHOD,
                "Confidence Level": "NORMAL",
                "Horizon": "6M",
                "Analog Count": 10,
                "Base Observations": 10,
                "Candidate Analog Count": 500,
                "Upside Target": 0.15,
                "Downside Risk": -0.08,
                "Base Probability >= Upside Target": 0.30,
                "Base Probability <= Downside Risk": 0.10,
                "Upside Probability CI Low": 0.20,
                "Current Trend State": "recovering / mixed",
                "Current Trailing Return 1M": 0.03,
                "Current Trailing Return 3M": 0.07,
                "Current Trailing Return 6M": -0.02,
                "Current Rebound From 3M Low": 0.08,
                "Current EMA 50/200 Gap": -0.01,
                "Current EMA 200 Slope 1M": 0.01,
                "Self-Relative Momentum Percentile": 0.45,
                "Self-Relative Momentum Percentile 1M Ago": 0.35,
                "Cross-Fund Momentum Percentile": 0.70,
            }
        )

        action, _ = decide(row)

        self.assertEqual(action, "BUY")

    def test_low_confidence_suppresses_sell(self):
        row = pd.Series(
            {
                "Forward Method Version": DEFAULT_FORWARD_METHOD,
                "Probability >= Upside Target": 0.05,
                "Probability <= Downside Risk": 0.55,
                "Expected Forward Return": -0.10,
                "Conditional Expected Edge": -0.08,
                "Relative Upside Probability Lift": -0.05,
                "Relative Downside Probability Lift": 0.10,
                "Decision Score": -1.0,
                "Confidence Level": "LOW",
                "Horizon": "6M",
                "Analog Count": 5,
                "Base Observations": 10,
                "Candidate Analog Count": 50,
                "Upside Target": 0.15,
                "Downside Risk": -0.08,
                "Current Trailing Return 6M": -0.10,
                "Current EMA 50/200 Gap": -0.04,
                "Current EMA 200 Slope 1M": -0.01,
                "Self-Relative Momentum Percentile": 0.20,
            }
        )
        self.assertEqual(decide(row)[0], "HOLD / WATCH")

    def test_confidence_uses_both_analog_and_baseline_counts(self):
        self.assertEqual(confidence_level(12, 5, 6), "LOW")
        self.assertEqual(confidence_level(8, 20, 6), "MEDIUM")
        self.assertEqual(confidence_level(12, 12, 6), "NORMAL")

    def test_score_is_unavailable_without_any_valid_sigma(self):
        self.assertTrue(pd.isna(decision_score(0.05, float("nan"))))

    def test_single_fund_cross_context_is_reporting_only(self):
        frame = pd.DataFrame([{"Fund Label": "A", "Decision Label": "HOLD / WATCH"}])
        result = add_cross_fund_context(frame)
        self.assertTrue(pd.isna(result.loc[0, "Cross-Fund Momentum Percentile"]))

    def test_relative_lifts_use_two_stage_shrunk_probabilities(self):
        starts = pd.date_range("2020-01-01", periods=8, freq="180D")
        forward = pd.DataFrame(
            {
                "Start Date": starts,
                "End Date": starts + pd.Timedelta(days=90),
                "Forward Return": [-0.20, -0.10, -0.05, 0.00, 0.05, 0.10, 0.20, 0.30],
            }
        )
        analogs = forward.iloc[[4, 5, 6, 7]].copy()
        analogs["Analog Distance"] = [0.1, 0.2, 0.3, 0.4]
        latest = pd.Series(
            {
                "Date": pd.Timestamp("2025-01-01"),
                "TotalReturn": 1.0,
                "Trend State": "uptrend",
                "Trailing Return 1M": 0.01,
                "Trailing Return 3M": 0.03,
                "Trailing Return 6M": 0.08,
                "Drawdown From 6M High": 0.0,
                "Drawdown From 1Y High": 0.0,
                "Rebound From 3M Low": 0.08,
                "Annualized Volatility 3M": 0.10,
                "RSI 14": 55.0,
                "EMA 50/200 Gap": 0.02,
                "EMA 200 Slope 1M": 0.01,
            }
        )
        args = SimpleNamespace(
            forward_method=DEFAULT_FORWARD_METHOD,
            upside_target=0.15,
            downside_risk=-0.08,
            primary_horizon_days=126,
            target_scaling="compounded",
            prior_strength=4.0,
            min_analogs=4,
        )
        result = summarize_analogs("A", latest, "6M", 126, analogs, forward, args)
        base_up, _, _ = shrunk_binomial_estimate(2, 8, 0.25, 4.0)
        conditional_up, _, _ = shrunk_binomial_estimate(2, 4, base_up, 4.0)
        self.assertAlmostEqual(result["Base Relative Upside Probability"], base_up)
        self.assertAlmostEqual(result["Relative Upside Probability Lift"], conditional_up - base_up)


if __name__ == "__main__":
    unittest.main()
