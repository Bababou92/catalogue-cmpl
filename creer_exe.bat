@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 goto nopython

if not exist ".venv\Scripts\python.exe" python -m venv .venv
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 goto erreur

pyinstaller --noconfirm --clean --onefile --noconsole --name "Catalogue CMPL" --icon "%~dp0icone.ico" --add-data "catalogue\assets;catalogue\assets" --add-data "catalogue\web;catalogue\web" --collect-data pptx --collect-submodules openpyxl --collect-submodules reportlab --collect-data reportlab --hidden-import et_xmlfile --hidden-import tkinter run.py
if errorlevel 1 goto erreur

rem Rafraichit le cache d'icones de Windows (sinon l'ancienne icone peut rester affichee)
ie4uinit.exe -show >nul 2>nul
ie4uinit.exe -ClearIconCache >nul 2>nul

echo.
echo Termine ! Le programme est ici : dist\Catalogue CMPL.exe
echo Copie ce fichier sur le PC de ton pere, il n'y a rien d'autre a installer.
echo Si l'icone n'apparait pas tout de suite sur ton PC : copie le .exe ailleurs (Bureau) ou redemarre l'explorateur, c'est le cache de Windows.
pause
exit /b 0

:nopython
echo Python n'est pas installe.
echo Installe-le depuis https://www.python.org/downloads/ (coche "Add python.exe to PATH"), puis relance ce fichier.
pause
exit /b 1

:erreur
echo Une erreur est survenue, copie le message ci-dessus et envoie-le moi.
pause
exit /b 1
