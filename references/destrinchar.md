# Destrinchar, decidir e POP

Leia quando a pessoa trouxer uma tarefa grande, uma entrega com data, disser que está travada, for decidir algo, ou quando um processo se repetir.

Em todos os casos, o primeiro passo para cada tarefa é **procurar o POP**. POP existente: usar e só encaixar na agenda. POP inexistente: destrinchar.

## Modo destrinchar (a pessoa traz uma tarefa grande)

1. Investigar o que existe (arquivos, POP, fonte citada) antes de perguntar. Fazer só as perguntas que bloqueiam.
2. **Com data fixa:** lista COMPLETA de trás pra frente, em tabela: tarefa, dono, tempo (avisando se é chute ou média), dependência, prazo-limite. Depois o conflito de capacidade, se houver.
3. **Sem data:** só a próxima camada, 3 a 6 ações pequenas com estimativa, e a lista do que fica "depende da decisão X". Quem dá prazo à tarefa sem prazo é o guardião, depois de olhar a agenda real.
4. Etapas diferentes são tarefas separadas, cada uma com seu tempo e janela (escrever e desenhar não são a mesma tarefa). Nunca uma tarefa "fazer o post".
5. A estratégia vem antes de qualquer peça de execução.
6. Se a tarefa vai se repetir, propor salvar o POP (seção 5).
7. **Tarefa mãe + subtarefas.** Demanda com mais de uma etapa ou mais de um responsável vira uma tarefa mãe na lista certa e uma subtarefa por etapa e por responsável, mesmo quando os executores são diferentes. Depois do ok, criar a mãe com `clickup_create_task`, guardar o id em `estado.md` e usar esse id no campo `pai` dos blocos novos do plano (o painel só cria tarefa de bloco, e `pai` só funciona se a mãe já existir). As subtarefas de outros donos nascem do briefing aprovado, já atribuídas ao dono. Demanda de uma etapa só e de um dono só não precisa de mãe. Sem o conector do ClickUp, as etapas viram tarefas soltas, uma por bloco.

## Bloco de decisão (a pessoa vai decidir algo)

O guardião chega com o contexto montado e a deixa decidir rápido; ela não deve explicar o projeto de novo.
1. Ler o índice `decisoes.md` (abrir o satélite do mês só das decisões que tocam o assunto), o trecho de `campanhas.md` da decisão e a tarefa no ClickUp. Não perguntar o que já está registrado.
2. Abrir em poucas linhas: o que está sendo decidido, o que já está fechado, o que essa decisão destrava (tarefas e datas) e o prazo-limite.
3. Montar 2 ou 3 opções, cada uma com o que custa e onde quebra, e uma recomendação com motivo. Nunca perguntar "o que você quer?" em aberto. Se a pessoa concluir rápido, perguntar onde discordaria.
4. Decisão de estratégia e de conteúdo é dela (regra 8): o guardião mostra opções e custos, não escolhe ideia nem tema.
5. Quando ela decidir, na hora: uma linha no índice `decisoes.md` e a entrada completa (data, decisão, por quê, o que foi descartado, o que destrava) no satélite do mês `decisoes\AAAA-MM.md`; atualizar `campanhas.md` e `estado.md`; e propor as tarefas que a decisão destrava. Criar no ClickUp só depois do ok.

## POP: onde fica e como usar

Todo POP vive em `pops\` na pasta da memória, um arquivo por processo, criado a partir de `pops\_modelo.md`. Nome do arquivo começa com `POP - `.

- Consultar: procurar pelo nome da tarefa em `pops\`. Sem varrer outras pastas.
- Criar: copiar o modelo, preencher e salvar com status "v1 em validação".
- Conteúdo: o que é, quando, etapas com dono, critério de pronto, prazo-limite relativo, tempos (em branco na 1ª execução), pontos de atenção, fontes.
- Nasce v1 e é revisado na 3ª execução, junto com a média de tempo.
- Quando descobrir um processo ou subtarefas repetíveis (em ClickUp ou conversa), propor o POP na hora, sem esperar a pessoa pedir.
