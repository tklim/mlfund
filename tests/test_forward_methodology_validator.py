from pathlib import Path
import sys
import unittest

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from validate_forward_decision_methodology import select_evaluation_periods, training_forward_frame


class WalkForwardCutoffTests(unittest.TestCase):
    def test_training_cutoff_excludes_equal_and_future_end_dates(self):
        frame = pd.DataFrame(
            {
                "Start Date": pd.to_datetime(["2023-01-01", "2023-02-01", "2023-03-01"]),
                "End Date": pd.to_datetime(["2023-05-31", "2023-06-01", "2023-06-02"]),
                "Forward Return": [0.1, 0.2, 0.3],
            }
        )
        result = training_forward_frame(frame, "2023-06-01")
        self.assertEqual(result["Forward Return"].tolist(), [0.1])

    def test_evaluation_periods_use_actual_non_overlapping_intervals(self):
        starts = pd.date_range("2020-01-01", periods=8, freq="180D")
        forward = pd.DataFrame(
            {
                "Start Date": starts,
                "End Date": starts + pd.Timedelta(days=120),
                "Forward Return": 0.01,
            }
        )
        features = pd.DataFrame({"Date": starts})
        for column in [
            "Trailing Return 1M", "Trailing Return 3M", "Trailing Return 6M",
            "Drawdown From 6M High", "Drawdown From 1Y High", "Rebound From 3M Low",
            "Annualized Volatility 3M", "RSI 14", "EMA 50/200 Gap", "EMA 200 Slope 1M",
        ]:
            features[column] = 1.0
        selected = select_evaluation_periods(forward, features, min_baseline=2)
        self.assertTrue(all(selected["Start Date"].iloc[1:].to_numpy() >= selected["End Date"].iloc[:-1].to_numpy()))
