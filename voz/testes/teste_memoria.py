"""A memória do guardião no modo rápido (0.7.0), sem Claude de verdade: as últimas 10 trocas ficam em arquivo e voltam junto da pergunta (inclusive depois de um
reinício e de horas de intervalo, no mesmo dia), o resumo do dia é feito pelo Claude quando a pessoa fica uns minutos parada, "nova conversa" zera tudo e o resumo
não passa para o dia seguinte."""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import limpeza_teste  # noqa: E402,F401
import hud_servidor as h  # noqa: E402
limpeza_teste.fixar_relogio(h)
import guardiao_voz as g  # noqa: E402
import memoria_conversa as m  # noqa: E402

resultados = []


def confere(nome, ok, detalhe=""):
    resultados.append(bool(ok))
    print(("PASSOU " if ok else "FALHOU ") + nome + (f" -> {detalhe}" if detalhe and not ok else ""))


tmp = tempfile.mkdtemp(prefix="gv_oper_mem_")
h.OPER = tmp
g.OPER = tmp
with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
    json.dump({"pessoa": {"nome": "Rafa Lima", "artigo": "o"}}, f)
m.esquecer_cache()
agora = time.time()

# ---------------- guarda e devolve as últimas 10 ----------------
for i in range(1, 13):
    m.lembrar(f"pergunta {i}", f"resposta {i}", agora - (13 - i) * 60)
texto = m.bloco("Rafa")
confere("as 10 últimas trocas voltam junto da pergunta", "pergunta 12" in texto and "pergunta 3" in texto and "pergunta 2\n" not in texto and "pergunta 1\n" not in texto, texto[:200])
confere("em ordem, com o nome da pessoa e o do guardião", texto.index("Rafa: pergunta 3") < texto.index("Rafa: pergunta 12") and "Guardiao: resposta 12" in texto)
confere("o arquivo existe na pasta de conversas", os.path.exists(os.path.join(tmp, "conversas", "memoria_rapida.json")))

# ---------------- reiniciar o programa ----------------
m.esquecer_cache()
g.CONVERSA.clear()
confere("depois de um reinício (memória do programa vazia), o guardião ainda lembra pelo arquivo", "pergunta 12" in m.bloco("Rafa") and len(m.recentes()) == 10)
g.CONVERSA.clear()
g.lembrar("e a da Marina?", "A da Marina é para sexta.")
bloco = g.bloco_conversa()
confere("o programa de voz monta o bloco da conversa a partir do arquivo", "pergunta 12" in bloco and "e a da Marina?" in bloco and bloco.startswith("CONVERSA RECENTE"), bloco[:120])
g.lembrar("(Rafa abriu o app)", "Bom dia, Rafa.")
confere("lembrar() do programa grava em arquivo (não só em memória)", any(t[1] == "e a da Marina?" for t in json.load(open(os.path.join(tmp, "conversas", "memoria_rapida.json"), encoding="utf-8"))["trocas"]))

# ---------------- horas de intervalo ----------------
m.esquecer_cache()
estado = json.load(open(os.path.join(tmp, "conversas", "memoria_rapida.json"), encoding="utf-8"))
for t in estado["trocas"]:
    t[0] -= 4 * 3600  # a última fala foi há 4 horas
json.dump(estado, open(os.path.join(tmp, "conversas", "memoria_rapida.json"), "w", encoding="utf-8"))
m.esquecer_cache()
confere("depois de mais de 3 horas sem falar, as trocas não vão mais junto (a conversa recomeça)", m.recentes() == [] and m.bloco("Rafa") == "")
m.lembrar("pergunta nova", "resposta nova")
confere("a conversa nova começa só com o que foi dito depois", len(m.recentes()) == 1)

# ---------------- resumo do dia ----------------
m.zerar()
chamadas = []


def claude_falso(pedido):
    chamadas.append(pedido)
    return "Ficou combinado mover a reunião do Rafael para 15h. Falta responder o cliente Marcos."


for i in range(1, 4):
    m.lembrar(f"pergunta {i}", f"resposta {i}", agora - 3000 + i)
