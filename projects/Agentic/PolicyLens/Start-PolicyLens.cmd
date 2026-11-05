@echo off
setlocal
cd /d "%~dp0"
title PolicyLens - Local Policy Workspace
echo.
echo   PolicyLens - Answers with evidence
echo.

if exist ".venv\Scripts\python.exe" goto configured
where uv >nul 2>nul
if errorlevel 1 goto python_setup
echo Installing pinned dependencies with uv...
uv sync --frozen
if errorlevel 1 goto failed
goto configured

:python_setup
echo Setting up Python and installing pinned dependencies...
py -3 -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed

:configured
if not exist ".env" copy /y ".env.example" ".env" >nul
if exist "data\index\policylens.sqlite3" goto launch
echo Building the first index...
.venv\Scripts\python.exe scripts\manage.py index
if errorlevel 1 goto failed

:launch
echo Open http://127.0.0.1:8765 in your browser.
echo Keep this window open. Press Ctrl+C to stop the app.
echo.
.venv\Scripts\python.exe run.py
if errorlevel 1 goto failed
goto end

:failed
echo.
echo PolicyLens could not start. Read the message above and the README.
echo Install Python 3.11 or newer if Python was not found.
pause

:end
endlocal

