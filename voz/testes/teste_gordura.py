"""Gordura de posts e auditoria das datas estabelecidas (2026-10-15): posts seg/qua/sex, meta de 1 a 2 prontos à frente; a data que o guardião marcou antes das travas
passa pela mesma conferência (limite, relatório antes de 24h, copy depois do design)."""
import json
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import etapas_post as ep
import gordura as gd
import plano_base as pb

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHA"), nome, "" if ok else extra)
    falhas += 0 if ok else 1


cfg = {"pessoa": {"nome": "Ana"}, "pastas": {"memoria": tempfile.mkdtemp()}, "rotina": {"posts": {"dias_semana": [0, 2, 4], "gordura_meta": 2, "gordura_minima": 1}}}
et = lambda i, nome, st: {"id": i, "nome": nome, "status": st}
pronta = lambda d, i: {"id": i, "nome": f"Post {d}", "prazo": d, "etapas": [et(i + "c", "Copy | x", "complete"), et(i + "d", "Design | x", "complete"), et(i + "m", "Manychat do x", "pendente")]}
meio = lambda d, i: {"id": i, "nome": f"Post {d}", "prazo": d, "etapas": [et(i + "c", "Copy | x", "complete"), et(i + "d", "Design | x", "pendente")]}
vazia = lambda d, i: {"id": i, "nome": f"Post {d}", "prazo": d, "etapas": []}
quinta = date(2026, 10, 15)

confere("sem a chave no config o recurso fica desligado", gd.situacao([], {"rotina": {}}, quinta) is None)
s = gd.situacao([pronta("2026-10-16", "A"), pronta("2026-10-19", "B"), meio("2026-10-21", "C")], cfg, quinta)
confere("dois posts prontos em sequência (sex 16 e seg 19): gordura 2, meta alcançada", s["gordura"] == 2 and "Meta alcançada" in gd.texto(s) and "dia fixo" in gd.texto(s), s)
s = gd.situacao([meio("2026-10-16", "A"), pronta("2026-10-19", "B")], cfg, quinta)
confere("o primeiro post à frente não está pronto: gordura 0, abaixo do mínimo, e o texto manda terminar o próximo", s["gordura"] == 0 and "ABAIXO DO MÍNIMO" in gd.texto(s), s)
s = gd.situacao([pronta("2026-10-16", "A"), vazia("2026-10-19", "B")], cfg, quinta)
confere("um pronto e o seguinte sem etapas: gordura 1, entre o mínimo e a meta", s["gordura"] == 1 and "Abaixo da meta" in gd.texto(s), s)
confere("post de hoje ou do passado não conta como à frente", gd.situacao([pronta("2026-10-15", "A")], cfg, quinta)["gordura"] == 0)
confere("só os dias de post (seg, qua, sex) entram: sábado e terça não", all(d.weekday() in (0, 2, 4) for d in s["prontos"] + s["faltando"]))

# o plano chama o Claude quando a gordura está abaixo da meta e o dossiê leva o texto
oper = tempfile.mkdtemp()
os.makedirs(os.path.join(oper, "planos"))
with open(os.path.join(oper, "resumo_clickup.json"), "w", encoding="utf-8") as f:
    json.dump({"tarefas": [{"id": "X", "nome": "Reunião", "prazo": "2026-10-15", "inicio": "09:00", "fim": "18:00", "lista": "Reuniões Gerais"}]}, f)
with open(os.path.join(oper, "posts_maes.json"), "w", encoding="utf-8") as f:
    json.dump({"maes": [meio("2026-10-16", "A")]}, f)
plano, motivos = pb.montar(quinta, oper, cfg, quinta)
confere("gordura abaixo da meta vira motivo para o Claude", any(m.startswith("GORDURA DE POSTS") for m in motivos), motivos)
confere("o dossiê leva o texto da gordura", "GORDURA DE POSTS" in pb.dossie(quinta, plano, motivos, oper, cfg))

# auditoria das datas que o guardião marcou antes das travas
maes = [{"id": "M", "nome": "Post", "prazo": "2026-10-21", "etapas": [{"id": "C"}, {"id": "D"}, {"id": "R"}]}]
t = lambda i, nome, prazo: {"id": i, "nome": nome, "prazo": prazo, "inicio": None, "fim": None}
tarefas = [t("C", "Copy | Post", "2026-10-19"), t("D", "Design | Post", "2026-10-18"), t("R", "Preencher relatório do Post", "2026-10-21")]
pm = ep.datas_por_mae(tarefas, maes)
confere("copy depois do design do mesmo post é violação; design antes da copy também", "depois do design" in ep.violacao(ep.info(tarefas[0], maes), tarefas[0], pm)
        and "antes da copy" in ep.violacao(ep.info(tarefas[1], maes), tarefas[1], pm))
confere("relatório no dia do post é violação; no dia seguinte não", "24h" in ep.violacao(ep.info(tarefas[2], maes), tarefas[2], pm)
        and ep.violacao(ep.info(t("R", "Preencher relatório do Post", "2026-10-22"), maes), t("R", "Preencher relatório do Post", "2026-10-22"), pm) is None)
ok_ = [t("C", "Copy | Post", "2026-10-17"), t("D", "Design | Post", "2026-10-18")]
confere("copy antes do design, dentro do limite: sem violação", all(ep.violacao(ep.info(x, maes), x, ep.datas_por_mae(ok_, maes)) is None for x in ok_))
sys.exit(1 if falhas else 0)
