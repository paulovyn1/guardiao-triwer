@echo off
rem Guarda a chave gratuita do Groq (a transcricao da fala). Abre a pagina e mostra o passo a passo.
title Guardiao - chave do Groq
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0definir_chave_groq.ps1"
echo.
pause
