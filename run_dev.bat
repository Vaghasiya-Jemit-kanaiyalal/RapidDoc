@echo off
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
setlocal enabledelayedexpansion
title RapidDoc Development Launcher
cd /d "%~dp0"

set "COMMAND=%~1"
if "%COMMAND%"=="" set "COMMAND=dev"

echo =================================================================
echo             RapidDoc AI Document Editor Launcher
echo =================================================================
echo   Mode: !COMMAND!
echo.

REM ==================================================================
REM  Usage
REM    run_dev.bat            Start the API and the web app (default)
REM    run_dev.bat check      Report the environment and stop
REM    run_dev.bat test       Run the backend test suite
REM    run_dev.bat setup      Reinstall backend + frontend dependencies
REM ==================================================================

REM --- 1. Set PYTHONPATH to include workspace roots ---
REM The backend imports itself as RapidDoc.backend.app..., so the parent of the
REM RapidDoc folder has to be importable; backend\ alone is not enough.
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
    ) else (
        echo [setup] WARNING: backend\.env is missing and there is no template to copy.
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
)
echo [backend] Python: !PYTHON_EXE!

REM --- 6. Install backend dependencies when they are out of date ---
REM A hash of both requirement files is stamped next to the venv. Comparing it
REM means an edited requirement installs, and an unchanged one costs nothing -
REM which matters because pip is slow enough that running it on every launch
REM would make this script unpleasant to use.
set "DEPS_HASH_FILE=%~dp0backend\venv\.deps_hash"
set "FORCE_INSTALL=0"
if "!COMMAND!"=="setup" set "FORCE_INSTALL=1"

set "CURRENT_HASH="
for /f "usebackq delims=" %%H in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0backend\tools\deps_fingerprint.ps1"`) do set "CURRENT_HASH=%%H"

set "STAMPED_HASH="
if exist "!DEPS_HASH_FILE!" set /p STAMPED_HASH=<"!DEPS_HASH_FILE!"

if "!FORCE_INSTALL!"=="0" if not "!CURRENT_HASH!"=="NO-REQUIREMENTS" if "!CURRENT_HASH!"=="!STAMPED_HASH!" (
    echo [backend] Dependencies are up to date.
    goto :deps_done
)

echo [backend] Installing backend dependencies...
call "%~dp0backend\venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "%~dp0backend\requirements-dev.txt"
if errorlevel 1 (
    echo [backend] ERROR: pip install failed. Check backend\requirements.txt.
    pause
    exit /b 1
)
if not "!CURRENT_HASH!"=="" (
    >"!DEPS_HASH_FILE!" echo !CURRENT_HASH!
)
:deps_done

REM --- 7. Frontend: install dependencies if needed ---
if not exist "frontend\node_modules" (
    echo [frontend] Installing npm dependencies...
    pushd frontend
    call npm install
    if errorlevel 1 (
        echo [frontend] ERROR: npm install failed.
        popd
        pause
        exit /b 1
    )
    popd
) else (
    if "!FORCE_INSTALL!"=="1" (
        echo [frontend] Refreshing npm dependencies...
        pushd frontend
        call npm install
        popd
    ) else (
        echo [frontend] node_modules present.
    )
)

REM --- 8. Environment report ---
echo.
echo [check] Environment
"!PYTHON_EXE!" -c "import sys; print('  Python      ', sys.version.split()[0])"
where mongod >nul 2>nul
if errorlevel 1 (
    echo   MongoDB      not on PATH - the app will use the MongoDB service
) else (
    echo   MongoDB      mongod found
)
set "SOFFICE_FOUND=0"
where soffice >nul 2>nul && set "SOFFICE_FOUND=1"
if not "!SOFFICE_FOUND!"=="1" if exist "C:\Program Files\LibreOffice\program\soffice.exe" set "SOFFICE_FOUND=1"
if not "!SOFFICE_FOUND!"=="1" if exist "C:\Program Files (x86)\LibreOffice\program\soffice.exe" set "SOFFICE_FOUND=1"
if "!SOFFICE_FOUND!"=="1" (
    echo   LibreOffice  found - PDF export and summary PDF export will work
) else (
    echo   LibreOffice  NOT found - DOCX/PPTX export still work, but PDF export
    echo               and "Download PDF" on a summary will fail with 503.
    echo               Install from https://www.libreoffice.org/download/ and rerun.
)

