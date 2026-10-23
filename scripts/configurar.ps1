# Configura o guardião numa máquina. Roda a partir da pasta da skill (scripts\configurar.ps1).
# Quem conduz a entrevista é o Claude (references\onboarding.md); este script faz a parte mecânica e não pergunta nada,
# exceto no modo -DefinirToken (o token nunca passa pelo chat).
#
# Modos:
#   -DefinirToken                  pede o token pessoal do ClickUp (entrada oculta) e grava como variável de usuário
#   -Descobrir                     lista workspaces, usuário, membros, listas e status do ClickUp (só leitura)
#   -Respostas <arquivo.json>      cria pastas, copia os scripts, grava config.json e os esqueletos da memória
#                                  (o painel e a voz são instalados por scripts\instalar_painel.ps1)
#   -AtualizarScripts              recopia os scripts da skill para a pasta operacional (config.json e dados ficam)
#   -Testar                        roda a leitura do ClickUp e confere o config.json
param(
    [switch]$DefinirToken,
    [string]$NomeVariavel = "CLICKUP_API_TOKEN",
    [switch]$Descobrir,
    [string]$Respostas = "",
    [switch]$AtualizarScripts,
    [switch]$Testar
)
$ErrorActionPreference = 'Stop'
$raizSkill = Split-Path -Parent $PSScriptRoot
. (Join-Path $raizSkill 'app\_comum.ps1')
$utf8 = New-Object System.Text.UTF8Encoding($false)
$utf8bom = New-Object System.Text.UTF8Encoding($true)
$arqMemoriaSkill = Join-Path $raizSkill 'memoria.md'

# Lista sem surpresa: nunca vira escalar com 1 item, nunca guarda $null, cai no padrão se vier vazia.
function Lista($valor, $padrao) {
    $a = @($valor | Where-Object { $_ -ne $null -and $_ -ne '' })
    if ($a.Count -gt 0) { return , $a }
    return , @($padrao)
}

function PastaOperacionalAtual {
    if (-not (Test-Path $arqMemoriaSkill)) { throw "memoria.md da skill nao existe: o onboarding ainda nao foi feito." }
    $m = [regex]::Match([System.IO.File]::ReadAllText($arqMemoriaSkill, $utf8), '(?m)^pasta_operacional:\s*(.+)$')
    if (-not $m.Success) { throw "memoria.md sem a linha pasta_operacional." }
    return $m.Groups[1].Value.Trim()
}

function CopiarApp([string]$destino) {
    foreach ($f in Get-ChildItem (Join-Path $raizSkill 'app') -File) {
        # Dados da pessoa nunca são sobrescritos.
        if ($f.Name -in @('tempos.json', 'plano_exemplo.json') -and (Test-Path (Join-Path $destino $f.Name))) { continue }
        if ($f.Name -eq 'config.exemplo.json') { continue }
        Copy-Item $f.FullName (Join-Path $destino $f.Name) -Force
    }
}

# ---------------------------------------------------------------------------------------------------------------
if ($DefinirToken) {
    Write-Host ""
    Write-Host "No ClickUp: foto de perfil > Configuracoes > Apps > Token de API > Gerar. Copie o token (comeca com pk_)."
    $seguro = Read-Host "Cole o token aqui (nao aparece na tela)" -AsSecureString
    $token = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguro))
    if (-not $token -or $token.Length -lt 20) { throw "Token vazio ou curto demais. Nada foi gravado." }
    [Environment]::SetEnvironmentVariable($NomeVariavel, $token, 'User')
    # Confere de verdade antes de dizer que deu certo.
    try {
        $u = Invoke-RestMethod -Uri 'https://api.clickup.com/api/v2/user' -Headers @{ Authorization = $token } -Method Get
        Write-Host "Token gravado em $NomeVariavel e funcionando. Conta: $($u.user.username)."
    } catch {
        [Environment]::SetEnvironmentVariable($NomeVariavel, $null, 'User')
        throw "O ClickUp recusou o token. Nada foi gravado. Gere outro e tente de novo."
    }
    exit
}

