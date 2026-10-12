@echo off
rem Instala o Guardiao neste computador: skill, painel, voz e atalho. De dois cliques e acompanhe a janela.
title Instalador do Guardiao
if not exist "%~dp0instalar.ps1" goto :faltando
if not exist "%~dp0voz\guardiao_voz.py" goto :faltando
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1" %*
echo.
pause
exit /b
:faltando
echo.
echo   Parece que a pasta do guardiao ainda esta dentro do arquivo .zip.
echo   Clique com o botao direito no arquivo .zip, escolha Extrair tudo,
echo   abra a pasta que aparecer e de dois cliques em instalar.bat de novo.
echo.
pause
