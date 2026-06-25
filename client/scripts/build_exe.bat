@echo off
REM Floor Tiling — Windows EXE build script (Batch version, no PowerShell)
REM Usage: build_exe.bat
REM
REM Models are bundled into the exe by floor_tiling.spec (offline-ready):
REM   mask2former\models  (Mask2Former swin-large)  +  depth\models  (Depth Anything V2)
REM Make sure both models\ folders contain model.safetensors before building.

SETLOCAL ENABLEDELAYEDEXPANSION

REM Set working directory to client\
SET SCRIPT_DIR=%~dp0
PUSHD "%SCRIPT_DIR%.."

SET DIST_DIR=dist\floor-tiling

ECHO.
ECHO ========================================================
ECHO  Floor Tiling -- EXE build
ECHO ========================================================

REM Sanity check: model weights present (bundled by the spec)
IF NOT EXIST "models\mask2former\model.safetensors" ECHO WARNING: missing models\mask2former\model.safetensors -- exe won't run offline.
IF NOT EXIST "models\depth\model.safetensors" ECHO WARNING: missing models\depth\model.safetensors -- exe won't run offline.

REM Step 1: Cython compile
ECHO.
ECHO [1/5] Compiling Cython extensions (.pyd) ...
python setup_cython.py build_ext --inplace
IF ERRORLEVEL 1 (
	ECHO Cython compilation failed.
	EXIT /B 1
)
ECHO OK  Cython done.

REM Step 2: Run PyInstaller
ECHO.
ECHO [2/5] Running PyInstaller ...
pyinstaller floor_tiling.spec --noconfirm --clean
IF ERRORLEVEL 1 (
	ECHO PyInstaller failed.
	EXIT /B 1
)
ECHO OK  PyInstaller done.

REM Step 3: (models are bundled by the spec — nothing to copy)

REM Step 4: Clean Cython artefacts
ECHO.
ECHO [4/5] Cleaning Cython build artefacts ...
FOR %%D IN (config core ml patterns processors licensing) DO (
	IF EXIST "src\floor_tiling\%%D" (
		FOR %%E IN (*.pyd *.c) DO FOR /R "src\floor_tiling\%%D" %%F IN (%%E) DO DEL /F /Q "%%F"
		FOR /D %%B IN (src\floor_tiling\%%D\build) DO RMDIR /S /Q "%%B"
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
ECHO   Output : %DIST_DIR%\
ECHO   Size   : %DIST_SIZE%   (includes both bundled models)
ECHO.
ECHO   Ship the entire  %DIST_DIR%\  folder to the customer.
ECHO   They also need  floor_tiling.lic  on a USB drive.
ECHO.
ECHO   Customer runs:
ECHO     Double-click launch.bat -> Run with Windows
ECHO ========================================================

POPD
ENDLOCAL
