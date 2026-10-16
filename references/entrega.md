# Entrega: plano, ClickUp e painel

Leia quando for gravar um plano, definir o formato de um bloco, ligar um bloco ao ClickUp, tratar etapa ou reserva de post, ou explicar o que o painel faz sozinho.


Terminar sempre com o plano para aprovação. Depois do ok, gravar `plano_do_dia.json` na pasta operacional (formato de `plano_exemplo.json`). O painel lê esse arquivo e mostra o plano na hora. Plano de outro dia vai em `planos\plano_AAAA-MM-DD.json` e entra sozinho quando o dia chega; ele pode ser aprovado antes, com a marca de aprovar com a data, e o ClickUp recebe os horários na hora.

**Formato do bloco:**
- `id` (sempre a primeira chave), `inicio`, `fim` (HH:mm), `titulo`, `dono` (nome de quem executa, como no config.json), `frente`.
- `primeiro_passo` (a primeira ação física, pequena) e `por_que_agora`.
- `descricao`: 1 ou 2 frases simples, o que é, o que produz, quando está pronta. Se não couber em 2 frases, a tarefa está grande demais: quebrar. No painel aparece no detalhe da tarefa.
- Ligação com o ClickUp: bloco de tarefa que já existe no resumo leva `clickup_id` (nunca duplicar). Bloco novo leva `lista_id` (uma das listas de `clickup.listas` no config.json, escolhida pelo campo `quando_usar`) e, se for parte de uma tarefa existente, `pai`.
- Etapa de um post (copy, design...): `post` com o dia dele (`"quinta"` ou `AAAA-MM-DD`) e `lista_id`. Ao aprovar, o app acha a tarefa mãe do post em Python (`posts_maes.py`, lista de conteúdo com o campo "Onde" = "Feed" nos próximos dias) e cria a etapa como subtarefa dela. Nunca procurar a mãe pelo Claude e nunca criar etapa de post como tarefa solta. Liga por `clickup.posts` no `config.json`.
- Bloco de criação de posts: `posts_previstos` com quantos posts o bloco deve render. Ao concluir o bloco, o app consulta o ClickUp uma vez e grava no registro de eventos quantos posts apareceram de verdade (evento `posts_criados`), para o report perguntar o porquê da diferença. Não há consulta automática em segundo plano.
- Reserva de tempo de post sem tema: copy e design de um post que ainda não existe (a mãe só nasce quando o bloco de ideias termina) entram no plano como bloco com `reserva_post` (data da postagem, AAAA-MM-DD) e `etapa` (`Copy` ou `Design`), com título "Reserva: design de post (seg 19), tema ainda não definido", sem `lista_id`, sem `clickup_id` e sem criar nada no ClickUp. Ao concluir o bloco de ideias, o app (`posts_maes.lancar_etapas`) troca cada reserva, pela data da postagem, por uma subtarefa real da mãe nova ("Copy | título do post"), no horário que já estava reservado, e grava o evento `etapas_lancadas`. Post sem reserva e reserva sem post voltam nesse evento: tratar no fim do dia, sem inventar tema nem letra (nunca "carrossel A, B").
- Reunião ou compromisso que existe como tarefa no ClickUp (vem no `resumo_clickup.json`) vai em `blocos` com `clickup_id`, para a pessoa poder marcar Feito, informar o horário real e concluir a tarefa. `fixos` (inicio, fim, titulo) é só para o que não tem tarefa, como o almoço: na tela não tem botão nem sincroniza.

**O que o painel faz sozinho, sem o guardião do chat:**
- Ao **aprovar o plano**, cria as tarefas dos blocos novos no ClickUp (com dono, início, fim e estimativa) e grava os `clickup_id`.
- Ao **concluir** uma tarefa (o check na tela), conclui na hora no ClickUp (status do tipo closed da lista). O início e o prazo combinados ficam intactos na tarefa; o horário real vai num comentário curto e assinado ("Realizado: das 9:00 às 10:15 (1 h 15 min)."). Não pede frase. Reabrir desfaz.
- Grava `registros\registro_AAAA-MM-DD.json` a cada marcação.

**Concluir pelo chat, modo automático e fim do dia:** ler `references/fechamento.md` quando o assunto for concluir uma tarefa pelo chat (inclui "já concluí X"), o plano gerado automaticamente ou a conferência do fim do dia.
