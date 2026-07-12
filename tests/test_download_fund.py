from pathlib import Path
import sys
import unittest

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from common import REINVESTED_TOTAL_RETURN_METHOD, TOTAL_RETURN_METHOD_COLUMN
from download_fund import build_total_return_frame


class BuildTotalReturnFrameTests(unittest.TestCase):
    def test_aligns_non_nav_dividend_date_forward_and_reinvests(self):
        nav = pd.DataFrame(
            {
                "Date": ["2026-01-02", "2026-01-04", "2026-01-05"],
                "NAV": [100.0, 90.0, 95.0],
            }
        )
        dividends = pd.DataFrame(
            {
                "Date": ["2026-01-03"],
                "Dividend": [10.0],
            }
        )

        result = build_total_return_frame(nav, dividends)

        self.assertEqual(result["Dividend"].tolist(), [0.0, 10.0, 0.0])
        self.assertAlmostEqual(result["TotalReturn"].iloc[0], 100.0)
        self.assertAlmostEqual(result["TotalReturn"].iloc[1], 100.0)
        self.assertAlmostEqual(result["TotalReturn"].iloc[2], 95.0 * (1 + 10.0 / 90.0))
        self.assertEqual(
            result[TOTAL_RETURN_METHOD_COLUMN].unique().tolist(),
            [REINVESTED_TOTAL_RETURN_METHOD],
        )

    def test_total_return_equals_nav_without_dividends(self):
        nav = pd.DataFrame(
            {
                "Date": ["2026-01-02", "2026-01-03"],
                "NAV": [100.0, 101.0],
            }
        )

        result = build_total_return_frame(nav)

        pd.testing.assert_series_equal(
            result["TotalReturn"],
            result["NAV"],
            check_names=False,
        )
