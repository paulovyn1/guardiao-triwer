# Instala (ou conserta) o painel e a voz do guardião na pasta operacional. Não pergunta nada e pode ser rodado quantas vezes for
# preciso: o que já está pronto é pulado, um download interrompido continua de onde parou.
# Não precisa de administrador nem de Python instalado: o ambiente do Python é baixado para dentro da pasta voz\.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File instalar_painel.ps1                 instala na pasta padrão (%USERPROFILE%\Guardiao-do-dia)
#   powershell -ExecutionPolicy Bypass -File instalar_painel.ps1 -Pasta <pasta>  instala em outra pasta operacional
#   powershell -ExecutionPolicy Bypass -File instalar_painel.ps1 -Verificar      só diz o que está pronto e o que falta (chave=valor)
#   -SemAtalho    não cria o atalho na área de trabalho
#   -Quieto       sem barra de progresso nos downloads (para rodar em segundo plano)
param(
    [string]$Pasta = "",
    [switch]$Verificar,
    [switch]$SemAtalho,
    [switch]$Quieto,
    [string]$VersaoPython = "3.14",
    [string]$FormatoDoDisco = ""  # só para teste: finge o formato do disco da pasta (NTFS, FAT32, exFAT)
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$raizSkill = Split-Path -Parent $PSScriptRoot
$utf8 = New-Object System.Text.UTF8Encoding($false)
$utf8bom = New-Object System.Text.UTF8Encoding($true)
$arqMemoriaSkill = Join-Path $raizSkill 'memoria.md'
. (Join-Path $raizSkill 'app\_comum.ps1')
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }  # o Python do guardião escreve em UTF-8

# O que é baixado. Tamanho e SHA256 conferem o arquivo antes de ele ser usado.
$VOSK = @{ url = 'https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip'; tamanho = 32453112; nome = 'o modelo de escuta (31 MB)' }
$KOKORO = @(
    @{ arquivo = 'kokoro-v1.0.int8.onnx'; tamanho = 92361271; sha = '6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb'; nome = 'a voz do guardião (88 MB)'
       url = 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx' },
    @{ arquivo = 'voices-v1.0.bin'; tamanho = 28214398; sha = 'bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d'; nome = 'os timbres da voz (27 MB)'
       url = 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin' }
)
$UV_URL = 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip'
$BIBLIOTECAS = 'import vosk, sounddevice, numpy, requests, edge_tts, kokoro_onnx, onnxruntime, num2words'

if (-not $Pasta) {
    if (Test-Path $arqMemoriaSkill) {
        $m = [regex]::Match([System.IO.File]::ReadAllText($arqMemoriaSkill, $utf8), '(?m)^pasta_operacional:\s*(.+)$')
        if ($m.Success) { $Pasta = $m.Groups[1].Value.Trim() }
    }
    if (-not $Pasta) { $Pasta = Join-Path $env:USERPROFILE 'Guardiao-do-dia' }
}
$op = $Pasta
$voz = Join-Path $op 'voz'
$venvPy = Join-Path $voz '.venv\Scripts\python.exe'

# O uv instala o Python criando links (uma junção para a versão menor). FAT32 e exFAT (pendrive, HD externo antigo) e pasta de rede não criam links:
# o uv falha com "Failed to create Python minor version link directory". Nesse caso o Python do guardião vai para %LOCALAPPDATA%\GuardiaoDoDia, que é NTFS.
function Disco-Aceita-Links([string]$pasta, [string]$formato = '') {
    if ($formato) { return ($formato -in @('NTFS', 'ReFS')) }  # (o teste passa o formato do disco)
    try { $raiz = [System.IO.Path]::GetPathRoot([System.IO.Path]::GetFullPath($pasta)) } catch { return $true }
    if (-not $raiz -or $raiz.StartsWith('\\')) { return $false }  # pasta de rede
    try { return ((New-Object System.IO.DriveInfo($raiz)).DriveFormat -in @('NTFS', 'ReFS')) } catch { return $true }  # sem saber, tenta do jeito normal
}

function Rodar([string]$exe, [string[]]$argumentos) {
    # programa de fora: os avisos dele saem na saída de erro e não podem derrubar o script
    $antes = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $exe @argumentos 2>&1 | ForEach-Object { "$_" } | Where-Object { $_ } | ForEach-Object { Write-Host "      $_" } } finally { $ErrorActionPreference = $antes }
    return $LASTEXITCODE
}
function Bibliotecas-Ok {
    if (-not (Test-Path $venvPy)) { return $false }
    $antes = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $saida = & $venvPy -c "$BIBLIOTECAS; print('ok')" 2>$null } finally { $ErrorActionPreference = $antes }
    return ("$saida".Trim() -eq 'ok')
}
function Vosk-Ok { (Test-Path (Join-Path $voz 'modelo\final.mdl')) -and (Test-Path (Join-Path $voz 'modelo\Gr.fst')) -and (Test-Path (Join-Path $voz 'modelo\ivector\final.ie')) }
function Arquivo-Ok([string]$arq, [long]$tamanho, [string]$sha) {
    if (-not (Test-Path $arq)) { return $false }
    if ((Get-Item $arq).Length -ne $tamanho) { return $false }
    if ($sha -and ((Get-FileHash $arq -Algorithm SHA256).Hash.ToLower() -ne $sha)) { return $false }
    return $true
}
function Kokoro-Ok {
    foreach ($k in $KOKORO) { $a = Join-Path $voz "kokoro\$($k.arquivo)"; if (-not (Test-Path $a) -or (Get-Item $a).Length -ne $k.tamanho) { return $false } }
    return $true
}
function Programa-Ok { (Test-Path (Join-Path $voz 'guardiao_voz.py')) -and (Test-Path (Join-Path $voz 'hud2\index.html')) -and (Test-Path (Join-Path $op 'ler_clickup.ps1')) }
function Variavel-Usuario([string]$nome) { [bool][Environment]::GetEnvironmentVariable($nome, 'User') }
# 'ok' = o Claude Code foi achado E executa (claude --version); 'nao_executa' = achado, mas não roda; 'falta' = não achado
function Estado-Claude {
    $e = Get-ClaudeEstado
    if ($e.Ok) { return 'ok' }
    if ($e.Erro) { return 'nao_executa' }
    return 'falta'
}
function Tem-Claude { (Estado-Claude) -eq 'ok' }

