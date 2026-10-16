# PRD: Motor de agenda do Guardião (v0.10)

Escrito em 2026-10-16 para a Milena Camila. Serve para qualquer agente (Claude Code ou Codex) continuar a implementação. Leia este arquivo inteiro antes de mexer no código. Marque o andamento na seção "Estado" no fim.

## 1. Contexto e problema

Em 16/10/2026 o Guardião ficou o dia inteiro sem refazer o plano dela. Causas medidas nos logs (`Guardiao-do-dia\logs\voz.log`, `gerar_plano_*.log`, `modelos.jsonl`):

- **Cinco portas montam plano, cada uma com seu prompt e suas regras:** plano da manhã (`app/gerar_plano.ps1`), manutenção dos 3 dias (`voz/manter_planos.py`, laço de 15 min), pedido por voz ("guardião completo", `guardiao_voz.rodar_completo`), sessão do Claude Code (`guardiao_sessao.py`) e supervisor de atraso (`guardiao_voz` → `v2.avaliar_atraso` → `iniciar_completo`).
- **A IA faz a conta de encaixar horário:** ela erra, a conferência (`voz/conferencia_plano.py`) barra, e cada correção relia dossiê, skill e memória. O plano de 20/10 foi refeito 4 vezes em 15 e 16/10.
- **Não existe plano de mês nem de semana:** o "mês" é a lista de marcos das campanhas, lida na hora (`rota_agenda.marcos`), e a "semana" é só a soma dos planos diários. Por isso a Estrateclass de terça 20/10 ficou sem tema e sem thumb: ninguém olhava a semana seguinte.
- **Consumo de tokens:** a conversa no modo sessão gasta de 230 a 390 mil tokens de entrada por fala (US$ 7 a 11 por dia). Um pedido "refazer plano" gasta de 1 a 1,6 milhão de tokens e de 3 a 6 minutos.
- **Mudanças sem consentimento:** às 15h24 do dia 16, o supervisor replanejou sozinho, gastou 6 minutos e a tela mostrou o plano errado.

## 2. Princípios (decididos pela Milena; não reabrir)

1. **O código monta e a IA revisa.** O código faz a conta: horários, janelas, capacidade, prazos, regras. A IA faz o julgamento: desdobrar entrega sem POP, estimar tarefa nova, priorizar numa semana apertada, entender pedido em texto livre. **A IA nunca escreve horário:** ela devolve instruções e o código aplica e recalcula.
2. **Quem decide a agenda é o guardião, não a pessoa.** Ele só pergunta quando é impossível. Até 2h de hora extra, a pergunta é "você prefere estender o dia ou renegociar o prazo?". Acima disso, renegociar o prazo com quem combinou. Ele nunca pergunta "onde você quer colocar".
3. **Nada muda no plano sem ela aprovar.** Processo automático só propõe e avisa, nunca aplica.
4. **Hierarquia mês, semana, 3 dias, dia:**
   - **Mês:** todo dia 1, o guardião pergunta "quais ações e campanhas vamos fazer este mês?" e registra as prioridades.
   - **Semana:** gerada no onboarding. O dia da semana do onboarding vira o dia fixo de planejar a semana. A semana é revista quando a agenda muda.
   - **Dia:** ela aprova todo dia. Se a agenda mudar depois, o guardião mostra o que mudou e pede aprovação de novo.
5. **Economia:** uma chamada de IA por evento de planejamento, com um resumo compacto. A IA não lê arquivos e não há ciclo de correções.

## 3. Regras de agenda da Milena (viram restrições do motor)

As regras gerais ficam no código geral. As pessoais ficam ligadas só no `config.json` dela (`rotina.*`).

- **Stories:**
  - A meta é 45 min por dia de trabalho, podendo ser quebrados em blocos de até 15 min espalhados.
  - Só 1 dia por semana é de captação, com pouco stories. Ele é a válvula: numa semana apertada, o planejamento semanal joga tarefas para esse dia.
  - Fora desse dia, o tempo de stories só encolhe se não houver nenhuma tarefa remanejável. A regra antiga "dia apertado: caixinha 15 min" (`conferencia_plano.STORIES_TIPOS_PADRAO`, `minutos_apertado`) contradiz isso e deve sair.
  - O que ela fez fora do plano (contou "já fiz caixinha") conta para a meta.
