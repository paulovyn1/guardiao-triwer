"""Motor da agenda (2026-10-16): o código monta a semana sem IA. Nada passa da hora de parar; consumo antes da copy; tarefa com limite no dia até o limite;
o que não cabe vira pergunta (estender ou renegociar); item com limite além do horizonte é adiado; aprovado não é sobrescrito; refazer hoje."""
import copy
import json
import os
import sys
import tempfile
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import motor_agenda as ma
import plano_base as pb
import rota_agenda as ra
import visao_semana as vs

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHA"), nome, "" if ok else extra)
    falhas += 0 if ok else 1


oper, mem = tempfile.mkdtemp(), tempfile.mkdtemp()
os.makedirs(os.path.join(oper, "planos"))
os.makedirs(os.path.join(mem, "campanhas"))
segunda = date(2026, 10, 19)
iso = lambda n: date(2026, 10, 19 + n).isoformat()  # 0 seg, 1 ter, 2 qua, 3 qui, 4 sex
cfg = {"pessoa": {"nome": "Milena Camila"}, "pastas": {"memoria": mem},
       "rotina": {"dias_trabalho": ["seg", "ter", "qua", "qui", "sex"],
                  "parar_por_dia": {"seg": "19:00", "ter": "19:20", "qua": "19:20", "qui": "19:20", "sex": "19:20"},
                  "fixos_semana": [{"dias": [0, 1, 2, 3, 4], "inicio": "13:00", "fim": "14:00", "titulo": "Almoço"}],
                  "stories": {"ativo": True},
                  "regras": {"ideia_depois_de_consumo": True}},
       "clickup": {"listas": [{"nome": "Conteúdos", "id": "L1"}]}}


