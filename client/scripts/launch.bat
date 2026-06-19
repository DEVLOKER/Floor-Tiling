@echo off
REM Floor Tiling — Windows Launcher (prod only, with health check and browser launch)

setlocal
set EXE_PATH=%~dp0floor-tiling.exe
set APP_PORT=8000
set APP_URL=http://localhost:%APP_PORT%

REM Check for EXE
if not exist "%EXE_PATH%" (
    echo ERROR: floor-tiling.exe not found at %EXE_PATH%
    echo Build first with build_exe.ps1.
    pause
    exit /b 1
)

REM Start the EXE in background
start "Floor Tiling" /B "%EXE_PATH%"

REM Wait for server to be ready (simple loop with curl)
set /a RETRIES=0
:waitloop
    set /a RETRIES+=1
    if %RETRIES% GTR 30 (
        echo ERROR: Server did not start within 60 seconds.
        goto end
    )
    curl --silent --max-time 2 %APP_URL%/health >nul 2>&1
    if %ERRORLEVEL%==0 goto server_ready
    timeout /t 2 >nul
    goto waitloop

:server_ready
    echo Server ready at %APP_URL%

REM Try to launch Chrome in kiosk mode, fallback to default browser
set CHROME_PATH=
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set CHROME_PATH=%ProgramFiles%\Google\Chrome\Application\chrome.exe
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set CHROME_PATH=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set CHROME_PATH=%LocalAppData%\Google\Chrome\Application\chrome.exe

set CHROME_ARGS=--kiosk %APP_URL% --incognito --disable-extensions --no-first-run --remote-debugging-port=0 --disable-features=Translate,TranslateUI --disable-translate
if defined CHROME_PATH (
    start "" "%CHROME_PATH%" %CHROME_ARGS%
) else (
    echo Chrome not found - opening default browser.
    start "" %APP_URL%
)

echo.
echo App is running at %APP_URL%
echo Close this window to stop the server.
pause

REM Optionally, kill the EXE process on exit (best effort)
taskkill /IM floor-tiling.exe >nul 2>&1
:end
endlocal
