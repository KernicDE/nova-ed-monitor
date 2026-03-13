@echo off
:: NOVA Windows Installer
:: This script downloads the proper files and sets up NOVA

set "TEMP_DIR=%TEMP%\nova_install"
set "INSTALL_DIR=%USERPROFILE%\nova"

:: Create directories
mkdir "%TEMP_DIR%" 2>nul
mkdir "%INSTALL_DIR%" 2>nul

echo Downloading NOVA files...

:: Download using PowerShell to get raw content
powershell -Command "Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/KernicDE/nova-ed-monitor/main/nova.ps1' -OutFile '%TEMP_DIR%\nova.ps1'"
powershell -Command "Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/KernicDE/nova-ed-monitor/main/nova.bat' -OutFile '%TEMP_DIR%\nova.bat'"

:: Copy files to install directory
copy "%TEMP_DIR%\nova.ps1" "%INSTALL_DIR%\" >nul
copy "%TEMP_DIR%\nova.bat" "%INSTALL_DIR%\" >nul

:: Clean up
rmdir /s /q "%TEMP_DIR%" 2>nul

echo Installation complete!
echo.
echo NOVA has been installed to: %INSTALL_DIR%\
echo.
echo To run NOVA:
cd /d "%INSTALL_DIR%"
start nova.bat

echo You can also double-click nova.bat in the installation directory.
pause