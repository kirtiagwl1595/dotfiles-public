@echo off
rem Windows: start install.ps1 even when PowerShell blocks scripts (execution policy).
rem   install.cmd --check   shows what would change; changes nothing
rem   install.cmd           makes the changes; asks before each one
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
exit /b %ERRORLEVEL%
