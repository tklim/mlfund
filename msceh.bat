set "FILE=MSCEH_ShariahChinaEquityARMHClass_nav_5Y.csv"
set "LOG=msceh.log"

:start
echo [%date% %time%] %FILE% run2.ps1 Start  >> "%LOG%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '.\run2.ps1' -Population 4 -Generations 2 -GaSearchPreset grid -ExtraArgs @('--data-file', '.\data\%FILE%')"
echo [%date% %time%] %FILE% run2.ps1 Completed  >> "%LOG%"


echo [%date% %time%] %FILE% run.ps1 6 Start  >> "%LOG%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '.\run.ps1' -Population 6 -Generations 3 -GaSearchPreset grid -ExtraArgs @('--data-file', '.\data\%FILE%')"
echo [%date% %time%] %FILE% run2.ps1 6 Completed  >> "%LOG%"

echo [%date% %time%] %FILE% run2.ps1 6 Start  >> "%LOG%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '.\run2.ps1' -Population 6 -Generations 3 -GaSearchPreset grid -ExtraArgs @('--data-file', '.\data\%FILE%')"
echo [%date% %time%] %FILE% run2.ps1 6 Completed  >> "%LOG%"


REM 888888

echo [%date% %time%] %FILE% run.ps1 8 Start  >> "%LOG%"
REM powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '.\run.ps1' -Population 8 -Generations 4 -GaSearchPreset grid -ExtraArgs @('--data-file', '.\data\%FILE%')"
echo [%date% %time%] %FILE% run.ps1 8 Completed  >> "%LOG%"

echo [%date% %time%] %FILE% run2.ps1 8 Start  >> "%LOG%"
REM powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '.\run2.ps1' -Population 8 -Generations 4 -GaSearchPreset grid -ExtraArgs @('--data-file', '.\data\%FILE%')"
echo [%date% %time%] %FILE% run2.ps1 8 Completed  >> "%LOG%"

exit
REM no need 10 for 3Y
REM 10 10 10

echo [%date% %time%] %FILE% run.ps1 10 Start  >> "%LOG%"
REM powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '.\run.ps1' -Population 10 -Generations 5 -GaSearchPreset grid -ExtraArgs @('--data-file', '.\data\%FILE%')"
echo [%date% %time%] %FILE% run.ps1 10 Completed  >> "%LOG%"

echo [%date% %time%] %FILE% run2.ps1 10 Start  >> "%LOG%"
REM powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '.\run2.ps1' -Population 10 -Generations 5 -GaSearchPreset grid -ExtraArgs @('--data-file', '.\data\%FILE%')"
echo [%date% %time%] %FILE% run2.ps1 10 Completed  >> "%LOG%"