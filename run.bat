@echo off
echo Starting RegComply AI...
echo.
echo Make sure you have set your API key in .env file
echo Copy .env.example to .env and fill in your key
echo.
cd /d "%~dp0"
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
