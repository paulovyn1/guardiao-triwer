# Gera o plano SUGERIDO do dia com o Claude (skill guardiao-triwer, modo planejar). No máximo 1 execução por dia.
# Só grava o arquivo do plano. Não toca no ClickUp nem em outro lugar: as tarefas são criadas pelo servidor
# quando a pessoa aprova o plano na tela.
# Uso: powershell -ExecutionPolicy Bypass -File gerar_plano.ps1 [-Data AAAA-MM-DD] [-Saida arquivo.json] [-Forcar] [-Manual]
param(
    [string]$Data = "",
    [string]$Saida = "",
    [switch]$Forcar,
    [switch]$Manual,
    [switch]$Replanejar
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

# Plano base por código (voz\plano_base.py): a semana combinada (ClickUp com hora) mais os fixos. Se nada pede decisão, o plano está pronto
# e o Claude NÃO é chamado. Se pede, o Claude parte de um dossiê curto (motivos, plano base, semana, alertas) em vez de reler tudo.
$py = Join-Path $pasta 'voz\.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }
$env:PYTHONIOENCODING = 'utf-8'
$dossie = Join-Path $pastaLogs ("dossie_" + $alvo + ".txt")
$copiaBase = Join-Path $pastaLogs ("plano_base_" + $alvo + ".json")
$codBase = -1
try {
    $saidaBase = & $py (Join-Path $pasta 'voz\plano_base.py') --data $alvo --saida $planoCaminho --dossie $dossie 2>&1
    $codBase = $LASTEXITCODE
    "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm') plano base de $alvo (código $codBase) ===`r`n$($saidaBase | Out-String)" | Out-File $log -Append -Encoding utf8
} catch { "plano_base falhou: $($_.Exception.Message)" | Out-File $log -Append -Encoding utf8 }
if ($codBase -eq 0) { exit }   # o dia já estava resolvido na semana combinada
if ($codBase -eq 2) { Copy-Item $planoCaminho $copiaBase -Force }
$temDossie = ($codBase -eq 2) -and (Test-Path $dossie)

# Listas e donos vêm de config.json, para o Claude escolher onde cada bloco novo nasce.
$linhasListas = (@($cfg.clickup.listas) | ForEach-Object { "- ""lista_id"": $($_.id) para $($_.quando_usar) (lista '$($_.nome)')." }) -join "`n"
$linhasDonos  = "- ${nome} (a propria pessoa): executa tudo que nao for delegado."
foreach ($m in @($cfg.clickup.membros)) { $linhasDonos += "`n- $($m.nome): $($m.papel)" }

$leitura = if ($temDossie) {
@"
Leia PRIMEIRO o dossie ${dossie}. Ele ja traz o plano base (a semana combinada, que voce mantem), os motivos pelos quais o plano precisa de voce (resolva so eles), a semana dos proximos dias e os alertas. NAO leia resumo_clickup.json nem planos de outros dias: o que precisa deles ja esta no dossie. Da pasta de memoria $memoria leia so perfil.md, estado.md e aprendizados.md, e da pasta operacional calibragem\regras.md se existir (tempos reais que ela confirmou: use ao estimar); nota de campanha em campanhas\ so se um motivo tocar nela. Pasta operacional: $pasta.
Se tirar do dia algo que estava agendado no plano base, ponha o titulo em "removidos" e diga no campo aviso para onde sugere levar.
"@
} else {
@"
Leia, na pasta de memoria $memoria, perfil.md, semana-base.md, equipe.md, estado.md, o indice campanhas.md (abra com Read a nota de uma campanha em campanhas\ SOMENTE se o plano do dia tocar nela), o indice decisoes.md, resumo_clickup.json (na pasta operacional), calibragem\regras.md (na pasta operacional, se existir: tempos reais que ela confirmou, use ao estimar), o registro de ontem em registros\ (se existir). Pasta operacional (scripts, plano, registros, resumo): $pasta.
"@
}

$prompt = @"
Use a skill guardiao-triwer no modo planejar e monte o plano do dia $alvo de $nome.
$leitura
Siga a conta de horario da skill. Horarios de reunioes vem de inicio/fim do resumo. Nao pergunte nada: se faltar informacao, deixe o bloco de fora e diga em uma frase no campo aviso.
Grave o arquivo $planoCaminho, em JSON valido no formato de plano_exemplo.json, com "status": "sugerido" e sem o campo "exemplo". Unica outra escrita permitida: o rascunho de um trabalho do guardiao vencido (veja abaixo).
Regras do formato: em cada bloco "id" e a PRIMEIRA chave; todo bloco leva titulo, inicio, fim (HH:mm), dono, frente, descricao, primeiro_passo e por_que_agora.
Ligacao com o ClickUp (o servidor cria as tarefas quando a pessoa aprovar):
- Se o bloco e uma tarefa que ja existe no resumo, coloque "clickup_id" com o id dela e nao coloque lista_id.
- Se e novo, coloque "lista_id" de uma destas listas:
$linhasListas
  Se for parte de uma tarefa existente, coloque tambem "pai" com o id da tarefa-mae.
- "dono" e o nome de quem executa, entre:
$linhasDonos
  Briefing de tarefa de outra pessoa e escrito por voce na descricao, completo, sem deixar decisao em aberto.
Reuniao ou compromisso que existe como tarefa no ClickUp vai em "blocos" com "clickup_id" (para poder ser marcado como feito). "fixos" (inicio, fim, titulo) e so para o que nao tem tarefa, como almoco.
Ponha no plano "agenda_impoe": uma frase do que as campanhas impoem a este dia. Bloco de tarefa com prazo final leva "prazo_final": "AAAA-MM-DD".
Trabalhos do guardiao: se estado.md tiver uma secao "Do guardiao" com um item cuja data de inicio ja chegou e cuja condicao esta cumprida (confira nos arquivos que o item cita, por exemplo decisoes.md), faca esse trabalho agora: grave o RASCUNHO no arquivo de memoria que o item indica, sem criar nada no ClickUp, e troque no item "a fazer" por "rascunho pronto em <arquivo>". Se a condicao nao estiver cumprida, diga em uma frase no campo aviso o que falta. Coloque no plano um aviso de que o rascunho esta pronto para a pessoa aprovar.
Fora isso, nao crie nem altere nada no ClickUp ou em outro lugar. Nao decida estrategia nem sugira temas, ganchos ou briefing de conteudo: o guardiao so reserva e protege tempo.
No fim, responda em ate 6 linhas: o que colocou, o que deixou de fora e por que.
"@

$env:CLAUDECODE = $null
Set-Location $pasta
# Achar o claude.exe de verdade (npm, instalador oficial ou extensão do VS Code) e fixar o modelo: sem isso o plano diário usaria o padrão
# da conta de quem instalou, que pode ser um modelo várias vezes mais caro. GUARDIAO_MODELO troca (o painel usa a mesma variável).
$claude = Get-ClaudeEstado
if (-not $claude.Ok) {
    "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm') plano de $alvo ===`r`nNão achei um Claude Code que execute: $($claude.Erro)" | Out-File $log -Append -Encoding utf8
    exit 1
}
$exeClaude = $claude.Comando[0]; $preClaude = @(); if ($claude.Comando.Count -gt 1) { $preClaude = @($claude.Comando[1..($claude.Comando.Count - 1)]) }
$modelo = if ($env:GUARDIAO_MODELO) { $env:GUARDIAO_MODELO } else { 'claude-sonnet-5-5' }
$saidaClaude = & $exeClaude @preClaude -p $prompt --model $modelo --add-dir $memoria --allowedTools "Read,Write,Glob,Skill" --max-turns 25 --output-format text 2>&1
"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm') plano de $alvo ===" | Out-File $log -Append -Encoding utf8
$saidaClaude | Out-String | Out-File $log -Append -Encoding utf8

# Limite de uso do Claude (ou da conta): a chamada não fez o plano e o que está no arquivo é só a base. Antes isso passava em silêncio.
# Marca o plano para ser refeito sozinho depois (manter_planos.py) e avisa a pessoa no próprio plano.
if (($saidaClaude | Out-String) -match 'session limit|usage limit|rate limit|limit reached|hit your') {
    "--- limite de uso do Claude: plano fica só com a base e será refeito ---" | Out-File $log -Append -Encoding utf8
    try {
        $pl = [System.IO.File]::ReadAllText($planoCaminho, $utf8) | ConvertFrom-Json
        $pl | Add-Member -NotePropertyName refazer_motivo -NotePropertyValue 'limite de uso do Claude' -Force
        $pl | Add-Member -NotePropertyName aviso -NotePropertyValue 'Este plano está só com a semana combinada: não consegui refiná-lo agora (limite de uso do Claude). Ele será refeito sozinho quando o limite voltar.' -Force
        [System.IO.File]::WriteAllText($planoCaminho, ($pl | ConvertTo-Json -Depth 6), $utf8)
    } catch { "não consegui marcar o plano para refazer: $($_.Exception.Message)" | Out-File $log -Append -Encoding utf8 }
    exit 3
}

# A mesma conferência da conversa (sobreposição, removidos, semana, prazo final): antes, o plano automático era gravado sem trava nenhuma.
# Reprovado: uma correção com os problemas apontados. Reprovado de novo: volta o plano base, com aviso.
$conf = & $py (Join-Path $pasta 'voz\plano_base.py') --conferir $planoCaminho 2>&1
if ($LASTEXITCODE -ne 0) {
    "--- conferência reprovou ---`r`n$($conf | Out-String)" | Out-File $log -Append -Encoding utf8
    $correcao = "O plano que voce gravou em $planoCaminho foi reprovado na conferencia. Corrija so isto e grave de novo, sem mexer no resto:`n$($conf | Out-String)"
    $saida2 = & $exeClaude @preClaude -p $correcao --model $modelo --add-dir $memoria --allowedTools "Read,Write" --max-turns 10 --output-format text 2>&1
    $saida2 | Out-String | Out-File $log -Append -Encoding utf8
    $conf = & $py (Join-Path $pasta 'voz\plano_base.py') --conferir $planoCaminho 2>&1
    if ($LASTEXITCODE -ne 0 -and (Test-Path $copiaBase)) {
        "--- reprovou de novo: volta o plano base ---`r`n$($conf | Out-String)" | Out-File $log -Append -Encoding utf8
        $base = [System.IO.File]::ReadAllText($copiaBase, $utf8) | ConvertFrom-Json
        $base | Add-Member -NotePropertyName aviso -NotePropertyValue "O plano automático não passou na conferência e voltei para a semana combinada. Ainda falta decidir: $((Get-Content $dossie -Encoding UTF8 | Select-Object -First 6) -join ' ')" -Force
        [System.IO.File]::WriteAllText($planoCaminho, ($base | ConvertTo-Json -Depth 6), $utf8)
    }
}

# Revisor sem contexto (voz\revisor.py): só roda em dia muito apertado ou replanejamento (tarefa nova, atraso, pedido). Aponta, não reescreve.
# Reprovado: UMA rodada de correção pelo gerador; se ainda reprovar, o plano fica e os pontos abertos vão para o aviso.
$argsRev = @('--plano', $planoCaminho, '--data', $alvo)
if ($temDossie) { $argsRev += @('--dossie', $dossie) }
if ($Replanejar) { $argsRev += '--replanejar' }
$rev = & $py (Join-Path $pasta 'voz\revisor.py') @argsRev 2>&1
if ($LASTEXITCODE -eq 1) {
    "--- revisor reprovou ---`r`n$($rev | Out-String)" | Out-File $log -Append -Encoding utf8
    $correcaoRev = "Um revisor independente apontou problemas no plano que voce gravou em $planoCaminho. Corrija SO isto e grave de novo, sem mexer no resto, mantendo o formato e o status sugerido:`n$($rev | Out-String)"
    $saidaRev = & $exeClaude @preClaude -p $correcaoRev --model $modelo --add-dir $memoria --allowedTools "Read,Write" --max-turns 10 --output-format text 2>&1
    $saidaRev | Out-String | Out-File $log -Append -Encoding utf8
    $conf = & $py (Join-Path $pasta 'voz\plano_base.py') --conferir $planoCaminho 2>&1
    if ($LASTEXITCODE -ne 0 -and (Test-Path $copiaBase)) {
        "--- depois do revisor o plano reprovou na conferência: volta o plano base ---`r`n$($conf | Out-String)" | Out-File $log -Append -Encoding utf8
        Copy-Item $copiaBase $planoCaminho -Force
    }
}
