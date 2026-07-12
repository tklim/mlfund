@echo off
set "LOG=run30.log"

:start

call :RunOne 1 "MIIEH_IndiaEquityRMH_nav_5Y.csv"


call :RunOne 1 "MIIEH_IndiaEquityRMH_nav_3Y.csv"


goto start


:RunOne
set "NO=%~1"
set "FILE=%~2"

echo [%date% %time%] >> "%LOG%"
echo "%NO%. %FILE%" >> "%LOG%"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '.\run.ps1' -Population 30 -Generations 30 -GaSearchPreset grid -ExtraArgs @('--data-file', '.\data\%FILE%')"

exit /b