confere("com poucas trocas novas, o resumo não gasta uma chamada", not m.resumir(claude_falso, "Rafa") and not chamadas)
m.lembrar("move a reunião do Rafael para as 15h", "Movi para as 15h.", agora - 2990)
confere("mas só depois de 5 minutos sem falar: logo depois da última troca, nada ainda", not m.resumir(claude_falso, "Rafa", agora=agora - 2990 + 60) and not chamadas)
confere("parada há mais de 5 minutos e com 4 trocas novas, o resumo é feito", m.resumir(claude_falso, "Rafa", agora=agora) and len(chamadas) == 1, chamadas)
confere("o pedido ao Claude traz as trocas e as regras do resumo", "move a reunião do Rafael" in chamadas[0] and "sem travessão" in chamadas[0] and "RESUMO ANTERIOR:\n(nenhum)" in chamadas[0], chamadas[0][-300:])
bloco = m.bloco("Rafa")
confere("o resumo vai junto das trocas, com o aviso de que é automático", "RESUMO DO DIA" in bloco and "mover a reunião do Rafael" in bloco and "resumo automático" in bloco and "CONVERSA RECENTE" in bloco, bloco[:300])
confere("sem trocas novas, não chama de novo", not m.resumir(claude_falso, "Rafa", agora=agora + 600) and len(chamadas) == 1)
for i in range(5, 9):
    m.lembrar(f"outra {i}", f"resposta {i}", agora - 1000 + i)
chamadas.clear()
m.resumir(claude_falso, "Rafa", agora=agora + 600)
confere("com trocas novas, o resumo é atualizado a partir do anterior", chamadas and "RESUMO ANTERIOR:\nFicou combinado" in chamadas[0] and "outra 5" in chamadas[0] and "move a reunião" not in chamadas[0].split("TROCAS NOVAS:")[1], chamadas)
m.esquecer_cache()
confere("o resumo também sobrevive ao reinício", "mover a reunião do Rafael" in m.resumo())

# ---------------- falha do Claude ----------------
for i in range(10, 15):
    m.lembrar(f"mais {i}", f"resposta {i}", agora - 500 + i)
antes = m.resumo()
confere("se o Claude falhar, o resumo antigo fica como está", not m.resumir(lambda p: None, "Rafa", agora=agora + 1200) and m.resumo() == antes)
chamadas.clear()
confere("e ele só tenta de novo depois de uns minutos (não insiste a cada 30 s)", not m.resumir(claude_falso, "Rafa", agora=agora + 1210) and not chamadas)
confere("a exceção do Claude não derruba o vigia", (m.esquecer_cache() or True) and not m.resumir(lambda p: (_ for _ in ()).throw(RuntimeError("caiu")), "Rafa", agora=agora + 5000))

# ---------------- nova conversa ----------------
m.esquecer_cache()
m.lembrar("a", "b")
g.CONVERSA.append((time.time(), "x", "y"))
g.comando_local("nova conversa")
confere("'nova conversa' (modo rápido) zera as trocas e o resumo", m.bloco("Rafa") == "" and m.resumo() == "" and not g.CONVERSA)

# ---------------- dia seguinte ----------------
m.lembrar("pergunta de ontem", "resposta de ontem")
estado = json.load(open(os.path.join(tmp, "conversas", "memoria_rapida.json"), encoding="utf-8"))
estado["dia"] = "2020-01-01"
estado["resumo"] = "resumo de ontem"
json.dump(estado, open(os.path.join(tmp, "conversas", "memoria_rapida.json"), "w", encoding="utf-8"))
m.esquecer_cache()
confere("no dia seguinte o resumo (e as trocas) de ontem não valem mais", m.resumo() == "" and m.bloco("Rafa") == "")

# ---------------- o prompt de sistema continua estável: a memória vai na mensagem, não no prompt ----------------
m.lembrar("pergunta A", "resposta A")
sistema1 = g.prompt_sistema()
m.lembrar("pergunta B", "resposta B")
confere("o prompt de sistema não muda quando a conversa muda (o cache do Claude continua valendo)", sistema1 == g.prompt_sistema())
confere("a conversa vai junto da pergunta", "pergunta B" in g.mensagem_do_turno("e agora?") and "pergunta A" in g.mensagem_do_turno("e agora?"))

# ---------------- o resumo de verdade usa o modelo leve e não gasta ferramenta nem conector ----------------
capturado = {}


class Saida:
    stdout = json.dumps({"result": "Resumo de teste.", "is_error": False, "total_cost_usd": 0.002, "usage": {}})


def executa_falso(cmd, **kw):
    capturado["cmd"], capturado["env"] = cmd, kw.get("env", {})
    return Saida()


import guardiao_sessao as gs  # noqa: E402
gs.COMANDO = ["claude-de-teste"]
g.subprocess.run = executa_falso
resposta = g._chamar_resumo("resuma")
cmd = capturado["cmd"]
confere("o resumo é pedido ao modelo leve, sem ferramentas, sem conectores e sem pensamento",
        resposta == "Resumo de teste." and cmd[0] == "claude-de-teste" and "--tools" in cmd and cmd[cmd.index("--tools") + 1] == "" and "--strict-mcp-config" in cmd
        and cmd[cmd.index("--model") + 1] == g.MODELO_LEVE and capturado["env"].get("MAX_THINKING_TOKENS") == "0", cmd)

print(f"\n{sum(resultados)}/{len(resultados)} verificações passaram")
sys.exit(0 if all(resultados) else 1)
