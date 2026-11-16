@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt -q
echo.
echo [1/2] Ingesting docs into Pinecone...
python ingest.py
echo.
echo [2/2] Starting bot at http://127.0.0.1:7860
python app.py
