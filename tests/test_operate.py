from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from operate import build_decision_scores, load_current_ga_by_fund


class ForwardAuthorityTests(unittest.TestCase):
    def test_forward_decision_remains_authoritative_when_ga_conflicts(self):
        dashboard = pd.DataFrame(
            [{
                "Fund Label": "A", "Decision Label": "BUY", "Forward Method Version": "dual_relative_v2",
                "Decision Score": 0.8, "Relative Upside Probability Lift": 0.08,
                "Relative Downside Probability Lift": -0.02, "Effective Observations": 8,
                "Base Observations": 9, "Confidence Level": "MEDIUM",
            }]
        )
        ga = pd.DataFrame([{"fund_label": "A", "ga_signal": "SELL/CASH"}])
        health = pd.DataFrame([{"fund_label": "A", "freshness_status": "fresh"}])
        result = build_decision_scores(dashboard, ga, health).iloc[0]
        self.assertEqual(result["Conclusion"], "BUY")
        self.assertEqual(result["GA Agreement"], "CONFLICT")
        self.assertNotIn("Buy Score", result.index)

    def test_ga_context_is_derived_from_latest_final_replay(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log = root / "run.log"
            log.write_text("BUY: 2026-07-01 Price: 1.23\n", encoding="utf-8")
            pd.DataFrame(
                [{
                    "status": "completed", "fund_label": "A", "log_file": str(log),
                    "ga_signal": "BUY/HOLD invested", "last_trade_date": "2026-07-01",
                    "adaptive_annualized_return_pct": 5.0, "excess_annualized_return_pct": 1.0,
                    "sharpe": 0.5, "max_dd_pct": -4.0, "short_ema": 10, "long_ema": 50,
                }]
            ).to_csv(root / "final_backtest_summary_20260713.csv", index=False)
            result = load_current_ga_by_fund(root).iloc[0]
        self.assertEqual(result["ga_signal"], "BUY/HOLD invested")
        self.assertEqual(result["last_trade_date"], "2026-07-01")


if __name__ == "__main__":
    unittest.main()