# ---------------------------------------------------------------------------------------------------------------
if ($Descobrir) {
    $token = [Environment]::GetEnvironmentVariable($NomeVariavel, 'User')
    if (-not $token) { throw "Token nao encontrado. Rode antes: powershell -ExecutionPolicy Bypass -File configurar.ps1 -DefinirToken" }
    $cab = @{ Authorization = $token }
    $api = 'https://api.clickup.com/api/v2'
    $u = (Invoke-RestMethod -Uri "$api/user" -Headers $cab).user
    Write-Output "USUARIO: id=$($u.id) nome=$($u.username) email=$($u.email)"
    $times = (Invoke-RestMethod -Uri "$api/team" -Headers $cab).teams
    foreach ($t in $times) {
        Write-Output ""
        Write-Output "WORKSPACE: id=$($t.id) nome=$($t.name)"
        foreach ($m in $t.members) { Write-Output "  MEMBRO: id=$($m.user.id) nome=$($m.user.username) email=$($m.user.email)" }
        $spaces = (Invoke-RestMethod -Uri "$api/team/$($t.id)/space?archived=false" -Headers $cab).spaces
        foreach ($s in $spaces) {
            Write-Output "  ESPACO: id=$($s.id) nome=$($s.name)"
            $nomesStatus = @($s.statuses | ForEach-Object { $_.status }) -join ' | '
            Write-Output "    status do espaco: $nomesStatus"
            foreach ($l in (Invoke-RestMethod -Uri "$api/space/$($s.id)/list?archived=false" -Headers $cab).lists) {
                Write-Output "    LISTA: id=$($l.id) nome=$($l.name)"
            }
            foreach ($p in (Invoke-RestMethod -Uri "$api/space/$($s.id)/folder?archived=false" -Headers $cab).folders) {
                foreach ($l in $p.lists) { Write-Output "    LISTA: id=$($l.id) nome=$($p.name) > $($l.name)" }
            }
        }
    }
    exit
}

# ---------------------------------------------------------------------------------------------------------------
if ($AtualizarScripts) {
    $op = PastaOperacionalAtual
    CopiarApp $op
    Write-Output "Scripts atualizados em $op. config.json, plano, registros e tempos foram mantidos."
    exit
}

# ---------------------------------------------------------------------------------------------------------------
if ($Testar) {
    $op = PastaOperacionalAtual
    $cfgArq = Join-Path $op 'config.json'
    if (-not (Test-Path $cfgArq)) { throw "config.json nao existe em $op" }
    $cfg = [System.IO.File]::ReadAllText($cfgArq, $utf8) | ConvertFrom-Json
    $faltando = @()
    foreach ($c in @('pessoa.nome', 'clickup.workspace_id', 'clickup.user_id', 'pastas.memoria')) {
        $v = $cfg; foreach ($p in $c.Split('.')) { $v = $v.$p }
        if (-not $v) { $faltando += $c }
    }
    if ($faltando) { throw "config.json sem: $($faltando -join ', ')" }
    & (Join-Path $op 'ler_clickup.ps1') | Out-Null
    $r = [System.IO.File]::ReadAllText((Join-Path $op 'resumo_clickup.json'), $utf8) | ConvertFrom-Json
    Write-Output "OK. config.json valido. O ClickUp respondeu: $($r.total) tarefa(s) abertas com data atribuidas a $($cfg.pessoa.nome)."
    exit
}

# ---------------------------------------------------------------------------------------------------------------
if (-not $Respostas) { throw "Use um dos modos: -DefinirToken, -Descobrir, -Respostas <arquivo>, -AtualizarScripts, -Testar" }
if (-not (Test-Path $Respostas)) { throw "Arquivo de respostas nao encontrado: $Respostas" }
$r = [System.IO.File]::ReadAllText((Resolve-Path $Respostas), $utf8) | ConvertFrom-Json

# Validação: falha cedo e diz o que falta, em vez de gravar um config pela metade.
$erros = @()
if (-not $r.pessoa.nome) { $erros += 'pessoa.nome' }
if (-not $r.pastas.operacional) { $erros += 'pastas.operacional' }
if (-not $r.pastas.memoria) { $erros += 'pastas.memoria' }
if (-not $r.clickup.workspace_id) { $erros += 'clickup.workspace_id' }
if (-not $r.clickup.user_id) { $erros += 'clickup.user_id' }
if (@($r.clickup.listas).Count -eq 0) { $erros += 'clickup.listas (pelo menos uma)' }
foreach ($l in @($r.clickup.listas)) { if (-not $l.id -or -not $l.nome -or -not $l.quando_usar) { $erros += "clickup.listas: toda lista precisa de id, nome e quando_usar ($($l.nome))" } }
if (-not $r.rotina.chegada -or -not $r.rotina.fim) { $erros += 'rotina.chegada e rotina.fim' }
if ($r.pessoa.artigo -and ("$($r.pessoa.artigo)".ToLower() -notin @('o', 'a'))) { $erros += 'pessoa.artigo (use "o", "a" ou deixe vazio)' }
if ($r.agente.voz -and ("$($r.agente.voz)" -notin @('pm_santa', 'pm_alex', 'pf_dora'))) { $erros += 'agente.voz (pm_santa, pm_alex ou pf_dora)' }
if ($erros) { throw "Respostas incompletas: $($erros -join '; ')" }

