# Lê as tarefas abertas da pessoa no ClickUp e grava resumo_clickup.json. Sem Claude.
# Regra: atribuída a ela, em um dos status abertos de config.json e com data.
# Token em variável de usuário (nome em config.json, padrão CLICKUP_API_TOKEN).
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_comum.ps1')
$cfg     = Get-Config
$token   = Get-Token $cfg
$headers = @{ Authorization = $token }

$workspace = $cfg.clickup.workspace_id
$userId    = $cfg.clickup.user_id
$semHora   = if ($cfg.clickup.hora_sem_hora) { $cfg.clickup.hora_sem_hora } else { '04:00' }
$prefixo   = $cfg.clickup.prefixo_aprovacao
$filtroStatus = (@($cfg.clickup.status_abertos) | Where-Object { $_ } | ForEach-Object { '&statuses[]=' + [uri]::EscapeDataString($_) }) -join ''

# Ignora tarefa vencida há mais de N dias (padrão 14, config clickup.atrasadas_dias; 0 = tudo).
$atrasadasDias = if ($null -ne $cfg.clickup.atrasadas_dias) { [int]$cfg.clickup.atrasadas_dias } else { 14 }
$desdeMs = if ($atrasadasDias -gt 0) { ([DateTimeOffset](Get-Date).Date.AddDays(-$atrasadasDias)).ToUnixTimeMilliseconds() } else { 0 }

$tarefas = @()
$page = 0
do {
    $url = "https://api.clickup.com/api/v2/team/$workspace/task?assignees[]=$userId$filtroStatus&due_date_gt=$desdeMs&subtasks=true&page=$page"
    $r = Invoke-RestMethod -Uri $url -Headers $headers -Method Get
    $tarefas += $r.tasks
    $page++
} while ($r.tasks.Count -ge 100)

function HoraLocal($ms) {
    # A API não informa se há hora marcada. Tarefa só com data aparece sempre na mesma hora (config.json,
    # clickup.hora_sem_hora); qualquer outra hora conta como horário marcado.
    if (-not $ms) { return $null }
    $h = ([DateTimeOffset]::FromUnixTimeMilliseconds([int64]$ms)).ToLocalTime().ToString('HH:mm')
    if ($h -eq $semHora) { return $null }
    return $h
}

$resumo = $tarefas | ForEach-Object {
    [pscustomobject]@{
        id      = $_.id
        nome    = $_.name
        status  = $_.status.status
        prazo   = ([DateTimeOffset]::FromUnixTimeMilliseconds([int64]$_.due_date)).ToLocalTime().ToString('yyyy-MM-dd')
        inicio  = HoraLocal $_.start_date
        fim     = HoraLocal $_.due_date
        aprovar = [bool]($prefixo -and $_.name -like "$prefixo*")   # subtarefa de aprovação: a data é falsa, vai para o bloco de aprovações
        lista   = $_.list.name
        tags    = @($_.tags | ForEach-Object { $_.name })
        criada_pelo_guardiao = [bool]((([string]$_.text_content) + ([string]$_.description)) -match 'Criada pelo Guardi')
        url     = $_.url
        pai     = $_.parent
    }
} | Sort-Object prazo, inicio, fim

# Eventos recorrentes com preparo (voz\preparos.py): a mãe tem a tag do evento (config clickup.eventos, ex. "live semanal") e a data do evento.
# Guarda as mães dos próximos 21 dias com TODAS as subtarefas (de qualquer dono e status): a antecipação é de outra pessoa da equipe e não vem na busca acima.
$eventos = @()
foreach ($tag in @($cfg.clickup.eventos | Where-Object { $_ })) {
    try {
        $ate = ([DateTimeOffset](Get-Date).Date.AddDays(21)).ToUnixTimeMilliseconds()
        $desde = ([DateTimeOffset](Get-Date).Date.AddDays(-1)).ToUnixTimeMilliseconds()
        $urlEv = "https://api.clickup.com/api/v2/team/$workspace/task?tags[]=$([uri]::EscapeDataString($tag))&due_date_gt=$desde&due_date_lt=$ate"
        foreach ($mae in @((Invoke-RestMethod -Uri $urlEv -Headers $headers -Method Get).tasks)) {
            if ($mae.parent) { continue }
            $completa = Invoke-RestMethod -Uri "https://api.clickup.com/api/v2/task/$($mae.id)?include_subtasks=true" -Headers $headers -Method Get
            $eventos += [pscustomobject]@{
                id     = $mae.id
                nome   = $mae.name
                data   = ([DateTimeOffset]::FromUnixTimeMilliseconds([int64]$mae.due_date)).ToLocalTime().ToString('yyyy-MM-dd')
                status = $mae.status.status
                tags   = @($mae.tags | ForEach-Object { $_.name })
                etapas = @($completa.subtasks | ForEach-Object {
                    [pscustomobject]@{
                        id     = $_.id
                        nome   = $_.name
                        status = $_.status.status
                        prazo  = if ($_.due_date) { ([DateTimeOffset]::FromUnixTimeMilliseconds([int64]$_.due_date)).ToLocalTime().ToString('yyyy-MM-dd') } else { $null }
                        donos  = @($_.assignees | ForEach-Object { $_.username })
                    }
                })
            }
        }
    } catch { Write-Warning "eventos ($tag): $($_.Exception.Message)" }
}

$saida = [pscustomobject]@{
    gerado_em = (Get-Date).ToString('yyyy-MM-dd HH:mm')
    total     = @($resumo).Count
    tarefas   = @($resumo)
    eventos   = @($eventos)
}
$saida | ConvertTo-Json -Depth 6 | Out-File (Join-Path $PSScriptRoot 'resumo_clickup.json') -Encoding utf8
$resumo | Format-Table prazo, inicio, fim, nome, lista -AutoSize | Out-String
