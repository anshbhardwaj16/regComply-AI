@echo off
echo Installing dependencies...
pip install -r backend\requirements.txt
echo.
echo Setup complete!
echo.
echo Next steps:
echo 1. Copy .env.example to .env
echo 2. Add your GROQ_API_KEY (free at console.groq.com) or ANTHROPIC_API_KEY
echo 3. Run: run.bat
echo 4. Open browser at: http://localhost:8000
