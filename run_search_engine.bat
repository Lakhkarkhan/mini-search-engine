@echo off
setlocal
title Mini Search Engine - setup and demo

echo ============================================
echo   Mini Search Engine - setup and demo
echo ============================================
echo.

REM ---- 1. Find the project folder (Documents, or Documents inside OneDrive) ----
set "PROJECT="
if exist "%USERPROFILE%\Documents\mini-search-engine" set "PROJECT=%USERPROFILE%\Documents\mini-search-engine"
if not defined PROJECT if exist "%USERPROFILE%\OneDrive\Documents\mini-search-engine" set "PROJECT=%USERPROFILE%\OneDrive\Documents\mini-search-engine"

if not defined PROJECT (
    echo Could not find a folder named mini-search-engine in your Documents folder.
    echo Unzip mini-search-engine.zip into Documents and run this file again.
    echo.
    pause
    exit /b 1
)

cd /d "%PROJECT%"

REM Windows sometimes unzips into a folder inside a folder. Step in if so.
if not exist "minisearch" if exist "mini-search-engine\minisearch" cd /d "mini-search-engine"

if not exist "minisearch" (
    echo Found "%PROJECT%" but the project files are not inside it.
    echo Make sure you can see the folders minisearch and tests in there.
    echo.
    pause
    exit /b 1
)

echo Project folder: %CD%
echo.

REM ---- 2. Find Python ----
set "PY="
python --version >nul 2>&1 && set "PY=python"
if not defined PY py --version >nul 2>&1 && set "PY=py"

if not defined PY (
    echo Python was not found.
    echo Install it from https://www.python.org/downloads/ and tick "Add Python to PATH",
    echo then run this file again.
    echo.
    pause
    exit /b 1
)

echo Using Python:
%PY% --version
echo.

REM ---- 3. Create the virtual environment ----
if not exist ".venv\Scripts\activate.bat" (
    echo [1/4] Creating virtual environment...
    %PY% -m venv .venv
    if errorlevel 1 goto :failed
) else (
    echo [1/4] Virtual environment already exists, reusing it.
)
call ".venv\Scripts\activate.bat"

REM ---- 4. Install dependencies ----
echo.
echo [2/4] Installing dependencies. This can take a minute...
python -m pip install --quiet -r requirements-dev.txt
if errorlevel 1 goto :failed

REM ---- 5. Build the index and run a demo search ----
echo.
echo [3/4] Indexing the sample documents...
python -m minisearch index sample_docs --out index.json.gz
if errorlevel 1 goto :failed

echo.
echo [4/4] Searching for: inverted index
echo --------------------------------------------
python -m minisearch search index.json.gz "inverted index"
if errorlevel 1 goto :failed
echo --------------------------------------------

REM ---- 6. Optional extras ----
echo.
set "RUNTESTS="
set /p RUNTESTS=Run the 69 automated tests now? (y/n): 
if /i "%RUNTESTS%"=="y" (
    echo.
    python -m pytest -q
)

echo.
set "RUNAPI="
set /p RUNAPI=Start the web API and open it in your browser? (y/n): 
if /i "%RUNAPI%"=="y" (
    echo.
    echo Starting the server. Your browser will open the API page.
    echo Press Ctrl+C in this window to stop the server.
    echo.
    set "INDEX_PATH=index.json.gz"
    echo Website:  http://localhost:8000
    echo API Docs: http://localhost:8000/docs
    start "" cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:8000"
    python -m uvicorn minisearch.api:app --port 8000
)

echo.
echo Done.
pause
exit /b 0

:failed
echo.
echo Something went wrong. Read the message above, or send a screenshot of this window.
echo.
pause
exit /b 1
