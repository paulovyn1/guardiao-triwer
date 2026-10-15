# Changelog: guardiao-triwer

Formato de cada entrada, sempre com a mais recente no topo:

```
## <versão> [CRITICAL] - <data>
- resumo objetivo da mudança
```

## 0.9.7 - 2026-10-14
- Imprevisto entra no plano aprovado na hora, e o ClickUp acompanha.
- O guardião enxerga a semana inteira e decide se a tarefa cabe hoje, na semana ou mais para frente.
- Quando não cabe, ele mostra as saídas com datas e horas.
- O plano da manhã sai mais rápido e gasta menos do Claude.
- Depois de atualizar, ele confere se falta algum ajuste na sua configuração e ajuda a completar.
- Plano de outro dia pode ser aprovado antes, com os horários já no ClickUp.

## 0.9.1 - 2026-10-14
- O aviso de começo de tarefa ganhou a cara do guardião, com o botão Iniciar.
- Tarefa já concluída no ClickUp não é mais cobrada pelo aviso de tempo.
- Tarefa nova no ClickUp: o guardião avisa e pergunta se você quer replanejar.
- Compromisso fixo que passou do horário: ele pergunta uma vez se você fez.

## 0.9.0 - 2026-10-14
- Na primeira abertura do dia, o guardião monta o plano, lê cada tarefa e pede o ok.
- Aprovado o plano, entra em execução; a tarefa só conta a partir do Iniciar.
- A voz sai inteira, sem picotar, em 1x, 1,5x ou 2x, e o Esc corta a voz.
- O painel abre no Edge, como um aplicativo.

## 0.8.2 - 2026-10-13
- O plano automático já deixa pronto o rascunho de um trabalho do guardião que venceu.
- A skill ficou mais leve: o fechamento do dia foi para um arquivo lido só quando precisa.
- Stories, caixinha e material de aula podem ser criados direto na lista de conteúdo.

## 0.8.1 - 2026-10-13
- O aviso de versão nova ficou curto e o botão de atualizar sempre aparece.
- Mais tempo e adiar pela voz, na hora, sem gastar o plano do Claude.
- "Concluí" só pergunta quando há dúvida de qual tarefa é.
- O prazo no ClickUp fica como estava. O horário realizado vira um comentário.
- Replaneja sozinho quando o atraso não cabe mais no dia.
- Suas regras pessoais valem também na conversa rápida.
- Etapas de post viram subtarefas do post quando a ideia fica pronta.
- Novo atalho atualizar_guardiao.bat, na pasta do guardião, para atualizar sem o painel.

## 0.8.0 - 2026-10-13
- O painel abre no seu navegador, no seu perfil.
- POPs da escola prontos para instalar, sem configurar nada.
- Planos com prioridade e conferidos antes de aparecer.
- Marcar como feita fecha a tarefa na hora.
- O microfone só liga quando você clica. A escuta contínua virou opção.
- Não cria tarefa repetida no ClickUp.
- Se uma ação pela voz falha, ele avisa.

## 0.7.1 - 2026-10-13
- Avisa quando a conta do Claude está no limite ou sem login.
- Voz sem pausas com o computador ocupado.
- Volta a falar mais rápido depois de fechar a janela.

## 0.7.0 - 2026-10-13
- Funciona com o Claude Code instalado pelo npm.
- Lembra da conversa do dia, mesmo depois de reiniciar.
- Fechar a janela faz o guardião parar de falar.
- A saudação não atrasa nem se repete.
- Diagnóstico para descobrir onde está a demora.

## 0.6.2 - 2026-10-12
- Corrigido: o botão "Nova versão" (o `atualizar.ps1`) falhava para quem instalou pelo zip do repositório público, porque a origem é um endereço do GitHub e o script a tratava como pasta.
- Testado de ponta a ponta como um aluno: baixar o zip público sem login, extrair, instalar numa pasta de usuário nova, gerar a configuração e receber uma versão nova pelo endereço público.

## 0.6.1 - 2026-10-12
- Corrigido: numa instalação nova o programa não ligava, porque faltava a biblioteca `num2words` na lista do instalador. A conferência final do instalador agora importa o programa inteiro, e o instalador completa um ambiente antigo sem refazê-lo.
- Repositório público do guardião: https://github.com/paulovyn1/guardiao-triwer. Quem instala por zip passa a receber o aviso de versão nova a partir dele.
- Nome de usuário do Windows com acento ("José", "Conceição") não impede mais a escuta nem a voz de carregar. Antes a instalação parava na conferência final.
- Pasta de usuário com espaço no nome não quebra mais a janela do painel nem a tarefa agendada do guardião.
- Claude Code instalado fora do PATH (pasta `.local\bin` do usuário) é encontrado pelo guardião e pelo plano automático. Sem o Claude Code, o painel diz o que falta em vez de mostrar um erro do Windows.
- `instalar.bat` aberto de dentro do `.zip` avisa para extrair a pasta primeiro.
- O LEIA-ME da pasta virou `README.md`, com o endereço para baixar e uma seção "Se algo não funcionar".
- Clone em que o guardião está na raiz do repositório é aceito como origem das atualizações.
- Testado: instalação completa numa pasta de usuário com espaço e acento, com o programa ligando de verdade nela (painel, versão e voz), e instalação a partir do zip baixado do repositório público. Ainda sem teste: uma conversa completa com microfone numa máquina nova e o onboarding com uma pessoa de verdade.

