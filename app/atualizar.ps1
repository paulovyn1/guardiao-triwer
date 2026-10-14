# Atualiza o guardião a partir do repositório: skill, scripts desta pasta, programa de voz e painel.
# NÃO toca em: config.json, memória, planos, registros, logs, calibragem, tempos.json, preferências, pronúncias,
# modelos de voz, ambiente do Python nem nos arquivos pessoais da skill (memoria.md e extensões).
# Antes de copiar, guarda um zip do código atual em logs\ (ficam os 3 últimos).
#
# Uso: powershell -ExecutionPolicy Bypass -File atualizar.ps1 [-Origem <pasta do clone, pasta simples ou endereço do GitHub>] [-Ramo main]
#        [-Local]        usa o clone como está, sem baixar nada (para quem desenvolve o guardião)
#        [-Forcar]       copia mesmo se a versão for a mesma
#        [-SemReiniciar] não desliga nem religa o programa de voz
#        [-SoVerificar]  só mostra a versão instalada e a publicada
param(
    [string]$Origem = "",
    [string]$Ramo = "",
    [switch]$Local,
    [switch]$Forcar,
    [switch]$SemReiniciar,
    [switch]$SoVerificar
)
$oper = $PSScriptRoot
$utf8 = New-Object System.Text.UTF8Encoding($false)
$logs = Join-Path $oper 'logs'
if (-not (Test-Path $logs)) { New-Item -ItemType Directory -Path $logs | Out-Null }
$arqResultado = Join-Path $logs 'atualizacao_resultado.json'
$arqLog = Join-Path $logs 'atualizacoes.log'

