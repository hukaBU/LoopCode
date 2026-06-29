@echo off
rem Launch LoopCode. pyw hides the console; py is the fallback.
where pyw >nul 2>nul
if %errorlevel%==0 (
  start "" pyw -3 "%~dp0launcher.py"
) else (
  start "" py -3 "%~dp0launcher.py"
)
