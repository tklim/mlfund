from pathlib import Path
import sys
import unittest

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from common import LEGACY_TOTAL_RETURN_METHOD, REINVESTED_TOTAL_RETURN_METHOD
from technical_signal_review import calculate_likelihoods, select_params_for_fund


class SelectParamsForFundTests(unittest.TestCase):
    def test_does_not_mix_total_return_methods(self):
        history = pd.DataFrame(
            [
                {
                    "fund_label": "APCR_AsiaPacificREIT",
                    "data_file": "data/APCR_AsiaPacificREIT_nav_5Y.csv",
                    "price_column": "TotalReturn",
                    "total_return_method": LEGACY_TOTAL_RETURN_METHOD,
                    "balanced_parameter_score": 1.0,
                    "run_started_at": "2026-01-01",
                    "run_id": "legacy",
                },
                {
                    "fund_label": "APCR_AsiaPacificREIT",
                    "data_file": "data/APCR_AsiaPacificREIT_nav_5Y.csv",
                    "price_column": "TotalReturn",
                    "total_return_method": REINVESTED_TOTAL_RETURN_METHOD,
                    "balanced_parameter_score": 0.5,
                    "run_started_at": "2026-01-02",
                    "run_id": "reinvested",
                },
            ]
        )

        selected = select_params_for_fund(
            history,
            "APCR_AsiaPacificREIT",
            "TotalReturn",
            REINVESTED_TOTAL_RETURN_METHOD,
        )

        self.assertEqual(selected["run_id"], "reinvested")


class TechnicalLikelihoodSchemaTests(unittest.TestCase):
    def test_absolute_names_and_compatibility_aliases_match(self):
        frame = pd.DataFrame({"Date": pd.date_range("2024-01-01", periods=5), "NAV": [1, 1.1, 1.2, 1.3, 1.4], "Position": 1})
        row = calculate_likelihoods(frame, "BUY/HOLD invested", {"2D": 2}, 0.10, -0.05, 1)[0]
        self.assertEqual(row["Technical Likelihood Method"], "absolute_fixed_threshold")
        self.assertEqual(row["Technical Absolute Probability >= Upside Target"], row["Technical Probability >= Upside Target"])
        self.assertEqual(row["Technical Absolute Expected Forward Return"], row["Technical Expected Forward Return"])


if __name__ == "__main__":
    unittest.main()
