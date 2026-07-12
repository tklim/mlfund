@echo off
set "LOG=run20.log"

:start

call :RunOne 1 "MIIEH_IndiaEquityRMH_nav_5Y.csv"
call :RunOne 2 "MGLVH_GlobalLowVolatilityEquityARMHClass_nav_5Y.csv"
call :RunOne 3 "MGPRH_GlobalPerspective_nav_5Y.csv"
call :RunOne 4 "HWFL_HWFlexi_nav_5Y.csv"
call :RunOne 5 "MAPF_Progress_nav_5Y.csv"

call :RunOne 1 "MIIEH_IndiaEquityRMH_nav_3Y.csv"
call :RunOne 2 "MGLVH_GlobalLowVolatilityEquityARMHClass_nav_3Y.csv"
call :RunOne 3 "MGPRH_GlobalPerspective_nav_3Y.csv"
call :RunOne 4 "HWFL_HWFlexi_nav_3Y.csv"
call :RunOne 5 "MAPF_Progress_nav_3Y.csv"

goto start


:RunOne
set "NO=%~1"
set "FILE=%~2"

echo [%date% %time%] >> "%LOG%"
echo "%NO%. %FILE%" >> "%LOG%"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '.\run.ps1' -Population 20 -Generations 20 -GaSearchPreset grid -ExtraArgs @('--data-file', '.\data\%FILE%')"

exit /b