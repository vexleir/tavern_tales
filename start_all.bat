@echo off
echo Starting Tavern Tales Reborn...
start cmd /k "call start_backend.bat"
start cmd /k "call start_frontend.bat"
echo Both services have been launched in separate windows!
echo Once the Vite server is ready, open http://localhost:5173/ in your browser.
