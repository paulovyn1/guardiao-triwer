# Changelog: guardiao-triwer

Formato de cada entrada, sempre com a mais recente no topo:

```
## <versão> [CRITICAL] - <data>
- resumo objetivo da mudança
```

## 0.8.0 - 2026-10-13
Vem do uso diário do guardião da Milena (07 a 13/10) e do relatório que ela mandou ao Paulo. Fica em cima da 0.7.1: o que o Paulo já entregou (resolvedor do Claude, janela do Edge, memória em arquivo, saudação, abertura, status dos serviços, modelo do plano) não foi mexido.
- **Matriz de prioridade** no SKILL.md (seção 3.1): importante e urgente (folga de 2 dias úteis ou menos), importante sem urgência ganha bloco curto diário, empate pela menor folga, tarefa "opcional" reclassificada a cada plano. "Importante" vem de uma seção nova do `perfil.md`, respondida no onboarding.
- **Auditoria de 12 perguntas sim ou não** antes de mostrar o plano (seção 3.2). Plano reprovado é corrigido antes de a pessoa ver.
- **`aprendizados.md`** (seção 7): cada correção da pessoa vira "quando X, faça Y, teste sim ou não", escrita na hora, lida em toda ativação e relida no fim do dia. A regra repetida sobe para o `perfil.md` ou para um `extensoes-*.md`, nunca para o SKILL.md.
- Regras de conduta (proposta decidida em vez de "opção A ou B", fato só se conferido hoje), horário (trabalho pesado só nas faixas boas, o dia vai até a hora de parar daquele dia, sobra com destino, fim de semana só como último recurso) e reunião que existe como tarefa no ClickUp vai em `blocos` com `clickup_id`.
- Templates: `perfil.md` (O que é importante, Faixas do dia, Sobra do dia), `semana-base.md` (Agenda por dia), `estado.md` (Aguardando gatilho), `aprendizados.md` novo. O onboarding avisa que a primeira semana é de calibragem e traz as perguntas que alimentam as seções novas. A manutenção da memória saiu do SKILL.md para `references/memoria.md`.
- **O check de "feito" conclui na hora**, inclusive tarefa do ClickUp. Antes a tarefa ficava "aguardando" até a pessoa escrever uma frase, sem lembrete, e nada fechava. O comentário de status ("Atualização de status: ...", com assinatura) foi removido: o ClickUp já registra quando fechou, e o horário real de início e fim vai para a própria tarefa. Os testes `teste_v2_servidor` e `teste_v2_tela` foram ajustados para esse comportamento.
- **A ação por voz reconhece blocos com nome** (`pensar`, `copy_a`). O app só entendia `b1`, `b2`: a voz dizia "estou concluindo" e a tarefa não mudava. O prompt da voz usa `{{concluir:ID}}` sem frase.
- **Concluir sem chamar o Claude.** Fala que começa com "concluí", "terminei", "acabei", "finalizei", "fechei", "encerrei" ou "já fiz" fecha a tarefa de agora em Python, guarda o relato da pessoa na calibragem (evento `relato`) e avança. Antes, um relato longo ia inteiro para a sessão e custava cerca de US$ 0,56 e 90 mil tokens.
- **Home**: o compromisso fixo que vem antes da próxima tarefa (almoço, live, pausa) vira o foco, e a tarefa aparece como "Depois". Antes a Home pulava direto para a próxima tarefa.
- **Etapa de post vira subtarefa da tarefa mãe**, achada em Python (`voz/posts_maes.py`) com uma consulta direta ao ClickUp: só a lista de conteúdo, só os próximos dias, só `Onde = Feed` (`clickup.posts` no `config.json`; desligado sem essa chave). Bloco de criação de posts (`posts_previstos`) mede, ao ser concluído, quantos posts apareceram e grava `posts_criados` para o report. Sem vigia em segundo plano.
- **Escuta contínua virou opção** (preferência `mic_sempre_ligado`, interruptor "Escuta contínua (Ei guardião)" em Comportamento). Desligada (padrão), o microfone fica fechado: só abre quando a pessoa clica no botão dele (ou em ditar um campo) e fecha de verdade no fim da gravação, então o indicador de microfone em uso do Windows apaga. Sem "Ei guardião" e sem reabrir sozinho depois de uma pergunta. Ligada, volta ao comportamento anterior. Motivo: quem não gosta de falar com o computador não aceita um microfone aberto o tempo todo; quem gosta liga o interruptor. Vale ao vivo, sem reiniciar. Não testado com microfone real.
- `.gitignore` com `memoria.md`, `extensoes-*.md` e `.repo-path`, para arquivos pessoais não irem ao repositório.
- Não testado ainda: onboarding completo com uma pessoa real e o plano gerado com o perfil novo. O SKILL.md está com cerca de 25 KB (meta: 20 KB). O teste `teste_versao` já falhava na 0.7.1 em uma checagem ("se o script falhar sem reiniciar o guardião...").

