# Instalador do Guardião. Jeito mais fácil: dois cliques em instalar.bat, nesta mesma pasta.
# Faz tudo que é mecânico: instala uma skill global para Claude, Codex ou ambos, além do painel e da voz.
# Não precisa de administrador e pode ser rodado de novo sem medo: o que já está pronto é pulado.
# O que é da pessoa (rotina, equipe, ClickUp) vem depois, numa conversa com o Claude Code: "configurar o guardião".
#
#   -Pasta <pasta>        pasta operacional (padrão: %USERPROFILE%\Guardiao-do-dia)
#   -PastaSkill <pasta>   pasta canônica da skill (padrão: global do provedor escolhido)
#   -Provedores <...>    Perguntar, Claude, Codex ou Ambos
#   -SemChave             não pergunta a chave do Groq agora
#   -SemAtalho            não cria o atalho na área de trabalho
#   -SemPerguntas         não pergunta nada no fim (não abre a demonstração nem o Claude Code)
param(
    [string]$Pasta = "",
    [string]$PastaSkill = "",
    [ValidateSet('Perguntar','Claude','Codex','Ambos')][string]$Provedores = 'Perguntar',
    [switch]$SemChave,
    [switch]$SemAtalho,
    [switch]$SemPerguntas
)
$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$origem = $PSScriptRoot
if (-not $Pasta) { $Pasta = Join-Path $env:USERPROFILE 'Guardiao-do-dia' }
$skillClaude = Join-Path $env:USERPROFILE '.claude\skills\guardiao-triwer'
$skillCodex = Join-Path $env:USERPROFILE '.codex\skills\guardiao-triwer'
if ($Provedores -eq 'Perguntar') {
    if ($SemPerguntas) {
        $Provedores = 'Ambos'  # instalação por chat: uma execução habilita os dois provedores
    } else {
        Write-Host '  Onde você quer usar o Guardião?'
        Write-Host '  1) Claude Code   2) Codex   3) Nos dois'
        $opcao = (Read-Host '  Escolha 1, 2 ou 3 (padrão 3)').Trim()
        $Provedores = if ($opcao -eq '1') { 'Claude' } elseif ($opcao -eq '2') { 'Codex' } else { 'Ambos' }
    }
}
$usarClaude = $Provedores -in @('Claude','Ambos')
$usarCodex = $Provedores -in @('Codex','Ambos')
if (-not $PastaSkill) { $PastaSkill = if ($usarClaude) { $skillClaude } else { $skillCodex } }
$versao = ([System.IO.File]::ReadAllText((Join-Path $origem 'VERSION'), $utf8)).Trim()

function Sim([string]$pergunta) {
    $r = Read-Host "$pergunta (S/n)"
    return ($r.Trim() -eq '' -or $r.Trim().ToLower().StartsWith('s'))
}

