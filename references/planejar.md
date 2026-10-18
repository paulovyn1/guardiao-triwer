# Montar e mexer no plano

Leia quando a conversa for montar, refazer ou mexer no plano do dia ou da semana, encaixar tarefa, dar prazo, ou explicar por que algo saiu ou entrou.

**Quem faz a conta é o motor da agenda, você julga.** `voz\motor_agenda.py` (pasta operacional) monta hoje e os próximos dias por código: fixos, tarefas com hora, fila por prazo, consumo antes da copy, stories na meta, nada depois da hora de parar, e o que não cabe vira a pergunta "estender o dia ou renegociar o prazo?". Para saber se algo cabe, rode o motor ou `onde_cabe.ps1`; não faça a conta de cabeça. As regras abaixo são o que o motor aplica e o que você usa para julgar, explicar e corrigir quando o motor não sabe (tarefa sem tempo medido, entrega sem POP, decisão de prioridade).

## 3. A conta de horário (antes de dizer "cabe" ou "não cabe")

- Dia de trabalho: de `rotina.chegada` a `rotina.fim` do config.json, nos dias de `rotina.dias_trabalho`. Tudo que não é compromisso fixo é horário de trabalho. Almoço em `rotina.almoco` (se um compromisso fixo cair nele, mover o almoço uma hora antes ou depois, sem cortá-lo, e avisar). O horário de parar do `perfil.md` vale por padrão; hora extra só entra como proposta explícita depois das alternativas da hierarquia abaixo, sujeita à aprovação da pessoa.
- Compromissos fixos, janelas e regras de cada dia: `semana-base.md`.
- Zona morta e melhor horário: `perfil.md`. Na zona morta, só tarefa leve, operacional, recarga e aprovações.
- Dia de evento pesado (mentoria, reunião longa, gravação, o que o `perfil.md` listar como dreno): sem tarefa estratégica nem criação nova.
- Depois de reunião que drena: só tarefa leve ou operacional. Trabalho que recarrega vai para depois.
- Dia sem trabalho e fim de semana: o que o `perfil.md` e a `semana-base.md` disserem. Achar horário em dia de trabalho primeiro e dizer quando o fim de semana foi a única saída.
- Conta pessoal curta (menos de 5 minutos): bloco de 5 min, agrupado com outras tarefas leves.
- **Faixas do dia.** Trabalho pesado (copy, decisão, estratégia, pensar) só cai nas faixas que o `perfil.md`, seção "Faixas do dia por tipo de trabalho", marca como boas. O resto do dia leva o que essa seção indica para as outras faixas.
- **O dia vai até a hora de parar daquele dia** (`semana-base.md`, "Agenda por dia"). Plano que termina antes está errado: a sobra tem o destino da seção "Sobra do dia" do `perfil.md`, com horário marcado.
- **Quando o tempo não basta, refaça o plano nesta ordem:** (1) retire de hoje o que não precisa acontecer hoje e marque outro dia; (2) reduza o escopo e o tempo de uma tarefa, mantendo uma entrega útil; (3) só se ainda faltar tempo, proponha trabalhar até mais tarde, com a hora extra identificada e sujeita ao ok da pessoa. Preserve o que já foi concluído e os compromissos fixos. Falta de tempo nunca é motivo para devolver o pedido sem uma proposta concreta. Stories não encolhe por o dia estar cheio: primeiro sai do dia o que pode ir para outro; o dia de captação é a válvula da semana apertada; só sem nenhuma tarefa remanejável o tempo de stories diminui. Hora extra de até 2 horas vira a pergunta "você prefere estender o dia ou renegociar o prazo?"; acima disso, renegociar o prazo com quem combinou.
- Fim de semana só em dose pequena, como último recurso e só se o `perfil.md` permitir. Antes, conferir se um dia útil absorve.
- Fazer a conta dia a dia, descontando compromissos fixos, e mostrar a conta junto com a conclusão.
- **Stories todo dia de trabalho (só se `rotina.stories` está no config; o onboarding pergunta e a pessoa decide).** O TIPO do dia vem primeiro e define o tempo, que pode ser quebrado em vários blocos curtos (15 min ou menos) espalhados pelo dia, antes de tarefa que dispute o horário: sequência normal = 30 min (10 telas, pelo menos 2 dias por semana); respostas da caixinha = 45 min (12 telas); captação de leads = 15 min (3 telas), um dia por semana. Divulgação (replay, convite) não conta. O código define o tipo pelo padrão da semana (seg normal, ter caixinha, qua normal, qui captação, sex caixinha), completa o plano e confere.
- **Quem manda na data é o guardião, não o ClickUp.** O prazo do ClickUp, sobretudo de tarefa criada por automação (copy e design de post), é só sugestão: o guardião replaneja para os objetivos serem alcançados. Quatro classes (código em `travas.py`; listas e tags em `config.json`, `rotina.travas`): **fixa** (reunião, aula, compromisso com hora de outra pessoa: data e horário não mudam), **prazo máximo** (entrega, combinado com cliente, marco de campanha: pode vir antes, nunca depois, porque mudar exige renegociar), **estabelecida** (o guardião já avaliou e marcou aquela data: fica, salvo necessidade) e **sugestão** (todo o resto, que é dele). Etapa de post (sugestão) termina até o dia anterior à postagem e entra na agenda do melhor jeito (copies juntas, designs juntos, copy antes do design); relatório só 24h depois. Aprovado o plano, a data nova vai para o ClickUp. A data que o próprio guardião marcou (estabelecida) passa pela mesma conferência: se quebra uma regra, ele a refaz. Com `rotina.posts` no config (dias de post e meta de "gordura", posts prontos à frente), enquanto a gordura está abaixo da meta a criação à frente é prioridade; ao alcançá-la, propor dia fixo para copies e para designs.

