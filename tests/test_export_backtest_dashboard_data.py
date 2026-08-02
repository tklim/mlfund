import csv
import tempfile
import unittest
from pathlib import Path

from scripts import export_backtest_dashboard_data as exporter


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class BacktestDashboardExporterTests(unittest.TestCase):
    def test_selects_newest_summary_with_a_completed_row(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_csv(root / "final_backtest_summary_20260101.csv", [{"status": "completed", "fund_label": "MAKGCF_GreaterChina"}])
            write_csv(root / "final_backtest_summary_20260102.csv", [{"status": "error", "fund_label": "MAKGCF_GreaterChina"}])
            path, rows = exporter.latest_successful_summary(root.glob("*.csv"))
            self.assertEqual(path.name, "final_backtest_summary_20260101.csv")
            self.assertEqual(len(rows), 1)

    def test_historical_best_is_nonzero_and_ties_use_latest_run(self):
        rows = [
            {"fund_label": "MAKGCF_GreaterChina", "excess_annualized_return_pct": "0", "run_started_at": "2026-03-01", "run_id": "zero"},
            {"fund_label": "MAKGCF_GreaterChina", "excess_annualized_return_pct": "7.5", "run_started_at": "2026-01-01", "run_id": "old"},
            {"fund_label": "MAKGCF_GreaterChina", "excess_annualized_return_pct": "7.5", "run_started_at": "2026-02-01", "run_id": "new"},
        ]
        self.assertEqual(exporter.best_history_rows(rows)["MAKGCF_GreaterChina"]["run_id"], "new")

    def test_normalizes_supported_signals(self):
        self.assertEqual(exporter.normalize_signal("BUY/HOLD invested"), "BUY / HOLD")
        self.assertEqual(exporter.normalize_signal("SELL/CASH"), "SELL / CASH")
        self.assertEqual(exporter.normalize_signal(""), "UNKNOWN")

    def test_snapshot_ranking_is_deterministic_and_missing_charts_are_safe(self):
        base = {
            "status": "completed", "latest_data_end": "2026-07-31", "run_completed_at": "2026-08-01 10:00:00",
            "latest_chart_file": "missing.png", "technical_chart_file": "", "simple_chart_file": "",
        }
        rows = [
            {**base, "fund_label": "MAPAC_AsiaPacificexJapan", "latest_adaptive_return_pct": "12"},
            {**base, "fund_label": "MAKGCF_GreaterChina", "latest_adaptive_return_pct": "12"},
            {**base, "fund_label": "HWFL_HWFlexi", "latest_adaptive_return_pct": "4"},
        ]
        snapshot = exporter.build_snapshot(Path("final_backtest_summary_test.csv"), rows, [])
        self.assertEqual([fund["code"] for fund in snapshot["funds"]], ["MAKGCF", "MAPAC", "HWFL"])
        self.assertEqual([fund["rank"] for fund in snapshot["funds"]], [1, 2, 3])
        self.assertEqual(snapshot["funds"][0]["chartSources"]["latestTechnical"], "missing.png")

    def test_static_build_copies_available_chart_and_marks_missing_chart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "styles.css").write_text("body{}", encoding="utf-8")
            (source / "dashboard.js").write_text("// test", encoding="utf-8")
            (source / "og.png").write_bytes(b"png")
            chart = root / "chart.png"
            chart.write_bytes(b"chart")
            row = {
                "status": "completed", "fund_label": "MAKGCF_GreaterChina",
                "latest_adaptive_return_pct": "10", "latest_chart_file": str(chart),
                "technical_chart_file": str(root / "missing.png"), "simple_chart_file": "",
            }
            snapshot = exporter.build_snapshot(Path("final_backtest_summary_test.csv"), [row], [])
            site = root / "site"
            exporter.build_site(snapshot, site=site, source=source)
            detail = (site / "funds" / "makgcf" / "index.html").read_text(encoding="utf-8")
            self.assertTrue((site / "assets" / "charts" / "makgcf-latest-technical.png").is_file())
            self.assertIn("../../assets/charts/makgcf-latest-technical.png", detail)
            self.assertIn("Chart unavailable", detail)


if __name__ == "__main__":
    unittest.main()
