@echo off
setlocal
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
echo HCL + VirtualBox AutoFix
echo Requirements:
echo   - HCL 5.10.3 at D:\HCL\HCL
echo   - VirtualBox 6.1.50 at D:\HCL\VirtualBox
echo   - Memory Integrity (HVCI) disabled
echo   - Close HCL labs and save your work first
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0HCL-VBox-AutoFix.ps1"
echo.
pause
endlocal