- **Consumo:**
  - Um por dia, rotina fixa, sempre ANTES das copies (as ideias de post nascem dele; `rotina.regras.ideia_depois_de_consumo`, hoje só vale para bloco de "ideia" e precisa valer para copy).
  - Um 2º consumo ou descanso só entra quando não há tarefa para adiantar (equilíbrio da semana).
  - Hoje o próprio `plano_base.montar` manda preencher buraco com "consumo com a pergunta, curso ou descanso programado", e isso gerou 2 consumos que a conferência barrou. O certo é preencher adiantando tarefa de dia cheio primeiro.
- **Estrateclass (live toda terça às 13h):**
  - Tema, thumb e live agendada até a QUARTA anterior (data da live menos 6 dias).
  - Antecipação do Paulo no grupo até a QUINTA (menos 5 dias), só com o link pronto.
  - Thumb leva no máximo 30 min. Se não couber, delegar ao Paulo.
  - Já implementado em `voz/preparos.py` (config `rotina.preparos` e `clickup.eventos: ["live semanal"]`). A tarefa mãe tem a tag "live semanal" e a data da live.
- **Etapas de post:** copy antes do design. Copies juntas, depois designs juntos (`rotina.regras.etapas_em_lote`). Etapa termina antes da postagem. Relatório só 24h depois. O guardião manda na data e o prazo do ClickUp é sugestão, exceto tarefa fixa (`voz/etapas_post.py`, `voz/travas.py`).
- **Janelas e limites:** já estão no config (horário nobre, zona morta 16h-18h, hora de parar por dia, almoço, fixos da semana, fixos por data).
- **Tarefa:** um dia só por tarefa. Tarefa não some. Prazo máximo nunca é ultrapassado. Fixa não muda de horário. Rotina sem id (consumo, stories) pode repetir em vários dias.

## 4. Arquitetura alvo

```
ClickUp (ler_clickup.ps1) + campanhas (Obsidian) + preparos + posts_maes + config + tempos.json
        |
        v
[motor_agenda.py]  código puro, sem IA
  - entregas(): tudo que precisa ser feito, com prazo, esforço e tipo
  - semana(): distribui nos dias de trás para frente a partir do prazo
  - dia(): encaixa horários (reusa rota_agenda.espacos, plano_base.inserir_stories etc.)
  - devolve: rascunho {dias: {data: plano}}, nao_coube[], julgar[]
        |
        v
[revisor_ia.py]  UMA chamada (Claude ou Codex, preferencias.provedor_ia), entrada compacta <= ~15k tokens
  - recebe: rascunho resumido, julgar[], nao_coube[], regras em texto curto, perfil resumido
  - devolve SÓ JSON de instruções:
    {"acao":"estimar","id":..,"minutos":N}
    {"acao":"desdobrar","id":..,"pop":"nome"} | {"acao":"desdobrar","id":..,"subtarefas":[{"titulo","minutos","tipo","dias_antes"}]}
    {"acao":"janela","id":..,"preferir":"manha|tarde|nobre"}
    {"acao":"prioridade","id":..,"nivel":1-4}
    {"acao":"perguntar","texto":"..."}   (estender x renegociar, decisão de campanha)
    {"acao":"explicar","texto":"..."}    (o "aviso" do plano, em linguagem dela)
        |
        v
motor aplica as instruções e recalcula (no máximo 1 vez) -> proposta (status "sugerido") -> tela -> ela aprova -> ClickUp
```

Portas que passam a chamar o motor: `gerar_plano.ps1` (manhã), `manter_planos.py` (só propõe), pedido por voz de plano (`rodar_completo` quando o pedido é de plano), supervisor (só pergunta) e onboarding/semana/mês.

