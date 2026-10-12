@echo off
rem Abre o painel novo do guardiao (liga ou reinicia o programa em segundo plano, se precisar).
start "" /min powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0abrir_guardiao_v2.ps1"
