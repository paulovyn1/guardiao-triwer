"""Planos dos próximos 3 dias úteis sempre gerados (2026-10-15): o que falta é calculado pela conta, o que existe não é refeito,
a janela anda quando o dia passa e uma falha espera antes de tentar de novo."""
import json
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import manter_planos as mp

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHA"), nome, "" if ok else extra)
    falhas += 0 if ok else 1


oper = tempfile.mkdtemp()
os.makedirs(os.path.join(oper, "planos"))
cfg = {"rotina": {"dias_trabalho": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]}}
quinta = date(2026, 10, 15)
confere("próximos 3 dias úteis a partir de quinta: sex 16, seg 19, ter 20", [d.isoformat() for d in mp.proximos_dias(quinta, cfg)] == ["2026-10-16", "2026-10-19", "2026-10-20"])
confere("sem nenhum plano, faltam os três", len(mp.faltando(quinta, oper, cfg)) == 3)


def grava(d):
    with open(os.path.join(oper, "planos", f"plano_{d}.json"), "w", encoding="utf-8") as f:
        json.dump({"data": d}, f)


grava("2026-10-16")
confere("plano que existe não falta", [d.isoformat() for d in mp.faltando(quinta, oper, cfg)] == ["2026-10-19", "2026-10-20"])
with open(os.path.join(oper, "plano_do_dia.json"), "w", encoding="utf-8") as f:
    json.dump({"data": "2026-10-19"}, f)
confere("dia que já está como plano_do_dia.json não falta", [d.isoformat() for d in mp.faltando(quinta, oper, cfg)] == ["2026-10-20"])
os.remove(os.path.join(oper, "plano_do_dia.json"))

chamados = []


def gerador_ok(d, o, refazer=False):
    chamados.append(d.isoformat())
    grava(d.isoformat())
    return True


feitos = mp.rodar_uma_vez(oper, cfg, quinta, gerador_ok, agora=1000)
confere("gera só o que falta, na ordem", chamados == ["2026-10-19", "2026-10-20"] and len(feitos) == 2, chamados)
confere("segunda rodada não gera nada", mp.rodar_uma_vez(oper, cfg, quinta, gerador_ok, agora=1001) == [] and len(chamados) == 2)
sexta = date(2026, 10, 16)
chamados.clear()
mp.rodar_uma_vez(oper, cfg, sexta, gerador_ok, agora=1002)
confere("na sexta a janela andou: entra o dia 21", chamados == ["2026-10-21"], chamados)

falhou = []
mp.rodar_uma_vez(oper, cfg, date(2026, 10, 19), lambda d, o, r=False: falhou.append(d) or False, agora=2000)
n1 = len(falhou)
mp.rodar_uma_vez(oper, cfg, date(2026, 10, 19), lambda d, o, r=False: falhou.append(d) or False, agora=2100)
confere("dia que falhou espera uma hora para tentar de novo", n1 == 1 and len(falhou) == 1, falhou)
mp.rodar_uma_vez(oper, cfg, date(2026, 10, 19), lambda d, o, r=False: falhou.append(d) or False, agora=2000 + mp.PAUSA_FALHA + 1)
confere("e tenta de novo depois da pausa", len(falhou) == 2, falhou)

# revisão dos planos futuros
oper2 = tempfile.mkdtemp()
os.makedirs(os.path.join(oper2, "planos"))
seg = date(2026, 10, 19)  # hoje: segunda; próximos: ter 20, qua 21, qui 22


def resumo2(tarefas):
    with open(os.path.join(oper2, "resumo_clickup.json"), "w", encoding="utf-8") as f:
        json.dump({"tarefas": tarefas}, f)


def plano2(d, status=None, origem=None, pasta=None):
    dados = {"data": d}
    if status:
        dados["status"] = status
    if origem:
        dados["origem"] = origem
    with open(os.path.join(pasta or oper2, "planos", f"plano_{d}.json"), "w", encoding="utf-8") as f:
        json.dump(dados, f)


# terça: base por código (semana combinada); quarta: aprovado; quinta: sugerido refinado (sem origem de base)
for d in ("2026-10-20", "2026-10-21", "2026-10-22"):
    plano2(d, "aprovado" if d == "2026-10-21" else "sugerido", "semana combinada (montado sem Claude)" if d == "2026-10-20" else ("refinado pela IA" if d == "2026-10-22" else None))
resumo2([{"id": "a", "nome": "X", "prazo": "2026-10-20", "inicio": "09:00", "fim": "10:00", "status": "pendente"}])
refeitos = []


def ger2(d, o, refazer=False):
    refeitos.append((d.isoformat(), refazer))
    return True


mp.rodar_uma_vez(oper2, cfg, seg, ger2, agora=10000)
confere("primeira vez que vê planos que já existiam: só marca o ponto de partida, não refaz", refeitos == [], refeitos)
resumo2([{"id": "a", "nome": "X", "prazo": "2026-10-20", "inicio": "09:00", "fim": "10:00", "status": "pendente"},
         {"id": "b", "nome": "Nova", "prazo": "2026-10-20", "inicio": "11:00", "fim": "12:00", "status": "pendente"},
         {"id": "c", "nome": "Nova de qua", "prazo": "2026-10-21", "inicio": "11:00", "fim": "12:00", "status": "pendente"},
         {"id": "d", "nome": "Nova de qui", "prazo": "2026-10-22", "inicio": "11:00", "fim": "12:00", "status": "pendente"}])
