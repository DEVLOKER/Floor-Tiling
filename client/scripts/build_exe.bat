@echo off
REM Floor Tiling — Windows EXE build script (Batch version, no PowerShell)
REM Usage: build_exe.bat [tiny|small|base_plus|large|all]

SETLOCAL ENABLEDELAYEDEXPANSION

REM Default model is tiny
SET MODEL=%1
IF "%MODEL%"=="" SET MODEL=tiny

REM Set working directory to client\
SET SCRIPT_DIR=%~dp0
PUSHD "%SCRIPT_DIR%.."

SET DIST_DIR=dist\floor-tiling

REM Model file mapping
SET "MODELFILE_tiny=sam2.1_hiera_tiny.pt"
SET "MODELFILE_small=sam2.1_hiera_small.pt"
SET "MODELFILE_base_plus=sam2.1_hiera_base_plus.pt"
SET "MODELFILE_large=sam2.1_hiera_large.pt"

REM Variant for settings.py
IF "%MODEL%"=="all" (
	SET VARIANT=tiny
) ELSE (
	SET VARIANT=%MODEL%
)

ECHO.
ECHO ========================================================
ECHO  Floor Tiling -- EXE build
ECHO ========================================================

REM Step 1: Cython compile
ECHO.
ECHO [1/5] Compiling Cython extensions (.pyd) ...
python setup_cython.py build_ext --inplace
IF ERRORLEVEL 1 (
	ECHO Cython compilation failed.
	EXIT /B 1
)
ECHO OK  Cython done.

REM Step 2: Patch settings.py, run PyInstaller, restore
ECHO.
ECHO [2/5] Running PyInstaller  (model variant: %VARIANT%) ...
SET SETTINGS_PATH=config\settings.py
COPY /Y "%SETTINGS_PATH%" "%SETTINGS_PATH%.bak" >NUL
REM Patch the variant in MODEL_CONFIG (simple replace)
FOR /F "usebackq delims=" %%A IN ("%SETTINGS_PATH%") DO (
	SET "line=%%A"
	ECHO !line! | FINDSTR /R /C:"\"variant\"\s*:\s*\".*\"" >NUL && (
		ECHO     "variant": "%VARIANT%", >> "%SETTINGS_PATH%.tmp"
	) || (
		ECHO !line!>>"%SETTINGS_PATH%.tmp"
	)
)
MOVE /Y "%SETTINGS_PATH%.tmp" "%SETTINGS_PATH%" >NUL
ECHO    Patched MODEL_CONFIG variant -> '%VARIANT%'

pyinstaller floor_tiling.spec --noconfirm --clean
IF ERRORLEVEL 1 (
	COPY /Y "%SETTINGS_PATH%.bak" "%SETTINGS_PATH%" >NUL
	ECHO PyInstaller failed.
	EXIT /B 1
)
COPY /Y "%SETTINGS_PATH%.bak" "%SETTINGS_PATH%" >NUL
ECHO    settings.py restored.
ECHO OK  PyInstaller done.

REM Step 3: Copy SAM2 model(s)
ECHO.
ECHO [3/5] Copying SAM2 model(s) [%MODEL%] -> %DIST_DIR%\sam2\models\ ...
SET MODELS_OUT=%DIST_DIR%\sam2\models
IF NOT EXIST "%MODELS_OUT%" MKDIR "%MODELS_OUT%"
IF "%MODEL%"=="all" (
	FOR %%F IN (sam2\models\*.pt) DO COPY /Y "%%F" "%MODELS_OUT%" >NUL
) ELSE (
	SET "PTFILE=sam2\models\!MODELFILE_%MODEL%!"
	IF EXIST "!PTFILE!" (
		COPY /Y "!PTFILE!" "%MODELS_OUT%" >NUL
	) ELSE (
		ECHO Model file not found: !PTFILE!
	)
)
ECHO OK  Models in dist:
DIR /-C /O-S "%MODELS_OUT%"

REM Step 4: Clean Cython artefacts
ECHO.
ECHO [4/5] Cleaning Cython build artefacts ...
FOR %%D IN (config core mask2former patterns processors utils) DO (
	IF EXIST "%%D" (
		FOR %%E IN (*.pyd *.c) DO FOR /R %%D %%F IN (%%E) DO DEL /F /Q "%%F"
		FOR /D %%B IN (%%D\build) DO RMDIR /S /Q "%%B"
	)
)
FOR %%D IN (..\shared\utils ..\shared\config) DO (
	IF EXIST "%%D" FOR %%F IN (%%D\*.c) DO DEL /F /Q "%%F"
)
ECHO OK  Clean.

REM Step 5: Copy customer launcher
ECHO.
ECHO [5/5] Copying launcher -> %DIST_DIR%\ ...
IF EXIST "%SCRIPT_DIR%launch.bat" (
	COPY /Y "%SCRIPT_DIR%launch.bat" "%DIST_DIR%\launch.bat" >NUL
	ECHO OK  launch.bat copied.
) ELSE (
	ECHO launch.bat not found -- customers will need to run floor-tiling.exe manually.
)

REM Step 6: Summary
FOR /F "tokens=3" %%A IN ('DIR /-C /S /A-D "%DIST_DIR%" ^| FIND "File(s)"') DO SET DIST_SIZE=%%A
ECHO.
ECHO ========================================================
ECHO OK  Build complete!
ECHO.
ECHO   Model  : %MODEL%  (!MODELFILE_%VARIANT%!)
ECHO   Output : %DIST_DIR%\
ECHO   Size   : %DIST_SIZE%
ECHO.
ECHO   To build with a different model:
ECHO     build_exe.bat                  ^# tiny (default, ~40 MB)
ECHO     build_exe.bat small
ECHO     build_exe.bat base_plus
ECHO     build_exe.bat large
ECHO     build_exe.bat all
ECHO.
ECHO   Ship the entire  %DIST_DIR%\  folder to the customer.
ECHO   They also need  floor_tiling.lic  on a USB drive.
ECHO.
ECHO   Customer runs:
ECHO     Double-click launch.bat -> Run with Windows
ECHO ========================================================

POPD
ENDLOCAL
