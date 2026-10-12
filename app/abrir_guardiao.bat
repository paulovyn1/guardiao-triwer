@echo off
rem Abre o painel do guardiao (liga o programa em segundo plano, se precisar).
if exist "%~dp0voz\abrir_guardiao_v2.ps1" (
    start "" /min powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0voz\abrir_guardiao_v2.ps1"
) else (
    echo.
    echo  O painel do guardiao ainda nao foi instalado nesta pasta.
    echo  De dois cliques em instalar.bat, na pasta do guardiao que voce baixou.
    echo.
    pause
)