## 0.6.0 - 2026-10-12
- Instalador de dois cliques (`instalar.bat`): copia a skill para o Claude Code, instala o painel e a voz sem precisar de Python nem de administrador, guia a chave gratuita do Groq com o endereço e o passo a passo, cria o atalho na área de trabalho e diz o próximo passo. Pode ser rodado de novo: continua de onde parou.
- `scripts\instalar_painel.ps1` instala ou conserta o painel e, com `-Verificar`, diz o que falta. O onboarding começa por ele, em segundo plano, enquanto a entrevista acontece.
- O painel é a única tela do guardião. Saíram a tela simples do plano (`servidor_tela.ps1`, `tela_modelo.html`) e as perguntas de título e cores do onboarding. No lugar, a pessoa escolhe a voz do guardião (`voz\ouvir_vozes.bat`), como quer ser tratada e se quer a conversa com memória.
- Sem a chave do Groq o painel abre do mesmo jeito e a conversa é por texto. O botão do microfone explica como ligar.
- `pessoa.artigo` = "a" faz o guardião tratar a pessoa no feminino. `agente.voz` escolhe a voz.
- Tarefas agendadas: entram a do guardião ligado em segundo plano (confere a cada 15 minutos) e a da janela do painel, no lugar da tela antiga.
- Regras que entraram na skill: comentário de status assinado antes de concluir tarefa pelo chat, "já concluí X" como autorização só para aquela tarefa, e tarefa mãe com uma subtarefa por etapa e por responsável.
- `references/opcionais.md`: cobrança de prazo por WhatsApp e delegar etapa a agente de IA, só para quem tem essas peças (seção "Canais e agentes" do `equipe.md`).
- Arquivos `extensoes-*.md` na pasta da skill passam a ser lidos junto com o `SKILL.md`: regras só daquela pessoa, que a atualização não toca.
- Todo comando de script documentado leva `-ExecutionPolicy Bypass` (o padrão do Windows recusa scripts).
- Quem instala por zip passa a receber o aviso de versão nova pelo endereço público do guardião.
- Testado: instalação limpa numa pasta vazia, com o PATH só do Windows (5 min 43 s; rodar de novo, 8 s). Ainda sem teste: o onboarding inteiro com uma pessoa de verdade.

## 0.5.2 - 2026-10-12
- A voz não lê mais endereços inteiros. Tarefa do ClickUp citada como link: só o título. Endereço solto: só o domínio e, no máximo, o nome da página. O texto da tela continua com o link.

## 0.5.1 - 2026-10-12
- A esfera ganhou o estado "trabalhando": dois pontos de luz orbitam por fora do anel enquanto o guardião usa um conector, uma skill ou um agente, ou enquanto um pedido corre em segundo plano.
- O guardião não manda mais a pessoa ir ao ClickUp resolver o que ele mesmo pode resolver: oferece e, com o sim, faz. Tarefa repetida é encerrada com a anotação de onde o trabalho segue.
- Para a pessoa o guardião é um só: ele não fala mais em "guardião completo" nem em limites técnicos da execução.
- No modo sessão, o plano de hoje gravado pela conversa é conferido e volta para aprovação, e ligar o modo com o app aberto já abre o Claude Code.

## 0.5.0 - 2026-10-12
- Modo sessão (Preferências, Comportamento, "Conversa com memória"): cada conversa vira uma sessão normal do Claude Code, num processo que fica aberto enquanto ela dura. O guardião lembra do que foi dito e pode usar os conectores, as skills e os agentes da pasta da pessoa. Desligado por padrão; o modo rápido continua igual e assume se a sessão falhar.
- Conversas: botão de nova conversa e lista das anteriores para voltar a qualquer uma (também por voz: "nova conversa", "abrir conversas"). Depois de 3 horas sem falar, a próxima fala abre uma conversa nova.
- Permissões: ler é livre; criar e alterar pedem permissão num cartão, com a pergunta em voz alta e resposta por voz, texto ou clique (com "permitir sempre"); enviar, apagar, publicar e executar perguntam todas as vezes.
- A tela diz o que o guardião está usando (conector, skill, agente, arquivo, pesquisa) e anota na resposta de onde ela veio.
- O microfone só aciona com "ei guardião" dito junto e no começo da fala. A palavra guardião solta, ou no meio de uma frase, não aciona mais.

