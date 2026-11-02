@echo off
rem Bygger dist\KiCadBOM\ (KiCadBOM.exe + _internal) - koerer uden Python, i sit eget vindue.
rem Kraever: pip install pyinstaller pypdf openpyxl pywebview certifi pypdfium2 pillow
rem Officielle versioner bygges af GitHub Actions naar et versions-tag pushes (se README) - de har
rem en selvbygget bootloader, saa antivirus ikke tager fejl af dem.
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onedir --windowed --icon bomtool/web/icon.ico --name KiCadBOM ^
  --add-data "bomtool\web;bomtool\web" ^
  --hidden-import pypdf --hidden-import openpyxl --hidden-import certifi --hidden-import pypdfium2 ^
  run_bomtool.py
echo.
echo Faerdig: dist\KiCadBOM\KiCadBOM.exe
pause
