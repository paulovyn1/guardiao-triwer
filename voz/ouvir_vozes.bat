@echo off
rem Toca a mesma frase nas tres vozes do guardiao, para escolher. Diga ao Claude o numero da preferida.
chcp 65001 >nul
"%~dp0.venv\Scripts\python.exe" "%~dp0escolher_voz.py" %*
pause
