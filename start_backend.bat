@echo off
echo Starting Tavern Tales Backend...
cd backend
python -m uvicorn main:app --reload --port 8000
pause
