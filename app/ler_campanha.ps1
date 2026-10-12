# Lê SÓ as seções pedidas de uma nota de campanha (economiza token: a nota inteira não entra na conversa).
# Padrão: cabeçalho + 1 Ficha + 2 Estado agora + 7 Caixa de entrada.
# Uso: powershell -ExecutionPolicy Bypass -File ler_campanha.ps1 -Slug lancamento-x [-Secao ficha,estado,tarefas,decisoes,ativos,resultado,entrada,historico | tudo]
param(
    [Parameter(Mandatory = $true)][string]$Slug,
    [string[]]$Secao = @('ficha', 'estado', 'entrada')
)
$utf8 = New-Object System.Text.UTF8Encoding($false)
. (Join-Path $PSScriptRoot '_comum.ps1')
$memoria = Get-PastaMemoria (Get-Config)
$arq = Join-Path $memoria "campanhas\$Slug.md"
if (-not (Test-Path $arq)) { Write-Output "Campanha nao encontrada: $Slug. Existentes: $((Get-ChildItem (Join-Path $memoria 'campanhas') -Filter '*.md' | ? { $_.Name -notlike '_*' } | % { $_.BaseName }) -join ', ')"; exit 1 }
$linhas = [System.IO.File]::ReadAllLines($arq, $utf8)
$Secao = @($Secao | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })   # aceita "a,b" e "a","b"
if ($Secao -contains 'tudo') { $linhas; exit }

$numero = @{ ficha = '1'; estado = '2'; tarefas = '3'; decisoes = '4'; ativos = '5'; resultado = '6'; entrada = '7'; historico = '8' }
$saida = New-Object System.Collections.Generic.List[string]

# Cabeçalho compacto em UMA linha: só o que o guardião precisa para decidir se continua lendo.
$h = @{}; $dentro = $false
foreach ($l in $linhas) {
    if ($l.Trim() -eq '---') { if ($dentro) { break } else { $dentro = $true; continue } }
    if ($dentro -and $l -match '^([a-z_]+):\s*(.*)$') { $h[$Matches[1]] = $Matches[2].Trim() }
}
$sig = if ($h['sigilo']) { " | SEGREDO ate $($h['sigilo'])" } else { '' }
$saida.Add("# $($h['nome']) | $($h['tipo']) | $($h['data_inicio']) a $($h['data_fim']) | status: $($h['status']) | importancia: $($h['importancia']) | revisado em $($h['revisado_em'])$sig")

foreach ($s in $Secao) {
    $n = $numero[$s.ToLower()]
    if (-not $n) { $saida.Add("[secao desconhecida: $s]"); continue }
    $ini = -1
    for ($k = 0; $k -lt $linhas.Count; $k++) { if ($linhas[$k] -match ('^## ' + $n + '\.')) { $ini = $k; break } }
    if ($ini -lt 0) { $saida.Add("[secao $n ausente na nota]"); continue }
    $saida.Add('')
    for ($k = $ini; $k -lt $linhas.Count; $k++) {
        if ($k -gt $ini -and $linhas[$k] -match '^## ') { break }
        $saida.Add($linhas[$k])
    }
}
$saida
