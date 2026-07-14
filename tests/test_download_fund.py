from pathlib import Path
import sys
import unittest
from unittest.mock import ANY, Mock, patch

import pandas as pd
from requests import RequestException


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from common import REINVESTED_TOTAL_RETURN_METHOD, TOTAL_RETURN_METHOD_COLUMN
from download_fund import (
    FundDownloadError,
    REQUEST_TIMEOUT_SECONDS,
    build_total_return_frame,
    download_fund,
    format_change,
    request_json,
)


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


class FundApiTests(unittest.TestCase):
    @patch("download_fund.requests.get")
    def test_request_json_sets_timeout_and_checks_status(self, get):
        response = Mock()
        response.json.return_value = {"ok": True}
        get.return_value = response

        result = request_json("https://example.test/fund", "test fund")

        self.assertEqual(result, {"ok": True})
        get.assert_called_once_with(
            "https://example.test/fund",
            headers=ANY,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status.assert_called_once_with()

    @patch("download_fund.requests.get", side_effect=RequestException("offline"))
    def test_request_json_wraps_network_errors(self, _get):
        with self.assertRaisesRegex(FundDownloadError, "Unable to load test fund"):
            request_json("https://example.test/fund", "test fund")

    @patch("download_fund.get_dividends", return_value=[])
    @patch("download_fund.request_json")
    def test_empty_price_response_has_clear_error(self, request, _dividends):
        request.side_effect = [
            {"fundName": "Test Fund", "nav": {}},
            [],
        ]

        with self.assertRaisesRegex(FundDownloadError, "No valid NAV price rows"):
            download_fund("TEST", years=3)

    def test_none_change_formats_as_not_available(self):
        self.assertEqual(format_change(None, None), "n/a")
        self.assertEqual(format_change(0, 0), "0.0000 (0.00%)")
