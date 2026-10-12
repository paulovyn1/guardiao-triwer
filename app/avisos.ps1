# Aviso por pop-up do guardião. Sem Claude, sem token, sem internet: só lê plano_do_dia.json e mostra uma
# notificação do Windows no começo de cada bloco, na abertura do dia e no fim do plano.
# Fica rodando escondido (uma instância só). Uso: powershell -ExecutionPolicy Bypass -File avisos.ps1 [-Teste]
param([switch]$Teste)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_comum.ps1')
$cfg   = Get-Config
$pasta = $PSScriptRoot
$utf8  = $script:utf8
$urlTela = 'http://localhost:8767/v2/'  # o painel do guardião
$nome  = if ($cfg.agente.nome) { $cfg.agente.nome } else { 'Guardião' }

[void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
[void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]
$appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'

function Esc([string]$s) { return [System.Security.SecurityElement]::Escape($s) }

function Mostrar-Aviso([string]$titulo, [string]$texto) {
    $xml = '<toast scenario="reminder" activationType="protocol" launch="' + (Esc $urlTela) + '">' +
        '<visual><binding template="ToastGeneric"><text>' + (Esc $titulo) + '</text><text>' + (Esc $texto) + '</text></binding></visual>' +
        '<actions><action content="Abrir a tela" activationType="protocol" arguments="' + (Esc $urlTela) + '"/>' +
        '<action content="Dispensar" activationType="system" arguments="dismiss"/></actions>' +
        '<audio src="ms-winsoundevent:Notification.Reminder"/></toast>'
    $doc = New-Object Windows.Data.Xml.Dom.XmlDocument
    $doc.LoadXml($xml)
    $toast = New-Object Windows.UI.Notifications.ToastNotification $doc
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
}

if ($Teste) {
    Mostrar-Aviso "${nome}: teste do aviso" "Se você está vendo isto, o pop-up funciona. Clique para abrir a tela."
    exit
}

$mutex = New-Object System.Threading.Mutex($false, 'Local\GuardiaoTriwerAvisos')
if (-not $mutex.WaitOne(0)) { exit }

$pastaLogs = Join-Path $pasta 'logs'
if (-not (Test-Path $pastaLogs)) { New-Item -ItemType Directory -Path $pastaLogs | Out-Null }
$log = Join-Path $pastaLogs 'avisos.log'
$arqEnviados = Join-Path $pasta 'avisos_enviados.json'

function Carregar-Enviados([string]$hoje) {
    if (Test-Path $arqEnviados) {
        try {
            $o = [System.IO.File]::ReadAllText($arqEnviados, $utf8) | ConvertFrom-Json
            if ($o.data -eq $hoje) { return @($o.chaves) }
        } catch { }
    }
    return @()
}
function Salvar-Enviados([string]$hoje, $chaves) {
    $o = [ordered]@{ data = $hoje; chaves = @($chaves) }
    [System.IO.File]::WriteAllText($arqEnviados, ($o | ConvertTo-Json -Compress), $utf8)
}
function Hora([string]$hoje, [string]$hhmm) { return [datetime]::ParseExact("$hoje $hhmm", 'yyyy-MM-dd HH:mm', $null) }

while ($true) {
    try {
        Promover-Plano $pasta
        $arqPlano = Join-Path $pasta 'plano_do_dia.json'
        $hoje = (Get-Date).ToString('yyyy-MM-dd')
        if (Test-Path $arqPlano) {
            $plano = [System.IO.File]::ReadAllText($arqPlano, $utf8) | ConvertFrom-Json
            if ($plano.data -eq $hoje -and -not $plano.exemplo) {
                $agora = Get-Date
                $enviados = @(Carregar-Enviados $hoje)
                $blocos = @($plano.blocos | Sort-Object inicio)
                $novos = @()

                # Abertura do dia: uma vez, a partir das 7h, se ainda não passou do primeiro bloco.
                if ($blocos.Count -gt 0 -and $enviados -notcontains 'abertura' -and $agora.Hour -ge 7) {
                    $primeiro = Hora $hoje $blocos[0].inicio
                    if ($agora -lt $primeiro.AddMinutes(10)) {
                        Mostrar-Aviso "${nome}: plano de hoje" ("{0} blocos. O primeiro começa às {1}: {2}" -f $blocos.Count, $blocos[0].inicio, $blocos[0].titulo)
                    }
                    $novos += 'abertura'
                }

                # Começo de cada bloco: avisa uma vez enquanto o bloco está acontecendo.
                foreach ($b in $blocos) {
                    $chave = 'bloco_' + $b.id
                    if ($enviados -contains $chave) { continue }
                    $ini = Hora $hoje $b.inicio
                    $fim = Hora $hoje $b.fim
                    if ($agora -ge $ini -and $agora -lt $fim) {
                        Mostrar-Aviso ("Agora: " + $b.titulo) ("Comece por: {0} (até {1})" -f $b.primeiro_passo, $b.fim)
                        $novos += $chave
                    }
                }

                # Fim do plano: uma vez, até 30 minutos depois do último bloco.
                if ($blocos.Count -gt 0 -and $enviados -notcontains 'fechamento') {
                    $ultimo = ($blocos | ForEach-Object { Hora $hoje $_.fim } | Sort-Object | Select-Object -Last 1)
                    if ($agora -ge $ultimo -and $agora -lt $ultimo.AddMinutes(30)) {
                        Mostrar-Aviso "${nome}: hora de fechar o dia" "Abra a tela e marque o que você concluiu. O que sobrar eu reprogramo."
                        $novos += 'fechamento'
                    }
                }

                if ($novos.Count -gt 0) { Salvar-Enviados $hoje (@($enviados) + $novos) }
            }
        }
    } catch {
        "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $($_.Exception.Message)" | Out-File $log -Append -Encoding utf8
    }
    Start-Sleep -Seconds 20
}
