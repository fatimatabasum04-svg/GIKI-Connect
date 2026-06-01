@echo off
title GIKI-Connect Server
cd /d "%~dp0"

echo.
echo  ============================================================
echo   GIKI-Connect - starting the web app
echo  ============================================================
echo.

where py >nul 2>&1
if %ERRORLEVEL%==0 (set PY=py -3) else (set PY=python)

%PY% --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python 3 and tick "Add to PATH".
  pause
  exit /b 1
)

echo Installing Python packages (Flask, sklearn, etc.)...
%PY% -m pip install -r requirements.txt -q
if errorlevel 1 (
  echo [WARN] pip had a problem — continuing anyway.
)

if not exist "output\model\kmeans.pkl" (
  echo.
  echo [ERROR] Missing trained model: output\model\kmeans.pkl
  echo Open GIKI_Connect_Notebook.ipynb in Jupyter and RUN ALL CELLS once.
  echo.
  pause
  exit /b 1
)

echo.
echo Starting server... Your browser should open automatically in ~2 seconds.
echo *** Leave this window OPEN while using the app — closing it stops the server ***
echo.
%PY% app_server.py
echo.
if errorlevel 1 echo Server stopped with an error.
pause