if "!COMMAND!"=="check" goto :done

REM --- 9. Run the backend test suite ---
if "!COMMAND!"=="test" (
    echo.
    echo [test] Running the backend suite...
    pushd "%~dp0backend"
    "!PYTHON_EXE!" -m pytest tests/
    set "TEST_EXIT=!errorlevel!"
    popd
    if not "!TEST_EXIT!"=="0" (
        echo [test] FAILED - see the output above.
    ) else (
        echo [test] All backend tests passed.
    )
    pause
    goto :done
)

if not "!COMMAND!"=="dev" (
    echo [launcher] ERROR: unknown mode '!COMMAND!'. Use: dev, check, test, setup.
    pause
    exit /b 1
)

REM --- 10. Check MongoDB ---
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

REM --- 11. Free the ports before binding ---
REM Starting a second copy silently crashes the new process against a port the
REM old one still holds, which looks like "my changes did not load". Say it out
REM loud instead.
for %%P in (8000 5173) do (
    netstat -ano 2>nul | find /r /c ":%%P .*LISTENING" >nul 2>nul
    if not errorlevel 1 echo [ports] Port %%P is already in use - stop the old server first.
)

REM --- 12. Launch Backend (FastAPI on port 8000) ---
echo.
echo [backend] Starting FastAPI Backend on http://127.0.0.1:8000 ...
REM The spawned window inherits PYTHONPATH from this bat, so run the venv
REM interpreter directly. A trailing space in a "set VAR=... &&" chain would
REM corrupt PYTHONPATH and crash CPython 3.12+ at startup ("failed to make
REM path absolute"), so we never re-set it here.
pushd "%~dp0backend"
start "RapidDoc-Backend" cmd /k "^"!PYTHON_EXE!^" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
popd

REM --- 13. Wait for the API to answer before handing over ---
REM Vite serves a page that immediately calls the API, so handing the user the
REM URL before the API is listening produces a page full of failed requests.
echo [backend] Waiting for the API to respond...
set "API_UP=0"
for /l %%I in (1,1,40) do (
    if "!API_UP!"=="0" (
        powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/' -TimeoutSec 2; if ($r.status -eq 'healthy') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
        if not errorlevel 1 (
            set "API_UP=1"
        ) else (
            ping -n 2 127.0.0.1 >nul
        )
    )
)

if "!API_UP!"=="1" (
    echo [backend] API is healthy.
    powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/' -TimeoutSec 3; Write-Host ('[backend] Database: ' + $r.database_status) -ForegroundColor Cyan } catch {}"
) else (
    echo [backend] WARNING: the API did not answer within 80 seconds.
    echo [backend] Check the RapidDoc-Backend window for the traceback.
)

REM --- 14. Launch Frontend (Vite on port 5173) ---
echo [frontend] Starting Vite Frontend on http://localhost:5173 ...
pushd "%~dp0frontend"
start "RapidDoc-Frontend" cmd /k "npm run dev"
popd

REM Vite binds the IPv6 loopback on some machines, so probe "localhost" rather
REM than 127.0.0.1 - the printed URL has to be the one that answers.
echo [frontend] Waiting for the UI to respond...
set "UI_UP=0"
for /l %%I in (1,1,40) do (
    if "!UI_UP!"=="0" (
        powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:5173' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
        if not errorlevel 1 (
            set "UI_UP=1"
        ) else (
            ping -n 2 127.0.0.1 >nul
        )
    )
)

if "!UI_UP!"=="1" (
    echo [frontend] UI is serving on http://localhost:5173
) else (
    echo [frontend] WARNING: the UI did not answer within 80 seconds.
    echo [frontend] Check the RapidDoc-Frontend window for the traceback.
)

echo.
echo =================================================================
echo   Servers are starting up in separate windows:
echo   * Web Application UI: http://localhost:5173
echo   * Swagger API Docs:   http://localhost:8000/docs
echo.
echo   Try it:
echo     1. Open the UI and upload a .docx or .pdf
echo     2. Hover an image - Resize sets a printed size, Replace swaps it
echo     3. Open the Edit Log drawer (right) to restore an earlier version
echo     4. Ask the AI to "Summarize this document", then export TXT/DOCX/PDF
echo =================================================================
echo.

:done
endlocal
