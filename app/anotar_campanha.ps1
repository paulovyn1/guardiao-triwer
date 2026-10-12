# Acrescenta UMA linha na "7. Caixa de entrada" de uma campanha, sem precisar ler a nota.
# Qualquer conversa ou agente pode usar. Só o guardião reorganiza as outras seções.
# Uso: powershell -ExecutionPolicy Bypass -File anotar_campanha.ps1 -Slug lancamento-x -Fonte "conversa X" -Texto "descobri que ..."
param(
    [Parameter(Mandatory = $true)][string]$Slug,
    [Parameter(Mandatory = $true)][string]$Fonte,
    [Parameter(Mandatory = $true)][string]$Texto
)
$utf8 = New-Object System.Text.UTF8Encoding($false)
. (Join-Path $PSScriptRoot '_comum.ps1')
$memoria = Get-PastaMemoria (Get-Config)
$arq = Join-Path $memoria "campanhas\$Slug.md"
if (-not (Test-Path $arq)) { Write-Output "Campanha nao encontrada: $Slug"; exit 1 }
$linhas = New-Object System.Collections.Generic.List[string]
$linhas.AddRange([System.IO.File]::ReadAllLines($arq, $utf8))

$ini = -1
for ($k = 0; $k -lt $linhas.Count; $k++) { if ($linhas[$k] -match '^## 7\.') { $ini = $k; break } }
if ($ini -lt 0) { Write-Output "A nota nao tem a secao 7 (Caixa de entrada)."; exit 1 }
$fim = $linhas.Count
for ($k = $ini + 1; $k -lt $linhas.Count; $k++) { if ($linhas[$k] -match '^## ') { $fim = $k; break } }

# Remove o marcador "(vazia)" na primeira anotação
for ($k = $fim - 1; $k -gt $ini; $k--) { if ($linhas[$k].Trim() -eq '_(vazia)_') { $linhas.RemoveAt($k); $fim-- } }
# Insere depois da última linha de conteúdo da seção (antes das linhas em branco finais)
$pos = $fim
while ($pos -gt $ini + 1 -and $linhas[$pos - 1].Trim() -eq '') { $pos-- }
$limpo = ($Texto -replace '[\r\n]+', ' ').Trim()
$linhas.Insert($pos, ('- ' + (Get-Date -Format 'yyyy-MM-dd') + ' | ' + $Fonte + ' | ' + $limpo))
[System.IO.File]::WriteAllLines($arq, $linhas, $utf8)
Write-Output "Anotado em $Slug (secao 7)."
