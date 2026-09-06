@echo off
chcp 65001 >nul
title voice2text
cd /d "%~dp0.."

python -m voice2text

if errorlevel 1 (
    echo.
    echo Da ist etwas schiefgegangen.
    echo Bitte einmal EINRICHTEN_WINDOWS.bat ausfuehren.
    echo.
    pause
)
