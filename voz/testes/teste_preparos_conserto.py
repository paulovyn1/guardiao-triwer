"""Preparos de evento, separar/anotar_avisos, plano_base.consertar e _aplicar_planos com preparar_arquivo."""
import json
import os
import sys
import tempfile
import types
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conferencia_plano as cp
import plano_base as pb
import preparos as pp

passou = falhou = 0


def confere(nome, ok, extra=""):
    global passou, falhou
    print(("PASSOU" if ok else "FALHOU"), nome, "" if ok else extra)
    if ok:
        passou += 1
    else:
        falhou += 1


def grava(pasta, nome, dado):
    caminho = os.path.join(pasta, *nome.split("/"))
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dado, f, ensure_ascii=False)
    return caminho


HOJE = date(2026, 10, 16)  # sexta
EVENTO = "2026-10-27"      # terça, 11 dias depois
CFG = {"pessoa": {"nome": "Milena Camila"},
       "rotina": {"dias_trabalho": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                  "preparos": [{"nome": "Estrateclass", "tag": "live semanal", "etapas": [
                      {"palavras": ["definir tema"], "dias_antes": 6, "rotulo": "tema definido"},
                      {"palavras": ["thumb"], "dias_antes": 6, "rotulo": "thumb pronta"},
                      {"palavras": ["agendar"], "dias_antes": 6, "rotulo": "live agendada"},
                      {"palavras": ["mensagem no grupo", "antecipa"], "dias_antes": 5, "rotulo": "antecipação no grupo"}]}]}}

with tempfile.TemporaryDirectory(prefix="guardiao_preparos_") as oper:
    grava(oper, "resumo_clickup.json", {"tarefas": [], "eventos": [
        {"id": "M1", "nome": "ESTRATECLASS #105 — Tema X", "data": EVENTO, "tags": ["live semanal"], "etapas": [
            {"id": "T1", "nome": "Fazer a Thumb", "status": "pendente", "prazo": "2026-10-20", "donos": ["Milena Camila"]},
            {"id": "A1", "nome": "Agendar a live no YT", "status": "pendente", "donos": ["Paulo Vinicius"]},
            {"id": "G1", "nome": "Enviar mensagem no grupo de alunos | ESTRATECLASS #105", "status": "pendente", "donos": ["Paulo Vinicius"]},
            {"id": "D1", "nome": "Definir tema — M1", "status": "complete", "donos": ["Milena Camila"]}]}]})
    es = {e["id"]: e for e in pp.etapas(CFG, oper, HOJE)}
    confere("limite da thumb = data - 6 (quarta 21/10)", es["T1"]["limite"] == date(2026, 10, 21), es.get("T1"))
    confere("limite da mensagem no grupo = data - 5 (quinta 22/10)", es["G1"]["limite"] == date(2026, 10, 22), es.get("G1"))
    confere("etapa concluída não aparece", "D1" not in es)
    confere("Thumb é dela, Paulo não", es["T1"]["eu"] is True and es["G1"]["eu"] is False and es["A1"]["eu"] is False)
    confere("ids() só traz T1", pp.ids(CFG, oper, HOJE) == {"T1"}, pp.ids(CFG, oper, HOJE))
    sem = {"pessoa": CFG["pessoa"], "rotina": {}}
    confere("sem rotina.preparos não sai nada", pp.etapas(sem, oper, HOJE) == [] and pp.ids(sem, oper, HOJE) == set())

    plano = {"data": "2026-10-22", "fixos": [], "blocos": [{"id": "b1", "inicio": "09:00", "fim": "10:00", "titulo": "Copy"}]}
    try:
        novos = pp.inserir_cobrancas(plano, date(2026, 10, 22), CFG, oper, "Milena", hoje=HOJE)
        g = [b for b in novos if "Conferir com Paulo" in b["titulo"] and "antecipação no grupo" in b["titulo"]]
        dur = None
        if g:
            h = lambda s: int(s[:2]) * 60 + int(s[3:5])
            dur = h(g[0]["fim"]) - h(g[0]["inicio"])
        confere("inserir_cobrancas põe 'Conferir com Paulo' (grupo) de 5 min no dia do limite", len(g) == 1 and dur == 5, novos)
        confere("o bloco não tem clickup_id e cita a etapa em cobranca_de", bool(g) and "clickup_id" not in g[0] and g[0]["cobranca_de"] == "G1", g)
        n2 = pp.inserir_cobrancas(plano, date(2026, 10, 22), CFG, oper, "Milena", hoje=HOJE)
        confere("rodar de novo não duplica a cobrança", n2 == [], n2)
    except Exception as erro:
        confere("inserir_cobrancas roda sem quebrar", False, repr(erro))
    confere("inserir_cobrancas no dia antes do limite não cobra",
            pp.inserir_cobrancas({"fixos": [], "blocos": []}, date(2026, 10, 19), CFG, oper, "M", hoje=HOJE) == [])

    depois = {"blocos": [{"id": "b1", "clickup_id": "T1", "titulo": "Fazer a Thumb", "inicio": "09:00", "fim": "10:00"}]}
    pr = pp.conferir(depois, date(2026, 10, 22), CFG, oper, hoje=HOJE)
    confere("conferir acusa T1 num plano depois do limite", any("Thumb" in p and "passa do limite" in p for p in pr), pr)
    antes_ = pp.conferir(depois, date(2026, 10, 20), CFG, oper, hoje=HOJE)
    confere("T1 antes do limite não é acusada", not any("passa do limite" in p for p in antes_), antes_)

    grava(oper, "resumo_clickup.json", {"tarefas": [], "eventos": [
        {"id": "M2", "nome": "ESTRATECLASS #106 — Definir tema", "data": EVENTO, "tags": ["live semanal"], "etapas": []}]})
    es2 = pp.etapas(CFG, oper, HOJE)
    confere("mãe 'Definir tema' sem subtarefa gera item 'Definir o tema...' com id None",
            len(es2) == 1 and es2[0]["id"] is None and es2[0]["titulo"].startswith("Definir o tema") and es2[0]["eu"], es2)

