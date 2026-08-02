# Backtest Intelligence

Standalone vinext dashboard for reviewing fixed-parameter fund backtests. This application is isolated from the nested `dashboard/` Fund Signal repository and has its own Cloudflare Sites configuration.

## Local development

```powershell
npm install
npm run dev
```

## Refresh generated data

Run from the parent `mlfund` repository:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/refresh_backtest_dashboard.ps1
```

Do not edit `app/backtest-data.generated.ts` or `public/backtests/` manually. They are generated from the pipeline's latest successful final-backtest summary and persistent run history.

## Validation

```powershell
npm run build
node --test tests/rendered-html.test.mjs
```
