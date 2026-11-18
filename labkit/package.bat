@echo off
rem Builds the exe and zips it with the tester guide: dist\SirauggaLab-0.2.0.zip
cd /d "%~dp0"
call "%~dp0build_windows.bat" || exit /b 1
copy /y TESTING.md dist\README.txt >nul
powershell -NoProfile -Command "Compress-Archive -Force -Path dist\siraugga-lab.exe,dist\README.txt -DestinationPath dist\SirauggaLab-0.2.0.zip"
echo Done: dist\SirauggaLab-0.2.0.zip