avisos_ex = ["Copy e design alternados no mesmo dia, separe", "Stories: faltam blocos hoje", "Todo dia de trabalho tem um bloco de consumo"]
graves_ex = ["Blocos sobrepostos às 09:00", "Uma tarefa tem um dia só: T9 aparece em dois dias"]
g, a = cp.separar(avisos_ex + graves_ex)
confere("separar manda copy/design alternados, Stories: e 'Todo dia de trabalho tem' para avisos", a == avisos_ex, a)
confere("separar mantém sobreposição e 'Uma tarefa tem um dia só' como graves", g == graves_ex, g)
p = cp.anotar_avisos({"aviso": "Já tinha."}, ["Stories: faltam blocos hoje"])
p = cp.anotar_avisos(p, ["Stories: faltam blocos hoje", "Outro"])
confere("anotar_avisos acrescenta ao aviso sem repetir",
        p["aviso"].count("Stories: faltam blocos hoje") == 1 and "Outro" in p["aviso"] and p["aviso"].startswith("Já tinha."), p)
confere("anotar_avisos sem aviso novo não mexe", cp.anotar_avisos({}, []) == {})

DIA = date(2026, 10, 20)
with tempfile.TemporaryDirectory(prefix="guardiao_conserto_") as oper:
    cfg = {"pessoa": {"nome": "Milena Camila"}, "rotina": {}}
    try:
        pl = {"data": DIA.isoformat(), "blocos": [
            {"id": "b1", "inicio": "09:00", "fim": "09:30", "titulo": "Consumo com a pergunta"},
            {"id": "b2", "inicio": "15:00", "fim": "15:30", "titulo": "Recarga de repertório"},
            {"id": "b3", "inicio": "10:00", "fim": "11:00", "titulo": "Copy do post"}]}
        feito = pb.consertar(pl, DIA, oper, cfg, outros={})
        ncons = [b for b in pl["blocos"] if pb.ROTINA.search(cp._norm(b["titulo"]))]
        confere("dois blocos consumo/recarga sem clickup_id: sobra um", len(ncons) == 1 and any("segundo bloco" in f for f in feito), (feito, pl["blocos"]))
        confere("plano sem agenda_impoe sai com o campo preenchido", bool(str(pl.get("agenda_impoe") or "").strip()), pl.get("agenda_impoe"))
    except Exception as erro:
        confere("consertar roda no plano de dois consumos", False, repr(erro))
    try:
        grava(oper, "resumo_clickup.json", {"tarefas": [{"id": "C1", "nome": "Consumo", "prazo": "2026-10-22"}]})
        pl = {"data": DIA.isoformat(), "agenda_impoe": "ok", "blocos": [
            {"id": "b1", "inicio": "09:00", "fim": "09:30", "titulo": "Consumo com a pergunta", "clickup_id": "C1"}]}
        outros = {"2026-10-22": {"blocos": [{"id": "b1", "clickup_id": "C1", "titulo": "Consumo com a pergunta"}]}}
        feito = pb.consertar(pl, DIA, oper, cfg, outros=outros)
        confere("bloco de rotina com clickup_id em outro dia: tira o id e mantém o bloco",
                len(pl["blocos"]) == 1 and "clickup_id" not in pl["blocos"][0], (feito, pl["blocos"]))
    except Exception as erro:
        confere("consertar roda com rotina repetida em outro dia", False, repr(erro))
    try:
        pl = {"data": DIA.isoformat(), "agenda_impoe": "ok", "blocos": [{"id": "b2", "inicio": "10:00", "fim": "11:00", "titulo": "A"},
                                                                         {"id": "b1", "inicio": "11:00", "fim": "12:00", "titulo": "B"},
                                                                         {"inicio": "13:00", "fim": "14:00", "titulo": "C"}]}
        pb.consertar(pl, DIA, oper, cfg, outros={})
        ids_ = [b["id"] for b in pl["blocos"]]
        confere("ids gerados nunca repetem um existente", len(ids_) == len(set(ids_)) and all(ids_), ids_)
        ocupado = {"blocos": [{"id": "b3"}, {"id": "b1"}]}
        confere("_id_livre evita colisão (b3 e b1 usados)", pb._id_livre(ocupado) not in {"b1", "b3"}, pb._id_livre(ocupado))
    except Exception as erro:
        confere("consertar/_id_livre", False, repr(erro))

