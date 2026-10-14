# Onboarding do guardião

Roda uma vez, no primeiro uso (quando `memoria.md` da skill ou `config.json` não existem), e de novo se a pessoa pedir "reconfigurar". Ao fim existem: o painel e a voz instalados na pasta operacional, o `config.json`, a pasta de memória com `perfil.md`, `semana-base.md` e `equipe.md` preenchidos, o token do ClickUp e a chave do Groq gravados, o painel abrindo pelo atalho da área de trabalho e, se a pessoa aceitar, as tarefas agendadas do Windows.

Todo comando de script deste roteiro leva `-ExecutionPolicy Bypass`: sem isso o Windows recusa rodar scripts em muitos computadores.

## Etapa 0: o painel (antes de qualquer pergunta)

O painel é o aplicativo do guardião: mostra o plano, escuta "Ei guardião", fala e age no ClickUp. Ele precisa de arquivos grandes (cerca de 500 MB), então começa a ser instalado já, enquanto a entrevista acontece.

1. Rodar `powershell -ExecutionPolicy Bypass -File "<pasta da skill>\scripts\instalar_painel.ps1" -Verificar` e ler as linhas `chave=valor`: `pasta_operacional`, `painel_instalado`, `chave_groq`, `token_clickup`, `claude`, `config`.
2. `painel_instalado=nao`: instalar em segundo plano e seguir para a abertura sem esperar: `powershell -ExecutionPolicy Bypass -File "<pasta da skill>\scripts\instalar_painel.ps1" -Quieto`. Leva de 5 a 10 minutos e não pede nada à pessoa. Avisar em uma frase que o painel está sendo baixado enquanto vocês conversam.
3. Se o script disser que a skill não traz a pasta `voz\`, a pessoa instalou só os textos da skill: pedir que ela dê dois cliques no `instalar.bat` da pasta do guardião que baixou e avise quando terminar.
4. A pasta operacional é a que o `-Verificar` mostrou. Não oferecer outra, a não ser que a pessoa peça.

## Abertura (obrigatória, antes da primeira pergunta)

Dizer isto à pessoa, com as suas palavras mas sem suavizar:

"Vou te fazer muitas perguntas e vou insistir quando a resposta for curta ou genérica. Não é desconfiança. O guardião só vai ser tão bom quanto o que você me contar agora: cada horário protegido, cada regra de energia e cada jeito seu de travar vem das suas respostas. Se você responder rápido ou no automático, vai ganhar um gestor genérico que erra o seu dia. Se responder com atenção e com situações reais, vai ganhar um que conhece você. Separe uns 30 a 40 minutos sem pressa. E a primeira semana é de calibragem: cada vez que eu errar o seu dia e você me corrigir, a correção vira uma regra escrita, e eu melhoro na sua frente."

Se a pessoa disser que está sem tempo, propor remarcar. Não rodar o onboarding pela metade.

## Regras da entrevista

1. Um bloco por mensagem, no máximo 4 perguntas por bloco. Esperar a resposta antes do próximo.
2. Não perguntar o que a pessoa já disse na conversa ou o que dá para ver em arquivo (CLAUDE.md, memórias, Notion dela). Ler antes.
3. **Pressionar de verdade.** Resposta que não passa no teste abaixo não fecha a pergunta: voltar com uma pergunta mais fechada, até 3 rodadas por ponto. Depois da terceira, registrar como HIPÓTESE e seguir.
   - Teste da resposta: tem uma situação real (quando, o que aconteceu, o que a pessoa fez)? Tem número ou horário? Dá para o guardião agir com ela amanhã?
   - Respostas que reprovam: "depende", "normal", "às vezes", "de manhã rendo mais", "tenho muita coisa", "sou organizada", "mais ou menos".
   - Como voltar: "me dá um dia em que isso aconteceu", "que horas exatamente?", "o que você fez em seguida?", "isso foi na semana passada ou é o que você acha que acontece?".
4. **Não aceitar o que a pessoa quer ser.** Perguntar o que ela fez nas últimas duas semanas. Meta ("quero postar todo dia") e histórico ("postei 3 vezes em 15 dias") são dois dados diferentes e os dois vão para o perfil.
5. **Quando a pessoa concluir algo, perguntar onde isso quebra.** Quando ela concordar com a sua leitura, perguntar onde discordaria. Reconhecer só o que for preciso, nomeando o que especificamente foi bom. Sem elogio de processo ("ótima reflexão").
6. **Nomear padrões.** Quando duas respostas apontarem para o mesmo mecanismo (ex: trava sempre que a tarefa exige decidir e executar juntas), dizer o padrão em uma frase e testar: "isso descreve você?". Só entra no perfil o que a pessoa confirmar; o resto é HIPÓTESE.
7. **Ler a resposta inteira antes de pressionar.** Pressão em cima de algo que a pessoa já disse duas mensagens atrás irrita e quebra a confiança. Reler o bloco antes de cada follow-up.
8. Pressão é sobre a resposta, nunca sobre a pessoa. Sem julgar, sem tom de interrogatório: firme e curioso.
9. O que for suposição sua leva a marca HIPÓTESE no perfil e é confirmado depois.
10. Nada da pessoa é gravado, criado no ClickUp ou agendado antes do resumo da etapa 4 ser aprovado. A instalação do painel (etapa 0) não depende disso: ela só baixa o programa.
11. O token do ClickUp e a chave do Groq NUNCA passam pelo chat. A pessoa os cola só na janela dela, nos passos da etapa 1. Se ela colar um deles no chat, avisar para gerar outro e não usar o que foi colado.
12. Sem travessão, sem frase isolada por linha. Frases curtas.

## Etapa 1: o que precisa existir (conferir, sem perguntar)

Rodar e anotar o resultado:
- `[Environment]::OSVersion` e `[Environment]::Is64BitOperatingSystem`. O guardião roda no Windows 10 ou 11 de 64 bits. Fora disso, parar e avisar.
- `claude=falta` no `-Verificar`: sem o comando `claude` no computador o guardião do painel não responde e o plano automático não roda. Orientar a instalar o Claude Code (https://claude.com/claude-code) antes de continuar.
- Conector do ClickUp no Claude. Sem ele, a descoberta de listas usa o script (etapa 3) e a reprogramação no fim do dia fica manual.
- Conta no ClickUp (a gratuita serve). Sem conta, parar e pedir para criar uma lista simples antes de continuar.

**Token do ClickUp** (se `token_clickup=falta`; a pessoa faz na janela dela, não no chat):
1. Dizer onde gerar: no ClickUp, foto de perfil, Configurações, Apps, Token de API, Gerar. Endereço direto: https://app.clickup.com/settings/apps
2. Mostrar o comando, trocando `<pasta da skill>` pelo caminho real: `powershell -ExecutionPolicy Bypass -File "<pasta da skill>\scripts\configurar.ps1" -DefinirToken`
3. O comando confere o token no ClickUp antes de gravar e só diz que deu certo se o ClickUp aceitou. Esperar a pessoa confirmar.

**Chave do Groq** (se `chave_groq=falta`): é ela que transforma a fala da pessoa em texto. É gratuita e não pede cartão.
1. Pedir que a pessoa dê dois cliques em `<pasta operacional>\voz\definir_chave_groq.bat`. A janela abre a página https://console.groq.com/keys e mostra o passo a passo: entrar com a conta do Google, clicar em Create API Key, dar o nome guardiao, copiar e colar na janela.
2. A janela confere a chave no Groq antes de gravar. Esperar a pessoa confirmar.
3. Pode ficar para depois: sem a chave o painel abre e a conversa é por texto. Dizer isso e seguir, sem insistir. Se o painel ainda está baixando e o arquivo não existe, deixar este passo para a etapa 6.

## Etapa 2: entrevista (6 blocos, com pressão)

Para cada bloco, a linha "Vai para" diz onde a resposta é gravada.

**Bloco 1: quem é e o que faz.**
- Seu nome, e como você quer que o guardião fale de você: "o Rafa", "a Marina" ou só o nome? E como você quer chamar o guardião (ele pode ter nome próprio)?
- O que você vende e para quem, em duas frases.
- Liste tudo que você faz numa semana normal, sem filtrar (conteúdo, atendimento, financeiro, gravação...).
- Dessas frentes, qual gera dinheiro e qual você mais adia?
- O que, no seu negócio, é importante de verdade: o que traz dinheiro com data marcada, o que mantém você aparecendo para quem compra, e o que você entrega a alguém com data que não pode escorregar? Tem tarefa que você chama de "opcional" e que na verdade serve ao foco da semana? Me dá um exemplo.
Vai para: `config.json` (pessoa.nome, pessoa.artigo "o" ou "a" ou vazio, agente.nome); `perfil.md` (Quem é, Frentes, O que é importante, Frente de receita). Avisar: qualquer que seja o nome escolhido, a palavra para chamar pelo microfone é sempre "Ei guardião".

**Bloco 2: papéis e equipe.**
- Quem trabalha com você, e o que cada um faz?
- O que cai em você mas não é seu? De quem é?
- Alguém aprova ou revisa o trabalho de outra pessoa na sua mão (ex: você revisa posts de um editor)? Isso acontece em dias e horas fixos?
- O seu Claude consegue mandar WhatsApp (por uma skill ou conector)? Você tem agentes de IA criados no seu Claude Code que executam etapas de trabalho?
Vai para: `perfil.md` (Papéis); `equipe.md` (Donos; Canais e agentes); `config.json` (clickup.membros, clickup.prefixo_aprovacao se houver subtarefas de aprovação); `semana-base.md` (bloco de aprovações). A última pergunta decide se as regras de `references/opcionais.md` valem para esta pessoa.

**Bloco 3: relógio e vida.**
- Quais dias você trabalha? Que horas chega, almoça e para?
- Dia a dia, de segunda a domingo: onde você está (casa, escritório, fora) e até que horas trabalha naquele dia? Os dias costumam ser diferentes, então um horário único de parar não serve.
- O que repete toda semana ou todo mês e já tem horário (reunião, live, mentoria, aula)?
- O que é inegociável na sua vida fora do trabalho (horário de parar, folgas, família, casa)?
- Sábado e domingo: trabalha, e quanto?
Vai para: `config.json` (rotina); `semana-base.md` (Agenda por dia, Compromissos fixos); `perfil.md` (Vida pessoal).

**Bloco 4: energia.**
- O que drena sua energia e o que recarrega?
- Qual seu melhor horário e qual o pior (aquele em que nada rende)?
- Em que horários exatos você faz o trabalho pesado (copy, decisão, estratégia, pensar), o leve (mensagens, aprovações, design com modelo pronto) e a recarga? E quando o trabalho do dia acaba antes da hora de parar, o que a sobra deve virar (consumo de conteúdo, curso, descanso)?
- Depois de um dia pesado (mentoria, gravação, reunião longa), o que você NÃO consegue fazer?
- Me conta de um dia ruim recente: o que aconteceu, e o que você faria no mínimo para o dia não ser perdido?
- Quando você troca de uma frente para outra (conteúdo para atendimento, por exemplo), o que custa? Quantas frentes diferentes cabem num dia sem você se esgotar?
- Ideia e criatividade: nos dias em que as ideias vieram fácil, o que tinha acontecido antes (consumo de conteúdo, descanso, conversa)? E nos dias em que não vieram? Se você marca horário para ter ideia, o que acontece?
Vai para: `perfil.md` (Energia, Relógio, Faixas do dia por tipo de trabalho, Sobra do dia, Troca de frente e limite por dia, Ideias e criação, Regras de decisão: dia ruim).

**Bloco 5: cobrança.**
- Notificação funciona com você, ou você ignora? Já desligou alguma?
- Você liga o computador todos os dias? O painel do guardião pode abrir sozinho quando ele liga. Se o computador fica sempre ligado, a que horas o painel deve abrir nos dias de trabalho?
- Quando você trava numa tarefa grande, o que ajuda e o que piora?
- Prefere cobrança mais firme ou mais gentil?
- Como você decide quando está cansado, ansioso ou animado? Já tomou uma decisão de negócio nesse estado e se arrependeu? Me conta uma.
- Pedidos rápidos de outras pessoas (aprovar algo, responder uma dúvida) interrompem o que você está fazendo. Quanto tempo cada um pode esperar sem prejuízo real?
- Qual foi a pior vez que um gestor, assistente ou ferramenta errou o seu plano? O que ele fez de errado e o que você teve de refazer?
- Antes de afirmar algo sobre o seu dia (se uma tarefa está feita, se o computador está ligado, que horas você sai), o que o guardião precisa conferir em vez de supor?
Vai para: `perfil.md` (Como cobrar, Decisão e interrupções); `config.json` (rotina.abrir_tela_as, se ela deu um horário); `aprendizados.md` (a pior vez que erraram o plano dela vira a primeira linha, no formato "quando X, faça Y, teste sim ou não"; o que conferir antes de afirmar vira outra). Se notificação não funciona, confirmar que o painel ao ligar o PC é a cobrança e registrar isso.

**Bloco 6: frente de receita e tempos.**
- Quantas entregas por semana da frente que gera dinheiro você quer como mínimo (posts, aulas, propostas, vídeos)?
- Quanto tempo leva cada etapa de uma entrega (escrever, produzir, revisar)? Chute honesto.
- Em que dias e horários isso é publicado ou entregue?
- Quantas entregas devem ficar prontas à frente, como colchão?
Vai para: `perfil.md` (Frente de receita); `equipe.md` (Tempos).

**Revisão de padrões (depois do bloco 6, antes da etapa 3).**
1. Reler todas as respostas e listar de 3 a 6 padrões que aparecem em mais de um bloco (ex: "trava quando decidir e executar vêm juntos", "rende depois de consumir conteúdo", "dia pesado destrói o dia seguinte"). Cada padrão leva as duas situações reais que o sustentam, nas palavras da pessoa.
2. Apresentar um por vez e perguntar: "isso descreve você? onde isso não é verdade?". Padrão confirmado vira linha em `perfil.md`, seção "Padrões descobertos". Negado ou duvidoso, não entra.
3. Ler a conta de horário (SKILL.md, seção 3) contra o que foi dito e apontar contradições reais (ex: a meta semanal não cabe nas horas livres; a pessoa diz que protege as noites mas marcou trabalho nelas). Parceiro, não validador.
4. Perguntar: "o que eu não perguntei e deveria ter perguntado para te conhecer melhor?". Acrescentar o que vier.

## Etapa 3: ClickUp, painel e pastas

**ClickUp.** Preencher `clickup` do config.json com dados reais, nunca de memória:
- Com o conector do ClickUp: `clickup_get_workspace_hierarchy` e `clickup_get_workspace_members`.
- Sem o conector: `powershell -ExecutionPolicy Bypass -File "<pasta da skill>\scripts\configurar.ps1" -Descobrir` (lista workspaces, membros, espaços, listas e status).
- Decidir com a pessoa: o workspace; as listas em que o guardião cria tarefas, cada uma com `quando_usar` em uma frase (ex: "conteúdo e publicações", "tarefas delegadas ao time", "reuniões"); os status que contam como tarefa aberta (`status_abertos`, os nomes exatos, ex: "to do"); o prefixo das subtarefas de aprovação, se houver.
- Se a pessoa não tem nenhuma lista adequada, propor uma lista nova e criá-la só depois do ok.
- Hora das tarefas só com data: pegar uma tarefa dela com data sem hora, ler o `due_date` pela API e usar essa hora local em `hora_sem_hora` (padrão 04:00 em muitos workspaces). Se não houver tarefa para olhar, deixar o padrão e avisar que o teste da etapa 6 confere.
- Muita tarefa antiga vencida: `atrasadas_dias` (padrão 14) faz o resumo ignorar o que venceu há mais dias que isso.
- Vida pessoal e contas pessoais NÃO vão para o ClickUp compartilhado. Se a pessoa quiser contas pessoais no ClickUp, usar uma lista privada.

**Painel.** O visual é um só, igual para todos. O que a pessoa escolhe:
- **Voz do guardião.** Com o painel já instalado (`-Verificar` de novo), pedir que ela dê dois cliques em `<pasta operacional>\voz\ouvir_vozes.bat`: toca a mesma frase em três vozes, numeradas. A escolha vai em `agente.voz`: 1 = `pm_santa` (masculina, mais grave, a padrão), 2 = `pm_alex` (masculina, mais leve), 3 = `pf_dora` (feminina). Se o painel ainda está baixando, usar a padrão e dizer que dá para trocar depois.
- **Conversa com memória.** Explicar em duas frases: desligada, cada fala é respondida sozinha, rápido e barato, e o guardião lembra só das últimas trocas; ligada, a conversa do painel vira uma sessão do Claude Code, lembra de tudo que foi dito e usa os conectores, as skills e os agentes da pessoa, gastando mais do plano dela. Se ela quiser, perguntar em que pasta ela costuma usar o Claude Code e gravar em `sessao.pasta`. Quem liga e desliga é ela, no painel: Preferências, Comportamento, Conversa com memória.
- Velocidade da voz, sons, tipo de bolinha e modo leve (computador fraco) ficam em Preferências, no próprio painel. Não perguntar agora.
- O painel usa a porta 8767 do próprio computador e só aceita pedidos dele. Não precisa de internet para abrir.

**Pastas.** Operacional: a que a etapa 0 mostrou (padrão `%USERPROFILE%\Guardiao-do-dia`). Memória: padrão `<pasta operacional>\memoria`. Se a pessoa usa Obsidian, perguntar o caminho da pasta dentro do vault e marcar `memoria_em_obsidian: true`. Não usar pasta do OneDrive para a operacional (os arquivos são reescritos o tempo todo).

## Etapa 4: resumo e aprovação

1. Gravar `respostas.json` na pasta temporária da sessão, no formato de `app\config.exemplo.json` (mesmos campos que o `config.json` final; `versao`, `atualizacao`, `sessao` e `agente.voz` são opcionais).
2. Mostrar à pessoa, em linguagem simples e sem JSON: nome do guardião e como ele vai falar dela, voz, horários, equipe, listas do ClickUp e para que cada uma serve, pastas, e o que o onboarding vai criar e gravar no computador.
3. Esperar o ok. Mudança pedida: ajustar o `respostas.json` e mostrar de novo.

## Etapa 5: montar

1. `powershell -ExecutionPolicy Bypass -File "<pasta da skill>\scripts\configurar.ps1" -Respostas "<respostas.json>"`. Falha de validação lista o que falta: voltar à pergunta certa, não inventar valor.
2. Abrir `perfil.md`, `semana-base.md` e `equipe.md` na pasta de memória e preencher cada `[preencher]` com as respostas da entrevista, nas palavras da pessoa. Suposições levam HIPÓTESE. Respeitar os tetos de linhas (SKILL.md, seção 4.1). Não pode sobrar nenhum `[preencher]`: `Select-String -Path "<memória>\*.md" -Pattern "\[preencher"` deve voltar vazio.
3. Conferir o perfil contra o teste da regra 3: cada linha precisa ser acionável (o guardião consegue agir com ela amanhã) e rastreável (vem de uma situação real ou está marcada HIPÓTESE). Linha genérica ("prefere trabalhar de manhã") volta para a pessoa como pergunta.
4. Registrar o primeiro combinado em `estado.md` (data do onboarding e foco da semana, se a pessoa já souber). O `aprendizados.md` nasce com as linhas do bloco 5 e o resto vazio: a primeira semana é de calibragem.

## Etapa 6: testar e ligar

1. `powershell -ExecutionPolicy Bypass -File "<pasta da skill>\scripts\configurar.ps1" -Testar`. Deve dizer quantas tarefas abertas o ClickUp devolveu. Erro de token, workspace ou status: corrigir o `config.json` e testar de novo.
2. Se a tarefa de teste mostrou hora errada para tarefa sem hora, ajustar `hora_sem_hora`.
3. Conferir o painel: `instalar_painel.ps1 -Verificar` precisa dizer `painel_instalado=sim`. Se ainda disser `nao`, rodar a instalação de novo (ela continua de onde parou) e só mostrar o erro à pessoa se ele se repetir. Fechar o que ficou pendente da etapa 1 (chave do Groq) e da etapa 3 (voz).
4. Abrir o painel: `powershell -ExecutionPolicy Bypass -File "<pasta operacional>\voz\abrir_guardiao_v2.ps1"`. A primeira abertura leva uns 20 segundos. Dizer à pessoa, em poucas linhas, como usar: falar "Ei guardião", esperar o som e falar, ou escrever na barra de baixo; levar o cursor ao topo para ver o menu (Dia, Planejador, Calibragem, POPs, Preferências); abrir sempre pelo atalho Guardião, na área de trabalho. Para mostrar o painel cheio antes do primeiro plano: `<pasta operacional>\voz\ver_painel_novo_demo.bat` (um dia de exemplo, que não toca em nada).
5. Tarefas agendadas do Windows (o guardião funcionar sozinho): mostrar primeiro `powershell -ExecutionPolicy Bypass -File "<pasta da skill>\scripts\registrar_tarefas.ps1" -SomenteMostrar`, explicar em uma frase cada uma (plano do dia ao ligar o PC e no horário combinado; leitura do ClickUp; o guardião ligado em segundo plano, escutando; a janela do painel ao ligar o PC) e perguntar se pode criar. Só depois do ok, rodar sem `-SomenteMostrar`. Avisar: o plano automático gasta uma execução do Claude por dia útil, e o PC precisa estar ligado e na tomada para os horários rodarem.
6. Primeiro plano: seguir o modo planejar do SKILL.md para o próximo dia de trabalho e terminar pedindo aprovação, como em qualquer plano. O plano aparece no painel, e é lá que a pessoa aprova.

## Reconfigurar

Pedido de mudança depois do onboarding não refaz a entrevista: editar só o que mudou (`config.json`, `perfil.md`, `semana-base.md`, `equipe.md`), mostrar a diferença antes e, se mudou horário de rotina, rodar `registrar_tarefas.ps1` de novo. Nome do guardião, tratamento e voz: editar `agente.nome`, `pessoa.artigo` e `agente.voz` no `config.json` e reabrir o painel pelo atalho. Troca de computador: rodar o `instalar.bat` e o onboarding inteiro de novo, apontando a pasta de memória existente (os esqueletos nunca sobrescrevem o que já está lá).
