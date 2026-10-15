# Testes do guardião por voz

Rodar sempre com o Python do ambiente do guardião, a partir da pasta `voz`: `.venv\Scripts\python.exe testes\<arquivo>.py`.
Cada teste sobe um servidor próprio (porta 8769 a 8774, nunca a 8767 do guardião de verdade), um Edge sem janela e um ClickUp **falso**: nada toca no ClickUp de verdade.
Ao terminar, `limpeza_teste.py` fecha o Edge de teste e apaga as pastas temporárias `gv_*` (cada perfil do Edge ocupa centenas de MB; sem isso o disco C: já encheu uma vez).
As capturas de tela ficam em `testes\capturas`.

| Arquivo | O que cobre |
|---|---|
| `teste_plano.py` | edição do plano (mover, editar, remover, adicionar, desfazer), conflitos e aprovação com ClickUp falso (28). Sem navegador |
| `teste_revisao.py` | cérebro: marcas, permissões, "sim" para aprovar, abertura do dia (plano lido tarefa a tarefa, Esc pula, pedido de ok, execução com incentivo, plano montado na abertura), microfone aberto (45). Sem Claude |
| `teste_preferencias.py` | preferências no servidor: padrão, validação, gravação, evento, velocidade da voz e as opções que saíram na 0.9 (22) |
| `teste_modelos.py` | qual modelo do Claude responde: consulta curta sem horário vai para o Haiku (sem pensamento), o resto para o Sonnet; chaves `--modelo`/`--modelo-leve`, comando `--model`, registro de custo (43). Sem Claude |
| `teste_prompt_estavel.py` | prompt estável: o prompt de sistema não tem nada que muda a cada turno, é idêntico no minuto seguinte (com conversa, proposta, aviso e tarefa concluída) e o contexto vai na mensagem; o plano muda de lugar quando está em revisão (20). Sem Claude |
| `teste_v2_servidor.py` | painel novo, sem navegador: modo execução, avisos de tempo e respostas, extensão, adiamento com motivo, tempos por tipo, calibragem de 30 dias, POPs, sessão da janela, preferências novas, comandos locais de voz e as marcas `{{estender}}` e `{{adiar}}` (88). Sem Claude |
| `teste_v2_tela.py` | painel novo no Edge sem janela: Home em dois estágios, execução, aviso de tempo, concluir com comentário, adiar com motivo, fala, foco, ação e proposta do guardião, Dia, Planejador, Calibragem, POPs, preferências, revisão e teclado (72). Capturas em `capturas\v2_*.png` |
| `v2_base.py`, `v2_sonda.py`, `v2_fotos.py` | base dos testes do painel novo (pasta temporária, ClickUp falso, relógio do teste, Edge por CDP), sonda de uma página e capturas da abertura, da janela compacta e do celular |
| `teste_escuta.py` | escuta sem microfone: fala longa não é cortada, pausa de quem pensa não encerra, estalo não conta, Esc e clique no microfone cancelam, frases que a transcrição inventa no silêncio são descartadas e a prévia não manda silêncio para o Groq (50). Sem Groq e sem Claude |
| `teste_versao.py` | sem navegador: nome da pessoa vindo do config, pendências e trazer tarefa atrasada para hoje, guardião completo em segundo plano (Claude de mentira), versão instalada e publicada (pasta e repositório git local), o `atualizar.ps1` numa pasta de teste e a janela compacta por cima das outras (74) |
| `teste_versao_tela.py` | no Edge sem janela: botão de versão nova, cartão com as notas, atualizar, versão à vista nas preferências, "Esc cancela", clique no microfone cancelando, aviso do guardião completo e a janela compacta pedindo para ficar por cima (24) |
| `teste_layout_tela.py` | no Edge sem janela: barra do topo recolhida (desce com o cursor, com o ícone do menu e some ao sair), data e hora acima da bolinha, palco usando a largura toda de uma janela larga (e voltando a 1440 na janela antiga), painel de detalhes mais largo, sem vazar para os lados e com os botões fixos, barras de rolagem do app, e a revisão do plano sem cartão vazio (24) |
| `teste_claude.py` | como o guardião acha e chama o Claude Code: instalador oficial, npm (claude.cmd), npm fora do PATH, extensão do VS Code, versão antiga com node, atalho quebrado, nada instalado, e se o que foi achado executa (21) |
| `teste_janela_painel.py` | o painel abre sempre no Edge como janela de aplicativo (sem perfil novo e sem opção que mexa no navegador), sem Edge no Chrome, sem os dois numa aba, o Edge deste computador é achado, a limpeza do perfil antigo sem mexer num perfil em uso (33) |
| `teste_rota_agenda.py` | roteador da agenda: nível 1, 2 e 3, janela de cada tipo, data segura, extensão, marco crítico, não cabe com saídas, tarefa longa em partes, alertas |
| `teste_plano_base.py` | plano da manhã por código, quando chamar o Claude e o dossiê que ele recebe |
| `teste_conferencia_plano.py` | conferência do plano: sobreposição, removidos, semana, regras de conteúdo |
| `teste_checar_config.py` | verificador de configuração depois da atualização |
| `teste_popup.py` | o aviso próprio com a janela de verdade (sem som): no canto, por cima, sem roubar o foco e sem barra de tarefas, um substitui o outro, some sozinho; a rota `/popup`, o Iniciar só da tarefa de agora e o `avisos.ps1` com a notificação do Windows de reserva (17) |
| `teste_tocador.py` | a velocidade da voz muda sem mudar o tom, e a placa de som de verdade (tocando silêncio) acompanha a posição, a troca de velocidade e a parada (14) |
| `teste_catalogo_pops.py` | POPs da escola: lidos da API do Supabase da escola (aqui um servidor falso local) com a chave pública e só os publicados, cache, último catálogo guardado quando a rede cai, troca pelo `config.json`, instalar em Meus POPs, e o arquivo do pacote leva só chave pública (15) |
| `teste_acoes_rapidas.py` | sem o Claude: "concluí" direto ou perguntando na dúvida, mais tempo, adiar, motivo perguntado e anotado, regras locais no prompt do modo rápido e o replanejamento quando o atraso passa de 30 minutos e o dia não tem folga (26) |
| `teste_posts_etapas.py` | bloco de ideias concluído: as reservas de copy e design viram subtarefas da mãe do post, sem duplicar nem criar tarefa solta (8). ClickUp falso |
| `teste_duplicadas.py` | tarefa que já existe no ClickUp não é criada de novo: título igual vira a mesma, mesmo assunto com outras palavras é avisado, tarefas irmãs (carrossel A e B, copy e design) continuam separadas (6). Sem ClickUp |
| `teste_acao_falha.py` | ação por voz que não deu certo: ele diz que não conseguiu (qual tarefa e por quê), espera a ação terminar, avisa o modelo para não afirmar o contrário, pergunta quando a pessoa não pediu e o "sim" vale, e cala se a janela foi fechada. Sem Claude, sem áudio, sem ClickUp (16) |
| `teste_controle_fala.py` | a voz só toca com a resposta inteira, numa saída só; fechar a janela para a fala (e interrompe a sessão do Claude Code), voz sem janela e página recarregada não param, Esc em camadas, velocidade trocada no meio da fala, erro de login explicado, tempos por frase (48) |
| `teste_memoria.py` | as 10 últimas trocas em arquivo, reinício, horas de intervalo, resumo do dia, nova conversa, dia seguinte, prompt de sistema estável (24) |
| `teste_abertura_tela.py` | no Edge sem janela: animação em toda abertura, a primeira do dia só é gasta quando a pessoa vê, carimbo no fim da animação, espera o primeiro olhar, execução direta com o plano aprovado, `?abertura=1` (21) |
| `teste_instalacao.py` | computador novo, sem baixar nada: o que o `-Verificar` diz, o `config.json` que o onboarding gera (tratamento, voz, sessão, origem das atualizações, sem a tela antiga), as tarefas agendadas que seriam criadas, o tratamento no feminino e o programa abrindo sem a chave do Groq, só por texto, os casos de pasta com espaço, Claude Code fora do PATH e zip não extraído, e se toda biblioteca importada está no `requirements.txt` (32). Rodar no clone do repositório |
| `teste_fala.py` | o que a voz lê: link vira o título ou o domínio com o nome da página, sem https nem códigos (8) |
| `teste_sessao.py` | sem navegador e sem o Claude de verdade (usa `claude_falso.py`): modo sessão do começo ao fim, regras de permissão, conversas (nova, voltar, vencer em 3 horas), rotas da tela e a palavra de ativação que só aceita "ei guardião" (81) |
| `teste_sessao_tela.py` | no Edge sem janela: faixa da conversa, lista de conversas, aviso do conector, da skill e do agente em uso, e o cartão de permissão (27) |
| `janela_real.py` | conferência manual: abre a janela compacta no Edge de verdade por alguns segundos e mede se ficou por cima, no tamanho e no canto certos (6) |
| `teste_diretivas.py` | interpretação das marcas `{{...}}` (11). Com `--real`, pergunta ao Claude de verdade o que ele emite (só lê, gasta assinatura) |

Dica: a tela de teste abre com `?semabertura=1` para pular a abertura; sem isso, ela roda (~7 s).

Os testes de tela abrem um Edge sem janela, que desenha por software e atrasa o primeiro quadro das animações: por isso eles esperam as transições acabarem antes de medir (`assentar()` no teste de layout), e o navegador de teste liga `Emulation.setFocusEmulationEnabled` e desliga `CalculateNativeWinOcclusion`. Sem isso, com a tela do Windows bloqueada ou em descanso, o Chromium dá a janela como coberta (`visibilityState = hidden`) e as animações param no instante zero: as medidas saem de uma tela no meio do caminho e o teste falha de um jeito diferente a cada rodada. Rode os testes de tela um de cada vez: eles usam portas fixas.

Os testes de tela fixam o relógio do servidor em 12:00 e usam blocos de horário fixo, para não dependerem da hora em que rodam (isso já quebrou perto da meia-noite). Nenhum deles toca em `preferencias.json` de verdade.
