python final_backtest_from_summary.py --top-funds 0


rem r.bat
python operate.py report

REM python scripts/final_backtest_from_summary.py --top-funds 0 --price-column TotalReturn
REM powershell -ExecutionPolicy Bypass -File refresh_backtest_dashboard.ps1
REM .\run_weekly_strategy_review.ps1 -RunFinalBacktest
REM powershell -ExecutionPolicy Bypass -File scripts/refresh_backtest_dashboard.ps1


powershell -ExecutionPolicy Bypass -File scripts/refresh_backtest_dashboard.ps1


REM generate-buyhold.bat
python generate_buyhold_dashboard_charts.py
python export_backtest_dashboard_data.py

cd ..
publish_backtest_dashboard.bat