function Anotar([string]$texto) {
    Write-Output $texto
    [System.IO.File]::AppendAllText($arqLog, "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $texto`r`n", $utf8)
}
function Ler-Versao([string]$pasta) {
    $arq = Join-Path $pasta 'VERSION'
    if (Test-Path $arq) { return ([System.IO.File]::ReadAllText($arq, $utf8)).Trim().TrimStart([char]0xFEFF) }
    return '0.0.0'
}
function Gravar-Resultado([string]$resultado, [string]$mensagem, [string]$de, [string]$para) {
    $obj = [ordered]@{ resultado = $resultado; mensagem = $mensagem; de = $de; para = $para; quando = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') }
    [System.IO.File]::WriteAllText($arqResultado, ($obj | ConvertTo-Json), $utf8)
}
function Git-Rodar([string[]]$a) {
    # o git escreve avisos na saída de erro; isso não pode derrubar o script
    $ErrorActionPreference = 'Continue'
    $env:GIT_TERMINAL_PROMPT = '0'
    $saida = & git @a 2>&1 | ForEach-Object { "$_" }
    return [pscustomobject]@{ codigo = $LASTEXITCODE; saida = ($saida -join "`n") }
}
function Robo([string]$de, [string]$para, [string[]]$semPastas, [string[]]$semArquivos) {
    $a = @($de, $para, '/E', '/R:2', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS', '/NP')
    if ($semPastas) { $a += '/XD'; $a += $semPastas }
    if ($semArquivos) { $a += '/XF'; $a += $semArquivos }
    & robocopy @a | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "a cópia de $de para $para falhou (robocopy $LASTEXITCODE)" }
}

$instalada = Ler-Versao $oper
$temp = $null
$estavaLigado = $false
$voz = Join-Path $oper 'voz'
try {
    # ---- de onde vem a versão nova ----
    $cfg = $null
    $arqCfg = Join-Path $oper 'config.json'
    if (Test-Path $arqCfg) { $cfg = [System.IO.File]::ReadAllText($arqCfg, $utf8) | ConvertFrom-Json }
    $at = if ($cfg -and $cfg.PSObject.Properties['atualizacao']) { $cfg.atualizacao } else { $null }
    if (-not $Origem -and $at -and $at.origem) { $Origem = [string]$at.origem }
    if (-not $Ramo) { $Ramo = if ($at -and $at.ramo) { [string]$at.ramo } else { 'main' } }
    $subpasta = if ($at -and $at.PSObject.Properties['pasta']) { [string]$at.pasta } else { 'guardiao-triwer' }
    $skillLocal = Join-Path $oper '.claude\skills\guardiao-triwer'
    $skillGlobal = Join-Path $env:USERPROFILE '.claude\skills\guardiao-triwer'
    foreach ($p in @($skillLocal, $skillGlobal)) {  # instalada a partir de um clone: o instalador deixa o caminho dele em .repo-path
        $marcador = Join-Path $p '.repo-path'
        if (-not $Origem -and (Test-Path $marcador)) { $Origem = ([System.IO.File]::ReadAllText($marcador, $utf8)).Trim() }
    }
    foreach ($p in @($skillLocal, $skillGlobal)) {  # endereço publicado junto com a skill
        $arqOrigem = Join-Path $p 'origem.json'
        if (-not $Origem -and (Test-Path $arqOrigem)) {
            $o = [System.IO.File]::ReadAllText($arqOrigem, $utf8) | ConvertFrom-Json
            if ($o.origem) { $Origem = [string]$o.origem; if ($o.ramo) { $Ramo = [string]$o.ramo }; $subpasta = [string]$o.pasta }
        }
    }
    if (-not $Origem) { throw 'A origem das atualizações não está configurada. Preencha o campo "atualizacao": {"origem": ...} do config.json.' }
    # origem local em que o guardião está na raiz (clone do repositório público): a subpasta não existe, vale a raiz
    $naRede = $Origem -match '^https?://'  # endereço do GitHub: não é pasta, e Join-Path com ele dá erro
    if (-not $naRede -and $subpasta -and (Test-Path $Origem) -and -not (Test-Path (Join-Path $Origem "$subpasta\VERSION")) -and (Test-Path (Join-Path $Origem 'VERSION'))) { $subpasta = '' }

    if (-not $naRede -and (Test-Path (Join-Path $Origem '.git'))) {
        if (-not $Local -and -not $SoVerificar) {
            $alvo = if ($subpasta) { $subpasta } else { '.' }
            $sujo = Git-Rodar @('-C', $Origem, 'status', '--porcelain', '--', $alvo)
            if ($sujo.saida.Trim()) { throw "O clone em $Origem tem mudanças ainda não publicadas em $alvo. Publique essas mudanças ou rode com -Local." }
            $puxar = Git-Rodar @('-C', $Origem, 'pull', '--ff-only', '--quiet', 'origin', $Ramo)
            if ($puxar.codigo -ne 0) { throw "Não consegui baixar a versão nova (git pull): $($puxar.saida)" }
        } elseif ($SoVerificar) {
            $null = Git-Rodar @('-C', $Origem, 'fetch', '--quiet', 'origin', $Ramo)
        }
        $fonte = if ($subpasta) { Join-Path $Origem $subpasta } else { $Origem }
    } elseif ($naRede) {
        if ($Origem -notmatch '^https://github\.com/([\w.-]+)/([\w.-]+?)(\.git)?/?$') { throw "A origem das atualizações ($Origem) não é um endereço de repositório do GitHub." }
        $dono = $Matches[1]; $repo = $Matches[2]
        $temp = Join-Path $env:TEMP ("guardiao_atualizacao_" + [guid]::NewGuid().ToString('N').Substring(0, 8))
        New-Item -ItemType Directory -Path $temp | Out-Null
        $zip = Join-Path $temp 'repo.zip'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest "https://codeload.github.com/$dono/$repo/zip/refs/heads/$Ramo" -OutFile $zip -UseBasicParsing -ErrorAction Stop
        Expand-Archive -Path $zip -DestinationPath $temp -Force -ErrorAction Stop
        $raiz = (Get-ChildItem $temp -Directory | Select-Object -First 1).FullName
        $fonte = if ($subpasta) { Join-Path $raiz $subpasta } else { $raiz }
        if (-not (Test-Path (Join-Path $fonte 'VERSION')) -and (Test-Path (Join-Path $raiz 'VERSION'))) { $fonte = $raiz }  # guardião na raiz do repositório (o público)
    } else {
        $fonte = if ($subpasta -and (Test-Path (Join-Path $Origem $subpasta))) { Join-Path $Origem $subpasta } else { $Origem }
    }
    if (-not (Test-Path (Join-Path $fonte 'VERSION'))) { throw "Não achei o guardião em $fonte (falta o arquivo VERSION)." }
    $nova = Ler-Versao $fonte

    if ($SoVerificar) {
        Write-Output "Instalada: $instalada"
        Write-Output "Na origem: $nova"
        exit 0
    }
    if ($nova -eq $instalada -and -not $Forcar) {
        Anotar "Já está na versão $instalada. Nada a fazer."
        Gravar-Resultado 'ok' "Já está na versão $instalada." $instalada $nova
        exit 0
    }
    Anotar "Atualizando de $instalada para $nova (origem: $Origem)"

    # ---- cópia de segurança do código atual ----
    $itens = @()
    $itens += Get-ChildItem $oper -File | Where-Object { $_.Extension -in '.ps1', '.bat', '.html', '.svg' -or $_.Name -eq 'VERSION' } | ForEach-Object { $_.FullName }
    if (Test-Path $voz) {
        $itens += Get-ChildItem $voz -File | Where-Object { $_.Extension -in '.py', '.ps1', '.bat', '.txt', '.ico' } | ForEach-Object { $_.FullName }
        foreach ($p in 'hud', 'hud2') { if (Test-Path (Join-Path $voz $p)) { $itens += (Join-Path $voz $p) } }
    }
    if ($itens.Count) {
        $bkp = Join-Path $logs ("codigo_antes_" + $instalada + "_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + ".zip")
        Compress-Archive -Path $itens -DestinationPath $bkp -Force -ErrorAction Stop
        Get-ChildItem $logs -Filter 'codigo_antes_*.zip' | Sort-Object LastWriteTime -Descending | Select-Object -Skip 3 | Remove-Item -Force -ErrorAction SilentlyContinue
    }

    # ---- desliga o programa de voz desta pasta (só o desta pasta) ----
    $venv = (Join-Path $voz '.venv').ToLower()
    $procs = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'guardiao_voz\.py' -and $_.ExecutablePath -and $_.ExecutablePath.ToLower().StartsWith($venv) })
    if ($procs.Count -and -not $SemReiniciar) {
        $estavaLigado = $true
        $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Milliseconds 1200
    }

    # ---- 1) scripts desta pasta (app\ do repositório). Dados da pessoa não são sobrescritos. ----
    $fonteApp = Join-Path $fonte 'app'
    if (Test-Path $fonteApp) {
        $guardar = @('config.json', 'tempos.json', 'plano_exemplo.json')
        foreach ($f in Get-ChildItem $fonteApp -File) {
            $dest = Join-Path $oper $f.Name
            if (($guardar -contains $f.Name) -and (Test-Path $dest)) { continue }
            if ($f.Name -eq 'atualizar.ps1' -and $f.FullName -eq $PSCommandPath) { continue }
            Copy-Item $f.FullName $dest -Force -ErrorAction Stop
        }
    }

    foreach ($velho in 'servidor_tela.ps1', 'tela_modelo.html', 'favicon.svg') {  # tela antiga, que saiu na 0.6.0
        Remove-Item (Join-Path $oper $velho) -Force -ErrorAction SilentlyContinue
    }

    # ---- 2) programa de voz e painel ----
    $fonteVoz = Join-Path $fonte 'voz'
    if ((Test-Path $fonteVoz) -and (Test-Path $voz)) {
        Robo $fonteVoz $voz @('.venv', 'modelo', 'kokoro', 'perfil_edge', '__pycache__', 'capturas', 'amostras') @('preferencias.json', 'pronuncias.json', '*.pyc')
        $pron = Join-Path $voz 'pronuncias.json'
        $pronEx = Join-Path $voz 'pronuncias.exemplo.json'
        if (-not (Test-Path $pron) -and (Test-Path $pronEx)) { Copy-Item $pronEx $pron }
        $req = Join-Path $voz 'requirements.txt'
        $py = Join-Path $voz '.venv\Scripts\python.exe'
        if ((Test-Path $req) -and (Test-Path $py)) {
            $marca = Join-Path $voz '.venv\requirements.hash'
            $hash = (Get-FileHash $req -Algorithm SHA256).Hash
            $anterior = if (Test-Path $marca) { (Get-Content $marca -Raw).Trim() } else { '' }
            if ($hash -ne $anterior) {
                Anotar 'Instalando as dependências novas do programa de voz...'
                & $py -m pip install -q --disable-pip-version-check -r $req 2>&1 | Out-Null
                if ($LASTEXITCODE -eq 0) { Set-Content -Path $marca -Value $hash -Encoding ascii } else { Anotar 'Aviso: o pip não terminou bem. Rode de novo com internet.' }
            }
        }
    } elseif (Test-Path $fonteVoz) {
        Anotar 'O programa de voz não está instalado nesta pasta: só a skill e os scripts foram atualizados.'
    }

    # ---- 3) skill instalada (uma ou mais pastas). memoria.md e extensões pessoais ficam. ----
    $pastasSkill = @()
    if (Test-Path $skillLocal) { $pastasSkill += $skillLocal }
    if (Test-Path $skillGlobal) { $pastasSkill += $skillGlobal }
    if ($at -and $at.PSObject.Properties['pastas_skill']) { foreach ($p in @($at.pastas_skill)) { if ($p -and (Test-Path $p)) { $pastasSkill += [string]$p } } }
    $feitas = @{}
    foreach ($p in $pastasSkill) {
        $item = Get-Item $p -Force
        $real = if ($item.LinkType -and $item.Target) { @($item.Target)[0] } else { $item.FullName }
        if ($feitas[$real.ToLower()]) { continue }
        $feitas[$real.ToLower()] = $true
        $semPastas = @('.git', 'node_modules', '__pycache__', '.venv', 'modelo', 'kokoro', 'perfil_edge', 'capturas', 'amostras')
        if (-not (Test-Path (Join-Path $real 'voz'))) { $semPastas += 'voz' }  # a cópia do programa só acompanha a skill onde o instalador a deixou
        Robo $fonte $real $semPastas @('memoria.md', 'NOTAS-PARA-INSTALADOR.md', 'HISTORICO-DETALHADO.md', '.repo-path', 'extensoes-*.md', '*.pyc', 'preferencias.json', 'pronuncias.json')
        foreach ($velho in 'app\servidor_tela.ps1', 'app\tela_modelo.html') { Remove-Item (Join-Path $real $velho) -Force -ErrorAction SilentlyContinue }
    }

    Copy-Item (Join-Path $fonte 'VERSION') (Join-Path $oper 'VERSION') -Force -ErrorAction Stop
    Anotar "Pronto: versão $nova instalada."
    Gravar-Resultado 'ok' "Versão $nova instalada." $instalada $nova
    $codigo = 0
} catch {
    Anotar "ERRO: $($_.Exception.Message)"
    Gravar-Resultado 'erro' $_.Exception.Message $instalada ''
    $codigo = 1
} finally {
    if ($temp -and (Test-Path $temp)) { Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue }
    if ($estavaLigado) {
        Start-Process -FilePath (Join-Path $voz '.venv\Scripts\pythonw.exe') -ArgumentList 'guardiao_voz.py', '--cerebro', '--sem-janela' -WorkingDirectory $voz -WindowStyle Hidden
    }
}
exit $codigo
