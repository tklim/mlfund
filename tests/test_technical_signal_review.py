from pathlib import Path
import sys
import unittest

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from common import LEGACY_TOTAL_RETURN_METHOD, REINVESTED_TOTAL_RETURN_METHOD
from technical_signal_review import select_params_for_fund


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


if __name__ == "__main__":
    unittest.main()
