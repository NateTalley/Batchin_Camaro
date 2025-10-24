@echo off
setlocal

set VENV_NAME=batchvenv
set REQUIREMENTS_FILE=requirements.txt

echo Checking for Python...
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Python is not found or not in your PATH.
    echo Please install Python and ensure it is available from the command line.
    echo.
    pause
    exit /b 1
)

echo.
if exist %VENV_NAME% (
    echo A virtual environment named "%VENV_NAME%" already exists.
    echo It will be used for installation.
    echo.
) else (
    echo Creating virtual environment "%VENV_NAME%"...
    python -m venv %VENV_NAME%
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create the virtual environment.
        pause
        exit /b 1
    )
    echo Virtual environment created.
    echo.
)

echo Installing dependencies from "%REQUIREMENTS_FILE%"...
call %VENV_NAME%\Scripts\activate.bat
pip install -r %REQUIREMENTS_FILE%
deactivate

echo.
echo Setup complete.
echo You can activate the environment by running: %VENV_NAME%\Scripts\activate.bat
echo.
pause
endlocal