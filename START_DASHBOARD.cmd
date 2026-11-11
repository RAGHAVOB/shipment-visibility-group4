@echo off
setlocal
cd /d "%~dp0"
echo Group 4 Shipment Visibility Dashboard
echo Creating a local Python environment if needed...
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Python 3.11 or newer is required. Install Python and try again.
    pause
    exit /b 1
  )
)
echo Installing the pinned dashboard requirements...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo Installation did not complete. Check your internet connection.
  pause
  exit /b 1
)
echo Opening Streamlit at http://localhost:8501
echo Keep this window open while presenting. Press Ctrl+C to stop.
".venv\Scripts\python.exe" -m streamlit run app.py --global.developmentMode false --server.address localhost --server.port 8501
endlocal
