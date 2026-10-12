@echo off
rem Gera o plano sugerido agora (dia util: o de hoje; sabado e domingo: o da proxima segunda).
rem Leva cerca de 3 minutos. No fim abre o painel para voce aprovar.
title Guardiao do dia - gerando o plano
echo.
echo  Gerando o plano do dia com o guardiao. Leva cerca de 3 minutos.
echo  Nao feche esta janela.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0gerar_plano.ps1" -Manual
echo.
echo  Pronto. Abrindo o painel para voce aprovar o plano.
call "%~dp0abrir_guardiao.bat"
timeout /t 5 >nul
