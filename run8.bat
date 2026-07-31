@echo off
set "LOG=run20-10.log"

:start

REM 3 hours each run, total 13 hr.
rem call :RunOne 1 "APCR_AsiaPacificREIT_nav_3Y.csv"
rem call :RunOne 2 "HWFL_HWFlexi_nav_3Y.csv"
rem call :RunOne 3 "MAKGCF_GreaterChina_nav_3Y.csv"
rem call :RunOne 4 "MAPAC_AsiaPacificexJapan_nav_3Y.csv"
rem call :RunOne 5 "MAPF_Progress_nav_3Y.csv"

REM x hour each run. xxhr
call :RunOne 1 "APCR_AsiaPacificREIT_nav_5Y.csv"
call :RunOne 2 "HWFL_HWFlexi_nav_5Y.csv"
call :RunOne 3 "MAKGCF_GreaterChina_nav_5Y.csv"
call :RunOne 4 "MAPAC_AsiaPacificexJapan_nav_5Y.csv"
rem call :RunOne 5 "MAPF_Progress_nav_5Y.csv"

rem call :RunOne 6 "MAUS_RMH_USEquityRMH_nav_5Y.csv"
call :RunOne 7 "MGLVH_GlobalLowVolatilityEquityARMHClass_nav_5Y.csv"
call :RunOne 8 "MGPRH_GlobalPerspective_nav_5Y.csv"
call :RunOne 9 "MIIEH_IndiaEquityRMH_nav_5Y.csv"
call :RunOne 10 "MSGLR_RM_ShariahGlobalREITMYR_nav_5Y.csv"

goto start


:RunOne
set "NO=%~1"
set "FILE=%~2"

echo [%date% %time%] >> "%LOG%"
echo "%NO%. %FILE%" >> "%LOG%"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '.\run2.ps1' -Population 20 -Generations 10 -GaSearchPreset grid -ExtraArgs @('--data-file', '.\data\%FILE%')"

exit /b