# ---------------------------------------------------------------------------------------------------------------
if ($Verificar) {
    $r = [ordered]@{
        pasta_operacional = $op
        programa          = $(if (Programa-Ok) { 'ok' } else { 'falta' })
        python            = $(if (Bibliotecas-Ok) { 'ok' } else { 'falta' })
        modelo_escuta     = $(if (Vosk-Ok) { 'ok' } else { 'falta' })
        voz               = $(if (Kokoro-Ok) { 'ok' } else { 'falta' })
        chave_groq        = $(if (Variavel-Usuario 'GROQ_API_KEY') { 'ok' } else { 'falta' })
        token_clickup     = $(if (Variavel-Usuario 'CLICKUP_API_TOKEN') { 'ok' } else { 'falta' })
        claude            = (Estado-Claude)
        config            = $(if (Test-Path (Join-Path $op 'config.json')) { 'ok' } else { 'falta' })
    }
    $r.painel_instalado = $(if ($r.programa -eq 'ok' -and $r.python -eq 'ok' -and $r.modelo_escuta -eq 'ok' -and $r.voz -eq 'ok') { 'sim' } else { 'nao' })
    foreach ($k in $r.Keys) { Write-Output "$k=$($r[$k])" }
    exit 0
}

# ---------------------------------------------------------------------------------------------------------------
function Passo([int]$n, [string]$texto) { Write-Host ""; Write-Host "[$n/6] $texto" -ForegroundColor Cyan }
function Feito([string]$texto) { Write-Host "      $texto" -ForegroundColor Green }

function Baixar([string]$url, [string]$destino, [long]$tamanho, [string]$sha, [string]$nome) {
    if (Arquivo-Ok $destino $tamanho $sha) { return }
    $parcial = "$destino.parte"
    $curl = Join-Path $env:SystemRoot 'System32\curl.exe'
    Write-Host "      Baixando $nome..."
    for ($t = 1; $t -le 3; $t++) {
        if ((Test-Path $parcial) -and (Get-Item $parcial).Length -gt $tamanho) { Remove-Item $parcial -Force }
        if (-not ((Test-Path $parcial) -and (Get-Item $parcial).Length -eq $tamanho)) {
            if (Test-Path $curl) {
                $a = @('-L', '--fail', '--retry', '3', '--retry-delay', '2', '-C', '-', '-o', $parcial, $url)
                if ($Quieto -or [Console]::IsOutputRedirected) { $a = @('-sS') + $a } else { $a = @('-#') + $a }
                $antes = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
                try { & $curl @a } finally { $ErrorActionPreference = $antes }
            } else {
                try { Invoke-WebRequest $url -OutFile $parcial -UseBasicParsing } catch { Write-Host "      (tentativa $t falhou: $($_.Exception.Message))" }
            }
        }
        if (Arquivo-Ok $parcial $tamanho $sha) { Move-Item $parcial $destino -Force; return }
        if ((Test-Path $parcial) -and (Get-Item $parcial).Length -ge $tamanho) { Remove-Item $parcial -Force }  # veio inteiro e não confere: começa de novo
        Start-Sleep -Seconds 2
    }
    throw "Não consegui baixar $nome. Confira a internet e rode o instalador de novo: ele continua de onde parou."
}

