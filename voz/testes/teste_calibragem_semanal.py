"""Calibragem semanal (2026-10-15): pergunta só com amostra, no máximo 3 por semana, sempre com número; só no fim de semana; a resposta vira ação
(medição tira registro da média; desvio vira linha de regras.md); resposta a pergunta que não existe é recusada."""
import json
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import calibragem_semanal as cs

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHA"), nome, "" if ok else extra)
    falhas += 0 if ok else 1


oper = tempfile.mkdtemp()
os.makedirs(os.path.join(oper, "calibragem"))
sabado = date(2026, 10, 17)
segunda = date(2026, 10, 12)


def ev(dia, titulo, frente, plan, real, conf=True):
    return {"data": dia, "tipo": "conclusao", "titulo": titulo, "frente": frente, "planejado": plan, "real": real, "confirmado": conf}


eventos = [ev("2026-10-15", "Encaixar ideias", "Conteúdo", 45, 1), ev("2026-10-15", "Config Sr Studio", "Agência", 38, 1),
           ev("2026-10-13", "Narrativa 1", "Stories", 5, 26), ev("2026-10-13", "Narrativa 2", "Stories", 5, 26), ev("2026-10-14", "Narrativa 3", "Stories", 12, 35),
           ev("2026-10-14", "Design A", "Design", 60, 58), ev("2026-10-14", "Design B", "Design", 60, 61), ev("2026-10-14", "Design C", "Design", 60, 59)]
with open(os.path.join(oper, "calibragem", "eventos.jsonl"), "w", encoding="utf-8") as f:
    for e in eventos:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")
with open(os.path.join(oper, "tempos.json"), "w", encoding="utf-8") as f:
    json.dump({"tipos": {"Conteúdo": {"registros": [{"data": "2026-10-15", "titulo": "Encaixar ideias", "planejado": 45, "real": 1, "confirmado": True}], "media": None}}}, f)

ps = cs.analisar(oper, sabado)
confere("acha a hipótese de medição (2 tarefas em 1 minuto) e o desvio de Stories", [p["tipo"] for p in ps] == ["medicao", "desvio"], [p["tipo"] for p in ps])
confere("a pergunta de medição traz o número e as tarefas", "2 tarefas" in ps[0]["texto"] and "Encaixar ideias" in ps[0]["texto"])
confere("a de desvio traz frente, amostra e os dois tempos", "Stories" in ps[1]["texto"] and "3 tarefas" in ps[1]["texto"] and ps[1]["real"] > ps[1]["planejado"] * 2)
confere("Design (desvio pequeno) não gera pergunta", all("Design" not in p["texto"] for p in ps))

with open(os.path.join(oper, "calibragem", "eventos.jsonl"), "w", encoding="utf-8") as f:
    f.write(json.dumps(ev("2026-10-14", "Narrativa 1", "Stories", 5, 26)) + "\n" + json.dumps(ev("2026-10-14", "Narrativa 2", "Stories", 5, 26)) + "\n")
confere("amostra pequena (2 registros) não gera pergunta", cs.analisar(oper, sabado) == [])
with open(os.path.join(oper, "calibragem", "eventos.jsonl"), "w", encoding="utf-8") as f:
    for e in eventos:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")

confere("em dia útil não gera nem mostra", cs.gerar_se_sabado(oper, segunda) is None and cs.contexto(oper, segunda) == "")
cs.gerar_se_sabado(oper, sabado)
ctx = cs.contexto(oper, sabado)
confere("no sábado o contexto traz as perguntas, a marca e o pedido de uma por vez", "UMA por vez" in ctx and "{{calibrar:ID|" in ctx and "medicao-2026-W42" in ctx, ctx[:200])
primeira = os.path.getmtime(cs._caminho(oper, sabado))
cs.gerar_se_sabado(oper, sabado)
confere("gera uma vez só por semana", os.path.getmtime(cs._caminho(oper, sabado)) == primeira)

ok, nota = cs.registrar_resposta(oper, "id-que-nao-existe", "sim", sabado)
confere("resposta a pergunta inexistente é recusada", not ok)
ok, nota = cs.registrar_resposta(oper, "medicao-2026-W42", "sim, fiz fora e marquei depois", sabado)
tempos = json.load(open(os.path.join(oper, "tempos.json"), encoding="utf-8"))
reg = tempos["tipos"]["Conteúdo"]["registros"][0]
confere("medição respondida com sim: o registro sai da média", ok and reg["confirmado"] is False and reg.get("descartado") is True, (nota, reg))
ok, nota = cs.registrar_resposta(oper, "desvio-stories-2026-W42", "era story rápido, só abrir a caixinha", sabado)
regras = cs.regras_texto(oper)
confere("desvio respondido vira linha em regras.md com o motivo dela", ok and "Stories" in regras and "story rápido" in regras, regras)
confere("depois de responder tudo, o contexto some", cs.contexto(oper, sabado) == "" and cs.pendentes(oper, sabado) == [])
sys.exit(1 if falhas else 0)
