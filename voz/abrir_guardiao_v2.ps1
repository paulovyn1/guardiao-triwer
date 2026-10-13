# Abre o painel do guardião (http://localhost:8767/v2/) numa janela só dele.
# Se o guardião estiver ligado com código mais antigo que o do disco (acabou de atualizar, por exemplo), este script o reinicia
# em segundo plano antes de abrir a janela.
$voz = $PSScriptRoot
$porta = 8767
$pythonw = "$voz\.venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Add-Type -AssemblyName System.Windows.Forms
    [void][System.Windows.Forms.MessageBox]::Show("O painel do guardião ainda não está instalado nesta pasta.`n`nDê dois cliques em instalar.bat, na pasta do guardião que você baixou.", 'Guardião')
    exit 1
}
function Escutando { [bool](Get-NetTCPConnection -LocalPort $porta -State Listen -ErrorAction SilentlyContinue) }
function PrecisaReiniciar {
    # /versao diz se os arquivos do programa mudaram depois que ele ligou. Guardião antigo, sem essa rota, também reinicia.
    try { return [bool](Invoke-RestMethod "http://localhost:$porta/versao" -TimeoutSec 5).reiniciar } catch { return $true }
}
function Ligar {
    Start-Process -FilePath $pythonw -ArgumentList 'guardiao_voz.py', '--cerebro', '--sem-janela' -WorkingDirectory $voz -WindowStyle Hidden
    for ($i = 0; $i -lt 80 -and -not (Escutando); $i++) { Start-Sleep -Milliseconds 500 }
}

if (-not (Escutando)) { Ligar }
elseif (PrecisaReiniciar) {
    Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'guardiao_voz\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    for ($i = 0; $i -lt 20 -and (Escutando); $i++) { Start-Sleep -Milliseconds 300 }
    Ligar
}

# Quem abre a janela é o janela_edge.py: perfil só do guardião, sem entrar na conta Microsoft da pessoa, sem sincronizar e sem extensões,
# e limpa um perfil antigo que já tenha entrado na conta. (Os argumentos do Edge ficam num lugar só, nele.)
Start-Process -FilePath $pythonw -ArgumentList "`"$voz\janela_edge.py`"", "http://localhost:$porta/v2/" -WorkingDirectory $voz -WindowStyle Hidden