O que sai:
- os ciclos de correção de `gerar_plano.ps1`;
- o revisor sem contexto (`voz/revisor.py`), cujos itens viram regra do motor ou parte do prompt do revisor de IA;
- o prompt gigante do guardião completo para pedidos de plano.

A conferência (`conferencia_plano.py`, `plano_base.conferir_plano`) continua como teste do motor: a saída do motor tem que passar nela.

## 5. Etapas

### Etapa 0: guardião usável (FEITA nesta sessão; ver Estado)
- Modo sessão desligado nas preferências dela (`voz/preferencias.json`, `"sessao": false`).
- O supervisor de atraso pergunta antes de replanejar.
- `manter_planos` não chama mais IA sozinho: só monta a base por código e avisa.
- Botão Parar no cartão de progresso. Codex registrado como trabalho em segundo plano para o Esc e o botão pararem.
- PENDENTE de investigação: às 15h31 do dia 16, o plano gravado pelo Codex apareceu na tela com blocos da manhã ("Abrir a caixinha 09:26" como tarefa de agora) e a fala disse "Plano aprovado". Conferir se `plano_do_dia.json` tinha blocos no passado, se `_aplicar_planos` gravou `planos/plano_2026-10-16.json` e `plano_do_dia.json` de forma divergente, e quem aprovou.

### Etapa 1: motor_agenda.py
- Função pura `montar_semana(inicio, oper, cfg, hoje)`. Reusa `plano_base.montar`, `rota_agenda`, `preparos`, `etapas_post`, `gordura`, `inserir_stories` e `inserir_blocos_diarios`.
- Ordem de alocação:
  1. fixos;
  2. stories (meta) e consumo (antes da copy);
  3. entregas por prazo, de trás para frente, respeitando janela por tipo (copy e decisão no nobre, design à tarde, leve na zona morta);
  4. preparo da live;
  5. etapas de post em lote;
  6. preencher buraco adiantando tarefa de dia cheio;
  7. só então o 2º consumo ou descanso.
- Quando não cabe:
  - mover o que não precisa ser naquele dia;
  - usar a válvula (dia de captação);
  - encolher stories;
  - hora extra até 2h, marcada como pergunta;
  - acima disso, `nao_coube` com o prazo a renegociar.
- Estimativa: média de `tempos.json` com 3 registros ou mais. Sem histórico, vai para `julgar[]`.
- POP: se existe POP estruturado (mãe, subtarefas, prazo relativo), o código desdobra. Se não existe, vai para `julgar[]`.
- Testes: `voz/testes/teste_motor_agenda.py` com os casos reais de 13 a 16/10 (Estrateclass sem tema, 2 consumos, stories 30 x 45, copy/design alternados, consumo em dois dias, semana apertada usando a captação). A saída tem que passar em `plano_base.conferir_plano` sem graves.

### Etapa 2: revisor_ia.py
- Monta a entrada compacta e chama o provedor uma vez. Claude com `-p`, sem ferramentas, `--output-format json`. Codex com `exec --sandbox read-only`, sem precisar ler.
- Valida o JSON de instruções e devolve ao motor. Instrução inválida é ignorada e registrada no log.
- Registra o uso em `logs/modelos.jsonl` (Codex também).
- Teste: provedor falso que devolve instruções. O motor aplica e a conferência passa.

### Etapa 3: mês
- No dia 1 (ou no onboarding), a pergunta "quais ações e campanhas vamos fazer este mês?". A resposta vira prioridades nas notas de campanha (`campanhas/*.md`, cabeçalho `prioridade:`).
- `motor_agenda.carga_do_mes()`: horas por semana contra a capacidade. Semana estourada gera a pergunta "estender ou renegociar?" com antecedência.

### Etapa 4: semana e dia
- A semana é gerada no onboarding. `config.rotina.dia_planejar_semana` = dia da semana do onboarding.
- `manter_planos` passa a chamar o motor e, se o resultado difere do aprovado, grava como proposta (`planos/proposta_AAAA-MM-DD.json`) e avisa na tela. Nunca troca o aprovado.
- Aprovação diária na tela. A tela mostra exatamente o plano aprovado, com tarefa de agora pelo horário atual.

