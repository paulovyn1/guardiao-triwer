# Fechamento: concluir pelo chat, modo automático e fim do dia

Lido pelo SKILL.md (seção 6) só quando o assunto pedir.

**Concluir tarefa pelo chat:**
- Mudar o status para o tipo closed da lista (`clickup_update_task`) e gravar o início e o fim reais na própria tarefa. Sem comentário de status e sem assinatura: o ClickUp já registra quando a tarefa fechou. Só comentar se a pessoa pedir.
- **"Já concluí X":** se a pessoa disser que concluiu uma tarefa e o ClickUp ainda a mostra aberta, a fala dela é a autorização, e vale só para a tarefa que ela citou. Concluir direto, sem montar plano nem pedir ok. Contar em uma linha o que mudou e registrar no registro do dia ou no `estado.md`. Sem horário real, marcar "não confirmado" e deixar fora da média de tempo.

**Modo automático** (`gerar_plano.ps1`, no logon e no horário de `rotina.gerar_plano_as`, 1 vez por dia de trabalho): o guardião não pergunta nada, grava o `plano_do_dia.json` com `"status": "sugerido"` e nunca escreve no ClickUp. Quem cria as tarefas é o painel, quando a pessoa aprova. Única outra escrita: trabalho do próprio guardião que venceu. Se o `estado.md` tiver a seção "Do guardião" com um item cuja data chegou e cuja condição está cumprida, ele grava o rascunho no arquivo de memória que o item indica, troca "a fazer" por "rascunho pronto em <arquivo>" e avisa no plano que o rascunho espera a aprovação da pessoa. Condição não cumprida: diz no aviso do plano o que falta.

**Fim do dia, no chat, quando a pessoa chamar:**
1. Ler `registros\registro_AAAA-MM-DD.json`. O que ela concluiu o painel já concluiu no ClickUp; conferir `clickup` de cada bloco (erro aparece ali).
2. Para cada bloco NÃO concluído, reprogramar a tarefa no ClickUp (`clickup_update_task`, novo dia e hora) e refazer o plano, mostrando a mudança antes de gravar.
3. Registrar o tempo real em `tempos.json` por tipo de tarefa. Bloco sem horário real: assumir o planejado e marcar "não confirmado", fora da média. Procurar o padrão do desvio (sempre estoura um tipo de tarefa? o bloco da tarde nunca acontece?).
4. Tarefa adiada 3 vezes: perguntar o motivo. Atualizar `estado.md`.
5. Reler `aprendizados.md` e gravar o desvio de tempo (seção 7). Correção do dia que ainda não tem linha lá: escrever agora.
