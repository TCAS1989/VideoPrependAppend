@echo off
REM ===================================================================
REM  Build the WGU Video Brander into a distributable Windows app.
REM  Produces:  dist\WGUVideoBrander\WGUVideoBrander.exe
REM ===================================================================
setlocal

echo [1/3] Installing build dependencies...
python -m pip install -r requirements.txt || goto :error

echo.
echo [2/3] Fetching bundled ffmpeg (if not already present)...
python get_ffmpeg.py || goto :error

echo.
echo [3/3] Building the app with PyInstaller...
python -m PyInstaller WGUVideoBrander.spec --noconfirm --distpath dist --workpath build_tmp || goto :error

echo.
echo ===================================================================
echo  Done!  The app is in:  dist\WGUVideoBrander\
echo  Give users the whole WGUVideoBrander folder (or a zip of it) and
echo  have them run WGUVideoBrander.exe.
echo ===================================================================
goto :eof

:error
echo.
echo Build failed. See the messages above.
exit /b 1
