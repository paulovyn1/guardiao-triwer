@echo off
rem Mostra o painel novo com um dia de exemplo: sem microfone, sem Claude e sem ClickUp. Porta 8768, fecha sozinha em 30 minutos.
cd /d "%~dp0"
start "" /min ".venv\Scripts\pythonw.exe" demo_v2.py
