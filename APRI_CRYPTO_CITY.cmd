@echo off
setlocal
title Apri Crypto City
echo Crypto City: apertura della citta' contenuta in questa cartella.
echo Lascia aperta la finestra del server che si aprira'.
echo.
where py >nul 2>nul
if errorlevel 1 goto python
py -3 --version >nul 2>nul
if errorlevel 1 goto python
py -3 "%~dp0start_city.py" %*
goto result
:python
where python >nul 2>nul
if errorlevel 1 goto missing
python --version >nul 2>nul
if errorlevel 1 goto missing
python "%~dp0start_city.py" %*
goto result
:missing
echo Python non trovato. Serve Python 3.10 o successivo, consigliato 3.12.
echo Installa Python da python.org scegliendo Add Python to PATH, poi riprova.
pause
exit /b 1
:result
set "city_result=%errorlevel%"
echo.
if not "%city_result%"=="0" goto failed
echo Crypto City pronta. Lascia aperta la finestra del server.
exit /b 0
:failed
echo Apertura non completata. Leggi l'errore sopra.
pause
exit /b %city_result%