if (-not (Test-Path (Join-Path $raizSkill 'voz\guardiao_voz.py'))) {
    throw "Esta cópia da skill não traz a pasta voz\ (o programa do painel). Rode o instalar.bat da pasta do guardião que você baixou."
}
if (-not [Environment]::Is64BitOperatingSystem) { throw "O painel do guardião precisa do Windows de 64 bits." }

# ---- 1) arquivos do programa ----
Passo 1 "Copiando o programa do guardião para $op"
foreach ($d in @($op, $voz, (Join-Path $op 'logs'), (Join-Path $op 'registros'), (Join-Path $op 'planos'))) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}
foreach ($f in Get-ChildItem (Join-Path $raizSkill 'app') -File) {
    if ($f.Name -eq 'config.exemplo.json') { continue }
    if ($f.Name -in @('tempos.json', 'plano_exemplo.json') -and (Test-Path (Join-Path $op $f.Name))) { continue }  # dados da pessoa nunca são sobrescritos
    Copy-Item $f.FullName (Join-Path $op $f.Name) -Force
}
$a = @((Join-Path $raizSkill 'voz'), $voz, '/E', '/R:2', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS', '/NP',
       '/XD', '.venv', 'modelo', 'kokoro', 'perfil_edge', '__pycache__', 'capturas', 'amostras', '.ferramentas',
       '/XF', 'preferencias.json', 'pronuncias.json', '*.pyc')
& robocopy @a | Out-Null
if ($LASTEXITCODE -ge 8) { throw "A cópia do programa para $voz falhou (robocopy $LASTEXITCODE)." }
$pron = Join-Path $voz 'pronuncias.json'
if (-not (Test-Path $pron)) { Copy-Item (Join-Path $voz 'pronuncias.exemplo.json') $pron }
Copy-Item (Join-Path $raizSkill 'VERSION') (Join-Path $op 'VERSION') -Force
# arquivo baixado da internet vem marcado como "de fora": tira a marca para o Windows não perguntar a cada abertura
Get-ChildItem $op -Recurse -File -Include *.ps1, *.bat, *.py -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notlike '*\.venv\*' } | Unblock-File -ErrorAction SilentlyContinue
# .ps1 precisa de UTF-8 com BOM para o Windows PowerShell 5.1 ler os acentos
foreach ($f in @(Get-ChildItem $op -Filter '*.ps1') + @(Get-ChildItem $voz -Filter '*.ps1')) {
    $bytes = [System.IO.File]::ReadAllBytes($f.FullName)
    if (-not ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)) {
        [System.IO.File]::WriteAllText($f.FullName, [System.IO.File]::ReadAllText($f.FullName, $utf8), $utf8bom)
    }
}
Feito "Programa na versão $(([System.IO.File]::ReadAllText((Join-Path $op 'VERSION'), $utf8)).Trim())."

