# Donos, tempos e fatos do ClickUp de {{nome}}

Teto: 80 linhas.

## Donos
[preencher: uma linha por pessoa. Nome, o que faz, e o que NÃO recebe. Incluir {{nome}}.]
- O briefing de quem recebe tarefa é escrito pelo guardião, não por {{nome}}: o quê, como, critério de pronto e prazo-limite, sem deixar decisão em aberto.

## Canais e agentes
[preencher: por onde o Claude de {{nome}} manda WhatsApp (skill ou conector) e quais agentes de IA executam etapas, com o que cada um cobre. Sem nenhum dos dois, escrever "nenhum" e as regras de references/opcionais.md não valem.]

## Tempos (chute inicial até a 3ª execução)
| Tipo de tarefa | Tempo |
|---|---|
| [preencher] | [preencher] |

Da 1ª e 2ª vez: estimativa avisada como chute, registrar o tempo real. Da 3ª vez: média dos tempos reais, avisada ao dar o plano. Tarefa feita uma vez só não tem média: estimar por etapa.

## Fatos do ClickUp
- Workspace e listas estão em config.json (clickup). Não criar campos nem listas desnecessárias.
- Status abertos lidos pelo guardião: [preencher, igual a config.json].
- "Concluído" é sempre o status do tipo closed da lista.
- Tarefa só com data aparece em uma hora fixa na API (config.json, hora_sem_hora): significa "sem hora marcada".
- [preencher: qualquer regra própria do ClickUp de {{nome}} (tarefa recorrente, status que não conta como concluído, subtarefas de aprovação).]
