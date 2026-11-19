@echo off
title WSL2 Memory Optimization Restart
echo ========================================================
echo   Applying WSL2 Memory Tuning (4GB Cap + DropCache)
echo ========================================================
echo.
echo [1/3] Shutting down WSL2 to apply .wslconfig...
wsl.exe --shutdown
timeout /t 3 /nobreak >nul

echo [2/3] Starting WSL2 and launching Siraugga server...
wsl.exe -e bash /mnt/c/Users/michael/Documents/DevCore/restart_server.sh
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Failed to restart server. Check logs inside WSL.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [3/3] Done! WSL2 is now running under the 4GB cap with auto-reclaim.
echo You can now return to your browser and refresh the page (F5).
echo.
pause
