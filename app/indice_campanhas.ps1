# Regenera a tabela do índice `campanhas.md` a partir do cabeçalho (frontmatter) de cada nota em campanhas\.
# O índice NUNCA é escrito à mão: assim ele não desatualiza. Também aponta revisão atrasada e caixa de entrada cheia.
# Uso: powershell -ExecutionPolicy Bypass -File indice_campanhas.ps1
$utf8 = New-Object System.Text.UTF8Encoding($false)
. (Join-Path $PSScriptRoot '_comum.ps1')
$cfg = Get-Config
$memoria = Get-PastaMemoria $cfg
$pastaNome = Split-Path $memoria -Leaf
$pasta = $memoria
$indice = Join-Path $pasta 'campanhas.md'
$hoje = (Get-Date).Date
$rank = @{ critica = 0; alta = 1; media = 2; baixa = 3 }

function LerCabecalho($arquivo) {
    $linhas = [System.IO.File]::ReadAllLines($arquivo, $utf8)
    $h = @{}; $dentro = $false
    foreach ($l in $linhas) {
        if ($l.Trim() -eq '---') { if ($dentro) { break } else { $dentro = $true; continue } }
        if ($dentro -and $l -match '^([a-z_]+):\s*(.*)$') { $h[$Matches[1]] = $Matches[2].Trim() }
    }
    # Conta anotações pendentes na caixa de entrada (linhas "- AAAA-...")
    $ini = -1
    for ($k = 0; $k -lt $linhas.Count; $k++) { if ($linhas[$k] -match '^## 7\.') { $ini = $k; break } }
    $pend = 0
    if ($ini -ge 0) { for ($k = $ini + 1; $k -lt $linhas.Count; $k++) { if ($linhas[$k] -match '^## ') { break }; if ($linhas[$k] -match '^- \d{4}-\d{2}-\d{2}') { $pend++ } } }
    $h['pendentes'] = $pend
    return $h
}
function Dm($s) { try { return ([datetime]::ParseExact($s, 'yyyy-MM-dd', $null)).ToString('dd/MM') } catch { return $s } }

$notas = Get-ChildItem (Join-Path $pasta 'campanhas') -Filter '*.md' | Where-Object { $_.Name -notlike '_*' }
$linhasTabela = @()
$registros = foreach ($n in $notas) {
    $h = LerCabecalho $n.FullName
    $h['arquivo'] = $n.Name
    [pscustomobject]$h
}
$ordenadas = $registros | Sort-Object @{ Expression = { if ($rank.ContainsKey($_.importancia)) { $rank[$_.importancia] } else { 9 } } }, data_inicio

$linhasTabela += '| Campanha | Tipo | Datas | Status | Importância | Abrir quando | Revisão | Nota |'
$linhasTabela += '|---|---|---|---|---|---|---|---|'
foreach ($r in $ordenadas) {
    $nome = $r.nome
    if ($r.sigilo) { $nome += " 🔒 segredo até $(Dm $r.sigilo)" }
    $datas = if ($r.data_inicio -eq $r.data_fim) { Dm $r.data_inicio } else { "$(Dm $r.data_inicio) a $(Dm $r.data_fim)" }
    $rev = $r.revisado_em
    try {
        $dias = ($hoje - [datetime]::ParseExact($r.revisado_em, 'yyyy-MM-dd', $null)).Days
        if ($r.status -ne 'encerrada' -and $dias -gt 7) { $rev = "⚠ atrasada ($dias dias)" } else { $rev = (Dm $r.revisado_em) }
    } catch { $rev = '⚠ sem data' }
    if ($r.pendentes -gt 0) { $rev += " · $($r.pendentes) na caixa de entrada" }
    $slugNota = $r.arquivo.Replace('.md', '')
    $link = if ($cfg.pastas.memoria_em_obsidian) { "[[$pastaNome/campanhas/$slugNota\|$slugNota]]" } else { "[$slugNota](campanhas/$slugNota.md)" }
    $linhasTabela += "| $nome | $($r.tipo) | $datas | $($r.status) | $($r.importancia) | $($r.abrir_quando) | $rev | $link |"
}
$bloco = "<!-- INDICE:INICIO (gerado por indice_campanhas.ps1, nao editar) -->`n" + ($linhasTabela -join "`n") + "`n<!-- INDICE:FIM -->"

$texto = [System.IO.File]::ReadAllText($indice, $utf8)
if ($texto -notmatch '(?s)<!-- INDICE:INICIO.*?<!-- INDICE:FIM -->') { Write-Output "Marcadores INDICE:INICIO/FIM nao encontrados em campanhas.md"; exit 1 }
$texto = [regex]::Replace($texto, '(?s)<!-- INDICE:INICIO.*?<!-- INDICE:FIM -->', { param($m) $bloco })
[System.IO.File]::WriteAllText($indice, $texto, $utf8)
Write-Output "Indice regenerado: $(@($ordenadas).Count) campanhas."
