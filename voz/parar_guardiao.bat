@echo off
rem Desliga o guardiao que roda em segundo plano (microfone, voz e tela). Use antes de rodar iniciar_guardiao.bat para depurar.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'guardiao_voz.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; 'Desligado: ' + $_.ProcessId }; 'Pronto.'"
pause
