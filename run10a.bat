@echo off
set "LOG=run10a.log"

:start

REM 3 hours each run, total 13 hr.
call :RunOne 1 "APCR_AsiaPacificREIT_nav_3Y.csv"
call :RunOne 2 "HWFL_HWFlexi_nav_3Y.csv"
call :RunOne 3 "MAKGCF_GreaterChina_nav_3Y.csv"
call :RunOne 4 "MAPAC_AsiaPacificexJapan_nav_3Y.csv"
call :RunOne 5 "MAPF_Progress_nav_3Y.csv"

REM 9 hour each run. 45hr
call :RunOne 1 "APCR_AsiaPacificREIT_nav_5Y.csv"
call :RunOne 2 "HWFL_HWFlexi_nav_5Y.csv"
call :RunOne 3 "MAKGCF_GreaterChina_nav_5Y.csv"
call :RunOne 4 "MAPAC_AsiaPacificexJapan_nav_5Y.csv"
call :RunOne 5 "MAPF_Progress_nav_5Y.csv"


goto start


:RunOne
set "NO=%~1"
set "FILE=%~2"

echo [%date% %time%] >> "%LOG%"
echo "%NO%. %FILE%" >> "%LOG%"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '.\run.ps1' -Population 10 -Generations 5 -GaSearchPreset grid -ExtraArgs @('--data-file', '.\data\%FILE%')"

exit /b