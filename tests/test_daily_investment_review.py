import csv
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import daily_investment_review as daily

from daily_investment_review import write_csv


class WriteCsvTests(unittest.TestCase):
    def test_ignores_additional_result_fields(self):
        rows = [
            {
                "fund_id": "APCR",
                "records": 100,
                "dividend_count": 4,
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "downloads.csv"
            write_csv(rows, output_path, ["fund_id", "records"])

            with output_path.open(newline="", encoding="utf-8") as handle:
                written_rows = list(csv.DictReader(handle))

        self.assertEqual(
            written_rows,
            [{"fund_id": "APCR", "records": "100"}],
        )


class DailyFailureTests(unittest.TestCase):
    def test_failed_child_does_not_publish_daily_outputs(self):
        args = SimpleNamespace(years=5, fund_ids=["APCR"], skip_download=True)
        download_rows = [{"fund_id": "APCR", "output_path": "fund.csv"}]
        failed = SimpleNamespace(returncode=1, stdout="", stderr="locked")
        succeeded = SimpleNamespace(returncode=0, stdout="ok", stderr="")

        with (
            patch.object(daily, "parse_args", return_value=args),
            patch.object(daily, "download_or_find_files", return_value=(download_rows, "download log")),
            patch.object(daily, "run_forward_decision", return_value=(["forward"], failed)),
            patch.object(daily, "run_technical_signal_review", return_value=(["technical"], succeeded)),
            patch.object(daily, "write_daily_log", return_value=Path("failed.log")),
            patch.object(daily, "write_daily_outputs") as write_outputs,
        ):
            with self.assertRaises(RuntimeError):
                daily.main()

        write_outputs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
