# Cria (ou atualiza) na área de trabalho o atalho que abre o painel do guardião, com o ícone dele.
# Uso: powershell -ExecutionPolicy Bypass -File criar_atalho.ps1            (atalho "Guardião")
#      powershell -ExecutionPolicy Bypass -File criar_atalho.ps1 -Nome "Guardião do dia"
param([string]$Nome = 'Guardião')
$voz = $PSScriptRoot
$pasta = [Environment]::GetFolderPath('Desktop')
$atalho = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $pasta "$Nome.lnk"))
$atalho.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$atalho.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$voz\abrir_guardiao_v2.ps1`""
$atalho.WorkingDirectory = $voz
$atalho.IconLocation = "$voz\guardiao.ico,0"
$atalho.Description = 'Abre o painel do Guardião'
$atalho.WindowStyle = 7
$atalho.Save()
Write-Output "Atalho criado: $(Join-Path $pasta "$Nome.lnk")"
