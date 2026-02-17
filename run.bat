@echo off
cd /d "%~dp0"
echo === PIDA - Personal Intrusion Detection Agent ===
python -c "import fastapi" 2>NUL
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
)
echo Starting agent...
python -m agent.tray
