@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File ".\batch.ps1"
pause