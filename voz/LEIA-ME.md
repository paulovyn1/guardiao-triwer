# Guardião por voz e painel

Programa que fica escutando o microfone ("Ei guardião"), conversa por voz ou por texto e mostra o painel em `http://localhost:8767/v2/`.
Roda na pasta `voz\` dentro da pasta operacional do guardião. Só Windows.

| Arquivo | O que é |
|---|---|
| `guardiao_voz.py` | escuta, transcreve, pergunta ao Claude e fala. É o programa que fica ligado |
| `hud_servidor.py` | servidor local do painel: plano, eventos ao vivo e ações no ClickUp |
| `guardiao_v2.py` | modo execução, avisos de tempo, calibragem de 30 dias e POPs |
| `guardiao_janela.py` | fixa a janela compacta por cima das outras, no canto da tela |
| `guardiao_atualizacao.py` | versão instalada e aviso de versão nova |
| `guardiao_sessao.py` | modo sessão: a conversa como sessão do Claude Code (processo aberto, lista de conversas, permissões e o que a tela mostra de cada ferramenta) |
| `hud2\` | o painel (veja o LEIA-ME de lá) |
| `nativo.py` | carrega a escuta e a voz por caminho relativo, para funcionar quando o nome do usuário do Windows tem acento |
| `fala.py`, `pronuncias.exemplo.json` | como o texto vira fala. O instalador copia o exemplo para `pronuncias.json`: ajuste as suas ali |
| `abrir_guardiao_v2.bat` | liga o programa (ou reinicia, se o código mudou) e abre a janela. É o que o atalho da área de trabalho chama |
| `criar_atalho.ps1` | cria o atalho Guardião na área de trabalho, com o ícone |
| `definir_chave_groq.bat` | guarda a chave gratuita do Groq, com o passo a passo na tela |
| `ouvir_vozes.bat` | toca as três vozes do guardião para escolher (a escolhida vai em `agente.voz` do `config.json`) |
| `diagnostico.bat` | confere cada peça (Claude, voz, escuta, microfone, Groq, janela), mede onde o tempo vai e escreve `logs\diagnostico.txt` |
| `janela_painel.py` | abre o painel no Edge, como janela de aplicativo, no perfil da pessoa (sem Edge, o Chrome; sem os dois, uma aba), e apaga a pasta do perfil que as versões antigas criaram |
| `visao_semana.py`, `rota_agenda.py` | a semana inteira no contexto; onde uma tarefa cabe (hoje, na semana ou mais para frente), por conta, chamado pelo `onde_cabe.ps1` |
| `plano_base.py`, `conferencia_plano.py` | o plano da manhã montado por código; a conferência de qualquer plano antes de gravar |
| `checar_config.py` | depois de uma atualização, confere se o `config.json` tem os campos que as versões novas usam |
| `popup.py` | o aviso do guardião na tela (preto e dourado, no canto, sem roubar o foco), usado pelo `avisos.ps1` e pelo painel escondido |
| `tocador.py` | toca a resposta inteira numa saída só (sem picotar) e muda a velocidade no meio da fala sem mudar o tom (1x, 1,5x, 2x) |
| `controle_fala.py`, `latencia.py` | parar a fala quando a janela fecha; os tempos de cada resposta em `logs\latencia.jsonl` |
| `memoria_conversa.py` | as últimas 10 trocas em arquivo e o resumo do dia (modo rápido) |
| `conferir_instalacao.py` | confere de verdade se a escuta, a voz e o painel funcionam. O instalador roda no fim |
| `parar_guardiao.bat` | desliga o programa |
| `iniciar_guardiao.bat` | liga o programa com o terminal aberto, para ver o que ele escreve (pare antes o que estiver em segundo plano) |
| `ver_painel_novo_demo.bat` | painel com um dia de exemplo, sem microfone, Claude nem ClickUp |
| `testes\` | testes que não tocam em nada de verdade (veja o LEIA-ME de lá) |

## Instalar

Dois cliques no `instalar.bat` da pasta do guardião, ou `powershell -ExecutionPolicy Bypass -File <pasta da skill>\scripts\instalar_painel.ps1`. O instalador cria o ambiente do Python em `voz\.venv` (com um Python próprio, baixado para `voz\.ferramentas`), baixa o modelo de escuta para `voz\modelo` e a voz para `voz\kokoro`. Com `-Verificar` ele só diz o que falta.

O que precisa existir no computador além disso:

1. Comando `claude` (Claude Code), com a skill `guardiao-triwer` instalada e configurada. É ele que pensa.
2. Chave gratuita do Groq (`definir_chave_groq.bat`). A transcrição da fala usa o Whisper do Groq. Sem ela o programa abre do mesmo jeito, com o microfone desligado e a conversa por texto.
3. O Microsoft Edge, para a janela do painel (vem com o Windows 10 e 11). Sem ele, o Chrome; sem os dois, o painel abre numa aba do navegador padrão.

Nenhum dado da pessoa fica nesta pasta do repositório. O que é dela (`preferencias.json`, `pronuncias.json`) nasce no computador dela e a atualização não toca.
