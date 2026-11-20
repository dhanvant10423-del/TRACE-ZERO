@echo off
cd /d "%~dp0"
py -3 -m pip install -r requirements.txt
if errorlevel 1 goto failed
py -3 backend/server.py --open
:failed
pause
