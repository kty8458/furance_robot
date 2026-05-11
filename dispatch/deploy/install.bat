@echo off
setlocal

set INSTALL_DIR=C:\FuranceDispatch
set SCRIPT_DIR=%~dp0

echo === Installing Dispatch System ===

echo [1/4] Creating directories...
mkdir "%INSTALL_DIR%\bin" 2>nul
mkdir "%INSTALL_DIR%\static" 2>nul
mkdir "%INSTALL_DIR%\config" 2>nul
mkdir "%INSTALL_DIR%\data" 2>nul
mkdir "%INSTALL_DIR%\logs" 2>nul
mkdir "%INSTALL_DIR%\service" 2>nul

echo [2/4] Copying files...
if exist "%SCRIPT_DIR%dist\dispatch\" (
    xcopy "%SCRIPT_DIR%dist\dispatch\*" "%INSTALL_DIR%\bin\" /E /Y /Q
) else (
    echo Error: dist\dispatch\ not found. Run build.sh first.
    exit /b 1
)

if exist "%SCRIPT_DIR%..\frontend\dist\" (
    xcopy "%SCRIPT_DIR%..\frontend\dist\*" "%INSTALL_DIR%\static\" /E /Y /Q
)

copy "%SCRIPT_DIR%config.yaml" "%INSTALL_DIR%\config\" /Y

echo [3/4] Downloading nssm if needed...
if not exist "%INSTALL_DIR%\service\nssm.exe" (
    echo Downloading nssm...
    powershell -Command "Invoke-WebRequest -Uri 'https://nssm.cc/release/nssm-2.24.zip' -OutFile '%INSTALL_DIR%\service\nssm.zip'"
    powershell -Command "Expand-Archive '%INSTALL_DIR%\service\nssm.zip' -DestinationPath '%INSTALL_DIR%\service\nssm_tmp' -Force"
    copy "%INSTALL_DIR%\service\nssm_tmp\nssm-2.24\win64\nssm.exe" "%INSTALL_DIR%\service\nssm.exe" /Y
    rmdir /S /Q "%INSTALL_DIR%\service\nssm_tmp"
    del "%INSTALL_DIR%\service\nssm.zip"
)

echo [4/4] Installing Windows service...
"%INSTALL_DIR%\service\nssm.exe" install FuranceDispatch "%INSTALL_DIR%\bin\dispatch_server.exe"
"%INSTALL_DIR%\service\nssm.exe" set FuranceDispatch AppDirectory "%INSTALL_DIR%"
"%INSTALL_DIR%\service\nssm.exe" set FuranceDispatch DisplayName "Furance Dispatch System"
"%INSTALL_DIR%\service\nssm.exe" set FuranceDispatch Start SERVICE_AUTO_START
"%INSTALL_DIR%\service\nssm.exe" set FuranceDispatch AppRestartDelay 5000
"%INSTALL_DIR%\service\nssm.exe" set FuranceDispatch AppStdout "%INSTALL_DIR%\logs\service_stdout.log"
"%INSTALL_DIR%\service\nssm.exe" set FuranceDispatch AppStderr "%INSTALL_DIR%\logs\service_stderr.log"

echo Starting service...
net start FuranceDispatch

echo === Installation complete ===
echo Service status: sc query FuranceDispatch
pause
