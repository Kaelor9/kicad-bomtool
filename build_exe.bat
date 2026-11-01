@echo off
rem Bygger dist\KiCadBOM.exe - en enkelt fil der koerer uden Python, i sit eget vindue.
rem Kraever: pip install pyinstaller pypdf openpyxl pywebview certifi
rem Officielle versioner bygges af GitHub Actions naar et versions-tag pushes (se README).
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onefile --windowed --name KiCadBOM ^
  --add-data "bomtool\web;bomtool\web" ^
  --hidden-import pypdf --hidden-import openpyxl --hidden-import certifi ^
  run_bomtool.py
echo.
echo Faerdig: dist\KiCadBOM.exe
pause