## 3.1 Prioridade: a matriz, antes de montar qualquer plano

Classificar cada tarefa e campanha antes de pensar em horário. O plano segue a classificação, nunca a ordem em que as tarefas chegaram.
- **Importante** = o que `perfil.md`, seção "O que é importante", diz: gera caixa com data, gera visibilidade ou entrega algo com data. Seção vazia: essa é a única pergunta do plano.
- **Urgente** = folga de 2 dias úteis ou menos. Folga = dias úteis até a data menos os dias úteis de trabalho que ainda faltam, somando as dependências.
- **Importante e urgente:** vai primeiro, nas faixas boas do dia.
- **Importante sem urgência:** ganha um bloco curto e fixo por dia, protegido, até a folga cair para 2 dias úteis ou menos. Nesse ponto vira importante e urgente. Nunca fica sem horário.
- **Urgente sem ser importante:** agrupar em bloco de tarefas leves, delegar ou responder em 2 minutos.
- **Nem urgente nem importante:** descartar ou perguntar uma vez.
- **Alavanca da campanha pública de venda:** a até 3 dias do fim, todo dia tem pelo menos um bloco que traga gente para a venda (stories, aviso no grupo, convite). A sobra do dia vai primeiro para isso, antes de tarefa que não move a campanha. Campanha interna não tem. O código confere.
- **Empate entre campanhas:** vence a de menor folga. Mesma folga: a que gera caixa.
- **Tarefa que a pessoa chama de "opcional"** é reclassificada toda vez que o plano é montado. Se serve ao foco da semana, deixa de ser opcional.
- O "Foco da semana" do `estado.md` é escrito já ranqueado por essa régua. Ela corrige a ordem, não a escreve.
- **Cliente ou tarefa que depende de um gatilho incerto** (pagamento, contrato): fica sem data até o gatilho. Anotar em "Aguardando gatilho" do `estado.md`.

## 3.2 Auditoria antes de mostrar o plano

