@echo off
set "LOG=run10b.log"

:start

call :RunOne 6 "MAUS_RMH_USEquityRMH_nav_3Y.csv"
call :RunOne 7 "MGLVH_GlobalLowVolatilityEquityARMHClass_nav_3Y.csv"
call :RunOne 8 "MGPRH_GlobalPerspective_nav_3Y.csv"
call :RunOne 9 "MIIEH_IndiaEquityRMH_nav_3Y.csv"
call :RunOne 10 "MSGLR_RM_ShariahGlobalREITMYR_nav_3Y.csv"

echo [%date% %time%] >> "%LOG%"

call :RunOne 6 "MAUS_RMH_USEquityRMH_nav_5Y.csv"
call :RunOne 7 "MGLVH_GlobalLowVolatilityEquityARMHClass_nav_5Y.csv"
call :RunOne 8 "MGPRH_GlobalPerspective_nav_5Y.csv"
call :RunOne 9 "MIIEH_IndiaEquityRMH_nav_5Y.csv"
call :RunOne 10 "MSGLR_RM_ShariahGlobalREITMYR_nav_5Y.csv"

echo [%date% %time%] >> "%LOG%"

goto start


:RunOne
set "NO=%~1"
set "FILE=%~2"

echo [%date% %time%] >> "%LOG%"
echo "%NO%. %FILE%" >> "%LOG%"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '.\run.ps1' -Population 10 -Generations 5 -GaSearchPreset grid -ExtraArgs @('--data-file', '.\data\%FILE%')"

exit /b