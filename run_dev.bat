@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
setlocal
title RapidDoc Development Launcher
cd /d "%~dp0"

echo =================================================================
echo             RapidDoc AI Document Editor Launcher
echo =================================================================
echo.

REM --- 1. Create required folders if missing ---
if not exist "backend\storage" (
    mkdir "backend\storage"
    echo [setup] Created backend\storage
)
if not exist "mongodb_data" (
    mkdir "mongodb_data"
    echo [setup] Created mongodb_data
)

REM --- 2. Ensure backend\.env exists ---
if not exist "backend\.env" (
    if exist "backend\.env.example" (
        copy "backend\.env.example" "backend\.env" >nul
        echo [setup] Created backend\.env from .env.example
    )
)

REM --- 3. Auto-generate a real JWT secret if placeholder present ---
if exist "backend\.env" (
    findstr /c:"JWT_SECRET_KEY=CHANGE_ME_GENERATE_A_RANDOM_SECRET" "backend\.env" >nul 2>nul
    if not errorlevel 1 (
        for /f %%S in ('python -c "import secrets; print(secrets.token_urlsafe(48))"') do set "NEW_SECRET=%%S"
        powershell -NoProfile -Command "(Get-Content 'backend\.env') -replace '^JWT_SECRET_KEY=.*','JWT_SECRET_KEY=%NEW_SECRET%' | Set-Content 'backend\.env'"
        echo [setup] Generated a fresh JWT_SECRET_KEY in backend\.env
    )
)

REM --- 4. Backend: create venv + install requirements if missing ---
if not exist "backend\venv\Scripts\python.exe" (
    echo [backend] Creating virtualenv...
    python -m venv backend\venv
    echo [backend] Installing dependencies...
    call backend\venv\Scripts\pip.exe install -r backend\requirements.txt
)


REM --- 5. Frontend: npm install if needed ---
if not exist "frontend\node_modules" (
    echo [frontend] Installing npm dependencies...
    pushd frontend
    call npm install
    popd
)

REM --- 6. Start MongoDB (skip if already running) ---
echo.
echo [mongo] Checking MongoDB...
set "MONGO_RUNNING=0"
tasklist /fi "IMAGENAME eq mongod.exe" 2>nul | find /i "mongod.exe" >nul
if not errorlevel 1 set "MONGO_RUNNING=1"

if "%MONGO_RUNNING%"=="0" (
    sc query MongoDB 2>nul | find "RUNNING" >nul
    if not errorlevel 1 set "MONGO_RUNNING=1"
)

if "%MONGO_RUNNING%"=="0" (
    where mongod >nul 2>nul
    if not errorlevel 1 (
        echo [mongo] Starting mongod on mongodb_data...
        start "RapidDoc-MongoDB" /min mongod --dbpath "%CD%\mongodb_data"
        set "MONGO_RUNNING=1"
    )
)

if "%MONGO_RUNNING%"=="0" (
    echo [mongo] Attempting to start the MongoDB Windows service...
    net start MongoDB >nul 2>nul
    if not errorlevel 1 set "MONGO_RUNNING=1"
)

if "%MONGO_RUNNING%"=="0" (
    echo [mongo] WARNING: Could not find MongoDB. Make sure MongoDB is running or download it from https://www.mongodb.com/try/download/community
) else (
    echo [mongo] MongoDB is ready.
)

REM --- 7. Launch Backend (port 8000) ---
echo.
echo [backend] Starting FastAPI on http://localhost:8000 ...
pushd backend
if exist "venv\Scripts\activate.bat" (
    start "RapidDoc-Backend" cmd /k ".\venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
) else (
    start "RapidDoc-Backend" cmd /k "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
)
popd

REM --- 8. Launch Frontend (port 5173) ---
echo [frontend] Starting Vite on http://localhost:5173 ...
pushd frontend
start "RapidDoc-Frontend" cmd /k "npm run dev"
popd

echo.
echo =================================================================
echo   Both servers are starting in separate windows!
echo   Frontend Web UI: http://localhost:5173
echo   Backend API Docs: http://localhost:8000/docs
echo =================================================================
echo.
endlocal