Responder sim ou não a cada item. Qualquer não: corrigir e refazer. Plano reprovado nunca chega à pessoa.
1. Cada tarefa e campanha foi classificada em 3.1, e a ordem do plano segue a classificação?
2. Todo bloco de copy, decisão, pensar ou estratégia cai numa faixa boa do dia?
3. O último bloco termina na hora de parar daquele dia, com a sobra destinada, ou a hora extra está claramente proposta como último recurso e espera aprovação?
4. Sei onde a pessoa está e até que horas trabalha neste dia? Se não, essa é a única pergunta do plano.
5. Cada estimativa de tempo vem do `tempos.json` (3 ou mais registros confirmados; a razão da natureza ajusta o palpite) ou de uma resposta da pessoa?
6. Nenhuma tarefa "opcional" serve ao foco da semana?
7. Existe trabalho em fim de semana que um dia útil poderia absorver?
8. Cada fato que afirmo foi conferido hoje, ou está marcado como hipótese?
9. Existe pergunta minha que a memória, o ClickUp ou um arquivo responde?
10. Existe "opção A ou B" onde eu poderia recomendar?
11. Li `aprendizados.md` e nenhuma linha dele é violada pelo plano?
12. Toda campanha de importante sem urgência tem o bloco curto diário?
13. Campanha pública de venda a até 3 dias do fim tem bloco de alavanca (stories, aviso, convite) neste dia?
14. Segui as linhas da CALIBRAGEM (`calibragem\calibragem_para_o_plano.md` ou a seção do dossiê) que tocam este dia, e todo bloco que aplica uma delas leva `"aprendizado": "<id>"` e diz isso no `por_que_agora`?
15. Existe uma tarefa marcada com `"principal": true`, e só uma?

## 4. Modo planejar (dia e semana)

1. Ler as tarefas do resumo e separar: o que tem prazo real, o que é bloco recorrente, o que é conta pessoal, o que é de outro dono. **Classificar tudo na matriz (3.1) antes de qualquer horário.**
2. **Reservar primeiro a frente de receita da semana** (seção "Frente de receita" do `perfil.md`), antes de encaixar o resto. O que gera dinheiro é o que mais se adia. Meta mínima, custo por entrega, ordem de produção, cadência e colchão vêm do perfil. A produção anda uma rodada à frente: nunca se produz a entrega do dia. Se não houver horas livres na semana, avisar e dizer o que sai. Nunca deixar a frente de receita sem horário.
3. Montar blocos com dia e hora respeitando a seção 3, a energia, o limite de frentes por dia (`perfil.md`, "Troca de frente e limite por dia"), a janela de interrupções (`perfil.md`, "Decisão e interrupções") e a vida pessoal (a vida pessoal vive só no `perfil.md`, nunca no ClickUp).
4. **Dono antes de tempo.** Tarefa de outro dono (os membros do config.json) recebe veredito "delegar para X". Quem escreve o briefing é o guardião, nunca a pessoa: o que fazer, como, critério de pronto e prazo-limite, em linguagem simples, sem deixar decisão em aberto. O briefing aparece no plano e, depois do ok, vira tarefa no ClickUp já atribuída ao dono.
5. Tarefa nova recebe veredito de uma linha: fazer agora, agendar (quando), delegar para X, ou descartar.
6. Decisão e execução ficam em blocos separados. Dúvida estratégica durante a execução vai para o estacionamento, resolvida no bloco de decisão.
7. **Fechamento semanal** (dia e duração em `semana-base.md`): decide a semana seguinte, com as decisões já listadas e opções montadas. Perguntar "algo mudou na semana que vem?". Decisão grande vira tarefa com bloco próprio e prazo-limite em dia de trabalho. O que a calibragem aprendeu e o que entra fora do plano e se repete têm roteiro próprio em `references/painel.md`, seção 3.
8. Se um bloco não foi cumprido, refazer o plano e mover os seguintes. Tarefa adiada 3 vezes: perguntar o motivo, sem empurrar.
9. Dia ruim: plano mínimo, como definido em `perfil.md` ("Regras de decisão").
10. Subtarefas com o prefixo de aprovação (`aprovar: true`): ignorar a data, tratar como item do bloco de aprovações de `semana-base.md`.
11. Tarefa de ideia ou criação nunca leva hora fixa com prazo aberto: leva parada marcada e plano mínimo.
12. **Passar na auditoria (3.2) antes de mostrar.** O que reprovar é corrigido antes de a pessoa ver.
