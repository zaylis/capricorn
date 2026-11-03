@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Запрос прав администратора...
powershell -Command "Start-Process -FilePath '%~dp0run.bat' -Verb RunAs"