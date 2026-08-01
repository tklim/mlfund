import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "backtest-ema-ga10-index.py"


def load_module():
    script_dir = str(SCRIPT_PATH.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location("backtest_ema_ga10_index", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExpandedGaCliTests(unittest.TestCase):
    def test_cli_exposes_expanded_ga_search_inputs(self):
        module = load_module()
        argv = [
            str(SCRIPT_PATH),
            "--initial-capital", "25000",
            "--pop_ranges", "20", "40",
            "--gen_ranges", "30", "60",
            "--take-profit-pct", "25",
            "--data-glob", "AAPL*.csv",
            "--fund-group", "AAPL",
            "--strategy-profile", "generic-bh-reachable",
            "--rebuild-mode", "latest_data",
        ]

        with patch.object(sys, "argv", argv):
            args = module.parse_args()

        self.assertEqual(args.initial_capital, 25000)
        self.assertEqual(args.pop_ranges, ["20", "40"])
        self.assertEqual(args.gen_ranges, ["30", "60"])
        self.assertEqual(args.take_profit_pct, 25)
        self.assertEqual(args.data_glob, "AAPL*.csv")
        self.assertEqual(args.fund_group, "AAPL")
        self.assertEqual(args.strategy_profile, "generic-bh-reachable")
        self.assertEqual(args.rebuild_mode, "latest_data")

    def test_take_profit_is_a_ga_gene_used_in_fitness_and_result(self):
        module = load_module()
        backtest_calls = []
        solution = np.array([10, 80, 10.0, 1, 3.0, 2.0, 30, 70, 12.5])

        class FakeGA:
            def __init__(self, **kwargs):
                self.fitness_func = kwargs["fitness_func"]

            def run(self):
                self.fitness_func(self, solution, 0)

            def best_solution(self):
                return solution, 1.0, 0

        class FakePygad:
            GA = FakeGA

        def fake_backtest(df, *args, **kwargs):
            backtest_calls.append(kwargs)
            result = pd.DataFrame({"Portfolio_Value": [10000.0, 10100.0]})
            return result, 1.0, 0, [], 0.0, 0.0, pd.DataFrame(), 0.0, 0.0

        metrics = {
            "excess_return": 1.0,
            "sharpe": 1.0,
            "max_dd": 0.0,
            "uptrend_cash_pct": 0.0,
            "missed_upside_after_exit_pct": 0.0,
        }
        df = pd.DataFrame(
            {"Date": pd.date_range("2020-01-01", periods=120), "NAV": np.arange(120) + 100.0}
        )

        with (
            patch.dict(sys.modules, {"pygad": FakePygad}),
            patch.object(module, "backtest_enhanced_dual_ema", side_effect=fake_backtest),
            patch.object(module, "calculate_index_strategy_metrics", return_value=metrics),
        ):
            best = module.genetic_optimize_params(
                df,
                pop_size=10,
                generations=1,
                take_profit_pct_value=25.0,
            )

        self.assertEqual(len(backtest_calls), 3)
        self.assertTrue(all(call["use_take_profit"] for call in backtest_calls))
        self.assertTrue(all(call["take_profit_pct"] == 12.5 for call in backtest_calls))
        self.assertTrue(best["use_take_profit"])
        self.assertEqual(best["take_profit_pct"], 12.5)


if __name__ == "__main__":
    unittest.main()
