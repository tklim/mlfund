
powershell .\run_daily_investment_review.ps1
powershell .\run_weekly_strategy_review.ps1





python scripts\export_dashboard_data.py

powershell -ExecutionPolicy Bypass -File scripts\sync_dashboard_snapshot.ps1

REM sync github. https://fund-signal-dashboard.ltkiat.workers.dev/


cd dashboard
npm run dev -- --host 127.0.0.1 --port 3000