@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%check-goldverse-backup-health.ps1"
echo.
echo Press any key to close this window...
pause >nul
endlocal
