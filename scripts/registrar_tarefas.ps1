# Cria as tarefas agendadas do Windows que fazem o guardião funcionar sozinho. Não precisa de administrador.
# Lê a rotina de config.json (dias, horário do plano, horários de leitura do ClickUp, horário de abrir o painel).
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File registrar_tarefas.ps1 -SomenteMostrar   mostra o que seria criado, sem criar nada
#   powershell -ExecutionPolicy Bypass -File registrar_tarefas.ps1                   cria (ou recria) as 4 tarefas
#   powershell -ExecutionPolicy Bypass -File registrar_tarefas.ps1 -Remover          apaga as tarefas do guardião
param(
    [switch]$SomenteMostrar,
    [switch]$Remover,
    [string]$Pasta = ""
)
$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$raizSkill = Split-Path -Parent $PSScriptRoot
if (-not $Pasta) {
    $m = [regex]::Match([System.IO.File]::ReadAllText((Join-Path $raizSkill 'memoria.md'), $utf8), '(?m)^pasta_operacional:\s*(.+)$')
    if (-not $m.Success) { throw "Nao achei a pasta operacional. Passe -Pasta ou rode o onboarding." }
    $Pasta = $m.Groups[1].Value.Trim()
}
$cfg = [System.IO.File]::ReadAllText((Join-Path $Pasta 'config.json'), $utf8) | ConvertFrom-Json

$prefixo = 'Guardiao Triwer'
$nomes = @("$prefixo - gerar plano", "$prefixo - ler ClickUp", "$prefixo - voz", "$prefixo - tela")
# "avisos" existiu em instalações antigas; hoje quem mantém o aviso por pop-up ligado é o próprio programa.
$antigas = @("$prefixo - avisos")

if ($Remover) {
    foreach ($n in ($nomes + $antigas)) {
        if (-not (Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue)) { continue }
        if ($SomenteMostrar) { Write-Output "Apagaria: $n"; continue }
        Unregister-ScheduledTask -TaskName $n -Confirm:$false
        Write-Output "Apagada: $n"
    }
    exit
}

$voz = Join-Path $Pasta 'voz'
$pythonw = Join-Path $voz '.venv\Scripts\pythonw.exe'
if (-not $SomenteMostrar -and -not (Test-Path $pythonw)) {
    throw "O painel ainda nao esta instalado em $voz. Rode antes: powershell -ExecutionPolicy Bypass -File `"$raizSkill\scripts\instalar_painel.ps1`""
}

# O agendador exige o usuário completo (DOMINIO\usuario) no gatilho de logon.
$usuario = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$dias = @($cfg.rotina.dias_trabalho | ForEach-Object { [System.DayOfWeek]$_ })
function Acao([string]$script, [string]$extra = '') {
    New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$(Join-Path $Pasta $script)`" $extra".Trim()
}
function Ajustes([bool]$semLimite) {
    $a = @{ AllowStartIfOnBatteries = $true; DontStopIfGoingOnBatteries = $true; StartWhenAvailable = $true }
    if ($semLimite) { $a.ExecutionTimeLimit = [TimeSpan]::Zero } else { $a.ExecutionTimeLimit = (New-TimeSpan -Minutes 30) }
    New-ScheduledTaskSettingsSet @a
}

$definicoes = @(
    @{
        nome = $nomes[0]; acao = (Acao 'gerar_plano.ps1'); ajustes = (Ajustes $false)
        gatilhos = @((New-ScheduledTaskTrigger -AtLogOn -User $usuario), (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $dias -At $cfg.rotina.gerar_plano_as))
        resumo = "ao ligar o PC e as $($cfg.rotina.gerar_plano_as) nos dias de trabalho (so gera 1 plano por dia)"
    },
    @{
        nome = $nomes[1]; acao = (Acao 'ler_clickup.ps1'); ajustes = (Ajustes $false)
        gatilhos = @((New-ScheduledTaskTrigger -AtLogOn -User $usuario)) + @($cfg.rotina.leituras_clickup | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ })
        resumo = "ao ligar o PC e as $(@($cfg.rotina.leituras_clickup) -join ', ')"
    },
    @{
        # O programa (escuta, voz e painel) fica ligado em segundo plano. Com --vigia, se ele já estiver ligado a tarefa sai em silêncio.
        nome = $nomes[2]; ajustes = (Ajustes $true)
        acao = (New-ScheduledTaskAction -Execute "`"$pythonw`"" -Argument 'guardiao_voz.py --cerebro --sem-janela --vigia' -WorkingDirectory $voz)
        gatilhos = @((New-ScheduledTaskTrigger -AtLogOn -User $usuario), (New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 15)))
        resumo = "ao ligar o PC e a cada 15 minutos confere se o guardiao esta ligado (escuta, voz e painel, sem janela)"
    },
    @{
        nome = $nomes[3]; acao = (Acao 'voz\abrir_guardiao_v2.ps1'); ajustes = (Ajustes $false)
        gatilhos = @((New-ScheduledTaskTrigger -AtLogOn -User $usuario)) + @($(if ($cfg.rotina.abrir_tela_as) { New-ScheduledTaskTrigger -Weekly -DaysOfWeek $dias -At $cfg.rotina.abrir_tela_as }))
        resumo = "ao ligar o PC e $(if ($cfg.rotina.abrir_tela_as) { "as $($cfg.rotina.abrir_tela_as) nos dias de trabalho " })(abre a janela do painel)"
    }
)

foreach ($d in $definicoes) {
    if ($SomenteMostrar) { Write-Output "Criaria: $($d.nome) -> $($d.resumo)"; continue }
    if (Get-ScheduledTask -TaskName $d.nome -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $d.nome -Confirm:$false }
    $null = Register-ScheduledTask -TaskName $d.nome -Action $d.acao -Trigger $d.gatilhos -Settings $d.ajustes -Description "Guardiao Triwer (config em $Pasta\config.json)"
    Write-Output "Criada: $($d.nome) -> $($d.resumo)"
}