# ---- 2) Python e bibliotecas, dentro da pasta voz\ ----
Passo 2 "Preparando o Python do guardião (não mexe em nada do seu computador fora desta pasta)"
if (Bibliotecas-Ok) {
    Feito "Já estava pronto."
} else {
    $req = Join-Path $voz 'requirements.txt'
    $pronto = $false
    # o ambiente existe e só falta alguma biblioteca (versão nova pediu mais uma): completa, sem refazer tudo
    if (Test-Path $venvPy) {
        Write-Host "      Completando as bibliotecas do ambiente que já existe..."
        $c = Rodar $venvPy @('-m', 'pip', 'install', '-q', '--disable-pip-version-check', '-r', $req)
        $pronto = ($c -eq 0) -and (Bibliotecas-Ok)
    }
    # a) uv: baixa sozinho o Python certo. Usa o do computador, se houver; senão baixa uma cópia para voz\.ferramentas.
    #    O Python que ele baixa também fica em voz\.ferramentas: nada vai para outras pastas do usuário.
    $ferr = Join-Path $voz '.ferramentas'
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $ferr 'python'
    $env:UV_CACHE_DIR = Join-Path $ferr 'cache'
    if (-not (Disco-Aceita-Links $voz $FormatoDoDisco)) {
        $env:UV_PYTHON_INSTALL_DIR = Join-Path $env:LOCALAPPDATA 'GuardiaoDoDia\python'
        $env:UV_LINK_MODE = 'copy'  # sem links, o uv copia os arquivos das bibliotecas em vez de ligá-los ao cache
        Write-Host "      Esta pasta está num disco sem suporte a links (FAT32, exFAT ou rede). O Python do guardião vai para $env:LOCALAPPDATA\GuardiaoDoDia; o resto fica aqui."
    }
    $uv = (Get-Command uv -ErrorAction SilentlyContinue | Select-Object -First 1).Source
    if (-not $pronto -and -not $uv) {
        $uv = Join-Path $ferr 'uv.exe'
        if (-not (Test-Path $uv)) {
            try {
                if (-not (Test-Path $ferr)) { New-Item -ItemType Directory -Path $ferr -Force | Out-Null }
                $zip = Join-Path $ferr 'uv.zip'
                Write-Host "      Baixando o instalador do Python (15 MB)..."
                Invoke-WebRequest $UV_URL -OutFile $zip -UseBasicParsing
                Expand-Archive -Path $zip -DestinationPath $ferr -Force
                Remove-Item $zip -Force
            } catch { Write-Host "      (não consegui baixar o instalador do Python: $($_.Exception.Message))"; $uv = $null }
        }
    }
    if (-not $pronto -and $uv -and (Test-Path $uv)) {
        Write-Host "      Criando o ambiente (Python $VersaoPython) e instalando as bibliotecas. Leva de 2 a 5 minutos..."
        if (Test-Path (Join-Path $voz '.venv')) { Remove-Item (Join-Path $voz '.venv') -Recurse -Force -ErrorAction SilentlyContinue }
        # só o Python baixado pelo uv: o ambiente não quebra se a pessoa mexer no Python dela
        $c = Rodar $uv @('venv', '--quiet', '--seed', '--python-preference', 'only-managed', '--python', $VersaoPython, (Join-Path $voz '.venv'))
        if ($c -eq 0) { $c = Rodar $uv @('pip', 'install', '--quiet', '--python', $venvPy, '-r', $req) }
        $pronto = ($c -eq 0) -and (Bibliotecas-Ok)
        Remove-Item (Join-Path $ferr 'cache') -Recurse -Force -ErrorAction SilentlyContinue  # só serve durante a instalação
    }
    # b) reserva: um Python 3.11 ou mais novo que já esteja no computador
    if (-not $pronto) {
        $py = $null
        foreach ($cand in @('py', 'python')) {
            $cmd = (Get-Command $cand -ErrorAction SilentlyContinue | Select-Object -First 1).Source
            if (-not $cmd -or $cmd -like '*WindowsApps*') { continue }
            $antes = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
            try { $v = & $cmd -c "import sys; print(int(sys.version_info >= (3, 11)))" 2>$null } finally { $ErrorActionPreference = $antes }
            if ("$v".Trim() -eq '1') { $py = $cmd; break }
        }
        if ($py) {
            Write-Host "      Usando o Python que já está no computador ($py). Se você desinstalar esse Python, rode o instalador de novo."
            if (Test-Path (Join-Path $voz '.venv')) { Remove-Item (Join-Path $voz '.venv') -Recurse -Force -ErrorAction SilentlyContinue }
            $c = Rodar $py @('-m', 'venv', (Join-Path $voz '.venv'))
            if ($c -eq 0) { $c = Rodar $venvPy @('-m', 'pip', 'install', '-q', '--disable-pip-version-check', '-r', $req) }
            $pronto = ($c -eq 0) -and (Bibliotecas-Ok)
        }
    }
    if (-not $pronto) {
        throw "Não consegui preparar o Python do guardião. Confira a internet e rode o instalador de novo. Se continuar, instale o Python 3.12 de https://www.python.org/downloads/ e rode de novo."
    }
    Set-Content -Path (Join-Path $voz '.venv\requirements.hash') -Value (Get-FileHash $req -Algorithm SHA256).Hash -Encoding ascii
    Feito "Python e bibliotecas prontos."
}

