@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    py -m venv .venv
    if errorlevel 1 goto :error
)

call ".venv\Scripts\activate.bat"
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

python booksy_pipeline.py
if errorlevel 1 goto :error

python load_database.py
if errorlevel 1 goto :error

python export_dashboard.py
if errorlevel 1 goto :error

echo.
echo Refresh complete.
echo Dashboard files are in data\dashboard\
exit /b 0

:error
echo.
echo Refresh failed. Review the error above.
exit /b 1
