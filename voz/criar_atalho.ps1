# Cria (ou atualiza) na área de trabalho o atalho que abre o painel do guardião, com o ícone dele.
# O atalho chama o pythonw com sem_janela.py: abrir pelo powershell, mesmo escondido, pisca uma janela preta de terminal.
# Uso: powershell -ExecutionPolicy Bypass -File criar_atalho.ps1            (atalho "Guardião")
#      powershell -ExecutionPolicy Bypass -File criar_atalho.ps1 -Nome "Guardião do dia"
param([string]$Nome = 'Guardião')
$voz = $PSScriptRoot
$pasta = [Environment]::GetFolderPath('Desktop')
$pythonw = Join-Path $voz '.venv\Scripts\pythonw.exe'
$atalho = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $pasta "$Nome.lnk"))
if (Test-Path $pythonw) {
    $atalho.TargetPath = $pythonw
    $atalho.Arguments = "`"$voz\sem_janela.py`" `"$voz\abrir_guardiao_v2.ps1`""
} else {  # programa ainda sem o Python instalado (não deveria acontecer: o instalador cria o atalho depois)
    $atalho.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $atalho.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$voz\abrir_guardiao_v2.ps1`""
}
$atalho.WorkingDirectory = $voz
$atalho.IconLocation = "$voz\guardiao.ico,0"
$atalho.Description = 'Abre o painel do Guardião'
$atalho.WindowStyle = 7
$atalho.Save()
Write-Output "Atalho criado: $(Join-Path $pasta "$Nome.lnk")"
