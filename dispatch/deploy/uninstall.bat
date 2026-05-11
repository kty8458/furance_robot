@echo off
setlocal

set INSTALL_DIR=C:\FuranceDispatch

echo === Uninstalling Dispatch System ===

echo [1/3] Stopping service...
net stop FuranceDispatch 2>nul
"%INSTALL_DIR%\service\nssm.exe" remove FuranceDispatch confirm 2>nul

echo [2/3] Removing files...
rmdir /S /Q "%INSTALL_DIR%" 2>nul

echo [3/3] Uninstallation complete
pause
