# Painel e guardião por voz

O painel é a tela do guardião. Fica na pasta `voz\` da pasta operacional e abre em `http://localhost:8767/v2/` (atalho Guardião na área de trabalho, ou `voz\abrir_guardiao_v2.bat`). Instalar ou consertar: `powershell -ExecutionPolicy Bypass -File <pasta da skill>\scripts\instalar_painel.ps1` (com `-Verificar`, só diz o que falta).
Quem fala com a pessoa durante o dia é o programa de voz, que é uma versão rápida do guardião. Este arquivo diz ao guardião do chat o que o painel grava e o que fazer com isso.
Sem a chave do Groq (`voz\definir_chave_groq.bat`) o painel funciona do mesmo jeito, só que por texto: o microfone fica desligado.

## 1. O que o painel grava (ler só quando o assunto tocar)

- `registros\execucao_AAAA-MM-DD.json`: sessões do **modo execução**. Para cada bloco: trechos trabalhados, avisos de tempo e a resposta dada, extensões (minutos e motivo) e o resultado (concluído, adiado).
- `calibragem\eventos.jsonl`: uma linha por fato (aviso de tempo, extensão, adiamento, imprevisto, conclusão com planejado e real). Todo "por que não deu para terminar" fica no campo `motivo`.
- `calibragem\reports\AAAA-MM-DD.json`: o **report do dia** (ajustes, picos, o que funcionou, última hora), enviado pela tela ou por voz. `calibragem\estado.json` guarda o dia 1 da calibragem de 30 dias (só dias de trabalho contam).
- `tempos.json`: preenchido sozinho a cada conclusão, por tipo (a `frente` do bloco). Guarda os 10 últimos registros, marca `confirmado` quando o tempo foi medido no modo execução e calcula a média a partir de 3 confirmados. No fim do dia o guardião só confere.
- `pops\POP - nome.md` na pasta da memória: POPs criados ou instalados pela tela (mesmo modelo, com as linhas `Frente:` e `Origem:`). O catálogo da escola vem da internet (`voz\catalogo_pops.json`, só leitura, só POPs publicados), sem a pessoa configurar nada; o campo `pops.catalogo` do `config.json`, se existir, troca por outro catálogo.

## 2. O que acontece durante o dia (sem o guardião do chat)

- A pessoa entra em execução pela tela ou dizendo "vou executar agora". O relógio do bloco só conta com o modo ligado.
- **Avisos de tempo**: bloco de 60 minutos ou mais avisa aos 30 e aos 10 minutos do fim; de 25 a 59, aos 10; de 15 a 24, aos 5; e sempre no fim do horário. O guardião fala, a tela mostra as respostas e o microfone abre.
- Sempre que a tarefa não termina no horário, a voz pergunta o porquê, uma vez e sem julgar, e oferece uma ajuda prática ligada ao motivo.
- Estender muda só o fim do bloco no `plano_do_dia.json` (campo `estendido_min`). Não empurra os blocos seguintes nem mexe no ClickUp. Adiar pela tela sempre pede o motivo.
- Concluir tarefa do ClickUp pela tela pede a frase do que foi feito. Ela vira o comentário de status antes de a tarefa fechar.
- **Pendências**: quando a pessoa pergunta o que ficou para trás, a voz lê as tarefas com prazo vencido do `resumo_clickup.json`, aponta as urgentes e, com o plano ainda sugerido, traz para hoje a que ela escolher. O bloco entra com o `clickup_id` da tarefa e `"reagendado": true`: nada é duplicado, a data muda no ClickUp quando o plano é aprovado.
- **Pedido grande pela voz** (refazer o plano, mexer em plano aprovado, planejar a semana): a voz chama esta skill inteira em segundo plano, sem conversa. Regras dessa execução: não perguntar nada, não tocar no ClickUp, não editar a memória, gravar só o arquivo de plano com `"status": "sugerido"` e responder em até 6 frases curtas para serem faladas.

## 3. O que o guardião do chat faz com isso

