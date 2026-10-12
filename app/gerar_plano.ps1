# Gera o plano SUGERIDO do dia com o Claude (skill guardiao-triwer, modo planejar). No máximo 1 execução por dia.
# Só grava o arquivo do plano. Não toca no ClickUp nem em outro lugar: as tarefas são criadas pelo servidor
# quando a pessoa aprova o plano na tela.
# Uso: powershell -ExecutionPolicy Bypass -File gerar_plano.ps1 [-Data AAAA-MM-DD] [-Saida arquivo.json] [-Forcar] [-Manual]
param(
    [string]$Data = "",
    [string]$Saida = "",
    [switch]$Forcar,
    [switch]$Manual
)
. (Join-Path $PSScriptRoot '_comum.ps1')
$cfg     = Get-Config
$pasta   = $PSScriptRoot
$memoria = Get-PastaMemoria $cfg
$nome    = $cfg.pessoa.nome
$utf8    = $script:utf8
$hoje    = Get-Date

$diasTrabalho = @($cfg.rotina.dias_trabalho)
if ($diasTrabalho.Count -eq 0) { $diasTrabalho = @('Monday','Tuesday','Wednesday','Thursday','Friday') }
$fimExpediente = [datetime]::ParseExact($(if ($cfg.rotina.fim) { $cfg.rotina.fim } else { '18:00' }), 'HH:mm', $null)

$alvo = if ($Data) { $Data } else { $hoje.ToString('yyyy-MM-dd') }
$diaAlvo = [datetime]::ParseExact($alvo, 'yyyy-MM-dd', $null)
if (-not $Data -and ($diasTrabalho -notcontains $diaAlvo.DayOfWeek.ToString())) {
    # Automático: dia sem trabalho não gera. Manual (ela chamou): planeja o próximo dia de trabalho.
    if (-not $Manual) { exit }
    do { $diaAlvo = $diaAlvo.AddDays(1) } while ($diasTrabalho -notcontains $diaAlvo.DayOfWeek.ToString())
    $alvo = $diaAlvo.ToString('yyyy-MM-dd')
}

$planoCaminho = if ($Saida) { $Saida } else { Join-Path $pasta 'plano_do_dia.json' }
if (-not $Saida) { Promover-Plano $pasta }

# Automático só roda dentro do expediente: depois do fim do dia não faz sentido gerar plano de um dia que já acabou.
if (-not $Data -and -not $Manual -and ($hoje.TimeOfDay -ge $fimExpediente.TimeOfDay)) { exit }

if ((Test-Path $planoCaminho) -and -not $Forcar) {
    $atual = [System.IO.File]::ReadAllText($planoCaminho, $utf8)
    $dataAtual = [regex]::Match($atual, '"data"\s*:\s*"(\d{4}-\d{2}-\d{2})"').Groups[1].Value
    # Já existe plano desse dia, ou de um dia POSTERIOR (ex: o de amanhã já aprovado): não sobrescreve.
    if ($dataAtual -and $dataAtual -ge $alvo) { exit }
}

$pastaLogs = Join-Path $pasta 'logs'
if (-not (Test-Path $pastaLogs)) { New-Item -ItemType Directory -Path $pastaLogs | Out-Null }
$log = Join-Path $pastaLogs ("gerar_plano_" + $alvo + ".log")

# Resumo do ClickUp fresco (sem Claude).
try { & (Join-Path $pasta 'ler_clickup.ps1') | Out-Null } catch { "ler_clickup falhou: $($_.Exception.Message)" | Out-File $log -Append -Encoding utf8 }

# Listas e donos vêm de config.json, para o Claude escolher onde cada bloco novo nasce.
$linhasListas = (@($cfg.clickup.listas) | ForEach-Object { "- ""lista_id"": $($_.id) para $($_.quando_usar) (lista '$($_.nome)')." }) -join "`n"
$linhasDonos  = "- ${nome} (a propria pessoa): executa tudo que nao for delegado."
foreach ($m in @($cfg.clickup.membros)) { $linhasDonos += "`n- $($m.nome): $($m.papel)" }

$prompt = @"
Use a skill guardiao-triwer no modo planejar e monte o plano do dia $alvo de $nome.
Leia, na pasta de memoria $memoria, perfil.md, semana-base.md, equipe.md, estado.md, o indice campanhas.md (abra com Read a nota de uma campanha em campanhas\ SOMENTE se o plano do dia tocar nela), o indice decisoes.md, resumo_clickup.json (na pasta operacional), o registro de ontem em registros\ (se existir). Pasta operacional (scripts, plano, registros, resumo): $pasta.
Siga a conta de horario da skill. Horarios de reunioes vem de inicio/fim do resumo. Nao pergunte nada: se faltar informacao, deixe o bloco de fora e diga em uma frase no campo aviso.
Grave SOMENTE o arquivo $planoCaminho, em JSON valido no formato de plano_exemplo.json, com "status": "sugerido" e sem o campo "exemplo".
Regras do formato: em cada bloco "id" e a PRIMEIRA chave; todo bloco leva titulo, inicio, fim (HH:mm), dono, frente, descricao, primeiro_passo e por_que_agora.
Ligacao com o ClickUp (o servidor cria as tarefas quando a pessoa aprovar):
- Se o bloco e uma tarefa que ja existe no resumo, coloque "clickup_id" com o id dela e nao coloque lista_id.
- Se e novo, coloque "lista_id" de uma destas listas:
$linhasListas
  Se for parte de uma tarefa existente, coloque tambem "pai" com o id da tarefa-mae.
- "dono" e o nome de quem executa, entre:
$linhasDonos
  Briefing de tarefa de outra pessoa e escrito por voce na descricao, completo, sem deixar decisao em aberto.
Reunioes e compromissos fixos do ClickUp vao em "fixos" (inicio, fim, titulo), nao em blocos.
Nao crie nem altere nada no ClickUp ou em outro lugar. Nao decida estrategia nem sugira temas, ganchos ou briefing de conteudo: o guardiao so reserva e protege tempo.
No fim, responda em ate 6 linhas: o que colocou, o que deixou de fora e por que.
"@

$env:CLAUDECODE = $null
# o instalador do Claude Code deixa o comando em %USERPROFILE%\.local\bin, que nem sempre está no PATH da tarefa agendada
$claudeLocal = Join-Path $env:USERPROFILE '.local\bin'
if (-not (Get-Command claude -ErrorAction SilentlyContinue) -and (Test-Path (Join-Path $claudeLocal 'claude.exe'))) { $env:PATH = "$claudeLocal;$env:PATH" }
Set-Location $pasta
$saidaClaude = & claude -p $prompt --add-dir $memoria --allowedTools "Read,Write,Glob,Skill" --max-turns 25 --output-format text 2>&1
"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm') plano de $alvo ===" | Out-File $log -Append -Encoding utf8
$saidaClaude | Out-String | Out-File $log -Append -Encoding utf8