$op      = $r.pastas.operacional
$memoria = $r.pastas.memoria
$nome    = $r.pessoa.nome
$agente  = if ($r.agente.nome) { $r.agente.nome } else { 'Guardião do dia' }
$hojeTxt = (Get-Date).ToString('yyyy-MM-dd')
$mesTxt  = (Get-Date).ToString('yyyy-MM')

# De onde vêm as versões novas: o que a pessoa respondeu; senão o clone de onde a skill foi instalada (.repo-path);
# senão o endereço publicado no origem.json da skill. Sem nenhum deles, a conferência diária fica desligada.
function OrigemPadrao {
    $marcador = Join-Path $raizSkill '.repo-path'
    if (Test-Path $marcador) {
        $clone = ([System.IO.File]::ReadAllText($marcador, $utf8)).Trim()
        # no repositório interno o guardião fica numa subpasta; no público, na raiz
        $sub = if ($clone -and (Test-Path (Join-Path $clone 'guardiao-triwer\VERSION'))) { 'guardiao-triwer' } else { '' }
        if ($clone) { return [ordered]@{ origem = $clone; ramo = 'main'; pasta = $sub; verificar = $true } }
    }
    $arq = Join-Path $raizSkill 'origem.json'
    if (Test-Path $arq) {
        $o = [System.IO.File]::ReadAllText($arq, $utf8) | ConvertFrom-Json
        if ($o.origem) { return [ordered]@{ origem = "$($o.origem)"; ramo = $(if ($o.ramo) { "$($o.ramo)" } else { 'main' }); pasta = "$($o.pasta)"; verificar = $true } }
    }
    return [ordered]@{ origem = ''; ramo = 'main'; pasta = 'guardiao-triwer'; verificar = $false }
}
$atualizacao = OrigemPadrao
if ($r.atualizacao.origem) {
    $atualizacao = [ordered]@{
        origem = "$($r.atualizacao.origem)"; ramo = $(if ($r.atualizacao.ramo) { "$($r.atualizacao.ramo)" } else { 'main' })
        pasta = $(if ($r.atualizacao.PSObject.Properties['pasta']) { "$($r.atualizacao.pasta)" } else { 'guardiao-triwer' }); verificar = $true
    }
}

$pessoa = [ordered]@{ nome = $nome }
if ($r.pessoa.artigo) { $pessoa.artigo = "$($r.pessoa.artigo)".ToLower() }

$cfg = [ordered]@{
    versao  = 1
    pessoa  = $pessoa
    agente  = [ordered]@{ nome = $agente; voz = $(if ($r.agente.voz) { "$($r.agente.voz)" } else { 'pm_santa' }) }
    pastas  = [ordered]@{ operacional = $op; memoria = $memoria; memoria_em_obsidian = [bool]$r.pastas.memoria_em_obsidian }
    rotina  = [ordered]@{
        dias_trabalho    = (Lista $r.rotina.dias_trabalho @('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'))
        chegada          = $r.rotina.chegada
        almoco           = $r.rotina.almoco
        fim              = $r.rotina.fim
        gerar_plano_as   = $(if ($r.rotina.gerar_plano_as) { $r.rotina.gerar_plano_as } else { '08:30' })
        leituras_clickup = (Lista $r.rotina.leituras_clickup @('09:00', '13:00', '18:00'))
    }
    clickup = [ordered]@{
        token_variavel    = $(if ($r.clickup.token_variavel) { $r.clickup.token_variavel } else { 'CLICKUP_API_TOKEN' })
        workspace_id      = "$($r.clickup.workspace_id)"
        user_id           = "$($r.clickup.user_id)"
        status_abertos    = (Lista $r.clickup.status_abertos @())
        hora_sem_hora     = $(if ($r.clickup.hora_sem_hora) { $r.clickup.hora_sem_hora } else { '04:00' })
        prefixo_aprovacao = $(if ($r.clickup.prefixo_aprovacao) { $r.clickup.prefixo_aprovacao } else { '' })
        listas            = @($r.clickup.listas | ForEach-Object { [ordered]@{ id = "$($_.id)"; nome = $_.nome; quando_usar = $_.quando_usar } })
        membros           = @($r.clickup.membros | Where-Object { $_.nome } | ForEach-Object { [ordered]@{ nome = $_.nome; id = "$($_.id)"; papel = $_.papel } })
    }
    atualizacao = $atualizacao
}
# Campos opcionais: só entram se a pessoa respondeu.
if ($r.agente.assinatura) { $cfg.agente.assinatura = "$($r.agente.assinatura)" }
if ($r.rotina.abrir_tela_as) { $cfg.rotina.abrir_tela_as = "$($r.rotina.abrir_tela_as)" }
if ($r.clickup.atrasadas_dias) { $cfg.clickup.atrasadas_dias = [int]$r.clickup.atrasadas_dias }
if ($r.sessao.pasta) {
    $cfg.sessao = [ordered]@{
        pasta = "$($r.sessao.pasta)"; esforco = $(if ($r.sessao.esforco) { "$($r.sessao.esforco)" } else { 'low' })
        nova_conversa_apos_horas = $(if ($r.sessao.nova_conversa_apos_horas) { [int]$r.sessao.nova_conversa_apos_horas } else { 3 })
        fecha_apos_min = $(if ($r.sessao.fecha_apos_min) { [int]$r.sessao.fecha_apos_min } else { 15 })
    }
}
if ($r.pops.catalogo) { $cfg.pops = [ordered]@{ catalogo = "$($r.pops.catalogo)" } }

