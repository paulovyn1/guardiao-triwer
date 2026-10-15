"""Edição do plano na revisão (mover, editar, remover, adicionar, desfazer), conflitos e aprovação com ClickUp falso. Sem navegador."""
import json
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import limpeza_teste  # noqa: F401
import requests  # noqa: E402
import hud_servidor as h  # noqa: E402
limpeza_teste.fixar_relogio(h)

resultados = []


def confere(nome, ok, detalhe=""):
    resultados.append(bool(ok))
    print(("PASSOU " if ok else "FALHOU ") + nome + (f" -> {detalhe}" if detalhe and not ok else ""))


tmp = tempfile.mkdtemp(prefix="gv_oper_plano_")
h.OPER = tmp
hoje = date.today().isoformat()
caminho = os.path.join(tmp, "plano_do_dia.json")


def bloco(i, ini, fim, titulo, **extra):
    return {"id": f"b{i}", "inicio": ini, "fim": fim, "titulo": titulo, "dono": "Rafa Lima", "frente": "Teste",
            "descricao": f"Descrição {i}", "primeiro_passo": f"Passo {i}", "por_que_agora": f"Motivo {i}", **extra}


def gravar_plano(status="sugerido"):
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump({"data": hoje, "status": status, "fixos": [{"inicio": "12:00", "fim": "13:00", "titulo": "Almoço fixo"}], "blocos": [
            bloco(1, "09:00", "09:30", "Primeira", clickup_id="cid1"),
            bloco(2, "10:00", "11:00", "Segunda", lista_id="L1"),
            bloco(3, "14:00", "14:30", "Terceira", clickup_id="cid3"),
        ]}, f, ensure_ascii=False)


def plano():
    return json.load(open(caminho, encoding="utf-8"))


with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
    json.dump({"agente": {"nome": "Guardião"}, "clickup": {"user_id": "1001", "listas": [{"id": "L1", "nome": "Rotineiras", "quando_usar": "tarefas rotineiras"}, {"id": "L2", "nome": "Contas a pagar"}],
                                                          "membros": [{"nome": "Rafa Lima", "id": "1001"}]}}, f)
gravar_plano()
fila = h.bus.assinar()


def eventos():
    saida = []
    while not fila.empty():
        saida.append(fila.get_nowait())
    return saida


# ---- mover
r = h.editar_plano("mover", "b2", {"horario": "15:00-16:00"})
confere("mover muda o horário e grava", r["ok"] and plano()["blocos"][1]["inicio"] == "15:00" and plano()["blocos"][1]["fim"] == "16:00", r)
ev = eventos()
confere("mover emite plano_editado e plano, nessa ordem", [e["t"] for e in ev] == ["plano_editado", "plano"] and ev[0]["op"] == "mover" and ev[0]["ref"] == "b2" and "15:00" in ev[0]["depois"], ev)
r = h.editar_plano("mover", "b1", {"horario": "9h"})
confere("só o começo mantém a duração (09:00-09:30 -> 09:00-09:30) e aceita '9h'", r["ok"] and plano()["blocos"][0]["fim"] == "09:30", r)
r = h.editar_plano("mover", "b1", {"horario": "10h30"})
b1 = plano()["blocos"][0]
confere("mover para '10h30' mantém 30 min e marca a tarefa existente para reagendar no ClickUp", r["ok"] and b1["inicio"] == "10:30" and b1["fim"] == "11:00" and b1.get("reagendado") is True, b1)
confere("mover para cima de outro bloco avisa o conflito (b1 10:30-11:00 bate com nada; b2 já foi para 15:00)", r["conflitos"] == [], r)
r = h.editar_plano("mover", "b3", {"horario": "12:30-13:30"})
confere("conflito com compromisso fixo é avisado", r["ok"] and any("Almoço fixo" in c for c in r["conflitos"]), r)
eventos()
r = h.editar_plano("mover", "b3", {"horario": "16:00-15:00"})
confere("fim antes do começo é recusado", not r["ok"] and "fim" in r["erro"], r)
r = h.editar_plano("mover", "b3", {"horario": "banana"})
confere("horário inválido é recusado", not r["ok"], r)
r = h.editar_plano("mover", "b9", {"horario": "10:00"})
confere("bloco que não existe é recusado", not r["ok"], r)
confere("recusas não emitem evento nem mexem no arquivo", eventos() == [] and plano()["blocos"][2]["inicio"] == "12:30")

# ---- editar
r = h.editar_plano("editar", "b2", {"titulo": "Segunda renomeada", "descricao": "Nova descrição"})
confere("editar muda título e descrição", r["ok"] and plano()["blocos"][1]["titulo"] == "Segunda renomeada" and plano()["blocos"][1]["descricao"] == "Nova descrição", r)
r = h.editar_plano("editar", "b2", {"id": "b99", "clickup_id": "x"})
confere("editar ignora campos que não são de texto (id, clickup_id)", not r["ok"] and plano()["blocos"][1]["id"] == "b2" and "clickup_id" not in plano()["blocos"][1])

