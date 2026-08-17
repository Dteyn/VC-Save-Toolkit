@echo off
setlocal
cd /d "%~dp0"

echo VC Save Toolkit - Windows dependency installer
echo.

where py >nul 2>&1
if %errorlevel%==0 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Python 3.10 or newer was not found in PATH.
        echo Install Python, then run this script again.
        exit /b 1
    )
    set "PYTHON=python"
)

%PYTHON% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
    echo ERROR: VC Save Toolkit requires Python 3.10 or newer.
    %PYTHON% --version
    exit /b 1
)

echo Using:
%PYTHON% --version
echo.
%PYTHON% -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo.
    echo ERROR: Dependency installation failed.
    exit /b 1
)

echo.
echo Dependencies installed successfully.
echo You can now launch vc_save_toolkit.pyw.
endlocal
