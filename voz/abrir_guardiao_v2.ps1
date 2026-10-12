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

$edge = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
if (-not (Test-Path $edge)) { $edge = 'C:\Program Files\Microsoft\Edge\Application\msedge.exe' }
if (Test-Path $edge) {
    # perfil próprio: o som da abertura toca sem clique e as permissões ficam guardadas
    # as aspas em volta do caminho contam: sem elas, uma pasta de usuário com espaço no nome quebra a linha de comando do Edge
    Start-Process -FilePath $edge -ArgumentList "--app=http://localhost:$porta/v2/", '--window-size=1456,939', "--user-data-dir=`"$voz\perfil_edge`"", '--autoplay-policy=no-user-gesture-required', '--no-first-run', '--no-default-browser-check'
} else {
    Start-Process "http://localhost:$porta/v2/"
}
