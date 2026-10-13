@echo off
rem Confere o guardiao neste computador e diz onde esta o problema (voz, microfone, Claude, janela). Escreve logs\diagnostico.txt para mandar a quem ajuda.
chcp 65001 >nul
title Diagnostico do Guardiao
"%~dp0.venv\Scripts\python.exe" "%~dp0diagnostico.py" %*
echo.
pause
