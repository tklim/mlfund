import copy
import importlib.util
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

    def test_final_backtest_command_uses_all_funds(self):
        command = operate.build_final_backtest_command(self.config)
        self.assertIn("final_backtest_from_summary.py", command[1])
        self.assertEqual(command[command.index("--top-funds") + 1], "0")
        self.assertEqual(command[command.index("--price-column") + 1], "TotalReturn")

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
