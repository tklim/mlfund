@echo off
setlocal

set "PUBLISH_SCRIPT=%~dp0scripts\publish_backtest_dashboard_pages.ps1"

if not exist "%PUBLISH_SCRIPT%" (
  echo Publisher script not found: %PUBLISH_SCRIPT%
  set "PUBLISH_EXIT=2"
  goto :finish
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PUBLISH_SCRIPT%" %*
set "PUBLISH_EXIT=%ERRORLEVEL%"

:finish
echo.
if "%PUBLISH_EXIT%"=="0" (
  echo Backtest dashboard publishing completed successfully.
) else (
  echo Backtest dashboard publishing failed with exit code %PUBLISH_EXIT%.
)
pause
exit /b %PUBLISH_EXIT%