### Etapa 5: uma porta só
- `gerar_plano.ps1`: motor, revisor de IA, proposta. Sem ciclos.
- Pedido por voz de plano: o motor recebe o pedido e o revisor de IA traduz o pedido em instruções.
- Aposentar `revisor.py` e as correções de `gerar_plano.ps1`.
- Medir: tokens por evento no log e um resumo semanal do custo.

## 6. Testes (regra da Milena)

- Os testes são feitos por um agente independente (Sonnet, esforço médio), sem o contexto da conversa. Rodam só no fim de cada etapa, agrupados numa rodada única.
- Python: `Guardiao-do-dia\voz\.venv\Scripts\python.exe`, rodando de dentro de `guardiao-triwer\voz`.
- Nunca usar a porta 8767 nem matar os processos python do guardião dela.
- Falhas conhecidas, de ambiente: `teste_versao` (caminho com parêntese e "ao aprovar... criadas 2") e `teste_rota_agenda` (nível 3).

## 7. Instalação (regra)

- Commitar na branch `milena/motor-agenda`. Rodar `Guardiao-do-dia\atualizar.ps1 -Origem <clone> -Local -Forcar -SemReiniciar`.
- Reiniciar: parar os `pythonw` com `guardiao_voz.py` e rodar `Start-ScheduledTask -TaskName "Guardiao Triwer - voz"`.
- Conferir: http://127.0.0.1:8767 responde e o log mostra "Pronto".
- NÃO clicar "Nova versão" no painel: ele baixa a main do Paulo e perde estas mudanças.
- Não enviar ao GitHub sem ela pedir.

## 8. Estado

- [x] PRD escrito (16/10).
- [x] Etapa 0 (16/10, v0.10.0, instalada). Feito:
  - `sessao: false` nas preferências dela.
  - O supervisor só avisa e pergunta (`guardiao_voz.supervisionar`).
  - `manter_planos.gerar` usa só código (`pb.montar`) e plano refinado não é trocado sozinho. O caminho antigo ficou em `gerar_com_ia`.
  - Botão Parar na coluna da conversa (`col.parar` no `Main.dc.html`, chama `esc()`). O Codex registra o processo em `controle_fala.registrar_fundo` e lança `InterruptedError` ao ser parado.
  - NÃO testado pelo agente (sessão da Milena acabando). Primeiro passo de quem continuar: rodar a bateria agrupada (seção 6). Mudança proposital que pode quebrar teste antigo: `teste_manter_planos` (plano sugerido não é mais refeito por IA).
  - Plano "errado na tela" das 15h31 do dia 16, investigado: não é bug de exibição. O replanejamento gravou um bloco no passado ("Abrir a caixinha e publicar 3 stories" 09:26, que ela já tinha feito) sem `status: feito`, e por isso a tela mostra esse bloco como a tarefa de agora. Também pôs blocos até 21h54 (hora de parar 19h20). Regras que faltam no motor (Etapa 1):
    - (a) o que ela diz que já fez entra como bloco feito ou não entra;
    - (b) nada passa da hora de parar, exceto hora extra até 2h aprovada por ela;
    - (c) as cobranças do preparo (`preparos.inserir_cobrancas`) respeitam a hora de parar.
  - Ainda automático sem pergunta: `guardiao_voz` na abertura sem plano chama `iniciar_completo(PEDIDO_PLANO_DO_DIA)`, e `gerar_plano.ps1` roda pela tarefa agendada de manhã (um por dia, gera "sugerido"). Avaliar na Etapa 5.
- [ ] Etapa 1
- [ ] Etapa 2
- [ ] Etapa 3
- [ ] Etapa 4
- [ ] Etapa 5

