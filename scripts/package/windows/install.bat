@echo off
REM Elevate and run install.ps1
net session >nul 2>&1
if %errorLevel% neq 0 (
  echo Requesting Administrator privileges...
  powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
pause