## 0.4.0 - 2026-10-12
- Ícone novo do Guardião: a letra G feita do anel da bolinha, com o núcleo no centro, em duas cores. Vale para o atalho, a janela, a barra de tarefas e o celular.
- A barra do topo fica recolhida e só o ícone do menu aparece no canto. Ela desce quando o cursor chega à faixa de cima ou ao ícone e se recolhe quando o cursor sai.
- A data e a hora saíram da barra do topo e ficam, pequenas, acima da bolinha.
- As preferências estão em seções que abrem e fecham. Fechada, cada seção mostra um resumo do que tem dentro.
- Atalho na área de trabalho com o ícone novo: `voz\criar_atalho.ps1`.

## 0.3.3 - 2026-10-12
- O painel acompanha qualquer largura de janela, inclusive monitores ultrawide (21:9 e 32:9): o fundo e a barra do topo vão de ponta a ponta. O conteúdo cresce até 1920 de largura e, numa janela mais larga que isso, fica centralizado em vez de esticar.

## 0.3.2 - 2026-10-12
- O painel usa a largura toda da janela (o palco vai de 1440 a 1840 de largura conforme o formato da tela), sem faixas pretas dos lados. A largura a mais vai para a coluna principal e para o painel de detalhes.
- Painel de detalhes com mais respiro: mais largo quando há espaço, campos separados, texto longo e endereços quebrando linha, e os botões fixos embaixo enquanto o conteúdo rola.
- Barras de rolagem na identidade do app em todos os lugares: fio dourado fino, sem trilho e sem setas.
- Corrigido o cartão vazio que aparecia no começo da revisão do plano. Na revisão, o destaque de cada bloco acontece na lista ao lado, sem cartão no meio.

## 0.3.1 - 2026-10-12
- Com o painel aberto, o bipe do Windows não toca mais ao dizer "Ei guardião": fica só o som do painel. Sem painel, o bipe continua como aviso da hora de falar.
- Cancelar a escuta (Esc ou clique no microfone) ganhou som próprio no painel, no lugar do bipe do Windows.

## 0.3.0 - 2026-10-12
- O programa de voz e o painel entram no repositório (pasta `voz\`), sem dado pessoal: o nome da pessoa vem de `pessoa.nome` e `pessoa.artigo` do `config.json`.
- Versão única para skill, scripts, voz e painel. O painel mostra a versão instalada, confere o repositório na primeira abertura do dia e, havendo versão nova, mostra um botão discreto. `app\atualizar.ps1` troca skill, scripts, voz e painel e não toca em memória, planos, registros, preferências nem `config.json`.
- Painel: modo execução com tempo medido, avisos de tempo com o porquê de cada atraso, calibragem de 30 dias, POPs e janela compacta que fica por cima das outras janelas, no canto da tela. Detalhes em `references/painel.md`.
- Voz: a escuta não corta mais a fala longa (o teto de 14 segundos saiu e a pausa que encerra cresce com a fala), Esc ou clique no microfone cancelam a escuta, e as frases que a transcrição inventa no silêncio são descartadas.
- Voz: revisa as tarefas atrasadas, aponta as urgentes e traz para o plano de hoje sem duplicar no ClickUp. Pedido grande (refazer o plano, planejar a semana) vai para a skill inteira em segundo plano e volta como plano sugerido.
- Scripts: plano de dia futuro em `planos\`, leitura do ClickUp ignora tarefa vencida há mais de `clickup.atrasadas_dias`, `avisos.ps1` (aviso do Windows no começo de cada bloco) e tarefa agendada que funciona com usuário de domínio.

## 0.2.0 - 2026-10-09
- Onboarding com abertura obrigatória (avisa que a qualidade das respostas define a qualidade do guardião) e entrevista com pressão: teste da resposta, até 3 rodadas por ponto, histórico real em vez de intenção, nomeação de padrões.
- Novas perguntas: custo de trocar de frente, ideias e criação, decisão sob emoção, interrupções.
- Etapa de revisão de padrões antes do ClickUp: só padrão confirmado entra no perfil.
- `perfil.md` ganha as seções "Troca de frente e limite por dia", "Ideias e criação", "Decisão e interrupções" e "Padrões descobertos". O SKILL.md passa a respeitar essas seções ao planejar.

## 0.1.0 - 2026-10-09
- Primeira versão compartilhável, derivada do guardião de uso interno. Skill em revisão: não publicada para alunos.
- Dados pessoais removidos de skill, scripts, tela e memória. Tudo que varia por pessoa vem de `config.json` e dos arquivos de memória gerados no onboarding.
- Onboarding em 6 etapas (`references/onboarding.md`) e `scripts/configurar.ps1` (token, descoberta do ClickUp, geração de config e memória, atualização de scripts, teste).
- Tela com nome, título, porta e 3 cores configuráveis (paleta derivada, aceita fundo escuro).
- `scripts/registrar_tarefas.ps1` para as tarefas agendadas do Windows.
- Índice de campanhas deixou de quebrar a tabela quando há itens na caixa de entrada.
