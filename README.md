# Guardião do dia

Gestor de projetos pessoal que roda no seu computador. Ele monta o plano do dia, cria e conclui as tarefas no ClickUp, acompanha o tempo de cada bloco e conversa com você por voz ("Ei guardião") ou por texto, num painel próprio. Nas Preferências, você escolhe se Claude Code ou Codex pensa por ele. Claude continua sendo o padrão.

## O que você precisa ter

- Windows 10 ou 11.
- Claude Code (https://claude.com/claude-code), Codex CLI (https://learn.chatgpt.com/docs/codex/cli) ou ambos, conforme a sua escolha. Cada um exige seu próprio login.
- Conta no ClickUp (a gratuita serve).
- Internet na instalação e cerca de 2 GB livres no disco.

Não precisa instalar Python nem nenhum outro programa: o instalador traz tudo.

## Instalar (3 passos)

**1. Baixe a pasta do guardião** por este endereço: https://github.com/paulovyn1/guardiao-triwer/archive/refs/heads/main.zip
Depois **descompacte**: clique com o botão direito no arquivo `.zip`, escolha "Extrair tudo" e abra a pasta que aparecer. Pode ser em Downloads mesmo.

**2. Dê dois cliques em `instalar.bat`.** Se o Windows mostrar um aviso de segurança, confirme que quer executar (em alguns computadores: "Mais informações" e depois "Executar assim mesmo"). Escolha Claude, Codex ou ambos. A janela mostra o andamento e faz tudo sozinha, em 5 a 10 minutos:
- instala uma skill global para o provedor escolhido. Se escolher ambos, a pasta global do Codex é um atalho para a mesma skill global do Claude, sem duplicar o `SKILL.md`;
- instala o painel e a voz em `Guardiao-do-dia`, na sua pasta de usuário;
- abre a página do Groq e mostra como pegar a chave gratuita que liga o microfone (2 minutos, sem cartão);
- cria o atalho **Guardião** na área de trabalho.

**3. Abra o Claude Code ou o Codex e escreva: `configurar o guardião`.** É uma conversa de 30 a 40 minutos em que o guardião conhece a sua rotina, a sua equipe e o seu ClickUp. No fim ele abre o painel com o seu primeiro plano. Se escolheu ambos, faça essa configuração uma vez só: os dois usam a mesma pasta operacional e a mesma memória.

**Instalação pelo chat do Claude:** ao pedir "instale este repositório e skill" e passar o link do GitHub, peça que ele baixe o repositório e execute `instalar.ps1 -Provedores Ambos -SemPerguntas` (ou `-Provedores Codex -SemPerguntas`). Se ele rodar o instalador sem indicar o provedor, a tela pergunta; com `-SemPerguntas`, instala nos dois. É uma única instalação; não é preciso repetir o comando no chat do Codex. Depois, abra o Codex CLI e rode `codex login` uma vez, se ainda não estiver conectado. A skill global do Claude continua disponível em qualquer conversa; a do Codex aponta para ela.

Deu erro no meio ou a internet caiu? Dê dois cliques em `instalar.bat` de novo: ele continua de onde parou.

## A chave do Groq

É ela que transforma a sua fala em texto. É gratuita. O instalador abre a página certa (https://console.groq.com/keys) e mostra o passo a passo: entrar com a conta do Google, clicar em **Create API Key**, dar o nome `guardiao`, copiar e colar na janela do instalador.

Pulou esse passo? O painel funciona do mesmo jeito, por texto. Para ligar o microfone depois, dê dois cliques em `Guardiao-do-dia\voz\definir_chave_groq.bat`.

## Usar

- Abra pelo atalho **Guardião**, na área de trabalho.
- Diga **"Ei guardião"**, espere o som e fale. Ou escreva na barra de baixo.
- Leve o cursor ao topo da janela para ver o menu: o dia, o planejador, a calibragem, os POPs e as preferências.
- **Fechar a janela não desliga o guardião.** Ele segue ouvindo "Ei guardião" em segundo plano; se estava falando, para na hora. Para desligar de vez: `Guardiao-do-dia\voz\parar_guardiao.bat`.
- Sem a "Conversa com memória" (o padrão), ele lembra das últimas 10 falas e de um resumo do dia, mesmo depois de reiniciar. "Nova conversa" esquece tudo.
- Em Preferências você ajusta a voz (inclusive a velocidade), os sons e liga a conversa com memória. A versão, os serviços e o modo leve ficam à vista no alto.
- Em Preferências → Comportamento → **Quem pensa pelo Guardião**, troque Claude/Codex. O Codex usa GPT-6 Sol com esforço médio por padrão. Quem quiser outro modelo ou esforço pode configurar `GUARDIAO_MODELO_CODEX` e `GUARDIAO_ESFORCO_CODEX` nas variáveis de ambiente do Windows e reiniciar o Guardião. A troca de provedor vale no próximo pedido. A conversa com memória persistente é um recurso do modo Claude; no Codex, o painel usa as últimas trocas e o resumo do dia.
- Ao pedir um plano ao Codex, ele lê os dados e devolve a proposta ao app; o app confere e grava apenas arquivos de plano. Se a conferência reprovar, o plano anterior é preservado e o painel avisa.

## Se algo não funcionar

- **O instalador parou no meio:** dê dois cliques em `instalar.bat` de novo. Ele pula o que já está pronto e continua.
- **"A pasta ainda está dentro do .zip":** você abriu o `instalar.bat` sem extrair. Extraia o `.zip` e abra de novo.
- **O guardião não responde, só o painel abre:** confira o provedor em Preferências. Para Claude, instale e entre no Claude Code. Para Codex, instale o Codex CLI e rode `codex login` no terminal.
- **O microfone não liga:** falta a chave do Groq (`Guardiao-do-dia\voz\definir_chave_groq.bat`), ou o Windows está bloqueando o microfone. Em Configurações, Privacidade e segurança, Microfone, deixe ligado "Permitir que aplicativos da área de trabalho acessem o microfone".
- **Ele não me ouve quando chamo:** diga "Ei guardião" junto, no começo da frase, e espere o som antes de falar o resto.
- **Ele diz que atingiu o limite do plano ou que o Claude Code não está conectado:** é a conta do Claude, não o guardião. O limite volta na hora que ele informa; para entrar na conta, abra o Claude Code e faça o login.
- **Ele demora para responder, ou a voz tem pausas entre as frases:** dê dois cliques em `Guardiao-do-dia\voz\diagnostico.bat`. Ele mede o Claude, a voz e o computador, diz onde está o problema e escreve `Guardiao-do-dia\logs\diagnostico.txt`. Se pedirem, mande também `logs\latencia.jsonl`.
- **O botão de atualizar não aparece ou não funciona:** dê dois cliques em `Guardiao-do-dia\atualizar_guardiao.bat`. Ele faz o mesmo que o botão "Nova versão" e mantém a sua memória, os planos e as preferências.
- **O painel abre no Microsoft Edge, como um aplicativo:** janela própria, sem abas nem barra de endereço, separada do seu Edge: o painel tem uma pasta de navegador só dele, sem conta, sem sincronização e sem extensões, e o seu Edge (perfis, favoritos, configurações) não é tocado. Assim a animação usa a placa de vídeo e os sons da abertura tocam sozinhos, seja qual for a configuração do seu navegador. O Edge vem com o Windows; se ele tiver sido removido, o painel abre no Chrome e, sem os dois, numa aba do seu navegador.
- **Esc:** pula a animação de abertura e a leitura do plano. Com o guardião falando, o primeiro Esc corta a voz e ele segue por escrito; o segundo cancela o resto da resposta.
- **Nada disso resolveu:** abra o Claude Code e escreva "o guardião não está funcionando, confere a instalação". Ele sabe conferir o que falta.

## Atualizar e desinstalar

- **Atualizar:** quando sair versão nova, o painel mostra o botão "Nova versão" no topo. Um clique e ele se atualiza, sem mexer no que é seu.
- **Desligar o guardião:** `Guardiao-do-dia\voz\parar_guardiao.bat`.
- **Desinstalar:** peça ao Claude Code "remover as tarefas agendadas do guardião", apague a pasta `Guardiao-do-dia` (o seu perfil e os seus planos estão lá: copie antes o que quiser guardar) e a pasta `.claude\skills\guardiao-triwer`.

## O que fica no seu computador

Tudo. O plano, o perfil e as conversas ficam em `Guardiao-do-dia`. O seu áudio só sai do computador depois de você dizer "Ei guardião", e vai apenas para o Groq, para virar texto. A voz do guardião é gerada no próprio computador. As tarefas vão para o seu ClickUp, com o seu token, que fica guardado só no seu Windows. A lista de "POPs da escola" é baixada da internet (só leitura: o painel pede os POPs publicados e nada seu vai junto).
