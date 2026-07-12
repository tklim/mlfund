from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from common import (
    LEGACY_TOTAL_RETURN_METHOD,
    NOT_APPLICABLE_TOTAL_RETURN_METHOD,
    calculate_rsi,
    infer_total_return_method,
    save_csv,
)


class CalculateRsiTests(unittest.TestCase):
    def test_rsi_is_100_for_uninterrupted_gains(self):
        prices = pd.Series(range(1, 31), dtype=float)

        self.assertEqual(calculate_rsi(prices, period=14).iloc[-1], 100.0)

    def test_rsi_is_0_for_uninterrupted_losses(self):
        prices = pd.Series(range(30, 0, -1), dtype=float)

        self.assertEqual(calculate_rsi(prices, period=14).iloc[-1], 0.0)

    def test_rsi_is_50_for_flat_prices(self):
        prices = pd.Series([10.0] * 30)

        self.assertEqual(calculate_rsi(prices, period=14).iloc[-1], 50.0)


class InferTotalReturnMethodTests(unittest.TestCase):
    def test_marks_untagged_total_return_as_legacy(self):
        self.assertEqual(
            infer_total_return_method(pd.DataFrame({"TotalReturn": [100.0]}), "TotalReturn"),
            LEGACY_TOTAL_RETURN_METHOD,
        )

    def test_marks_nav_as_not_applicable(self):
        self.assertEqual(
            infer_total_return_method(pd.DataFrame({"NAV": [100.0]}), "NAV"),
            NOT_APPLICABLE_TOTAL_RETURN_METHOD,
        )


class SaveCsvTests(unittest.TestCase):
    def test_strict_write_does_not_create_a_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "canonical.csv"
            with patch.object(pd.DataFrame, "to_csv", side_effect=PermissionError("locked")) as to_csv:
                with self.assertRaises(PermissionError):
                    save_csv(
                        pd.DataFrame({"value": [1]}),
                        output_path,
                        allow_fallback=False,
                    )

        to_csv.assert_called_once()


if __name__ == "__main__":
    unittest.main()
