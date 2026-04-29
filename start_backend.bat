@echo off
echo Starting Tavern Tales Backend...
echo Binding to 0.0.0.0 so LAN-connected guests can join multiplayer sessions.
echo If you do not want LAN access, change the host flag below to 127.0.0.1.
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
pause
