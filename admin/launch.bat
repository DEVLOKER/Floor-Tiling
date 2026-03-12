@echo off
REM Floor Tiling Admin - Production Launcher
REM Starts admin-panel.exe and opens http://localhost:9000 in browser (private/incognito mode)

setlocal
set EXE=%~dp0admin-panel.exe
set URL=http://localhost:9000
@REM set URL=https://localhost:9000

REM Start the server
start "Admin Panel" "%EXE%"

REM Try Edge (inprivate), then Chrome (incognito), then default browser
set EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe
set CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe
set CHROME_X86=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe
set LOCAL_CHROME=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe

if exist "%EDGE%" (
    start "" "%EDGE%" --inprivate %URL%
) else if exist "%CHROME%" (
    start "" "%CHROME%" --incognito %URL%
) else if exist "%CHROME_X86%" (
    start "" "%CHROME_X86%" --incognito %URL%
) else if exist "%LOCAL_CHROME%" (
    start "" "%LOCAL_CHROME%" --incognito %URL%
) else (
    start "" %URL%
)

endlocal