# ---- adicionar
r = h.editar_plano("adicionar", None, {"titulo": "Pagar a hospedagem", "inicio": "17:00", "fim": "17:30", "lista": "contas a pagar", "descricao": "Pagamento mensal"})
novo = next(b for b in plano()["blocos"] if b["titulo"] == "Pagar a hospedagem")
confere("adicionar cria bloco b4 na lista certa, sem clickup_id", r["ok"] and novo["id"] == "b4" and novo["lista_id"] == "L2" and "clickup_id" not in novo and novo["dono"] == "Rafa Lima", novo)
confere("o bloco novo entra na ordem de horário", [b["id"] for b in plano()["blocos"]] == sorted([b["id"] for b in plano()["blocos"]], key=lambda i: next(b["inicio"] for b in plano()["blocos"] if b["id"] == i)))
r = h.editar_plano("adicionar", None, {"titulo": "Sem hora"})
confere("adicionar sem horário é recusado", not r["ok"], r)

# ---- remover
r = h.editar_plano("remover", "b3")
p = plano()
confere("remover tira do plano e guarda em 'removidos' (com o id do ClickUp, para reprogramar depois)", r["ok"] and all(b["id"] != "b3" for b in p["blocos"]) and p["removidos"][0]["clickup_id"] == "cid3", p.get("removidos"))

# ---- desfazer
n_antes = len(plano()["blocos"])
r = h.editar_plano("desfazer")
confere("desfazer volta o bloco removido", r["ok"] and len(plano()["blocos"]) == n_antes + 1 and any(b["id"] == "b3" for b in plano()["blocos"]))
r = h.editar_plano("desfazer")
confere("desfazer de novo volta o bloco adicionado", r["ok"] and all(b["titulo"] != "Pagar a hospedagem" for b in plano()["blocos"]))

# ---- conflitos
gravar_plano()
c = h.conflitos_do_plano()
confere("plano limpo não tem conflito", c == [], c)
h.editar_plano("mover", "b2", {"horario": "09:15-09:45"})
c = h.conflitos_do_plano()
confere("conflito entre dois blocos é listado", len(c) == 1 and "Primeira" in c[0]["texto"] and "Segunda" in c[0]["texto"], c)

# ---- resumo e aprovação
gravar_plano()
h.HISTORICO_PLANO.clear()
h.editar_plano("mover", "b1", {"horario": "09:30-10:00"})
h.editar_plano("adicionar", None, {"titulo": "Bloco novo", "inicio": "16:00", "fim": "16:30"})
res = h.resumo_aprovacao()
confere("resumo: 4 blocos, 2 tarefas novas (b2 e o novo), 1 reagendada", res["blocos"] == 4 and res["novos"] == 2 and res["reagendadas"] == 1, res)

chamadas = []


class Resp:
    def __init__(self, d=None):
        self.d = d or {}

    def raise_for_status(self):
        pass

    def json(self):
        return self.d


class FakeRequests:
    RequestException = requests.RequestException

    @staticmethod
    def post(url, **kw):
        chamadas.append(("post", url, kw.get("json")))
        return Resp({"id": f"novo{len(chamadas)}"})

    @staticmethod
    def put(url, **kw):
        chamadas.append(("put", url, kw.get("json")))
        return Resp()


h.requests = FakeRequests
h._token_clickup = lambda: "token-de-teste"
eventos()
r = h.agir("aprovar")
confere("aprovar: ok, 2 tarefas criadas e 1 reagendada", r["ok"] and r["criadas"] == 2 and r["reagendadas"] == 1 and r["erros"] == [], r)
posts = [c for c in chamadas if c[0] == "post"]
puts = [c for c in chamadas if c[0] == "put"]
confere("aprovar: as tarefas novas vão para as listas dos blocos", {c[1].split("/list/")[1].split("/")[0] for c in posts} == {"L1"} or len(posts) == 2, [c[1] for c in posts])
confere("aprovar: a tarefa movida muda de hora no ClickUp (início e fim novos)", len(puts) == 1 and "/task/cid1" in puts[0][1] and puts[0][2]["due_date_time"] is True and puts[0][2]["time_estimate"] == 30 * 60 * 1000, puts)
p = plano()
confere("aprovar: plano fica aprovado e o 'reagendado' some", p["status"] == "aprovado" and "reagendado" not in p["blocos"][0] and all(b.get("clickup_id") for b in p["blocos"] if b["id"] in ("b2",)), p["blocos"][0])
ev = eventos()
tipos = [(e["t"], e.get("tipo")) for e in ev]
confere("aprovar: eventos acao -> acao_fim -> plano, com contagens", tipos[0] == ("acao", "aprovar") and ("acao_fim", "aprovar") in tipos and ev[tipos.index(("acao_fim", "aprovar"))]["criadas"] == 2, tipos)
antes_puts = len([c for c in chamadas if c[0] == "put"])
r = h.editar_plano("mover", "b2", {"horario": "10:00-10:30"})
confere("depois de aprovado, imprevisto é aceito: o plano continua aprovado (a execução não para)", r["ok"] and plano()["status"] == "aprovado", r)
novos_puts = [c for c in chamadas if c[0] == "put"][antes_puts:]
confere("depois de aprovado, o bloco movido muda de hora no ClickUp na mesma hora", any("/task/" in c[1] for c in novos_puts) and "reagendado" not in next(b for b in plano()["blocos"] if b["id"] == "b2"), novos_puts)
r = h.agir("aprovar")
confere("aprovar de novo não cria nada", r["ok"] and r["criadas"] == 0)

