@echo off
chcp 65001 >nul
title Установка зависимостей Капри
cd /d "%~dp0"

echo ===================================================
echo   УСТАНОВКА БИБЛИОТЕК ДЛЯ КАПРИ
echo ===================================================
echo.

set "PY="
for %%v in (3.13 3.12 3.11 3.14) do if not defined PY py -%%v -c "" >nul 2>nul && set "PY=py -%%v"
if not defined PY where py >nul 2>nul && set "PY=py"
if not defined PY where python >nul 2>nul && set "PY=python"

if not defined PY (
    echo [ОШИБКА] Python не найден!
    echo Скачайте Python 3.13 с https://www.python.org/downloads/
    echo При установке ОБЯЗАТЕЛЬНО поставьте галочку "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

echo [1/3] Найден Python. Обновляем pip...
%PY% -m pip install --upgrade pip

echo.
echo [2/3] Устанавливаем зависимости из requirements.txt...
%PY% -m pip install -r requirements.txt

echo.
echo [3/3] Запуск скрипта установки (Vosk и настройки)...
%PY% tools\install.py

echo.
echo ===================================================
echo   ГОТОВО! Теперь запустите setup_ai.bat
echo ===================================================
pause