try {
    Write-Host ""
    Write-Host "  GUARDIÃO, versão $versao" -ForegroundColor Yellow
    Write-Host "  Vou instalar o painel e a voz do guardião neste computador."
    Write-Host "  Baixo cerca de 500 MB e levo de 5 a 10 minutos. Pode deixar esta janela aberta e fazer outra coisa."
    Write-Host ""

    # ---- o computador serve? ----
    if ([Environment]::OSVersion.Version.Major -lt 10) { throw "O guardião precisa do Windows 10 ou 11." }
    if (-not [Environment]::Is64BitOperatingSystem) { throw "O guardião precisa do Windows de 64 bits." }
    $disco = Get-PSDrive -Name ([System.IO.Path]::GetPathRoot($Pasta).Substring(0, 1)) -ErrorAction SilentlyContinue
    if ($disco -and $disco.Free -lt 2GB) { throw "Preciso de pelo menos 2 GB livres no disco $($disco.Name):. Libere espaço e rode de novo." }
    . (Join-Path $origem 'app\_comum.ps1')
    $claude = if ($usarClaude) { Get-ClaudeEstado } else { $null }
    $temClaude = $usarClaude -and $claude.Ok
    if (-not $usarClaude) {
        Write-Host '  Claude Code não foi escolhido; ele não será exigido.'
    } elseif ($temClaude) {
        Write-Host "  Claude Code encontrado: $($claude.Versao)." -ForegroundColor Green
        Write-Host ""
    } elseif ($claude.Erro) {
        Write-Host "  ATENÇÃO: achei o Claude Code, mas ele não executa ($($claude.Erro))." -ForegroundColor Yellow
        Write-Host "  Abra um terminal, rode 'claude' e siga o que ele pedir (entrar na conta, atualizar). Vou instalar o resto mesmo assim."
        Write-Host ""
    } else {
        Write-Host "  ATENÇÃO: não achei o Claude Code neste computador." -ForegroundColor Yellow
        Write-Host "  Vou instalar tudo mesmo assim. Depois instale o Claude Code (https://claude.com/claude-code), entre com a sua conta"
        Write-Host "  e siga para o passo da configuração. Não precisa rodar este instalador de novo."
        Write-Host ""
    }
    if ($usarCodex) {
        $codex = Get-Command codex -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($codex) {
            Write-Host "  Codex encontrado: $($codex.Source)" -ForegroundColor Green
            $estadoLogin = & $codex.Source login status 2>&1 | Out-String
            if ($LASTEXITCODE -ne 0) { Write-Host "  Para usar Codex no painel, rode 'codex login' uma vez. $($estadoLogin.Trim())" -ForegroundColor Yellow }
        } else {
            Write-Host "  Codex CLI não encontrado. A skill será ligada agora; depois instale o CLI e rode 'codex login'." -ForegroundColor Yellow
            Write-Host "  Instruções: https://learn.chatgpt.com/docs/codex/cli"
        }
    }

    # ---- uma pasta canônica da skill, global no provedor escolhido ----
    $aqui = (Resolve-Path $origem).Path.TrimEnd('\')
    $la = if (Test-Path $PastaSkill) { (Resolve-Path $PastaSkill).Path.TrimEnd('\') } else { $PastaSkill.TrimEnd('\') }
    if ($aqui -ne $la) {
        Write-Host "Copiando a skill para $PastaSkill"
        if (-not (Test-Path $PastaSkill)) { New-Item -ItemType Directory -Path $PastaSkill -Force | Out-Null }
        $a = @($origem, $PastaSkill, '/E', '/R:2', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS', '/NP',
               '/XD', '.git', 'node_modules', '__pycache__', '.venv', 'modelo', 'kokoro', 'perfil_edge', 'capturas', 'amostras', '.ferramentas',
               '/XF', 'memoria.md', 'NOTAS-PARA-INSTALADOR.md', 'HISTORICO-DETALHADO.md', '.repo-path', 'extensoes-*.md', '*.pyc', 'preferencias.json', 'pronuncias.json')
        & robocopy @a | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "Não consegui copiar a skill para $PastaSkill (robocopy $LASTEXITCODE)." }
        Get-ChildItem $PastaSkill -Recurse -File -Include *.ps1, *.bat, *.py -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue
    }
    # baixada com git: as próximas versões vêm do próprio clone (git pull)
    $clone = $origem
    while ($clone -and -not (Test-Path (Join-Path $clone '.git'))) { $pai = Split-Path -Parent $clone; $clone = if ($pai -and $pai -ne $clone) { $pai } else { $null } }
    if ($clone) { [System.IO.File]::WriteAllText((Join-Path $PastaSkill '.repo-path'), $clone, $utf8) }

    # Cada provedor aponta para a pasta canônica. Não há segunda cópia do SKILL.md.
    $globais = @()
    if ($usarClaude) { $globais += $skillClaude }
    if ($usarCodex) { $globais += $skillCodex }
    foreach ($global in $globais) {
        if ([IO.Path]::GetFullPath($global) -eq [IO.Path]::GetFullPath($PastaSkill)) { continue }
        $paiGlobal = Split-Path -Parent $global
        if (-not (Test-Path $paiGlobal)) { New-Item -ItemType Directory -Path $paiGlobal -Force | Out-Null }
        if (Test-Path $global) {
            $ligacao = Get-Item -LiteralPath $global -Force
            if ($ligacao.LinkType -ne 'Junction' -or [IO.Path]::GetFullPath([string]$ligacao.Target) -ne [IO.Path]::GetFullPath($PastaSkill)) {
                throw "Já existe outra skill em $global. Não a sobrescrevi; mova-a antes de instalar nos dois."
            }
        } else {
            New-Item -ItemType Junction -Path $global -Target $PastaSkill -ErrorAction Stop | Out-Null
        }
    }

    # ---- painel e voz ----
    & (Join-Path $PastaSkill 'scripts\instalar_painel.ps1') -Pasta $Pasta -SemAtalho:$SemAtalho -Provedores $Provedores
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "A instalação do painel não terminou." }
    if ($usarCodex -and -not $usarClaude) {
        $arqPref = Join-Path $Pasta 'voz\preferencias.json'
        $preferencias = if (Test-Path $arqPref) { [System.IO.File]::ReadAllText($arqPref, $utf8) | ConvertFrom-Json } else { [pscustomobject]@{} }
        $preferencias | Add-Member -NotePropertyName provedor_ia -NotePropertyValue 'codex' -Force
        [System.IO.File]::WriteAllText($arqPref, ($preferencias | ConvertTo-Json -Depth 8), $utf8)
    }

    # ---- chave gratuita do Groq (o microfone) ----
    $temChave = [bool][Environment]::GetEnvironmentVariable('GROQ_API_KEY', 'User')
    if (-not $SemChave -and -not $temChave) {
        & (Join-Path $Pasta 'voz\definir_chave_groq.ps1')
        $temChave = [bool][Environment]::GetEnvironmentVariable('GROQ_API_KEY', 'User')
    }

    # ---- o que falta ----
    $configurado = Test-Path (Join-Path $Pasta 'config.json')
    Write-Host ""
    Write-Host "  PRONTO. O guardião está instalado." -ForegroundColor Green
    Write-Host "  Painel e voz:  $Pasta"
    Write-Host "  Skill:         $PastaSkill"
    if ($usarCodex -and $usarClaude) { Write-Host "  Codex global:  $skillCodex (atalho para a mesma skill)" }
    Write-Host "  Microfone:     $(if ($temChave) { 'ligado (chave do Groq gravada)' } else { 'desligado, falta a chave do Groq (voz\definir_chave_groq.bat)' })"
    Write-Host "  Se algo não funcionar: dois cliques em $Pasta\voz\diagnostico.bat (ele confere cada peça e diz o que fazer)."
    Write-Host ""
    if ($configurado) {
        Write-Host "  Este computador já tinha o guardião configurado. Abra pelo atalho Guardião, na área de trabalho."
    } else {
        Write-Host "  FALTA UM PASSO: a conversa em que o guardião conhece a sua rotina (uns 30 a 40 minutos)." -ForegroundColor Yellow
        Write-Host "  Abra $(if ($usarClaude) { 'o Claude Code' } else { 'o Codex' }) e escreva:  configurar o guardião"
        Write-Host ""
        if (-not $SemPerguntas) {
            if (Sim "  Quer ver agora o painel com um dia de exemplo") {
                Start-Process -FilePath (Join-Path $Pasta 'voz\.venv\Scripts\pythonw.exe') -ArgumentList 'demo_v2.py' -WorkingDirectory (Join-Path $Pasta 'voz') -WindowStyle Hidden
                Write-Host "  Abrindo a demonstração. Ela fecha sozinha em 30 minutos."
            }
            if ($temClaude -and (Sim "  Abro o Claude Code aqui para começar a configuração")) {
                Start-Process -FilePath 'cmd.exe' -ArgumentList '/k', 'claude "configurar o guardiao"' -WorkingDirectory $env:USERPROFILE
            }
        }
    }
    exit 0
} catch {
    Write-Host ""
    Write-Host "  NÃO TERMINOU: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "  Pode rodar o instalador de novo: ele continua de onde parou."
    exit 1
}