### [FEITO] Etapa 1 (16/10, commit seguinte a 4ceb40e)
- `voz/motor_agenda.py`: `montar_semana(oper, cfg, hoje, dias=5, incluir_hoje=False)` devolve `dias`, `aprovados`, `nao_coube` (com a pergunta pronta), `julgar` (tempo padrão, a IA estima) e `problemas` (graves). Também tem `gravar()`, `resumo()` e a CLI `python motor_agenda.py [--dias N] [--gravar] [--hoje]`.
- Usa `plano_base.montar(..., so_aprovados=True)`, que agora expõe a fila estruturada em `plano_base.PENDENCIAS[iso]` (atrasada, etapa, prazo_hora com `ate`, sem_hora, preparo).
- Dia aprovado: o motor só ACRESCENTA em espaço livre e o dia volta para aprovação com aviso. Hoje fica fora, salvo com `--hoje`.
- Consertos junto:
  - `_mover_almoco` roda antes dos stories e empurra até não bater em nenhum bloco;
  - `preparos.inserir_cobrancas` cobra só no dia do limite (ou hoje) e só para live que ainda não passou;
  - `manter_planos.gerar` usa o motor.
- Verificado nos dados reais de 16/10: a thumb da #105 entra na seg 19 antes do limite (21); o Substack e as entregas de seg 19 viram pergunta de estender ou renegociar; consumo antes da copy; designs juntos.
- NÃO testado por agente ainda: rodar a bateria (seção 6) e criar `teste_motor_agenda.py` com os casos da Etapa 1.
- Falta no motor: (a) bloco do que ela já fez entra como feito; (b) 2º consumo ou descanso para preencher buraco só sem tarefa para adiantar; (c) válvula do dia de captação na semana apertada; (d) a POP desdobrando entrega.

### [FEITO] Etapa 2 (16/10)
- `voz/revisor_ia.py`:
  - `montar_prompt(resultado, cfg, marcos)` monta a entrada compacta (rascunho, julgar, não coube, marcos sem tarefa, perfil cortado em 1800 caracteres);
  - `chamar()` faz uma chamada, Claude `-p --max-turns 1` sem ferramentas, ou Codex numa pasta temporária VAZIA (dentro da operacional ele lia 200 mil tokens), e registra o uso em `logs/modelos.jsonl` com o motivo "revisor da agenda";
  - `interpretar()` valida as instruções e `ajustes()` converte para o motor.
- `motor_agenda.planejar(oper, cfg, hoje, dias, incluir_hoje, ia=True)`: o motor monta, a IA revisa uma vez se há o que julgar, e o motor remonta com os ajustes. O motor aplica `minutos`, `janela`, `prioridade` e `desdobrar` (subtarefa nova leva `lista_id` e `pai`; a de outra pessoa vai para `delegar`).
- Resultado novo: `adiados` (vence depois do horizonte, sem virar pergunta), `delegar`, `perguntas` e `explicacao`.
- Medido nos dados reais: 44 s e 16 mil tokens de entrada (antes, de 1 a 1,6 milhão e de 3 a 6 min).
- CLI: `python motor_agenda.py --dias 5 --ia [--hoje] [--gravar]`.

### [FEITO] Etapa 5, portas principais (16/10, v0.10.1)
- "Refaça meu plano" por voz ou texto: `guardiao_voz._chamar_completo` desvia para `_planejar_pelo_motor` quando o pedido bate em `PEDE_PLANO`. Ele chama `motor_agenda.planejar(incluir_hoje=True, ia=True, pedido=...)` e `gravar(..., hoje_mesmo_aprovado=True)`, e o plano de hoje volta para aprovação. `_revisar_completo` não roda no caminho do motor.
- A IA traduz o pedido: `feito`, `tirar` e `imprevisto` (com horário).
- `motor_agenda._refazer_hoje`:
  - o feito (registro do dia ou dito por ela) fica como feito;
  - stories feitos descontam minutos;
  - o que passou sem ser feito, ou ficou por baixo de um fixo, volta para a fila (leva `prazo_final` como limite);
  - o que ela mandou tirar vai para `removidos`.
