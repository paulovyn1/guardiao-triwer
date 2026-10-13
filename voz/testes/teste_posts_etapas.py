# Bloco de ideias concluído: os blocos reservados de copy e design viram subtarefas reais da mãe do post. ClickUp falso, sem servidor e sem Claude.
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import posts_maes as pm

ok = falhas = 0


def confere(nome, cond, extra=""):
    global ok, falhas
    print(("PASSOU " if cond else "FALHOU ") + nome + ("" if cond else f"  {extra}"))
    ok, falhas = ok + bool(cond), falhas + (not cond)


tmp = tempfile.mkdtemp(prefix="gv_etapas_")
os.makedirs(os.path.join(tmp, "planos"))
cfg = {"clickup": {"user_id": "1", "listas": [{"id": "L1", "nome": "Conteúdos"}], "membros": [], "posts": {"lista": "Conteúdos"}}}


def bloco(i, etapa, post, ini, fim):
    return {"id": i, "inicio": ini, "fim": fim, "titulo": f"Reserva: {etapa.lower()} de post ({post}), tema ainda não definido", "dono": "Milena",
            "reserva_post": post, "etapa": etapa}


hoje = {"data": "2026-10-14", "blocos": [bloco("r1", "Copy", "2026-10-19", "09:00", "10:00"), bloco("r2", "Design", "2026-10-19", "14:00", "16:00"),
                                          {"id": "x", "inicio": "11:00", "fim": "12:00", "titulo": "Outro", "dono": "Milena"}]}
outro = {"data": "2026-10-16", "blocos": [bloco("r3", "Design", "2026-10-21", "15:30", "17:30")]}
json.dump(hoje, open(os.path.join(tmp, "plano_do_dia.json"), "w", encoding="utf-8"))
json.dump(outro, open(os.path.join(tmp, "planos", "plano_2026-10-16.json"), "w", encoding="utf-8"))

chamadas = []


class Resp:
    def __init__(self, i): self.i = i
    def raise_for_status(self): pass
    def json(self): return {"id": self.i}


pm.requests.post = lambda url, **kw: (chamadas.append((url, kw["json"])), Resp(f"T{len(chamadas)}"))[1]

maes = [{"id": "M1", "nome": "O post de segunda", "prazo": "2026-10-19", "criada_em": "2026-10-14 10:00"},
        {"id": "M2", "nome": "Um post que ninguém reservou", "prazo": "2026-10-25", "criada_em": "2026-10-14 10:05"}]
r = pm.lancar_etapas(cfg, "tok", tmp, maes)
confere("cria copy e design como subtarefas da mãe certa", [c[1]["name"] for c in chamadas] == ["Copy | O post de segunda", "Design | O post de segunda"]
        and all(c[1]["parent"] == "M1" and c[0].endswith("/list/L1/task") for c in chamadas), chamadas)
confere("usa o horário que estava reservado", chamadas[0][1]["time_estimate"] == 3600000 and chamadas[1][1]["time_estimate"] == 7200000)
novo = json.load(open(os.path.join(tmp, "plano_do_dia.json"), encoding="utf-8"))["blocos"]
confere("o bloco reservado vira a tarefa real: título, clickup_id e pai, sem a marca de reserva",
        novo[0]["clickup_id"] == "T1" and novo[0]["pai"] == "M1" and novo[0]["titulo"].startswith("Copy | ") and "reserva_post" not in novo[0] and novo[1]["clickup_id"] == "T2")
confere("bloco que não era reserva fica como estava", novo[2] == hoje["blocos"][2])
confere("post sem reserva é avisado e não cria tarefa solta", r["posts_sem_reserva"] == ["Um post que ninguém reservou"] and len(chamadas) == 2)
confere("a reserva de outro dia continua reservada e é contada", r["reservas_sem_post"] == 1
        and "reserva_post" in json.load(open(os.path.join(tmp, "planos", "plano_2026-10-16.json"), encoding="utf-8"))["blocos"][0])
n = len(chamadas)
pm.lancar_etapas(cfg, "tok", tmp, maes[:1])
confere("rodar de novo não duplica", len(chamadas) == n)
confere("sem token, sem lista ou sem posts não cria nada", pm.lancar_etapas(cfg, "", tmp, maes)["criadas"] == [] and pm.lancar_etapas({}, "tok", tmp, maes)["criadas"] == [])
print(f"\n{ok} de {ok + falhas} checagens passaram.")
sys.exit(1 if falhas else 0)
