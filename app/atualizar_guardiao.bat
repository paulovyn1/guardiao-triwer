@echo off
rem Atualiza o guardiao para a versao mais nova (o mesmo que o botao Nova versao do painel).
rem Mantem memoria, planos, registros e preferencias. O guardiao reinicia sozinho.
title Atualizar o Guardiao
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0atualizar.ps1"
echo.
pause