import guardiao_codex as codex
dia = date.today().isoformat()
plano = {"data": dia, "agenda_impoe": "Sem campanha ativa hoje.", "status": "aprovado",
         "blocos": [{"id": "b1", "titulo": "Revisar agenda", "inicio": "09:00", "fim": "09:30"}]}
msg = json.dumps({"fala": "ok", "planos": [{"arquivo": "plano_do_dia.json", "conteudo": plano}]}, ensure_ascii=False)
original = sys.modules.get("plano_base")
try:
    with tempfile.TemporaryDirectory(prefix="guardiao_codex_prep_") as pasta:
        caminho = os.path.join(pasta, "plano_do_dia.json")
        antigo = {"data": dia, "status": "aprovado", "agenda_impoe": "x", "blocos": [{"id": "b9", "titulo": "Antigo", "inicio": "08:00", "fim": "08:30"}]}
        grava(pasta, "plano_do_dia.json", antigo)
        chamadas = []
        sys.modules["plano_base"] = types.SimpleNamespace(
            preparar_arquivo=lambda c, oper=None, cfg=None: (chamadas.append(c) or (["grave X"], [])),
            conferir_arquivo=lambda c, oper=None: [])
        try:
            codex._aplicar_planos(msg, pasta)
            reprovou = False
        except RuntimeError as erro:
            reprovou = "grave X" in str(erro)
        confere("preparar_arquivo devolvendo grave reprova (usa preparar_arquivo)", reprovou and len(chamadas) == 1)
        confere("e restaura o plano anterior", json.load(open(caminho, encoding="utf-8")) == antigo)
        sys.modules["plano_base"] = types.SimpleNamespace(preparar_arquivo=lambda c, oper=None, cfg=None: ([], ["conserto"]),
                                                          conferir_arquivo=lambda c, oper=None: ["NAO DEVIA CHAMAR"])
        codex._aplicar_planos(msg, pasta)
        confere("sem graves e com conserto: grava como sugerido", json.load(open(caminho, encoding="utf-8")).get("status") == "sugerido")
finally:
    if original is not None:
        sys.modules["plano_base"] = original

print(f"\n{passou}/{passou + falhou} verificações passaram")
sys.exit(1 if falhou else 0)