- **Fim do dia:** ler `execucao_AAAA-MM-DD.json` e os eventos do dia junto com o registro. Bloco adiado ou estendido já vem com o motivo: usar na reprogramação e não perguntar de novo.
- **Fechamento semanal:** ler os reports e os eventos da semana (só as linhas da semana, nunca o arquivo inteiro). Procurar o que se repete: tipo de tarefa que sempre estoura, horário em que rende, motivo mais citado, tarefa adiada 3 vezes. Depois:
  1. levar o que virou padrão para "Padrões descobertos" do `perfil.md`, substituindo a linha antiga;
  2. gravar `calibragem\aprendizados.json` no formato `{"atualizado_em": "AAAA-MM-DD", "cartoes": [{"k": "rótulo curto", "v": "o aprendizado", "d": "em que se baseia"}], "dicas": ["uma estratégia prática por linha"], "mudancas": ["o que mudou no plano por causa disso"]}`, com no máximo 4 de cada. É o que a aba Calibragem mostra;
  3. usar no próximo plano: tempo do bloco pela média real do tipo, tarefa de foco no horário de pico medido, folga onde o motivo mais citado for interrupção.
- **Contra a procrastinação e a perda de foco** (nas dicas e no plano): tarefa adiada 3 vezes vira um primeiro passo de 10 minutos com hora marcada; "me distraí" pede trecho de 25 minutos com pausa; "faltou informação" vira uma subtarefa de cobrar a pessoa antes do bloco; "subestimei o tempo" corrige a estimativa do tipo. Sem tom de cobrança: o registro serve para planejar melhor.

## 4. Versão e atualização

- A versão instalada fica no arquivo `VERSION` da pasta operacional e vale para tudo: skill, scripts, voz e painel. O painel mostra o número no alto das Preferências.
- Na primeira abertura do dia o painel compara com o repositório indicado no campo `atualizacao` do `config.json` (`origem` é a pasta do clone ou o endereço do repositório, `ramo` e `pasta`). Havendo versão nova, aparece o botão "Nova versão" no topo, com as notas do `CHANGELOG.md`.
- Atualizar roda `atualizar.ps1` na pasta operacional. Ele guarda um zip do código atual em `logs\`, copia skill, scripts, voz e painel, e não toca em `config.json`, memória, planos, registros, calibragem, `tempos.json`, preferências, pronúncias nem nos arquivos pessoais da skill (`memoria.md` e extensões).
- Se a pessoa pedir para atualizar pelo chat: `powershell -ExecutionPolicy Bypass -File <pasta operacional>\atualizar.ps1`. Para só conferir: `-SoVerificar`.
- Toda mudança na skill, nos scripts, na voz ou no painel sobe o número em `VERSION` e ganha uma entrada no topo do `CHANGELOG.md`.

## 5. Configuração que o painel usa

- `pessoa.nome` e `pessoa.artigo` ("o" ou "a", opcional): como a voz chama a pessoa e como assina os comentários no ClickUp. Com "a", o guardião trata a pessoa no feminino. `agente.assinatura` troca a assinatura inteira.
- `agente.voz`: a voz do guardião (`pm_santa`, `pm_alex` ou `pf_dora`). Para ouvir as três: `voz\ouvir_vozes.bat`. A troca vale na próxima abertura do guardião.
- `rotina.abrir_tela_as`: horário em que a janela do painel abre sozinha nos dias de trabalho (tarefa agendada "tela").
- `atualizacao`: de onde vêm as versões novas. `"verificar": false` desliga a conferência diária.
- `sessao`: só para o modo sessão. `pasta` é onde o Claude Code roda (a pasta em que a pessoa já usa o Claude Code, com as skills e os agentes dela; sem o campo, a pasta operacional), `esforco` (`low` por padrão; `padrao` usa o do Claude Code), `nova_conversa_apos_horas` e `fecha_apos_min`.

## 6. Modo sessão (conversa com memória)
Ligado em Preferências, Comportamento. Com ele, a conversa do painel é uma sessão normal do Claude Code: aparece no histórico do Claude Code daquela pasta e pode ser retomada lá.
- O guardião do painel passa a ter os conectores, as skills e os agentes da pasta, e segue esta skill quando o pedido é de planejar, destrinchar ou decidir.
- Cada conversa fica em `conversas\` na pasta operacional: `indice.json` (a lista), `<id>.jsonl` (o que foi dito) e `permissoes.json` (o que a pessoa mandou permitir sempre).
- O que o painel resolve sozinho (saudação, comando de tela, aviso de tempo) chega à sessão na fala seguinte, num bloco de contexto. Não trate esse bloco como fala da pessoa.
- Ação que altera algo fora do computador passa pelo cartão de permissão do painel. No chat comum do Claude Code nada muda.
- `pops.catalogo` (opcional): endereço ou arquivo de outro catálogo de POPs, no lugar do da escola. Sem o campo vale o da escola; se nenhum POP foi publicado ainda, a aba "POPs da escola" aparece vazia.
