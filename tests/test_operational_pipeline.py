import copy
import importlib.util
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd
import pandas.testing as pdt

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SCRIPTS_DIR))

import common
import download_fund
import final_backtest_from_summary
import fund_forward_decision
import fund_strategy_review
import operate


def load_backtester_module():
    path = SCRIPTS_DIR / "backtest-ema-ga10-index.py"
    spec = importlib.util.spec_from_file_location("backtest_ema_ga10_index", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OperationalPipelineTests(unittest.TestCase):
    def setUp(self):
        self.config = operate.load_config()

    def test_fund_label_from_multi_underscore_data_file(self):
        label = common.fund_label_from_data_file("data/MAUS_RMH_USEquityRMH_nav_5Y.csv")
        self.assertEqual(label, "MAUS_RMH_USEquityRMH")

    def test_dividend_reinvested_index_matches_fixture(self):
        fixture = pd.read_csv(FIXTURES_DIR / "dividend_reinvestment.csv")
        actual = common.dividend_reinvested_index(fixture["NAV"], fixture["Dividend"])
        expected = fixture["ExpectedTotalReturn"].rename("TotalReturn")
        pdt.assert_series_equal(actual, expected, check_exact=False, rtol=1e-12, atol=1e-12)

    def test_dividend_reinvested_index_preserves_financial_invariants(self):
        fixture = pd.read_csv(FIXTURES_DIR / "dividend_reinvestment.csv")
        total_return = common.dividend_reinvested_index(fixture["NAV"], fixture["Dividend"])

        no_dividend = common.dividend_reinvested_index(fixture["NAV"], fixture["Dividend"] * 0)
        pdt.assert_series_equal(
            no_dividend,
            fixture["NAV"].rename("TotalReturn"),
            check_exact=False,
            rtol=1e-12,
            atol=1e-12,
        )

        ex_dividend_row = fixture.index[fixture["Dividend"].eq(0.10)][0]
        self.assertAlmostEqual(total_return.iloc[ex_dividend_row], total_return.iloc[ex_dividend_row - 1])

        scaled = common.dividend_reinvested_index(fixture["NAV"] * 10, fixture["Dividend"] * 10)
        pdt.assert_series_equal(
            total_return / total_return.iloc[0],
            scaled / scaled.iloc[0],
            check_names=False,
            check_exact=False,
            rtol=1e-12,
            atol=1e-12,
        )

    def test_backtester_uses_shared_multi_underscore_label(self):
        backtester = load_backtester_module()
        label = backtester.infer_fund_output_label("data/MSGLR_RM_ShariahGlobalREITMYR_nav_5Y.csv")
        self.assertEqual(label, "MSGLR_RM_ShariahGlobalREITMYR")

    def test_strategy_review_canonicalizes_history_labels_from_data_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.csv"
            pd.DataFrame(
                [
                    {
                        "fund_label": "MAUSRMHUSEquityRMHnav5Y",
                        "data_file": str(REPO_ROOT / "data" / "MAUS_RMH_USEquityRMH_nav_5Y.csv"),
                        "run_status": "completed",
                        "adaptive_return_pct": 10,
                        "buy_hold_return_pct": 8,
                        "adaptive_annualized_return_pct": 5,
                        "buy_hold_annualized_return_pct": 4,
                        "excess_annualized_return_pct": 1,
                    }
                ]
            ).to_csv(history_path, index=False)
            loaded = fund_strategy_review.load_history(history_path)
        self.assertEqual(loaded.iloc[0]["fund_label"], "MAUS_RMH_USEquityRMH")

    def test_best_by_fund_selects_each_funds_own_best_ga_row(self):
        df = pd.DataFrame(
            [
                {
                    "fund_label": "AAA",
                    "adaptive_annualized_return_pct": 5,
                    "buy_hold_annualized_return_pct": 4,
                    "excess_annualized_return_pct": 1,
                    "adaptive_return_pct": 10,
                    "buy_hold_return_pct": 8,
                    "excess_return_pct": 2,
                    "sharpe": 0.5,
                    "max_dd_pct": 10,
                    "win_rate_pct": 40,
                    "lookback_years": 1,
                    "offset_months": 3,
                    "log_file": "",
                },
                {
                    "fund_label": "AAA",
                    "adaptive_annualized_return_pct": 8,
                    "buy_hold_annualized_return_pct": 4,
                    "excess_annualized_return_pct": 4,
                    "adaptive_return_pct": 16,
                    "buy_hold_return_pct": 8,
                    "excess_return_pct": 8,
                    "sharpe": 0.7,
                    "max_dd_pct": 9,
                    "win_rate_pct": 45,
                    "lookback_years": 2,
                    "offset_months": 6,
                    "log_file": "",
                },
                {
                    "fund_label": "BBB",
                    "adaptive_annualized_return_pct": -1,
                    "buy_hold_annualized_return_pct": -3,
                    "excess_annualized_return_pct": 2,
                    "adaptive_return_pct": -2,
                    "buy_hold_return_pct": -6,
                    "excess_return_pct": 4,
                    "sharpe": 0.1,
                    "max_dd_pct": 12,
                    "win_rate_pct": 35,
                    "lookback_years": 1,
                    "offset_months": 9,
                    "log_file": "",
                },
            ]
        )
        best = fund_strategy_review.build_best_by_fund(df).set_index("fund_label")
        self.assertEqual(len(best), 2)
        self.assertEqual(best.loc["AAA", "lookback_years"], 2)
        self.assertEqual(best.loc["BBB", "offset_months"], 9)

    def test_rejects_percent_style_upside_target(self):
        config = copy.deepcopy(self.config)
        config["upside_target"] = 15
        with self.assertRaises(ValueError):
            operate.validate_config(config)

    def test_forward_command_uses_decimal_upside_target(self):
        command = operate.build_forward_decision_command(self.config)
        idx = command.index("--upside-target")
        self.assertEqual(command[idx + 1], "0.15")
        self.assertNotIn("--upside-target 15", operate.command_text(command))
        self.assertEqual(command[command.index("--min-analogs") + 1], "6")
        self.assertEqual(command[command.index("--max-analogs") + 1], "20")
        self.assertEqual(command[command.index("--prior-strength") + 1], "8")

    def test_forward_confidence_is_low_with_too_few_independent_observations(self):
        self.assertEqual(fund_forward_decision.confidence_level(150, 4, 40), "LOW")
        self.assertEqual(fund_forward_decision.confidence_level(150, 5, 40), "LOW")

    def test_forward_analogs_are_non_overlapping(self):
        frame = pd.DataFrame(
            {
                "Start Date": pd.date_range("2020-01-01", periods=18, freq="MS"),
                "Forward Return": range(18),
            }
        )
        selected = fund_forward_decision.select_non_overlapping_rows(frame, horizon_days=63)
        gaps = selected["Start Date"].sort_values().diff().dropna().dt.days
        self.assertTrue((gaps >= 91).all())
        self.assertLess(len(selected), len(frame))

    def test_forward_probability_shrinks_toward_fund_base_rate(self):
        probability, low, high = fund_forward_decision.shrunk_binomial_estimate(
            successes=4,
            observations=4,
            base_probability=0.20,
            prior_strength=8,
        )
        self.assertGreater(probability, 0.20)
        self.assertLess(probability, 1.0)
        self.assertLess(low, probability)
        self.assertGreater(high, probability)

    def test_practical_buy_requires_trend_and_relative_strength_confirmation(self):
        bullish = pd.Series(
            {
                "Probability >= Upside Target": 0.50,
                "Base Probability >= Upside Target": 0.20,
                "Upside Probability CI Low": 0.20,
                "Probability <= Downside Risk": 0.08,
                "Base Probability <= Downside Risk": 0.10,
                "Probability > 0": 0.70,
                "Expected Forward Return": 0.12,
                "Conditional Expected Edge": 0.05,
                "Relative Upside Probability Lift": 0.08,
                "Relative Downside Probability Lift": -0.03,
                "Decision Score": 0.8,
                "Confidence Level": "MEDIUM",
                "Horizon": "6M",
                "Analog Count": 8,
                "Candidate Analog Count": 500,
                "Upside Target": 0.15,
                "Downside Risk": -0.08,
                "Current Trailing Return 6M": 0.18,
                "Current EMA 50/200 Gap": 0.06,
                "Current EMA 200 Slope 1M": 0.02,
                "Self-Relative Momentum Percentile": 0.80,
                "Cross-Fund Momentum Percentile": 0.90,
            }
        )
        weak_rebound = bullish.copy()
        weak_rebound["Current Trailing Return 6M"] = -0.18
        weak_rebound["Current EMA 50/200 Gap"] = -0.06
        weak_rebound["Current EMA 200 Slope 1M"] = -0.02
        weak_rebound["Cross-Fund Momentum Percentile"] = 0.10

        self.assertEqual(fund_forward_decision.decide(bullish)[0], "BUY")
        self.assertNotEqual(fund_forward_decision.decide(weak_rebound)[0], "BUY")

    def test_final_backtest_command_uses_all_funds(self):
        command = operate.build_final_backtest_command(self.config)
        self.assertIn("final_backtest_from_summary.py", command[1])
        self.assertEqual(command[command.index("--top-funds") + 1], "0")
        self.assertEqual(command[command.index("--price-column") + 1], "TotalReturn")

    def test_latest_dashboard_sorts_funds_and_includes_zoom_controls(self):
        rows = [
            {
                "status": "completed",
                "fund_label": "LOW_RETURN",
                "latest_chart_file": "charts/low.png",
                "latest_adaptive_annualized_return_pct": 3.0,
                "latest_adaptive_return_pct": 4.0,
                "latest_buy_hold_annualized_return_pct": 2.0,
                "latest_excess_annualized_return_pct": 1.0,
                "latest_max_dd_pct": 5.0,
                "latest_data_end": "2026-07-10",
            },
            {
                "status": "completed",
                "fund_label": "HIGH_RETURN",
                "latest_chart_file": "charts/high.png",
                "latest_adaptive_annualized_return_pct": 12.0,
                "latest_adaptive_return_pct": 18.0,
                "latest_buy_hold_annualized_return_pct": 8.0,
                "latest_excess_annualized_return_pct": 4.0,
                "latest_max_dd_pct": 6.0,
                "latest_data_end": "2026-07-10",
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            chart_dir = Path(tmpdir) / "charts"
            chart_dir.mkdir()
            for row in rows:
                chart_path = chart_dir / f"{row['fund_label']}.png"
                final_backtest_from_summary.plt.imsave(
                    chart_path,
                    final_backtest_from_summary.np.ones((20, 40, 3)),
                )
                row["latest_chart_file"] = str(chart_path)
            with mock.patch.object(final_backtest_from_summary, "REPORTS_DIR", Path(tmpdir)):
                dashboard_path = final_backtest_from_summary.write_latest_dashboard(rows, "test-run")
                pdf_path = final_backtest_from_summary.write_latest_pdf(rows)
            dashboard = dashboard_path.read_text(encoding="utf-8")
            pdf_bytes = pdf_path.read_bytes()

        self.assertLess(dashboard.index("HIGH_RETURN"), dashboard.index("LOW_RETURN"))
        self.assertEqual(dashboard.count('class="fund-card"'), 2)
        self.assertIn("Click to zoom", dashboard)
        self.assertIn("@page{size:A4 landscape", dashboard)
        self.assertIn("break-after:page", dashboard)
        self.assertIn("image.addEventListener('load',fit)", dashboard)
        self.assertIn("viewport.addEventListener('wheel'", dashboard)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertEqual(len(re.findall(rb"/Type\s*/Page\b", pdf_bytes)), 2)

    def test_report_commands_include_final_backtest(self):
        commands = operate.build_report_commands(self.config)
        command_texts = [operate.command_text(command) for command in commands]
        self.assertTrue(any("final_backtest_from_summary.py" in text for text in command_texts))

    def test_parallel_runner_rejects_zero_workers(self):
        with self.assertRaises(ValueError):
            operate.run_commands_parallel([["python", "--version"]], max_workers=0, dry_run=True)

    def test_deep_backtest_dry_run_builds_all_configured_commands(self):
        with mock.patch("builtins.print"):
            results = operate.run_commands_parallel(
                operate.build_backtest_commands(self.config),
                max_workers=4,
                dry_run=True,
            )
        expected = len(self.config["backtest"]["lookback_years"]) * len(self.config["backtest"]["offset_months"])
        self.assertEqual(len(results), expected)
        self.assertTrue(all("--reuse-tuned-params" in row["command"] for row in results))

    def test_data_health_rows_detect_fresh_valid_file(self):
        config = copy.deepcopy(self.config)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            csv_path = tmp_path / "MAUS_RMH_USEquityRMH_nav_5Y.csv"
            pd.DataFrame(
                {
                    "Date": [pd.Timestamp.today().date().isoformat()],
                    "NAV": [1.0],
                    "Dividend": [0.0],
                    "TotalReturn": [1.0],
                }
            ).to_csv(csv_path, index=False)
            with mock.patch.object(operate, "DATA_DIR", tmp_path):
                rows = operate.data_health_rows(config)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["fund_label"], "MAUS_RMH_USEquityRMH")
        self.assertEqual(rows[0]["freshness_status"], "fresh")
        self.assertEqual(rows[0]["missing_columns"], "")

    def test_decision_scores_identify_bullish_bearish_and_low_reliability_cases(self):
        dashboard = pd.DataFrame(
            [
                {
                    "Fund Label": "BULL",
                    "Decision Label": "BUY",
                    "Probability >= Upside Target": 0.80,
                    "Probability <= Downside Risk": 0.05,
                    "Probability > 0": 0.90,
                    "Expected Forward Return": 0.20,
                    "Upside Target": 0.15,
                    "Downside Risk": -0.08,
                    "Current Trend State": "uptrend",
                    "Effective Observations": 20,
                    "Confidence Level": "NORMAL",
                },
                {
                    "Fund Label": "BEAR",
                    "Decision Label": "SELL / AVOID",
                    "Probability >= Upside Target": 0.05,
                    "Probability <= Downside Risk": 0.80,
                    "Probability > 0": 0.10,
                    "Expected Forward Return": -0.12,
                    "Upside Target": 0.15,
                    "Downside Risk": -0.08,
                    "Current Trend State": "downtrend",
                    "Effective Observations": 20,
                    "Confidence Level": "NORMAL",
                },
                {
                    "Fund Label": "THIN_SAMPLE",
                    "Decision Label": "HOLD / WATCH",
                    "Probability >= Upside Target": 0.80,
                    "Probability <= Downside Risk": 0.05,
                    "Probability > 0": 0.90,
                    "Expected Forward Return": 0.20,
                    "Upside Target": 0.15,
                    "Downside Risk": -0.08,
                    "Current Trend State": "uptrend",
                    "Effective Observations": 2,
                    "Confidence Level": "MEDIUM",
                },
            ]
        )
        strategies = pd.DataFrame(
            [
                {"fund_label": "BULL", "ga_signal": "BUY/HOLD invested", "excess_annualized_return_pct": 20},
                {"fund_label": "BEAR", "ga_signal": "SELL / CASH", "excess_annualized_return_pct": -20},
                {"fund_label": "THIN_SAMPLE", "ga_signal": "BUY/HOLD invested", "excess_annualized_return_pct": 20},
            ]
        )
        health = pd.DataFrame(
            [
                {"fund_label": fund, "freshness_status": "fresh"}
                for fund in ["BULL", "BEAR", "THIN_SAMPLE"]
            ]
        )

        scores = operate.build_decision_scores(dashboard, strategies, health).set_index("Fund Label")

        self.assertEqual(scores.loc["BULL", "Conclusion"], "BUY")
        self.assertEqual(scores.loc["BEAR", "Conclusion"], "SELL / AVOID")
        self.assertEqual(scores.loc["THIN_SAMPLE", "Conclusion"], "HOLD / WATCH")
        self.assertNotIn("Buy Score", scores.columns)

    def test_download_many_continues_after_one_failed_fund(self):
        def fake_download(fund_id, years):
            if fund_id == "BAD":
                raise RuntimeError("network failed")
            return {
                "fund_id": fund_id,
                "fund_name": "Good Fund",
                "fund_label": "GOOD_GoodFund",
                "current_nav": 1.0,
                "current_date": "2026-06-14",
                "change": 0.0,
                "change_pct": 0.0,
                "dividend_count": 0,
                "records": 1,
                "output_path": "data/GOOD_GoodFund_nav_5Y.csv",
            }

        with (
            mock.patch.object(download_fund, "download_fund", side_effect=fake_download),
            mock.patch("builtins.print"),
        ):
            results, failed = download_fund.download_many(["GOOD", "BAD", "ALSO_GOOD"], years=5)

        self.assertEqual(failed, 1)
        self.assertEqual([row["status"] for row in results], ["ok", "failed", "ok"])
        self.assertEqual(len(results), 3)

    def test_download_many_marks_dividend_warning_as_partial_success(self):
        def fake_download(_fund_id, years):
            return {
                "fund_id": "WARN",
                "fund_name": "Warning Fund",
                "fund_label": "WARN_Warning",
                "current_nav": 1.0,
                "current_date": "2026-06-14",
                "change": 0.0,
                "change_pct": 0.0,
                "dividend_count": 0,
                "dividend_source": "unavailable",
                "warning": "unable to load dividend history",
                "records": 1,
                "output_path": "data/WARN_Warning_nav_5Y.csv",
            }

        with (
            mock.patch.object(download_fund, "download_fund", side_effect=fake_download),
            mock.patch("builtins.print"),
        ):
            results, failed = download_fund.download_many(["WARN"], years=5)

        self.assertEqual(failed, 0)
        self.assertEqual(results[0]["status"], "ok_with_warnings")
        self.assertIn("dividend", results[0]["warning"])

    def test_download_fund_reuses_cached_dividends_when_dividend_endpoint_fails(self):
        today = pd.Timestamp.today().date().isoformat()

        def fake_fetch_json(_url, *, description):
            if "fund details" in description:
                return {
                    "fundName": "Manulife Test Fund",
                    "nav": {
                        "price": 1.10,
                        "asOfDate": today,
                        "changePrice": 0.01,
                        "changePercent": 0.9,
                    },
                }
            if "NAV prices" in description:
                return [{"asOfDate": today, "price": 1.10}]
            if "dividend history" in description:
                raise RuntimeError("bad dividend payload")
            raise AssertionError(description)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            cached_path = tmp_path / "TEST_Test_nav_5Y.csv"
            pd.DataFrame(
                {
                    "Date": [today],
                    "NAV": [1.0],
                    "Dividend": [0.05],
                    "TotalReturn": [1.05],
                }
            ).to_csv(cached_path, index=False)

            with (
                mock.patch.object(download_fund, "DATA_DIR", tmp_path),
                mock.patch.object(download_fund, "fetch_json", side_effect=fake_fetch_json),
                mock.patch("builtins.print"),
            ):
                result = download_fund.download_fund("TEST", years=5)

            self.assertEqual(result["dividend_source"], "cached_existing_file")
            self.assertIn("reused 1 cached dividend", result["warning"])
            saved = pd.read_csv(result["output_path"])
            self.assertEqual(float(saved.iloc[0]["Dividend"]), 0.05)


if __name__ == "__main__":
    unittest.main()
