# Roteador da agenda: diz em que nível a mudança mexe (1 dia, 2 semana, 3 horizonte), onde a tarefa cabe e o que o guardião precisa ler.
# Rodar ANTES de encaixar tarefa nova ou mudar uma tarefa de dia. Sem Claude, sem rede: só conta com os planos, o resumo do ClickUp e as campanhas.
# Uso: powershell -ExecutionPolicy Bypass -File onde_cabe.ps1 -Minutos 90 [-Tipo pesado|design|leve|auto] [-Prazo AAAA-MM-DD] [-Frente Agência] [-Titulo "..."] [-DependeDias 0] [-Estender 2026-10-16=21:30]
param(
    [Parameter(Mandatory = $true)][int]$Minutos,
    [string]$Tipo = 'auto',
    [string]$Prazo = '',
    [string]$Frente = '',
    [string]$Titulo = '',
    [int]$DependeDias = 0,
    [string[]]$Estender = @()
)
$python = Join-Path $PSScriptRoot 'voz\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }
$argumentos = @((Join-Path $PSScriptRoot 'voz\rota_agenda.py'), '--minutos', $Minutos, '--tipo', $Tipo, '--depende-dias', $DependeDias)
if ($Prazo) { $argumentos += @('--prazo', $Prazo) }
if ($Frente) { $argumentos += @('--frente', $Frente) }
if ($Titulo) { $argumentos += @('--titulo', $Titulo) }
foreach ($e in ($Estender | ForEach-Object { $_ -split ',' } | Where-Object { $_ })) { $argumentos += @('--estender', $e.Trim()) }
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = 'utf-8'
& $python @argumentos