# Pastas
foreach ($d in @($op, (Join-Path $op 'registros'), (Join-Path $op 'logs'), (Join-Path $op 'planos'), $memoria, (Join-Path $memoria 'campanhas'), (Join-Path $memoria 'decisoes'), (Join-Path $memoria 'pops'), (Join-Path $memoria 'arquivo'))) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

# Scripts e dados iniciais
CopiarApp $op
[System.IO.File]::WriteAllText((Join-Path $op 'config.json'), ($cfg | ConvertTo-Json -Depth 6), $utf8)
# Instalação nova: o painel oferece o tour guiado na primeira abertura. Só cria se ainda não existir: reconfigurar não oferece de novo, e quem já usava o guardião não recebe convite.
$arqTutorial = Join-Path $op 'tutorial_estado.json'
if (-not (Test-Path $arqTutorial)) { [System.IO.File]::WriteAllText($arqTutorial, ([ordered]@{ convidar = $true; criado_em = $hojeTxt } | ConvertTo-Json), $utf8) }

# Esqueletos da memória: só criados se ainda não existirem (nunca sobrescreve o que a pessoa já tem).
$mapa = @{
    'perfil.md' = 'perfil.md'; 'semana-base.md' = 'semana-base.md'; 'equipe.md' = 'equipe.md'; 'estado.md' = 'estado.md'; 'aprendizados.md' = 'aprendizados.md'
    'decisoes.md' = 'decisoes.md'; 'campanhas.md' = 'campanhas.md'; 'Index.md' = 'Index.md'
    'campanhas\_modelo.md' = 'campanhas\_modelo.md'; 'pops\_modelo.md' = 'pops\_modelo.md'; "decisoes\$mesTxt.md" = 'decisoes\mes.md'
}
$criados = @()
foreach ($k in $mapa.Keys) {
    $destino = Join-Path $memoria $k
    if (Test-Path $destino) { continue }
    $texto = [System.IO.File]::ReadAllText((Join-Path $raizSkill "templates\$($mapa[$k])"), $utf8)
    $texto = $texto.Replace('{{nome}}', $nome).Replace('{{agente}}', $agente).Replace('{{data}}', $hojeTxt).Replace('{{mes}}', $mesTxt).Replace('{{pasta_operacional}}', $op)
    [System.IO.File]::WriteAllText($destino, $texto, $utf8)
    $criados += $k
}

# Ponteiro local da skill (memoria.md é local por máquina e nunca vai para o repositório)
[System.IO.File]::WriteAllText($arqMemoriaSkill, "# Memoria local do guardiao-triwer`n`npasta_operacional: $op`nconfigurado_em: $hojeTxt`n", $utf8)

# .ps1 precisa de UTF-8 com BOM para o Windows PowerShell 5.1 ler os acentos
foreach ($f in Get-ChildItem $op -Filter '*.ps1') {
    $bytes = [System.IO.File]::ReadAllBytes($f.FullName)
    if (-not ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)) {
        [System.IO.File]::WriteAllText($f.FullName, [System.IO.File]::ReadAllText($f.FullName, $utf8), $utf8bom)
    }
}

# Índice de campanhas com a tabela vazia
& (Join-Path $op 'indice_campanhas.ps1') | Out-Null

Write-Output "Configurado para $nome."
Write-Output "  Pasta operacional: $op"
Write-Output "  Memoria legivel:   $memoria"
Write-Output "  Esqueletos criados: $($criados -join ', ')"
if (-not (Test-Path (Join-Path $op 'voz\.venv\Scripts\pythonw.exe'))) {
    Write-Output "  AVISO: o painel ainda nao esta instalado nesta pasta. Rode: powershell -ExecutionPolicy Bypass -File `"$raizSkill\scripts\instalar_painel.ps1`" -Pasta `"$op`""
}
Write-Output "Proximo passo: o Claude preenche perfil.md, semana-base.md e equipe.md com as respostas da entrevista."
