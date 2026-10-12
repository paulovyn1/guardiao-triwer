# Funções comuns dos scripts do guardião. Cada script carrega este arquivo com:
#   . (Join-Path $PSScriptRoot '_comum.ps1')
# Tudo que muda de pessoa para pessoa vem de config.json (mesma pasta). Nenhum dado pessoal fica nos scripts.

$script:utf8 = New-Object System.Text.UTF8Encoding($false)

function Get-Config {
    $arq = Join-Path $PSScriptRoot 'config.json'
    if (-not (Test-Path $arq)) { throw "config.json nao encontrado em $PSScriptRoot. Rode o onboarding do guardiao primeiro." }
    return ([System.IO.File]::ReadAllText($arq, $script:utf8) | ConvertFrom-Json)
}

function Get-Token($cfg) {
    $nome = if ($cfg.clickup.token_variavel) { $cfg.clickup.token_variavel } else { 'CLICKUP_API_TOKEN' }
    $t = [Environment]::GetEnvironmentVariable($nome, 'User')
    if (-not $t) { throw "$nome nao encontrado. Rode: powershell -ExecutionPolicy Bypass -File configurar.ps1 -DefinirToken" }
    return $t
}

# Id do ClickUp de quem recebe a tarefa. Procura o nome do bloco na lista de membros; sem achar, é a própria pessoa.
function Get-IdDono($cfg, [string]$dono) {
    if ($dono) {
        foreach ($m in @($cfg.clickup.membros)) {
            if ($m.nome -and $dono -like "*$($m.nome)*") { return [int64]$m.id }
        }
    }
    return [int64]$cfg.clickup.user_id
}

function Get-PastaMemoria($cfg) { return $cfg.pastas.memoria }

# Plano de dia futuro fica em planos\plano_AAAA-MM-DD.json e entra em plano_do_dia.json quando o dia chega.
function Promover-Plano([string]$pasta) {
    $hoje = (Get-Date).ToString('yyyy-MM-dd')
    $cand = Join-Path $pasta "planos\plano_$hoje.json"
    $atual = Join-Path $pasta 'plano_do_dia.json'
    if (-not (Test-Path $cand)) { return }
    $dataAtual = ''
    if (Test-Path $atual) { $dataAtual = [regex]::Match([System.IO.File]::ReadAllText($atual, $script:utf8), '"data"\s*:\s*"(\d{4}-\d{2}-\d{2})"').Groups[1].Value }
    if ($dataAtual -eq $hoje) { return }
    Copy-Item $cand $atual -Force
}
