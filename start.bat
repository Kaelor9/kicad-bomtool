@echo off
rem Starter KiCad BOM-tjek og aabner browseren.
cd /d "%~dp0"
where py >nul 2>nul && (py -3 -m bomtool %*) || (python -m bomtool %*)
pause
