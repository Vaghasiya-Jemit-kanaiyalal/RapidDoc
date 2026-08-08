@echo off
setlocal
title RapidDoc Development Launcher
cd /d "%~dp0"

echo ============================================
echo   RapidDoc - One-Click Development Launcher
echo ============================================
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

REM --- 2. Ensure backend/.env exists ---
if not exist "backend\.env" (
    copy "backend\.env.example" "backend\.env" >nul
    echo [setup] Created backend\.env from .env.example
)

REM --- 3. Auto-generate a real JWT secret if the placeholder is still present ---
findstr /c:"JWT_SECRET_KEY=CHANGE_ME_GENERATE_A_RANDOM_SECRET" "backend\.env" >nul 2>nul
if not errorlevel 1 (
    for /f %%S in ('python -c "import secrets; print(secrets.token_urlsafe(48))"') do set "NEW_SECRET=%%S"
    powershell -NoProfile -Command "(Get-Content 'backend\.env') -replace '^JWT_SECRET_KEY=.*','JWT_SECRET_KEY=%NEW_SECRET%' | Set-Content 'backend\.env'"
    echo [setup] Generated a fresh JWT_SECRET_KEY in backend\.env
)

REM --- 4. Backend: create venv + install requirements if missing ---
if not exist "backend\venv\Scripts\python.exe" (
    echo [backend] Creating virtualenv...
    python -m venv backend\venv
)
echo [backend] Installing requirements (first run may take a while)...
call "backend\venv\Scripts\activate.bat"
pip install -r backend\requirements.txt
call deactivate

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
tasklist /fi "IMAGENAME eq mongod.exe" 2>nul | find /i "mongod.exe" >nul
if not errorlevel 1 goto mongo_ok

sc query MongoDB 2>nul | find "RUNNING" >nul
if not errorlevel 1 goto mongo_ok

where mongod >nul 2>nul
if not errorlevel 1 (
    echo [mongo] Starting mongod on mongodb_data...
    start "RapidDoc-MongoDB" /min mongod --dbpath "%CD%\mongodb_data"
    goto mongo_ok
)

echo [mongo] Attempting to start the MongoDB Windows service...
net start MongoDB >nul 2>nul
if not errorlevel 1 goto mongo_ok

echo [mongo] WARNING: Could not find MongoDB. Install it from https://www.mongodb.com/try/download/community
:mongo_ok

REM --- 7. Launch Backend (port 8000) ---
echo.
echo [backend] Starting FastAPI on http://localhost:8000 ...
pushd backend
start "RapidDoc-Backend" /min cmd /k ".\venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
popd

REM --- 8. Launch Frontend (port 5173) ---
echo [frontend] Starting Vite on http://localhost:5173 ...
pushd frontend
start "RapidDoc-Frontend" /min cmd /k "npm run dev"
popd

echo.
echo ============================================
echo   Both servers are starting in separate windows.
echo   Frontend: http://localhost:5173
echo   Backend : http://localhost:8000  (docs at /docs)
echo ============================================
echo.
pause
endlocal
