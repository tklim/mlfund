# Backtest Intelligence

A standalone static dashboard for reviewing fixed-parameter fund backtests. It is independent from the separate live dashboard repository.

## View locally

Double-click `site/index.html`. The generated pages use only relative links, so they work from `file://`, any basic web server, a GitHub Pages project path, or a custom domain.

## Refresh generated pages

From the parent repository:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/refresh_backtest_dashboard.ps1
```

The exporter selects the newest successful final-backtest summary, enriches each fund with its best valid historical run, copies stable chart assets, and rebuilds only `site/`. Shared maintainable assets live in `source/`; do not edit generated files under `site/` directly.

## Generate buy-and-hold charts directly

The chart helper generates trailing 5Y, 4Y, and 3Y charts by default, all ending on the latest usable date in the selected CSV:

```powershell
python scripts/generate_buyhold_dashboard_charts.py --data-file data/MAKGCF_GreaterChina_nav_5Y.csv --output-dir buyhold-preview --prefix makgcf
```

Use `--years`, `--end-date`, `--prefix`, and `--output-dir` to override the defaults. Run the command with `--help` for the complete option list. Horizons without enough source history are reported and skipped.

## Publish

The repository includes a manual GitHub Pages workflow. Running `Publish Backtest Dashboard to GitHub Pages` uploads `site/` unchanged and requires no Node build.

For a complete local refresh-and-publish flow, double-click `publish_backtest_dashboard.bat` in the repository root. It validates the dashboard, commits only dashboard-owned files, pushes `main`, starts the Pages workflow, and waits for the published URL. Existing unrelated working files are not staged. Use `publish_backtest_dashboard.bat -SkipRefresh` to publish the current generated `site/` without rebuilding it, or add `-NoWait` to return immediately after dispatch.
