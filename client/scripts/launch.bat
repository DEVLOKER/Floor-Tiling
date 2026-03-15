@echo off
REM Floor Tiling — Windows Launcher (prod only)
REM This batch file runs the EXE in the current directory.

setlocal
set USB_DRIVE=D
set LICENSE_USB_PATH=%USB_DRIVE%:\license
set EXE_PATH=%~dp0floor-tiling.exe

if not exist "%EXE_PATH%" (
    echo ERROR: floor-tiling.exe not found at %EXE_PATH%
    echo Build first with build_exe.ps1.
    pause
    exit /b 1
)

if not exist "%LICENSE_USB_PATH%\floor_tiling.lic" (
    echo ERROR: License file not found at %LICENSE_USB_PATH%\floor_tiling.lic
    echo Make sure your USB drive is plugged in and the drive letter is %USB_DRIVE%:
    echo To use a different drive letter, edit USB_DRIVE in this file.
    pause
    exit /b 1
)

set LICENSE_USB_PATH=%LICENSE_USB_PATH%
start "Floor Tiling" /B "%EXE_PATH%"
endlocal