# ---- 3) modelo de escuta (a palavra "Ei guardião" é reconhecida no próprio computador) ----
Passo 3 "Modelo de escuta"
if (Vosk-Ok) {
    Feito "Já estava pronto."
} else {
    $tmp = Join-Path $voz '.baixando'
    if (-not (Test-Path $tmp)) { New-Item -ItemType Directory -Path $tmp -Force | Out-Null }
    $zip = Join-Path $tmp 'vosk.zip'
    Baixar $VOSK.url $zip $VOSK.tamanho '' $VOSK.nome
    $solto = Join-Path $tmp 'vosk'
    if (Test-Path $solto) { Remove-Item $solto -Recurse -Force }
    Expand-Archive -Path $zip -DestinationPath $solto -Force
    $dentro = Get-ChildItem $solto -Directory | Select-Object -First 1
    if (-not $dentro -or -not (Test-Path (Join-Path $dentro.FullName 'final.mdl'))) { throw "O modelo de escuta veio em formato inesperado. Rode o instalador de novo." }
    if (Test-Path (Join-Path $voz 'modelo')) { Remove-Item (Join-Path $voz 'modelo') -Recurse -Force }
    Move-Item $dentro.FullName (Join-Path $voz 'modelo')
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    if (-not (Vosk-Ok)) { throw "O modelo de escuta não ficou completo. Rode o instalador de novo." }
    Feito "Modelo de escuta pronto."
}

# ---- 4) voz do guardião (gerada no próprio computador) ----
Passo 4 "Voz do guardião"
$pastaKokoro = Join-Path $voz 'kokoro'
if (-not (Test-Path $pastaKokoro)) { New-Item -ItemType Directory -Path $pastaKokoro -Force | Out-Null }
$baixou = $false
foreach ($k in $KOKORO) {
    $dest = Join-Path $pastaKokoro $k.arquivo
    if (-not ((Test-Path $dest) -and (Get-Item $dest).Length -eq $k.tamanho)) { Baixar $k.url $dest $k.tamanho $k.sha $k.nome; $baixou = $true }
}
Feito $(if ($baixou) { "Voz pronta." } else { "Já estava pronta." })

# ---- 5) atalho e ponteiro da skill ----
Passo 5 "Atalho na área de trabalho"
if ($SemAtalho) {
    Write-Host "      Pulado (-SemAtalho)."
} else {
    try { & (Join-Path $voz 'criar_atalho.ps1') | ForEach-Object { Feito "$_" } } catch { Write-Host "      (não consegui criar o atalho: $($_.Exception.Message). O painel abre por voz\abrir_guardiao_v2.bat.)" }
}
if (-not (Test-Path $arqMemoriaSkill)) {
    # só o caminho: sem config.json na pasta operacional, a skill sabe que o onboarding ainda não foi feito
    [System.IO.File]::WriteAllText($arqMemoriaSkill, "# Memoria local do guardiao-triwer`n`npasta_operacional: $op`n", $utf8)
}

# ---- 6) conferência de verdade: carrega o modelo de escuta e faz a voz falar uma frase (sem tocar som) ----
Passo 6 "Conferindo se tudo funciona"
$c = Rodar $venvPy @((Join-Path $voz 'conferir_instalacao.py'))
if ($c -ne 0) { throw "A conferência final falhou (veja as linhas acima). Rode o instalador de novo." }

Write-Host ""
Write-Host "Painel do guardião instalado em $op." -ForegroundColor Green
if (-not (Variavel-Usuario 'GROQ_API_KEY')) { Write-Host "Falta a chave gratuita do Groq para o microfone: dois cliques em $voz\definir_chave_groq.bat. Sem ela o painel abre e funciona por texto." }
switch (Estado-Claude) {
    'falta' { Write-Host "Não achei o Claude Code neste computador. É ele que pensa: instale em https://claude.com/claude-code, entre com a sua conta e abra o guardião." }
    'nao_executa' { Write-Host "Achei o Claude Code, mas ele não executa ($((Get-ClaudeEstado).Erro)). Abra um terminal, rode 'claude' e siga o que ele pedir (entrar na conta, atualizar)." }
}
if (-not (Test-Path (Join-Path $op 'config.json'))) { Write-Host "Próximo passo: abra o Claude Code e escreva: configurar o guardião." }