- Todo dia refeito: bloco que termina depois da hora de parar volta para a fila. Item sem limite que não coube vira pergunta.
- Plano da manhã: `gerar_plano.ps1` sem `-Data`/`-Saida` roda `motor_agenda.py --hoje --ia --gravar --dias 5` e sai. O caminho antigo com IA ficou só para `-Data`.
- Codex sem leitura (`guardiao_codex.executar_sem_arquivos`, pasta temporária vazia) na conversa, no resumo do dia e no revisor da agenda. Isso vale para qualquer instalação.
- Instalação do zero:
  - `config.exemplo.json` ganhou `clickup.eventos: []`;
  - `references/onboarding.md` pergunta por evento recorrente com preparo e explica `rotina.preparos`;
  - caixinha fica em 45 min (`minutos_apertado` 45).
- Verificado em dados reais (16/10 16h40): o resto do dia saiu a partir de agora, até 19h20, com a thumb antes do limite. O que não coube virou pergunta.
- FALTA:
  - Etapa 3 (mês: pergunta das campanhas no dia 1 e carga por semana);
  - Etapa 4 (semana gerada no onboarding, dia fixo `rotina.dia_planejar_semana`, proposta quando a agenda muda);
  - aposentar `revisor.py`, os ciclos de `gerar_plano.ps1 -Data` e o supervisor chamando IA;
  - válvula do dia de captação;
  - POP estruturado desdobrando sem IA;
  - `teste_motor_agenda.py`;
  - rodar a bateria pelo agente Sonnet.

### [FEITO] Rodada de testes da v0.10.1 (16/10, agente Sonnet médio)
- Teste novo `voz/testes/teste_motor_agenda.py`: 25/25.
- Passaram 100%: codex_planos, preparos_conserto, revisao, v2_servidor, prompt_estavel, modelos, sessao, instalacao, preferencias, plano, controle_fala, memoria.
- TESTES DESATUALIZADOS A REESCREVER (o comportamento novo é o certo, decidido pela Milena):
  - `teste_conferencia_plano`, 2 testes: "em dia apertado a caixinha cai para 15 min" e "dia apertado continua apertado depois de reagendar". Agora a caixinha é 45 sempre.
  - `teste_plano_base:59`: o almoço empurrado. Agora empurra até não bater e volta ao original se não houver lugar até 15h; o cenário do teste tem um bloco às 14h, trocar os dados.
  - `teste_manter_planos`: "refaz o plano sugerido de terça". Agora só refaz plano de origem "semana combinada" ou "motor da agenda" e sem IA.
  - `teste_acoes_rapidas`, 4 testes do supervisor. Agora o supervisor só avisa e pergunta, sem chamar `iniciar_completo`.
- Ambiente (não é defeito): `teste_versao` "sem origem configurada", "ao aprovar... criadas 2" e "se o script falhar sem reiniciar... avisa" (espera de 6 s).
- Ponto de atenção para o motor: quando um compromisso longo de manhã e um bloco às 14h impedem o almoço até 15h, o almoço volta ao horário e fica sobreposto. O melhor é o motor devolver à fila o bloco que está por baixo do almoço (como faz com imprevisto).

### [FEITO] v0.10.2 (16/10)
- O botão Parar agora troca o botão de enviar (`snd-parar`, `col.parar` e `col.enviar` no `Main.dc.html`). O botão abaixo do texto de status não aparecia na tela.
- `controle_fala.ENCERRADOS` (pids encerrados pelo Esc ou pelo Parar): o Codex só diz "cancelado" se o próprio processo foi encerrado. Caso real às 16h54: a revisão da IA "cancelou" 1 s depois de começar e o motivo real se perdeu.
- `_planejar_pelo_motor` fala os blocos do resto de hoje.

### [FEITO] v0.10.3 (16/10)
- `ler_o_plano` (abertura e plano pronto) só vai para a aba Dia e diz numa frase que há plano para aprovar na barra de baixo. A leitura antiga ficou em `ler_o_plano_em_voz`, sem uso. "Ainda espera o seu ok" também não abre mais `propor_aprovacao`.
- `_planejar_pelo_motor` leva a tela para a aba Dia e termina com "confira e aprove na barra de baixo".
- Teste desatualizado de propósito: `teste_revisao` ("plano montado: lê tarefa a tarefa e pede o ok", "sem plano...", "Esc pula a leitura").
