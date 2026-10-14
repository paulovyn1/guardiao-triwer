"""Qual modelo do Claude responde: consulta curta vai para o leve; planejar, escrever, agir e a saudação ficam com o padrão. Sem Claude e sem navegador."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import limpeza_teste  # noqa: E402,F401
import guardiao_voz as g  # noqa: E402

resultados = []


def confere(nome, ok, detalhe=""):
    resultados.append(bool(ok))
    print(("PASSOU " if ok else "FALHOU ") + nome + (f" -> {detalhe}" if detalhe and not ok else ""))


P, L = g.MODELO_PADRAO, g.MODELO_LEVE
confere("o padrão é o Sonnet 5.5 e o leve é o Haiku 4.5", P == "claude-sonnet-5-5" and L == "claude-haiku-4-5-20251001", (P, L))

g.CONVERSA.clear()
g.PROPOSTA = None
g.REVISAO = None

# consulta curta, só de leitura e sem conta de horário: leve
for frase in ["o que é a tarefa do relatório", "me fala do bloco das dez", "qual o prazo da tarefa da Marina", "como eu começo a tarefa do contador",
              "quem é o dono da tarefa do roteiro", "me explica o bloco dos stories"]:
    m, motivo = g.escolher_modelo(frase)
    confere(f"leve: '{frase}'", m == L, (m, motivo))
# o que envolve relógio ficou com o padrão (o Haiku errou conta de horas e "o que tenho agora" na bateria)
for frase in ["o que eu tenho agora", "qual é o próximo bloco", "que horas é a reunião das duas", "quanto tempo falta pro almoço", "tem alguma coisa atrasada",
              "o que tenho amanhã", "quanto falta pra acabar o expediente"]:
    m, motivo = g.escolher_modelo(frase)
    confere(f"padrão (horário): '{frase}'", m == P and ("horário" in motivo or "pendências" in motivo), (m, motivo))

# agir, escrever, planejar: padrão
for frase, esperado in [("conclui a tarefa do relatório", "concluir"), ("reabre a tarefa da Marina", "reabrir"), ("anota que o cliente aprovou", "comentar"),
                        ("cria uma tarefa pra ligar pro contador", "criar"), ("move a reunião pra três horas", "mover"), ("tira o bloco da tarde", "remover"),
                        ("pode aprovar o plano", "aprovar")]:
    m, motivo = g.escolher_modelo(frase)
    confere(f"padrão ({esperado}): '{frase}'", m == P and esperado in motivo, (m, motivo))
for frase in ["me ajuda a planejar a semana", "o que você acha de começar pelo relatório", "escreve uma legenda pro post", "será que eu consigo terminar tudo hoje",
              "por que você colocou isso de manhã", "reorganiza o meu dia"]:
    m, motivo = g.escolher_modelo(frase)
    confere(f"padrão (pensar): '{frase}'", m == P, (m, motivo))
m, _ = g.escolher_modelo("um dois três quatro cinco seis sete oito nove dez onze doze treze quatorze quinze dezesseis dezessete dezoito dezenove vinte vinte e um vinte e dois vinte e três vinte e quatro vinte e cinco vinte e seis vinte e sete vinte e oito vinte e nove trinta e um")
confere("fala muito comprida vai para o padrão", m == P)
confere("a abertura do dia não chama o Claude: a saudação saiu do escolher_modelo", "saudacao" not in g.escolher_modelo.__code__.co_varnames)

# estado da conversa
g.REVISAO = {"inicio": time.time(), "ultimo": time.time()}
m, motivo = g.escolher_modelo("o que é a tarefa do relatório")
confere("durante a revisão do plano, até a consulta vai para o padrão", m == P and "revisão" in motivo, (m, motivo))
g.REVISAO = None
g.PROPOSTA = {"tipo": "criar", "dados": {}, "quando": time.time()}
m, motivo = g.escolher_modelo("sim")
confere("com proposta esperando o sim, vai para o padrão", m == P and "proposta" in motivo, (m, motivo))
g.PROPOSTA = None
g.CONVERSA[:] = [(time.time(), "conclui a tarefa do relatório", "O que foi feito?")]
m, motivo = g.escolher_modelo("revisei o texto e mandei pro cliente")
confere("a resposta a 'o que foi feito?' continua com o padrão (a intenção veio da fala anterior)", m == P and "concluir" in motivo, (m, motivo))
g.CONVERSA.clear()

# chaves
g.MODELO_LEVE = "nenhum"
m, motivo = g.escolher_modelo("o que é a tarefa do relatório")
confere("modelo leve desligado: tudo no padrão", m == P and "sem modelo leve" in motivo, (m, motivo))
g.MODELO_LEVE = ""
m, _ = g.escolher_modelo("o que é a tarefa do relatório")
confere("modelo leve vazio também desliga", m == P)
g.MODELO_LEVE = L
g.MODELO_PADRAO = "outro-modelo"
m, _ = g.escolher_modelo("conclui a tarefa")
confere("--modelo troca o padrão", m == "outro-modelo")
g.MODELO_PADRAO = P

# o comando leva o --model certo
cmd, _ = g.comando_claude("oi", streaming=False, modelo=L)
confere("o comando do Claude leva --model do modelo escolhido", cmd[cmd.index("--model") + 1] == L and "--effort" in cmd, cmd)
cmd, _ = g.comando_claude("oi", streaming=False)
confere("sem escolha, o comando usa o padrão", cmd[cmd.index("--model") + 1] == P, cmd)

# o modelo leve responde sem pensamento estendido (o Haiku pensava 10 a 36 s mesmo com --effort low)
_, env = g.comando_claude("oi", streaming=False, modelo=L)
confere("no modelo leve o pensamento fica desligado (MAX_THINKING_TOKENS=0)", env.get("MAX_THINKING_TOKENS") == "0", env.get("MAX_THINKING_TOKENS"))
_, env = g.comando_claude("oi", streaming=False, modelo=P)
confere("no modelo padrão o ambiente não muda", "MAX_THINKING_TOKENS" not in env or env["MAX_THINKING_TOKENS"] == os.environ.get("MAX_THINKING_TOKENS"), env.get("MAX_THINKING_TOKENS"))
g.MODELO_LEVE = "nenhum"
_, env = g.comando_claude("oi", streaming=False, modelo=L)
confere("com o modelo leve desligado, nada de variável extra", env.get("MAX_THINKING_TOKENS") == os.environ.get("MAX_THINKING_TOKENS"), env.get("MAX_THINKING_TOKENS"))
g.MODELO_LEVE = L

# o registro de custo
tmp = limpeza_teste.pasta_temporaria("gv_oper_modelos_") if hasattr(limpeza_teste, "pasta_temporaria") else None
import tempfile  # noqa: E402
tmp = tempfile.mkdtemp(prefix="gv_oper_modelos_")
g.OPER = tmp
g.registrar_chamada(L, "consulta curta", {"total_cost_usd": 0.0123, "usage": {"input_tokens": 10, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 5, "output_tokens": 40}, "duration_ms": 1500})
import json  # noqa: E402
linha = json.loads(open(os.path.join(tmp, "logs", "modelos.jsonl"), encoding="utf-8").read().splitlines()[0])
confere("o registro guarda modelo, motivo, custo, tokens e tempo", linha["modelo"] == L and linha["custo_usd"] == 0.0123 and linha["entrada"] == 115 and linha["saida"] == 40 and linha["ms"] == 1500, linha)

# ---- toda chamada ao Claude do guardião fixa o modelo ----
import re  # noqa: E402

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIZ_APP = os.path.dirname(AQUI) if os.path.exists(os.path.join(os.path.dirname(AQUI), "gerar_plano.ps1")) else os.path.join(os.path.dirname(AQUI), "app")
fontes = [os.path.join(AQUI, n) for n in os.listdir(AQUI) if n.endswith(".py")] + [os.path.join(RAIZ_APP, n) for n in os.listdir(RAIZ_APP) if n.endswith(".ps1")]
sem_modelo, sem_prioridade = [], []
chamadas_achadas = 0
for caminho in fontes:
    with open(caminho, encoding="utf-8-sig") as f:
        texto = f.read()
    for m in re.finditer(r'("-p"|"--print"|\s-p\s+\$)', texto):
        chamadas_achadas += 1
        if "--model" not in texto[m.start():m.start() + 700]:
            sem_modelo.append(f"{os.path.basename(caminho)}:{texto.count(chr(10), 0, m.start()) + 1}")
        if caminho.endswith(".py") and "FLAGS_CLAUDE" not in texto[m.start():m.start() + 2200] and not os.path.basename(caminho).startswith("teste"):
            sem_prioridade.append(f"{os.path.basename(caminho)}:{texto.count(chr(10), 0, m.start()) + 1}")
confere("toda chamada ao Claude (voz, sessão, guardião completo, resumo do dia e plano diário) leva --model: nenhuma usa o padrão da conta",
        chamadas_achadas >= 5 and not sem_modelo, (chamadas_achadas, sem_modelo))
confere("e todo Claude lançado pelo programa roda abaixo do normal (a voz, gerada neste computador, não pode ficar sem CPU quando os conectores arrancam)",
        not sem_prioridade, sem_prioridade)

print(f"\n{sum(resultados)}/{len(resultados)} verificações passaram")
sys.exit(0 if all(resultados) else 1)