# ---- concluir depois da meia-noite (o guardião trabalha de madrugada)
import json as _json
with open(caminho, "w", encoding="utf-8") as f:
    _json.dump({"data": hoje, "status": "aprovado", "fixos": [], "blocos": [bloco(7, "23:00", "23:30", "Bloco da noite"), bloco(8, "09:00", "09:30", "Bloco da manhã")]}, f, ensure_ascii=False)
h.time = type("R", (), {"__getattr__": lambda self, n: getattr(__import__("time"), n), "strftime": lambda self, fmt, t=None: "00:10" if fmt == "%H:%M" and t is None else __import__("time").strftime(fmt)})()
r = h.concluir_bloco({"id": "b7", "concluido": True})
reg = _json.load(open(os.path.join(tmp, "registros", f"registro_{hoje}.json"), encoding="utf-8"))
b7 = next(b for b in reg["blocos"] if b["id"] == "b7")
confere("meia-noite: bloco de 23:00 concluído às 00:10 vale e conta 70 minutos", r["ok"] and b7["real"]["minutos"] == 70 and b7["desvio_minutos"] == 40, (r, b7))
r = h.concluir_bloco({"id": "b8", "concluido": True})
confere("concluir às 00:10 um bloco que só começa às 09:00 continua recusado", not r["ok"] and "fim" in r["erro"], r)

# plano de outro dia aprovado agora: o ClickUp recebe os horários na hora (antes só quando o dia chegava)
from datetime import timedelta as _td
amanha = (date.today() + _td(days=1)).isoformat()
os.makedirs(os.path.join(tmp, "planos"), exist_ok=True)
arq_amanha = os.path.join(tmp, "planos", f"plano_{amanha}.json")
with open(arq_amanha, "w", encoding="utf-8") as f:
    _json.dump({"data": amanha, "status": "sugerido", "fixos": [], "blocos": [bloco(1, "09:00", "10:00", "Copy movida", clickup_id="cid9", reagendado=True),
                                                                              bloco(2, "10:00", "10:30", "Tarefa nova de amanhã", lista_id="L1"),
                                                                              bloco(3, "11:00", "11:30", "Já no lugar", clickup_id="cid8")]}, f, ensure_ascii=False)
hoje_antes = open(caminho, encoding="utf-8").read()
chamadas.clear()
r = h.agir("aprovar", amanha)
p_amanha = _json.load(open(arq_amanha, encoding="utf-8"))
puts = [c for c in chamadas if c[0] == "put"]
confere("plano de amanhã: aprovado agora, com a tarefa movida e a nova levadas ao ClickUp", r["ok"] and r["reagendadas"] == 1 and r["criadas"] == 1
        and p_amanha["status"] == "aprovado" and any("/task/cid9" in c[1] for c in puts), (r, chamadas))
from datetime import datetime as _dt
confere("plano de amanhã: o horário que vai ao ClickUp é o de amanhã", puts and _dt.fromtimestamp(puts[0][2]["start_date"] / 1000).date().isoformat() == amanha, puts)
confere("plano de amanhã: a tarefa que já estava no lugar não é mexida e o plano de hoje fica como estava",
        not any("/task/cid8" in c[1] for c in chamadas) and open(caminho, encoding="utf-8").read() == hoje_antes)
chamadas.clear()
confere("aprovar de novo o plano de amanhã não manda nada", h.agir("aprovar", amanha)["ok"] and not chamadas)
confere("dia sem plano gravado: avisa", not h.aprovar_plano_de_outro_dia((date.today() + _td(days=9)).isoformat())["ok"])

print(f"\n{sum(resultados)}/{len(resultados)} verificações passaram")
sys.exit(0 if all(resultados) else 1)