## 0.7.1 - 2026-10-13
- **Conta do Claude no limite ou sem login.** O guardião agora fala e escreve o motivo, em português e com o dia e a hora em que o limite volta ("Você atingiu o limite semanal do seu plano do Claude. Ele volta em 17 de outubro, às 19h."). Antes ficava mudo ou mostrava "o Claude não respondeu", e a sessão ainda tentava de novo pelo outro caminho, dobrando a espera para o mesmo erro.
- **A voz não fica mais com pausas quando o computador está ocupado.** O Claude Code e os conectores que ele abre passam a rodar com prioridade abaixo do normal. Medido com a carga de uma partida dos conectores: a voz, gerada neste computador, levava 1,16 s para cada segundo de fala (mais devagar do que a fala, com pausas entre as frases) e passa a levar 0,52 s; parado, 0,41 s.
- Na pausa entre duas frases da mesma resposta, a tela diz "Ainda respondendo", em vez de "Pensando".
- O aviso de "Nova versão" funciona também para quem instalou clonando o repositório público (o guardião fica na raiz dele e a configuração antiga procurava uma subpasta).
- Depois de fechar a janela no meio de uma fala, a fala seguinte não espera 3 segundos à toa.
- Testado com o Claude de verdade: memória depois de reiniciar (pedir uma anotação, reiniciar o programa e perguntar o que foi combinado), resumo do dia, "Se apresente" no modo sessão com 8 conectores (primeira frase em 2,9 s), corte da fala no meio e a fala seguinte (1,8 s). Ainda sem teste: um computador mais fraco, com a geração de voz medida por `voz\diagnostico.bat`.

## 0.7.0 - 2026-10-13
Correções que vieram da primeira instalação em um computador de fora da equipe de desenvolvimento.
- **Claude Code instalado por npm funciona.** O guardião procurava o comando `claude` pelo nome puro, e o Windows não abre o `claude.cmd` do npm desse jeito: nenhuma fala funcionava e o instalador dizia que estava tudo certo. Agora há um só jeito de achar o Claude Code (instalador oficial, npm, npm fora do PATH ou extensão do VS Code), que confere se ele de fato executa, e vale para a voz, a sessão, o plano diário e o `-Verificar` do instalador.
- **A janela do painel não entra mais na conta Microsoft.** Medido: um perfil novo do Edge entrava sozinho na conta do Windows e ligava a sincronização de favoritos, preenchimento automático e extensões dentro da pasta do guardião (uma extensão chegou a abrir uma segunda janela). Agora a janela abre sem conta, sem sincronização e sem extensões, e o perfil antigo que já tinha entrado é apagado e recriado limpo na próxima abertura (só o perfil do painel; o Edge da pessoa e os dados dela na nuvem não são tocados).
- **Fechar a janela para a fala.** Se o guardião está falando e a última janela do painel fecha, ele para (inclusive a sessão do Claude Code, que é interrompida). O programa segue ouvindo "Ei guardião" em segundo plano. Página recarregada não corta a fala, e sem janela nenhuma (só voz) ele fala normalmente.
- **A saudação tem prazo.** Se a saudação do Claude não chega em 18 segundos, entra um "Bom dia, <nome>." local, e ela nunca mais é dita tarde, "do nada". Falhando ou não, a saudação conta como feita (não repete no próximo reinício).
- **A abertura animada só é gasta quando a pessoa a vê.** O carimbo agora é gravado quando a animação termina (ou é pulada), e uma janela que abre sozinha (tarefa agendada) espera o primeiro olhar, para a abertura e a saudação. Em Preferências, Comportamento, o botão "Rever a abertura".
- **O guardião lembra da conversa mesmo com a "Conversa com memória" desligada.** As últimas 10 trocas ficam em arquivo (sobrevivem a reinício e a horas de intervalo, no mesmo dia) e vão junto de cada pergunta. Quando você fica uns minutos sem falar, o Claude (modelo leve, uma chamada curta de uns centavos) atualiza um resumo do dia: decisões, tarefas e prazos, pendências. "Nova conversa" zera tudo, e o resumo vale só no dia em que foi feito.
- **Status dos serviços em tempo real.** Chave do Groq gravada com o guardião aberto liga o microfone em até 1 minuto, sem reiniciar; fone ligado depois e Claude Code instalado depois também passam a valer, e a tela mostra o estado de agora.
- **Erro do Claude explicado.** Sem login ou no limite de uso, a tela diz o que fazer em vez de "o Claude não respondeu". O que o Claude Code escreve de erro fica em `logs\claude_erro.log`.
- **Plano diário com modelo fixo** (Sonnet 5.5; `GUARDIAO_MODELO` troca), em vez do padrão da conta de quem instalou.
- **Instalação em disco FAT32/exFAT ou pasta de rede**: o Python do guardião vai para `%LOCALAPPDATA%\GuardiaoDoDia` em vez de falhar ou cair em silêncio no Python do sistema.
- **Ruído transcrito como palavra** ("Mãe.", "Obrigado." no silêncio) não gasta mais uma resposta.
- **Descobrir onde está a demora:** cada resposta grava em `logs\latencia.jsonl` os tempos do Claude, da geração da voz e de cada frase, e o uso do computador. Novo `voz\diagnostico.bat` confere cada peça (Claude, voz, escuta, microfone, Groq, janela), diz o que fazer e escreve `logs\diagnostico.txt` para mandar a quem ajuda. O instalador também mede a velocidade da voz neste computador.
- A sessão do Claude Code (Conversa com memória) fica aberta enquanto a janela do painel estiver aberta, em vez de fechar em 15 minutos parada: a fala depois de uma pausa não paga a partida de novo.
- Testes que acompanham o guardião (`voz\testes`): resolvedor do Claude Code, janela do Edge, controle de fala, memória, abertura, instalação e os de antes. Ainda sem teste: uma conversa completa por microfone numa máquina nova, o disco FAT32 de verdade (só simulado) e o Claude Code dela com muitos conectores.

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
