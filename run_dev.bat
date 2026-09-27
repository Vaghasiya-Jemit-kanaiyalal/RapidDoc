@echo off
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
setlocal enabledelayedexpansion
title RapidDoc Development Launcher
cd /d "%~dp0"

echo =================================================================
echo             RapidDoc AI Document Editor Launcher
echo =================================================================
echo.

REM --- 1. Set PYTHONPATH to include workspace roots ---
for %%I in ("%~dp0..") do set "ROOT_DIR=%%~fI"
set "PYTHONPATH=%ROOT_DIR%;%~dp0;%~dp0backend;!PYTHONPATH!"

REM --- 2. Create required storage and data folders ---
if not exist "backend\storage" (
    mkdir "backend\storage"
    echo [setup] Created backend\storage
)
if not exist "mongodb_data" (
    mkdir "mongodb_data"
    echo [setup] Created mongodb_data
)

REM --- 3. Ensure backend\.env exists ---
if not exist "backend\.env" (
    if exist "backend\.env.example" (
        copy "backend\.env.example" "backend\.env" >nul
        echo [setup] Created backend\.env from template
    )
)

REM --- 4. Auto-generate JWT secret if missing or placeholder ---
if exist "backend\.env" (
    findstr /c:"JWT_SECRET_KEY=CHANGE_ME_GENERATE_A_RANDOM_SECRET" "backend\.env" >nul 2>nul
    if not errorlevel 1 (
        powershell -NoProfile -Command "$bytes = New-Object byte[] 48; (New-Object Security.Cryptography.RNGCryptoServiceProvider).GetBytes($bytes); $secret = [Convert]::ToBase64String($bytes).Replace('+','-').Replace('/','_'); (Get-Content 'backend\.env') -replace '^JWT_SECRET_KEY=.*', ('JWT_SECRET_KEY=' + $secret) | Set-Content 'backend\.env'"
        echo [setup] Generated fresh JWT_SECRET_KEY in backend\.env
    )
)

REM --- 5. Find Python Executable or create Virtualenv ---
set "PYTHON_EXE=python"
if exist "backend\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0backend\venv\Scripts\python.exe"
    echo [backend] Using virtual environment Python: !PYTHON_EXE!
) else (
    if not exist "backend\venv" mkdir "backend\venv"
    where python >nul 2>nul
    if errorlevel 1 (
        where py >nul 2>nul
        if errorlevel 1 (
            echo [backend] ERROR: Python not found. Install Python 3.10+ and rerun.
            pause
            exit /b 1
        )
        echo [backend] Creating virtual environment with py -3 ...
        py -3 -m venv "%~dp0backend\venv"
    ) else (
        echo [backend] Creating virtual environment at backend\venv...
        python -m venv "%~dp0backend\venv"
    )
    if not exist "%~dp0backend\venv\Scripts\python.exe" (
        echo [backend] ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    set "PYTHON_EXE=%~dp0backend\venv\Scripts\python.exe"
    echo [backend] Installing backend dependencies...
    call "%~dp0backend\venv\Scripts\pip.exe" install -r "%~dp0backend\requirements.txt"
    if errorlevel 1 (
        echo [backend] ERROR: pip install failed. Check backend\requirements.txt.
        pause
        exit /b 1
    )
)

REM --- 6. Frontend: install dependencies if needed ---
if not exist "frontend\node_modules" (
    echo [frontend] Installing npm dependencies...
    pushd frontend
    call npm install
    popd
)

REM --- 7. Check MongoDB ---
echo.
echo [mongo] Checking MongoDB service and process...
set "MONGO_RUNNING=0"
tasklist /fi "IMAGENAME eq mongod.exe" 2>nul | find /i "mongod.exe" >nul
if not errorlevel 1 set "MONGO_RUNNING=1"

if "!MONGO_RUNNING!"=="0" (
    sc query MongoDB 2>nul | find "RUNNING" >nul
    if not errorlevel 1 set "MONGO_RUNNING=1"
)

if "!MONGO_RUNNING!"=="0" (
    where mongod >nul 2>nul
    if not errorlevel 1 (
        echo [mongo] Starting local mongod on mongodb_data folder...
        start "RapidDoc-MongoDB" /min mongod --dbpath "%~dp0mongodb_data"
        set "MONGO_RUNNING=1"
    )
)

if "!MONGO_RUNNING!"=="0" (
    echo [mongo] Attempting to start the MongoDB Windows service...
    net start MongoDB >nul 2>nul
    if not errorlevel 1 set "MONGO_RUNNING=1"
)

if "!MONGO_RUNNING!"=="0" (
    echo [mongo] WARNING: MongoDB was not detected. Please ensure MongoDB is running on port 27017.
) else (
    echo [mongo] MongoDB is active.
)

REM --- 8. Launch Backend (FastAPI on port 8000) ---
echo.
echo [backend] Starting FastAPI Backend on http://127.0.0.1:8000 ...
REM The spawned window inherits PYTHONPATH from this bat, so run the venv
REM interpreter directly. A trailing space in a "set VAR=... &&" chain would
REM corrupt PYTHONPATH and crash CPython 3.12+ at startup ("failed to make
REM path absolute"), so we never re-set it here.
pushd "%~dp0backend"
start "RapidDoc-Backend" cmd /k "^"!PYTHON_EXE!^" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
popd

REM --- 9. Launch Frontend (Vite on port 5173) ---
echo [frontend] Starting Vite Frontend on http://localhost:5173 ...
pushd "%~dp0frontend"
start "RapidDoc-Frontend" cmd /k "npm run dev"
popd

echo.
echo =================================================================
echo   Servers are starting up in separate windows:
echo   * Web Application UI: http://localhost:5173
echo   * Swagger API Docs:   http://localhost:8000/docs
echo   * AI Brain Models:    Attached and Cascaded
echo =================================================================
echo.
endlocal