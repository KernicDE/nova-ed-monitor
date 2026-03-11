@echo off
:: NOVA — Navigation, Operations, and Vessel Assistance
:: Double-click launcher for Windows
:: Runs nova.ps1 with execution policy bypass

powershell.exe -ExecutionPolicy Bypass -File "%~dp0nova.ps1" %*

:: Keep window open if launched by double-click (no arguments)
if "%~1"=="" pause
