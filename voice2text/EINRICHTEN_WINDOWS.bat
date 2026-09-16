@echo off
chcp 65001 >nul
title voice2text - Einrichtung
cd /d "%~dp0.."

echo.
echo ============================================
echo    voice2text wird eingerichtet
echo ============================================
echo.

python --version >/dev/null 2>&1
if errorlevel 1 (
    echo [FEHLER] Python wurde nicht gefunden.
    echo.
    echo Bitte zuerst Python installieren: https://www.python.org/downloads/
    echo WICHTIG: Beim Installieren den Haken bei "Add Python to PATH" setzen!
    echo.
    pause
    exit /b 1
)

python voice2text\einrichten.py

echo.
pause