def grava(nome, dados):
    with open(os.path.join(oper, nome), "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False)


grava("config.json", cfg)
grava("resumo_clickup.json", {"tarefas": [{"id": "t1", "nome": "Reunião com o time", "prazo": iso(1), "inicio": "15:00", "fim": "16:00", "lista": "Conteúdos"}]})

# A fila do motor vem de pb.PENDENCIAS, que montar() preenche. O teste usa a montagem real (fixos, tarefa com hora, stories)
# e acrescenta a fila que quer, uma vez só, no primeiro dia.
EXTRA = []
montar_real = pb.montar


def montar_com_fila(dia, *a, **k):
    r = montar_real(dia, *a, **k)
    if dia == segunda:
        pb.PENDENCIAS[dia.isoformat()] = pb.PENDENCIAS.get(dia.isoformat(), []) + copy.deepcopy(EXTRA)
    return r


pb.montar = montar_com_fila

copy1 = {"id": "c1", "titulo": "Copy | carrossel da semana", "limite": date(2026, 10, 20), "abre": None, "origem": "etapa", "etapa": "copy", "minutos": 60}
design1 = {"id": "d1", "titulo": "Design | carrossel da semana", "limite": date(2026, 10, 21), "abre": None, "origem": "etapa", "etapa": "design", "minutos": 60}
leve1 = {"id": "l1", "titulo": "Revisar contrato do cliente", "limite": date(2026, 10, 21), "origem": "sem_hora", "lista": "Conteúdos", "minutos": 30}
EXTRA[:] = [copy1, design1, leve1]
r = ma.montar_semana(oper, cfg, segunda, 5, incluir_hoje=True)
memoria = pb._memoria(cfg)


def todos_blocos():
    return [(i, b) for i, p in r["dias"].items() for b in p.get("blocos") or []]


# 1. nada termina depois da hora de parar
ruins = [(i, b["titulo"], b["fim"]) for i, b in todos_blocos() if vs.hm(b["fim"]) > ra.parar_em(date.fromisoformat(i), memoria)]
confere("nenhum bloco termina depois da hora de parar (nem os stories)", not ruins and len(r["dias"]) == 5, ruins)

# 2. consumo antes da copy no mesmo dia
dia_copy, bc = next(((i, b) for i, b in todos_blocos() if b.get("clickup_id") == "c1"), (None, None))
consumo = next((b for b in (r["dias"].get(dia_copy) or {}).get("blocos") or [] if "consumo" in ma._norm(b["titulo"])), None)
confere("a copy foi posta e o consumo do mesmo dia vem antes dela", bc is not None and consumo is not None and vs.hm(consumo["fim"]) <= vs.hm(bc["inicio"]),
        (dia_copy, bc, consumo))
confere("um consumo por dia, em todos os dias montados", all(sum("consumo" in ma._norm(b["titulo"]) for b in p["blocos"]) == 1 for p in r["dias"].values()))

# 3. tarefa com limite fica no dia até o limite
dia_leve = next((i for i, b in todos_blocos() if b.get("clickup_id") == "l1"), None)
dia_design = next((i for i, b in todos_blocos() if b.get("clickup_id") == "d1"), None)
confere("copy até terça, design e tarefa até quarta: cada uma no dia até o limite", bool(dia_copy and dia_copy <= iso(1) and dia_design and dia_design <= iso(2)
        and dia_leve and dia_leve <= iso(2)), (dia_copy, dia_design, dia_leve))
confere("o prazo final do bloco guarda o limite", bool(bc and bc.get("prazo_final") == "2026-10-20"))

# 4. não coube: pergunta com estender ou renegociar (falta até 120 min)
# Com o fallback "qualquer horário livre antes do limite", só não cabe o que passa do maior vão contínuo de QUALQUER janela até o limite.
vao_max = max([y - x for i in (iso(0), iso(1)) for x, y in pb._vaos_do_dia(r["dias"][i], date.fromisoformat(i), memoria, ma._a_partir(date.fromisoformat(i)))] or [0])
nobre_ter = vao_max
grande = {"id": "g1", "titulo": "Escrever a página de vendas inteira", "limite": date(2026, 10, 20), "origem": "sem_hora", "lista": "Conteúdos", "minutos": vao_max + 60}
EXTRA[:] = [copy1, design1, leve1, grande]
r = ma.montar_semana(oper, cfg, segunda, 5, incluir_hoje=True)
nc = next((n for n in r["nao_coube"] if n["id"] == "g1"), None)
confere("o que não cabe até o limite vai para nao_coube com 'estender ... ou renegociar'", bool(nc and "estender o dia" in nc["pergunta"] and "renegociar o prazo" in nc["pergunta"]),
        (nc, nobre_ter, r["nao_coube"]))
livre_tipo = max([y - x for x, y in ra.espacos(r["dias"][iso(1)], date.fromisoformat(iso(1)), ma._tipo_janela(grande, None), memoria=memoria)] or [0])  # a falta é medida na janela do tipo
confere("a pergunta diz quanto falta e o dia", bool(nc and f"em {grande['minutos'] - livre_tipo} min" in nc["pergunta"] and "20/10" in nc["pergunta"]), nc)
confere("a pergunta vai no aviso do dia até o limite", "estender" in r["dias"][iso(1)]["aviso"], r["dias"][iso(1)]["aviso"])
enorme = dict(grande, id="g2", titulo="Escrever o livro inteiro", minutos=nobre_ter + 400)
EXTRA[:] = [enorme]
r = ma.montar_semana(oper, cfg, segunda, 5, incluir_hoje=True)
nc2 = next((n for n in r["nao_coube"] if n["id"] == "g2"), None)
confere("faltando mais de 120 min a pergunta é só renegociar", bool(nc2 and "estender" not in nc2["pergunta"] and "renegociar" in nc2["pergunta"]), nc2)

# 5. limite depois do horizonte: adiados, não nao_coube
longe = {"id": "z1", "titulo": "Escrever o livro inteiro de novo", "limite": date(2026, 11, 30), "origem": "sem_hora", "lista": "Conteúdos", "minutos": 1500}
EXTRA[:] = [longe]
r = ma.montar_semana(oper, cfg, segunda, 5, incluir_hoje=True)
confere("item que não cabe mas vence depois do horizonte vai para adiados", any(a["id"] == "z1" for a in r["adiados"]) and not any(n["id"] == "z1" for n in r["nao_coube"]),
        (r["adiados"], r["nao_coube"]))

# 6. gravar: aprovado não é sobrescrito, salvo hoje com hoje_mesmo_aprovado
aprov = {"data": iso(1), "status": "aprovado", "blocos": [], "fixos": [], "marca": "AQUI"}
grava(os.path.join("planos", f"plano_{iso(1)}.json"), aprov)
grava(os.path.join("planos", f"plano_{iso(0)}.json"), dict(aprov, data=iso(0)))
grava("plano_do_dia.json", dict(aprov, data=iso(0)))
lido = lambda c: json.load(open(os.path.join(oper, c), encoding="utf-8"))
novo = lambda n: {"data": iso(n), "status": "sugerido", "blocos": [], "aviso": "novo"}
fake = {"dias": {iso(0): novo(0), iso(1): novo(1), iso(2): novo(2)}}
ma.gravar(fake, oper, segunda)
confere("dia aprovado não é sobrescrito; dia sem plano é gravado", lido(os.path.join("planos", f"plano_{iso(1)}.json")).get("marca") == "AQUI"
        and lido(os.path.join("planos", f"plano_{iso(2)}.json"))["status"] == "sugerido")
confere("hoje aprovado também fica como está sem o pedido", lido("plano_do_dia.json").get("marca") == "AQUI" and lido(os.path.join("planos", f"plano_{iso(0)}.json")).get("marca") == "AQUI")
ma.gravar(fake, oper, segunda, hoje_mesmo_aprovado=True)
confere("com hoje_mesmo_aprovado=True só hoje é refeito (plano_do_dia e plano de hoje); amanhã aprovado continua",
        lido("plano_do_dia.json")["status"] == "sugerido" and lido(os.path.join("planos", f"plano_{iso(0)}.json"))["status"] == "sugerido"
        and lido(os.path.join("planos", f"plano_{iso(1)}.json")).get("marca") == "AQUI")

# 7. montar_semana não refaz dia aprovado
grava(os.path.join("planos", f"plano_{iso(3)}.json"), {"data": iso(3), "status": "aprovado", "blocos": [], "fixos": [], "marca": "AQUI"})
EXTRA[:] = []
r = ma.montar_semana(oper, cfg, segunda, 5, incluir_hoje=False)
confere("dia aprovado sem nada a acrescentar fica de fora do resultado; hoje (sem incluir_hoje) conta como aprovado", iso(3) not in r["dias"] and iso(3) in r["aprovados"] and iso(0) in r["aprovados"],
        (list(r["dias"]), r["aprovados"]))


# 8. _refazer_hoje (relógio fixo em 11:00 de segunda)
class Relogio(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 19, 11, 0)


ma.datetime = Relogio


def bl(i, ini, fim, titulo, **x):
    return dict({"id": i, "inicio": ini, "fim": fim, "titulo": titulo, "dono": "Milena Camila", "frente": "Conteúdos"}, **x)


def plano_hoje():
    return {"data": iso(0), "fixos": [{"inicio": "13:00", "fim": "14:00", "titulo": "Almoço"}],
            "blocos": [bl("b1", "15:00", "16:00", "Escrever manifesto da semana"), bl("b2", "09:00", "10:00", "Revisar proposta do cliente", clickup_id="x1"),
                       bl("b3", "16:00", "16:15", "Stories: sequência normal"), bl("b4", "17:00", "17:30", "Cronograma de stories", clickup_id="s9"),
                       bl("b5", "14:30", "15:00", "Responder mensagens")]}


p, fila = plano_hoje(), {}
ma._refazer_hoje(p, segunda, oper, {"feitos": [{"titulo": "Escrever manifesto da semana"}]}, fila)
st = {b["id"]: b.get("status") for b in p["blocos"]}
confere("o feito dito (título de 10+ letras) marca o bloco como feito", st.get("b1") == "feito", st)

p, fila = plano_hoje(), {}
ma._refazer_hoje(p, segunda, oper, {"feitos": [{"titulo": "Stories", "minutos": 15}]}, fila)
st = {b["id"]: b.get("status") for b in p["blocos"]}
confere("'stories' feito não marca 'Cronograma de stories' como feito", "b4" in st and st["b4"] != "feito", st)
confere("'stories' feito desconta o bloco de stories do dia", "b3" not in st, st)

p, fila = plano_hoje(), {}
ma._refazer_hoje(p, segunda, oper, {"feitos": [{"titulo": "tarefa"}]}, fila)
confere("feito com título curto (menos de 10 letras) não marca nada", all(b.get("status") != "feito" for b in p["blocos"]))

p, fila = plano_hoje(), {}
ma._refazer_hoje(p, segunda, oper, None, fila)
confere("bloco que passou sem ser feito (09h, agora 11h) volta para a fila e sai do plano", "b2" not in [b["id"] for b in p["blocos"]] and "x1" in fila, (fila, p["blocos"]))
confere("o que ainda não passou continua no plano", {"b1", "b4"} <= {b["id"] for b in p["blocos"]})

p, fila = plano_hoje(), {}
ma._refazer_hoje(p, segunda, oper, {"imprevistos": [{"titulo": "Dentista", "inicio": "15:00", "fim": "16:00"}]}, fila)
ids = [b["id"] for b in p["blocos"]]
confere("imprevisto com horário entra em fixos", any(f["titulo"] == "Dentista" and f.get("imprevisto") for f in p["fixos"]), p["fixos"])
confere("o que estava por baixo do imprevisto sai do plano e volta para a fila", "b1" not in ids and any("manifesto" in str(v.get("titulo")).lower() for v in fila.values()), (ids, fila))
confere("o que não bate no imprevisto fica", "b4" in ids and "b5" in ids)

p, fila = plano_hoje(), {}
ma._refazer_hoje(p, segunda, oper, {"tirar": ["Escrever manifesto da semana"]}, fila)
confere("o que ela mandou tirar sai e fica em removidos", "b1" not in [b["id"] for b in p["blocos"]] and p.get("removidos") == ["Escrever manifesto da semana"])

import revisor_ia as rev
aj = rev.ajustes([{"acao": "cancelar", "titulo": "Escrever manifesto da semana"}])
confere("revisor_ia.ajustes aceita a ação 'cancelar' e guarda o título", aj.get("cancelar") == ["Escrever manifesto da semana"], aj)
p, fila = plano_hoje(), {}
p["blocos"].append(bl("b6", "16:30", "17:00", "Gravar replay da live", clickup_id="cid6"))
ma._refazer_hoje(p, segunda, oper, rev.ajustes([{"acao": "cancelar", "titulo": "Gravar replay da live"}]), fila)
confere("cancelar ao refazer hoje: o bloco sai, vai para removidos e o clickup_id vai para plano['cancelar'] (sem voltar à fila)",
        "b6" not in [b["id"] for b in p["blocos"]] and p.get("cancelar") == ["cid6"] and "Gravar replay da live" in p.get("removidos", []) and "cid6" not in fila, (p.get("cancelar"), fila))
p, fila = plano_hoje(), {}
ma._refazer_hoje(p, segunda, oper, {"tirar": ["Revisar proposta do cliente"]}, fila)
confere("tirar (sem cancelar) não fecha nada no ClickUp", not p.get("cancelar"), p.get("cancelar"))
ma.datetime = datetime

# 9. planejar sem IA
EXTRA[:] = [copy1]
r = ma.planejar(oper, cfg, segunda, 5, incluir_hoje=True, ia=False)
confere("planejar(ia=False) devolve o rascunho com perguntas e explicação vazia (sem chamar IA)", bool(r["dias"]) and "perguntas" in r and r["explicacao"] == "")
pb.montar = montar_real

# 10. novidades do commit f197014
# 10a. fixos do dia ganham id estável f1, f2...
fx = ra.fixos_do_dia(segunda, {"rotina": {"fixos_semana": [{"dias": [0], "inicio": "09:00", "fim": "09:30", "titulo": "WhatsApp"},
                                                            {"dias": [0], "inicio": "13:00", "fim": "14:00", "titulo": "Almoço"}]}})
confere("rota_agenda.fixos_do_dia devolve ids f1, f2...", [f.get("id") for f in fx] == ["f1", "f2"], fx)

# 10b/c. servidor com pasta temporária e ClickUp falso (nenhuma chamada de rede)
import limpeza_teste  # noqa: F401,E402
import hud_servidor as h  # noqa: E402
limpeza_teste.fixar_relogio(h)
tmp = tempfile.mkdtemp(prefix="gv_oper_motor_")
h.OPER = tmp
hoje_txt = date.today().isoformat()
caminho = os.path.join(tmp, "plano_do_dia.json")
with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
    json.dump({"agente": {"nome": "Guardião"}, "clickup": {"user_id": "1", "listas": [], "membros": []}}, f)
with open(caminho, "w", encoding="utf-8") as f:
    json.dump({"data": hoje_txt, "status": "aprovado", "fixos": [{"id": "f1", "inicio": "09:00", "fim": "09:30", "titulo": "WhatsApp"},
                                                              {"id": "f2", "inicio": "13:00", "fim": "14:00", "titulo": "Almoço"}],
               "blocos": [{"id": "b1", "inicio": "10:00", "fim": "11:00", "titulo": "Copy"}]}, f)
try:
    r = h.concluir_bloco({"id": "f1", "concluido": True, "inicio": "09:00", "fim": "09:30"})
except KeyError as erro:  # DEFEITO DO CÓDIGO: _gravar_registro (hud_servidor.py:328) só semeia o registro com plano["blocos"], não com fixos
    r = {"ok": False, "erro": f"KeyError {erro} em _gravar_registro"}
confere("hud_servidor.concluir_bloco acha o compromisso fixo pelo id 'f1'", r.get("ok") is True, r)
confere("e um id que não existe em blocos nem em fixos continua recusado", h.concluir_bloco({"id": "f9", "concluido": True})["ok"] is False)

# aprovar com erro de sincronização deixa pendência; a segunda aprovação tenta de novo
chamadas = []
saidas = [(0, 0, ["Copy: ClickUp fora do ar"]), (0, 0, [])]
h._levar_ao_clickup = lambda plano: (chamadas.append(1), saidas[min(len(chamadas) - 1, 1)])[1]
h._v2 = lambda: type("V", (), {"entrar": staticmethod(lambda: None)})()
with open(caminho, "w", encoding="utf-8") as f:
    json.dump({"data": hoje_txt, "status": "sugerido", "fixos": [], "blocos": [{"id": "b1", "inicio": "10:00", "fim": "11:00", "titulo": "Copy"}]}, f)
lido_plano = lambda: json.load(open(caminho, encoding="utf-8"))
r1 = h.aprovar_plano()
confere("aprovar com erro de sincronização: aprova, mas deixa sincronizacao_pendente no plano", r1["ok"] and lido_plano()["status"] == "aprovado"
        and lido_plano().get("sincronizacao_pendente") == ["Copy: ClickUp fora do ar"], (r1, lido_plano()))
r2 = h.aprovar_plano()
confere("a segunda aprovação chama _levar_ao_clickup de novo e limpa a pendência", len(chamadas) == 2 and "sincronizacao_pendente" not in lido_plano(), (chamadas, lido_plano()))
h.aprovar_plano()
confere("sem pendência, aprovar de novo não chama mais nada", len(chamadas) == 2, chamadas)

# 10e. pergunta de tarefa atrasada há 2 dias ou mais
op2 = tempfile.mkdtemp()
grava_op2 = {"tarefas": [{"id": "a1", "nome": "Replay da live", "prazo": "2026-10-17"},      # 2 dias de atraso em 19/10
                         {"id": "a2", "nome": "Subir o PDF", "prazo": "2026-10-18"},          # 1 dia: não pergunta
                         {"id": "a3", "nome": "Briefing antigo", "prazo": "2026-10-10"}]}     # cancelada pela IA: não pergunta
json.dump(grava_op2, open(os.path.join(op2, "resumo_clickup.json"), "w", encoding="utf-8"))
pq = ma._perguntas_de_atraso(op2, segunda, {"cancelar": ["Briefing antigo"]})
confere("_perguntas_de_atraso pergunta da vencida há 2+ dias; não da de 1 dia nem da cancelada",
        len(pq) == 1 and "Replay da live" in pq[0] and "17/10" in pq[0] and "cancela" in pq[0], pq)

print(f"\n{'PASSOU' if not falhas else 'FALHOU'}: {falhas} falha(s)")
sys.exit(1 if falhas else 0)
