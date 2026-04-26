@echo off
echo Starting Tavern Tales Reborn...

echo.
echo === Checking backend dependencies ===
where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python not found on PATH. Install Python 3 and try again.
    pause
    exit /b 1
)
pushd backend
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install backend Python dependencies.
    popd
    pause
    exit /b 1
)
popd

echo.
echo === Checking frontend dependencies ===
where npm >nul 2>nul
if errorlevel 1 (
    echo ERROR: npm not found on PATH. Install Node.js and try again.
    pause
    exit /b 1
)
pushd frontend
call npm install
if errorlevel 1 (
    echo ERROR: Failed to install frontend dependencies.
    popd
    pause
    exit /b 1
)
popd

echo.
echo === Launching services ===
start cmd /k "call start_backend.bat"
start cmd /k "call start_frontend.bat"
echo Both services have been launched in separate windows!
echo Once the Vite server is ready, open http://localhost:5173/ in your browser.
