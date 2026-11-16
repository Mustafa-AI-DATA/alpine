@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt -q
echo.
echo Open in browser: http://127.0.0.1:5055
echo.
python app.py