mp.rodar_uma_vez(oper2, cfg, seg, ger2, agora=10000 + 600)
confere("mudou, mas ainda dentro das 3 h da última revisão: espera", refeitos == [], refeitos)
mp.rodar_uma_vez(oper2, cfg, seg, ger2, agora=10000 + mp.REVISAO_PAUSA + 1)
confere("mudou e passou a pausa: refaz o plano de origem 'semana combinada' de terça, com refazer (sem IA: o gerador é o do código)", ("2026-10-20", True) in refeitos, refeitos)
confere("plano aprovado (quarta) nunca é refeito sozinho, mesmo com mudança", all(d != "2026-10-21" for d, _ in refeitos), refeitos)
confere("plano sugerido refinado (quinta, mesmo com mudança) não é refeito sozinho", all(d != "2026-10-22" for d, _ in refeitos), refeitos)
# plano de origem 'motor da agenda' também é refeito; sugerido sem origem não
oper5 = tempfile.mkdtemp()
os.makedirs(os.path.join(oper5, "planos"))
plano2("2026-10-20", "sugerido", "motor da agenda", oper5)
plano2("2026-10-21", "sugerido", None, oper5)
plano2("2026-10-22", "sugerido", "semana combinada (montado sem Claude)", oper5)
with open(os.path.join(oper5, "resumo_clickup.json"), "w", encoding="utf-8") as f:
    json.dump({"tarefas": [{"id": "a", "nome": "X", "prazo": "2026-10-20", "inicio": "09:00", "fim": "10:00", "status": "pendente"}]}, f)
r5 = []
mp.rodar_uma_vez(oper5, cfg, seg, lambda d, o, refazer=False: r5.append((d.isoformat(), refazer)) or True, agora=70000)
with open(os.path.join(oper5, "resumo_clickup.json"), "w", encoding="utf-8") as f:
    json.dump({"tarefas": [{"id": "a", "nome": "X", "prazo": "2026-10-20", "inicio": "09:00", "fim": "10:00", "status": "pendente"},
                           {"id": "n", "nome": "N20", "prazo": "2026-10-20", "inicio": "11:00", "fim": "12:00", "status": "pendente"},
                           {"id": "m", "nome": "N21", "prazo": "2026-10-21", "inicio": "11:00", "fim": "12:00", "status": "pendente"},
                           {"id": "o", "nome": "N22", "prazo": "2026-10-22", "inicio": "11:00", "fim": "12:00", "status": "pendente"}]}, f)
mp.rodar_uma_vez(oper5, cfg, seg, lambda d, o, refazer=False: r5.append((d.isoformat(), refazer)) or True, agora=70000 + mp.REVISAO_PAUSA + 1)
confere("só origem 'semana combinada' ou 'motor da agenda' é refeita; sugerido sem origem fica", sorted(r5) == [("2026-10-20", True), ("2026-10-22", True)], r5)
n = len(refeitos)
mp.rodar_uma_vez(oper2, cfg, seg, ger2, agora=10000 + 2 * mp.REVISAO_PAUSA + 5)
confere("sem nova mudança não refaz de novo", len(refeitos) == n, refeitos)
# plano que saiu só com a base por limite de uso do Claude é refeito depois da pausa; o aprovado não
oper4 = tempfile.mkdtemp()
os.makedirs(os.path.join(oper4, "planos"))
resumo_vazio = os.path.join(oper4, "resumo_clickup.json")
with open(resumo_vazio, "w", encoding="utf-8") as f:
    json.dump({"tarefas": []}, f)
for d, status in (("2026-10-20", None), ("2026-10-21", "aprovado"), ("2026-10-22", None)):
    with open(os.path.join(oper4, "planos", f"plano_{d}.json"), "w", encoding="utf-8") as f:
        json.dump({"data": d, "status": status, "refazer_motivo": "limite de uso do Claude"} if d != "2026-10-22" else {"data": d}, f)
chamadas = []


def ger4(d, o, refazer=False):
    chamadas.append((d.isoformat(), refazer))
    with open(os.path.join(oper4, "planos", f"plano_{d.isoformat()}.json"), "w", encoding="utf-8") as f:  # o gerador real grava o plano sem a marca
        json.dump({"data": d.isoformat()}, f)
    return True


mp.revisar(oper4, cfg, seg, ger4, agora=50000)
confere("plano marcado para refazer é refeito; o aprovado e o sem marca não", chamadas == [("2026-10-20", True)], chamadas)
with open(os.path.join(oper4, "planos", "plano_2026-10-22.json"), "w", encoding="utf-8") as f:
    json.dump({"data": "2026-10-22", "refazer_motivo": "limite de uso do Claude"}, f)
falhas4 = []
mp.revisar(oper4, cfg, seg, lambda d, o, r=False: falhas4.append(d) or False, agora=60000)
mp.revisar(oper4, cfg, seg, lambda d, o, r=False: falhas4.append(d) or False, agora=60000 + 60)
confere("se a nova tentativa também falha, só tenta de novo depois da pausa de uma hora", len(falhas4) == 1, falhas4)
mp.revisar(oper4, cfg, seg, lambda d, o, r=False: falhas4.append(d) or False, agora=60000 + mp.PAUSA_FALHA + 1)
confere("e tenta de novo passada a pausa", len(falhas4) == 2, falhas4)
sys.exit(1 if falhas else 0)
