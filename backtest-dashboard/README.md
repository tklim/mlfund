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

## Publish

The repository includes a manual GitHub Pages workflow. Running `Publish Backtest Dashboard to GitHub Pages` uploads `site/` unchanged and requires no Node build.
