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

# --- Claude Code: achar o que executar. O nome "claude" puro não basta: quem instalou por npm tem um claude.cmd, e o cmd.exe corta o
# pedido na primeira quebra de linha. Aqui se acha o claude.exe de verdade e se confere que ele executa (a mesma lógica do guardiao_sessao.py).
function Get-ClaudeReal([string]$atalho) {
    $base = Split-Path -Parent $atalho
    $texto = try { [System.IO.File]::ReadAllText($atalho) } catch { '' }
    $alvos = @()
    foreach ($m in [regex]::Matches($texto, '%dp0%\\([^"\r\n]+?\.(?:exe|js))"', 'IgnoreCase')) { $alvos += (Join-Path $base $m.Groups[1].Value) }
    $pacote = Join-Path $base 'node_modules\@anthropic-ai\claude-code'
    $alvos += (Join-Path $pacote 'bin\claude.exe')
    $alvos += (Join-Path $pacote 'cli.js')
    foreach ($alvo in $alvos) {
        if (-not (Test-Path -LiteralPath $alvo)) { continue }
        if ($alvo -like '*.exe') { return @($alvo) }
        $node = (Get-Command node -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source
        if ($node) { return @($node, $alvo) }
    }
    return @()
}

function Get-ClaudeCandidatos {
    if ($env:GUARDIAO_CLAUDE) { $env:GUARDIAO_CLAUDE.Trim('"') }
    $achado = (Get-Command claude -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source
    if ($achado) { $achado }
    Join-Path $env:USERPROFILE '.local\bin\claude.exe'
    if ($env:APPDATA) { Join-Path $env:APPDATA 'npm\claude.cmd' }
    $ext = Join-Path $env:USERPROFILE '.vscode\extensions'
    if (Test-Path $ext) {
        Get-ChildItem $ext -Directory -Filter 'anthropic.claude-code-*' -ErrorAction SilentlyContinue | Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName 'resources\native-binary\claude.exe' }
    }
}

function Test-ClaudeComando($cmd) {
    $cmd = @($cmd)
    $exe = $cmd[0]; $pre = @(); if ($cmd.Count -gt 1) { $pre = @($cmd[1..($cmd.Count - 1)]) }
    $antes = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try { $saida = @(& $exe @pre --version 2>&1 | ForEach-Object { "$_" }); $codigo = $LASTEXITCODE } catch { $saida = @($_.Exception.Message); $codigo = -1 } finally { $ErrorActionPreference = $antes }
    [pscustomobject]@{ Ok = ($codigo -eq 0); Texto = $(if ($saida.Count) { $saida[0] } else { '' }) }
}

# Devolve Comando (lista para chamar: o claude.exe, ou node e o cli.js das versões antigas do npm), Versao, De e, se nenhum executou, Erro.
function Get-ClaudeEstado {
    $erros = @(); $vistos = @{}
    foreach ($c in @(Get-ClaudeCandidatos)) {
        if (-not $c -or $vistos[$c.ToLower()]) { continue }
        $vistos[$c.ToLower()] = $true
        if (-not (Test-Path -LiteralPath $c)) { continue }
        $cmd = @(if ($c -match '\.(cmd|bat)$') { Get-ClaudeReal $c } else { $c })  # @(...) em volta: um só item não pode virar texto (cmd[0] seria a primeira letra)
        if (-not $cmd.Count) { $erros += "${c}: não achei o programa que ele chama"; continue }
        $t = Test-ClaudeComando $cmd
        if ($t.Ok) { return [pscustomobject]@{ Ok = $true; Comando = @($cmd); Versao = $t.Texto; De = $c; Erro = '' } }
        $erros += "${c}: $($t.Texto)"
    }
    [pscustomobject]@{ Ok = $false; Comando = @(); Versao = ''; De = ''; Erro = ($erros -join '; ') }
}

function Get-ClaudeComando { return @((Get-ClaudeEstado).Comando) }

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
