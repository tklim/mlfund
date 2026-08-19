@echo off
set "LOG=run4.log"

:start

REM 3 hours each run, total 13 hr.
call :RunOne 1 "APCR_AsiaPacificREIT_nav_3Y.csv"
call :RunOne 2 "HWFL_HWFlexi_nav_3Y.csv"
call :RunOne 3 "MAKGCF_GreaterChina_nav_3Y.csv"
call :RunOne 4 "MAPAC_AsiaPacificexJapan_nav_3Y.csv"
call :RunOne 5 "MAPF_Progress_nav_3Y.csv"
call :RunOne 11 "SPGA_ShariahPRSGoldenAsiaClassC_nav_3Y.csv"
call :RunOne 12 "MSCEH_ShariahChinaEquityARMHClass_nav_3Y.csv"
echo [%date% %time%] >> "%LOG%"

REM 9 hour each run. 45hr
call :RunOne 1 "APCR_AsiaPacificREIT_nav_5Y.csv"
call :RunOne 2 "HWFL_HWFlexi_nav_5Y.csv"
call :RunOne 3 "MAKGCF_GreaterChina_nav_5Y.csv"
call :RunOne 4 "MAPAC_AsiaPacificexJapan_nav_5Y.csv"
call :RunOne 5 "MAPF_Progress_nav_5Y.csv"
call :RunOne 11 "SPGA_ShariahPRSGoldenAsiaClassC_nav_5Y.csv"
call :RunOne 12 "MSCEH_ShariahChinaEquityARMHClass_nav_5Y.csv"


echo [%date% %time%] >> "%LOG%"
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

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '.\run.ps1' -Population 4 -Generations 2 -GaSearchPreset grid -ExtraArgs @('--data-file', '.\data\%FILE%')"

exit /b