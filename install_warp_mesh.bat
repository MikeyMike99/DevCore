@echo off
rem Installs the Cloudflare WARP client (Mesh node) inside WSL.
rem Runs as the WSL root user, so it does not ask for a sudo password.
rem Uses the script in Documents: install_warp_mesh.sh
echo Installing Cloudflare WARP in WSL...
wsl -u root -e bash -c "bash \"$(wslpath -u '%USERPROFILE%\Documents\install_warp_mesh.sh')\""
echo.
if errorlevel 1 (echo FAILED. Copy the lines above and send them to Claude.) else (echo Finished. Tell Claude it is done.)
pause
