import re
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "backtest-dashboard" / "site"
EXPECTED_FUNDS = {"apcr", "hwfl", "makgcf", "mapac", "mapf", "maus", "mglvh", "mgprh", "miieh", "mpgfc", "msglr"}


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        for key in ("href", "src"):
            if values.get(key):
                self.references.append(values[key])


class StaticBacktestDashboardTests(unittest.TestCase):
    def test_expected_pages_and_assets_are_generated(self):
        self.assertTrue((SITE / "index.html").is_file())
        self.assertTrue((SITE / "excess-ranking" / "index.html").is_file())
        self.assertTrue((SITE / "buyhold-ranking" / "index.html").is_file())
        self.assertTrue((SITE / "annualized-ranking" / "index.html").is_file())
        actual = {path.parent.name for path in (SITE / "funds").glob("*/index.html")}
        self.assertEqual(actual, EXPECTED_FUNDS)
        for asset in ("styles.css", "dashboard.js", "og.png"):
            self.assertTrue((SITE / "assets" / asset).is_file())

    def test_master_contains_one_deterministically_ranked_row_per_fund(self):
        master = (SITE / "index.html").read_text(encoding="utf-8")
        rows = re.findall(r'<tr data-fund-result data-code="([A-Z]+)".*?<td data-rank>#(\d+)</td>', master)
        self.assertEqual(len(rows), 11)
        self.assertEqual([int(rank) for _, rank in rows], list(range(1, 12)))
        self.assertEqual(len({code for code, _ in rows}), 11)

    def test_all_html_references_are_relative_and_exist(self):
        for page in SITE.rglob("*.html"):
            parser = References()
            parser.feed(page.read_text(encoding="utf-8"))
            for reference in parser.references:
                self.assertFalse(reference.startswith(("/", "\\", "file:", "http:", "https:")), (page, reference))
                target = (page.parent / reference.split("#", 1)[0]).resolve()
                self.assertTrue(target.exists(), (page, reference))

    def test_excess_ranking_has_group_controls_and_chart_assets(self):
        page = (SITE / "excess-ranking" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Excess Ranking", page)
        self.assertIn('href="../index.html"', page)
        self.assertIn('data-excess-source="mixed"', page)
        self.assertIn('data-excess-run="all"', page)
        self.assertIn("data-excess-view", page)
        self.assertIn("excess-charts", page)
        self.assertTrue(any((SITE / "assets" / "excess-charts").glob("*.png")))

    def test_master_historical_excess_links_to_static_ranking_page(self):
        master = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="excess-ranking/index.html"', master)

    def test_master_has_four_compact_overview_cards_without_chart_gallery(self):
        master = (SITE / "index.html").read_text(encoding="utf-8")
        styles = (SITE / "assets" / "styles.css").read_text(encoding="utf-8")
        overview = re.search(r'<section class="lens-grid".*?</section>', master)
        self.assertIsNotNone(overview)
        self.assertEqual(overview.group(0).count('<button'), 1)
        self.assertEqual(overview.group(0).count('<a href='), 3)
        self.assertNotIn("Chart gallery", overview.group(0))
        self.assertIn('<span>4</span><strong>Buy &amp; hold horizons</strong>', overview.group(0))
        self.assertIn("grid-template-columns:repeat(4,minmax(0,1fr))", styles)
        self.assertIn(".lens-grid button,.lens-grid a{display:block;min-height:88px", styles)
        self.assertIn(".lens-grid button,.lens-grid a{min-width:185px;min-height:84px", styles)

    def test_buyhold_ranking_has_run_year_controls_and_compact_chart_assets(self):
        page = (SITE / "buyhold-ranking" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Buy &amp; Hold Ranking", page)
        self.assertIn('href="../index.html"', page)
        self.assertIn('data-buyhold-run="mixed"', page)
        self.assertIn('data-buyhold-run="run-5"', page)
        self.assertIn('data-buyhold-run="run-4"', page)
        self.assertIn('data-buyhold-run="run-3"', page)
        self.assertIn("Choose the buy-and-hold scored/run duration.", page)
        self.assertIn("data-buyhold-view", page)
        self.assertIn("buyhold-charts", page)
        self.assertTrue(any((SITE / "assets" / "buyhold-charts").glob("*.png")))

    def test_master_buyhold_horizons_links_to_static_ranking_page(self):
        master = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="buyhold-ranking/index.html"', master)

    def test_annualized_ranking_has_horizon_controls_and_chart_assets(self):
        page = (SITE / "annualized-ranking" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Top Annualized Return", page)
        self.assertIn('href="../index.html"', page)
        self.assertIn('data-annualized-source="mixed"', page)
        self.assertIn("data-annualized-view", page)
        self.assertIn("annualized-charts", page)
        self.assertTrue(any((SITE / "assets" / "annualized-charts").glob("*.png")))

    def test_master_annualized_card_links_to_static_ranking_page(self):
        master = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="annualized-ranking/index.html"', master)

    def test_site_is_decoupled_from_server_and_live_dashboard(self):
        text = "\n".join(path.read_text(encoding="utf-8") for path in SITE.rglob("*.html"))
        for forbidden in ("Cloudflare", "vinext", "Fund Signal", "worker.js", "C:\\Users\\"):
            self.assertNotIn(forbidden, text)
        self.assertIsNone(re.search(r'(?:href|src)=["\']/[^/]', text))

    def test_interactive_and_responsive_contracts_are_present(self):
        master = (SITE / "index.html").read_text(encoding="utf-8")
        script = (SITE / "assets" / "dashboard.js").read_text(encoding="utf-8")
        styles = (SITE / "assets" / "styles.css").read_text(encoding="utf-8")
        for marker in ("data-search", "data-sort", "data-direction", "data-column", "mobile-results"):
            self.assertIn(marker, master)
        for marker in ("localStorage", "data-chart-tab", "scrollIntoView", "column-hidden"):
            self.assertIn(marker, script)
        for marker in ("data-excess-dashboard", "data-excess-source", "data-tab-group"):
            self.assertIn(marker, script)
        self.assertIn("data-buyhold-dashboard", script)
        self.assertIn("data-annualized-dashboard", script)
        self.assertIn("@media(max-width:760px)", styles)
        self.assertIn("grid-template-columns:repeat(4", styles)
        self.assertIn(".buyhold-grid", styles)

    def test_detail_pages_link_back_and_offer_three_chart_tabs(self):
        for page in (SITE / "funds").glob("*/index.html"):
            text = page.read_text(encoding="utf-8")
            self.assertIn('href="../../index.html"', text)
            self.assertEqual(text.count("data-chart-tab"), 3)
            self.assertIn("Chart unavailable", text)

    def test_pages_workflow_uploads_site_without_a_runtime_build(self):
        workflow = (ROOT / ".github" / "workflows" / "backtest-dashboard-pages.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch", workflow)
        self.assertIn("path: backtest-dashboard/site", workflow)
        self.assertNotIn("npm", workflow.lower())
        self.assertNotIn("node", workflow.lower())

    def test_local_publish_launcher_is_guarded_and_dashboard_scoped(self):
        batch = (ROOT / "publish_backtest_dashboard.bat").read_text(encoding="utf-8")
        publisher = (ROOT / "scripts" / "publish_backtest_dashboard_pages.ps1").read_text(encoding="utf-8")
        self.assertIn("publish_backtest_dashboard_pages.ps1", batch)
        self.assertIn("refresh_backtest_dashboard.ps1", publisher)
        self.assertIn('if ($branch -ne "main")', publisher)
        self.assertIn("origin/main has", publisher)
        self.assertIn("git commit --only", publisher)
        self.assertIn("backtest-dashboard-pages.yml", publisher)
        self.assertIn("workflow_dispatch", publisher)


if __name__ == "__main__":
    unittest.main()
