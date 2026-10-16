"""Plano do dia por código (2026-10-14): dia resolvido na semana combinada sai sem Claude; atrasada, tarefa sem hora, buraco grande ou trabalho
do guardião vencido pedem o Claude com dossiê; almoço anda para depois de compromisso que o cobre; a conferência pega tarefa que sumiu do dia."""
import json
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import plano_base as pb

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHA"), nome, "" if ok else extra)
    falhas += 0 if ok else 1


oper, mem = tempfile.mkdtemp(), tempfile.mkdtemp()
os.makedirs(os.path.join(oper, "planos"))
os.makedirs(os.path.join(mem, "campanhas"))
dia = date(2026, 10, 21)  # quarta
cfg = {"pessoa": {"nome": "Ana"}, "pastas": {"memoria": mem},
       "rotina": {"fixos_semana": [{"dias": [0, 1, 2, 3, 4], "inicio": "13:00", "fim": "14:00", "titulo": "Almoço"}]}}


def resumo(tarefas):
    with open(os.path.join(oper, "resumo_clickup.json"), "w", encoding="utf-8") as f:
        json.dump({"tarefas": tarefas}, f, ensure_ascii=False)


def t(i, nome, prazo, ini=None, fim=None, **x):
    return dict(id=i, nome=nome, prazo=prazo, inicio=ini, fim=fim, lista="Conteúdos", **x)


cheio = [t("a1", "Gravar vídeo", "2026-10-21", "08:40", "10:40"), t("a2", "Reunião de alinhamento", "2026-10-21", "10:40", "13:00"),
         t("a3", "Aula gravada", "2026-10-21", "14:00", "16:00"), t("a4", "Stories", "2026-10-21", "16:00", "17:00"),
         t("a5", "Aula", "2026-10-21", "17:00", "19:20")]
resumo(cheio)
plano, motivos = pb.montar(dia, oper, cfg, dia)
confere("dia resolvido na semana combinada: sem motivo para chamar o Claude", motivos == [], motivos)
confere("blocos vêm do ClickUp com clickup_id e na ordem", [b["clickup_id"] for b in plano["blocos"]] == ["a1", "a2", "a3", "a4", "a5"])
confere("plano tem agenda_impoe e passa na conferência", plano["agenda_impoe"] and pb.cp.conferir(plano) == [])

resumo(cheio + [t("z9", "Pendência esquecida", "2026-10-20", "09:00", "10:00")])
confere("tarefa atrasada chama o Claude", any("atrasada" in m for m in pb.montar(dia, oper, cfg, dia)[1]))
resumo(cheio + [t("z8", "Substack", "2026-10-21")])
confere("tarefa do dia sem hora chama o Claude", any("sem horário" in m for m in pb.montar(dia, oper, cfg, dia)[1]))
resumo(cheio[:2])
confere("buraco grande no expediente chama o Claude", any("livres no expediente" in m for m in pb.montar(dia, oper, cfg, dia)[1]))
resumo(cheio + [t("z7", "APROVAR | post do Carlos", "2026-10-20", aprovar=True)])
confere("aprovação com data falsa não chama o Claude (vai para o bloco de aprovações)", pb.montar(dia, oper, cfg, dia)[1] == [])

resumo([t("h1", "Hotseat", "2026-10-21", "09:00", "14:00")] + cheio[2:])
plano, motivos = pb.montar(dia, oper, cfg, dia)
almoco = next(f for f in plano["fixos"] if f["titulo"] == "Almoço")
confere("compromisso que cobre o almoço empurra o almoço para depois dele", almoco["inicio"] == "14:00" and almoco["fim"] == "15:00", almoco)

with open(os.path.join(mem, "estado.md"), "w", encoding="utf-8") as f:
    f.write("# Estado\n## Do guardião (x)\n- **Lista do evento** | status: a fazer | início: seg 19/10 | condição: x\n- **Outro** | status: a fazer | início: sex 30/10 | x\n## Outra\n")
resumo(cheio)
m = pb.montar(dia, oper, cfg, dia)[1]
confere("trabalho do guardião com data chegada chama o Claude (só o vencido)", any("Lista do evento" in x for x in m) and not any("Outro" in x for x in m), m)
os.remove(os.path.join(mem, "estado.md"))

resumo(cheio)
arq = os.path.join(oper, "plano_teste.json")
plano, _ = pb.montar(dia, oper, cfg, dia)
plano["blocos"] = plano["blocos"][1:]
with open(arq, "w", encoding="utf-8") as f:
    json.dump(dict(plano, data="2026-10-21"), f, ensure_ascii=False)
pb.OPER = oper
confere("conferência: tarefa da semana combinada que some do dia é barrada", any("Gravar vídeo" in p for p in pb.conferir_arquivo(arq, oper, cfg)))
plano["removidos"] = ["Gravar vídeo"]
with open(arq, "w", encoding="utf-8") as f:
    json.dump(dict(plano, data="2026-10-21"), f, ensure_ascii=False)
confere("conferência: tirada com motivo (removidos) passa", pb.conferir_arquivo(arq, oper, cfg) == [], pb.conferir_arquivo(arq, oper, cfg))
d = pb.dossie(dia, *pb.montar(dia, oper, cfg, dia), oper, cfg)
confere("dossiê traz motivos, plano base e semana", "POR QUE" in d and "PLANO BASE" in d and "VISÃO DA SEMANA" in d)
# buraco: primeiro alivia um dia cheio
resumo(cheio[:2] + [t("q1", "Revisão de quinta", "2026-10-22", "08:40", "10:00"), t("q2", "Reunião de quinta", "2026-10-22", "10:00", "13:00"),
                    t("q3", "Aula gravada de quinta", "2026-10-22", "14:00", "18:00"), t("q4", "Aula de quinta", "2026-10-22", "18:00", "19:20")])
m = pb.montar(dia, oper, cfg, dia)[1]
confere("buraco: sugere adiantar tarefa do dia cheio que cabe hoje", any("Preencha" in x and "de quinta" in x for x in m), m)

# plano do mês: marco de campanha a 8 dias sem tarefa no ClickUp chama o Claude, mesmo com o dia de hoje resolvido
with open(os.path.join(mem, "campanhas", "lancamento.md"), "w", encoding="utf-8") as f:
    f.write("---\nnome: Lançamento\nslug: lancamento\ntipo: estrategia\nstatus: em-execucao\nimportancia: alta\ndata_inicio: 2026-10-01\ndata_fim: 2026-11-03\n---\n"
            "# Lançamento\n\n## 3. Marcos e tarefas\n| Data | Marco | Dono |\n|---|---|---|\n| Qui 29 | Decidir o bônus | Ana |\n| Sex 30 | Tarefa de outro | Paulo |\n")
resumo(cheio)
m = pb.montar(dia, oper, cfg, dia)[1]
confere("marco de campanha dela sem tarefa nos próximos 14 dias chama o Claude", any("Decidir o bônus" in x for x in m) and not any("de outro" in x for x in m), m)
confere("o dossiê traz o horizonte até 14 dias", "HORIZONTE" in pb.dossie(dia, *pb.montar(dia, oper, cfg, dia), oper, cfg))
# plano de dia FUTURO: o que vence entre hoje e o dia é do plano daquele dia, não "atrasada" (bug de 15/10: 7 tarefas em mais de um plano)
resumo([t("f1", "Reunião de sexta", "2026-10-16", "11:00", "13:00"), t("f2", "Substack - Newsletter", "2026-10-19", None, "09:00"),
        t("f3", "Atrasada de verdade", "2026-10-14", "09:00", "10:00")])
plano_seg, mot_seg = pb.montar(date(2026, 10, 19), oper, cfg, date(2026, 10, 15))
texto_mot = " ".join(mot_seg)
confere("plano de segunda, planejado na quinta: a tarefa de sexta NÃO é atrasada nem entra", "Reunião de sexta" not in texto_mot and all(b["clickup_id"] != "f1" for b in plano_seg["blocos"]), texto_mot)
confere("o que venceu antes de hoje continua atrasada", "Atrasada de verdade" in texto_mot)
confere("entrega só com horário limite (Substack 9h) não vira bloco e pede o trabalho ANTES", all(b["clickup_id"] != "f2" for b in plano_seg["blocos"]) and "ANTES do horário limite" in texto_mot, texto_mot)
# blocos diários: o plano base já nasce com stories todo dia de trabalho, na tarde, sem chamar o Claude só por isso
cfg_s = dict(cfg, rotina=dict(cfg.get("rotina") or {}, dias_trabalho=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
             blocos_diarios=[{"nome": "stories", "palavras": ["stories", "story"], "excluir": ["cronograma"], "minutos_minimos": 15, "bloco_max_min": 40, "titulo_padrao": "Stories do dia (3 telas ou mais)"}]))
resumo([t("s1", "Reunião", "2026-10-21", "09:00", "11:00")])
plano_s, mot_s = pb.montar(date(2026, 10, 21), oper, cfg_s, date(2026, 10, 21))
st = [b for b in plano_s["blocos"] if "Stories" in b["titulo"]]
confere("o plano base de dia útil nasce com o bloco de stories, de 15 min, na tarde (a partir das 14h)", len(st) == 1 and st[0]["inicio"] >= "14:00" and st[0]["fim"] > st[0]["inicio"], plano_s["blocos"])
confere("com o bloco inserido não há motivo de bloco diário faltando", not any("BLOCO DIÁRIO" in m for m in mot_s), mot_s)
confere("o bloco inserido não cria tarefa no ClickUp (sem clickup_id nem lista_id)", not st[0].get("clickup_id") and not st[0].get("lista_id"))
plano_sab, _ = pb.montar(date(2026, 10, 24), oper, cfg_s, date(2026, 10, 24))
confere("sábado não ganha stories", all("Stories" not in b["titulo"] for b in plano_sab["blocos"]))
# stories: o plano base define o tipo do dia pelo padrão da semana e completa o tempo, quebrado em blocos de até 15 min
cfg_st = dict(cfg, rotina=dict(cfg.get("rotina") or {}, dias_trabalho=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], stories={"ativo": True}))
resumo([])
mins = lambda blocos: sum(int(b["fim"][:2]) * 60 + int(b["fim"][3:]) - int(b["inicio"][:2]) * 60 - int(b["inicio"][3:]) for b in blocos)
qua_, _ = pb.montar(date(2026, 10, 21), oper, cfg_st, date(2026, 10, 21))
sq = [b for b in qua_["blocos"] if "Stories" in b["titulo"]]
confere("quarta (sequência normal): 30 min em blocos de até 15, na tarde, sem tarefa no ClickUp, com o tipo no plano",
        mins(sq) == 30 and len(sq) == 2 and qua_.get("stories_tipo") == "normal" and all(b["inicio"] >= "14:00" and not b.get("clickup_id") and not b.get("lista_id") for b in sq), qua_["blocos"])
sex_, mot_sex = pb.montar(date(2026, 10, 23), oper, cfg_st, date(2026, 10, 23))
cx = [b for b in sex_["blocos"] if "caixinha" in b["titulo"]]
confere("sexta (caixinha): 45 min em 3 blocos de 15, espalhados (1 h entre eles)", mins(cx) == 45 and len(cx) == 3 and sex_.get("stories_tipo") == "caixinha"
        and all(int(cx[i + 1]["inicio"][:2]) * 60 + int(cx[i + 1]["inicio"][3:]) - (int(cx[i]["fim"][:2]) * 60 + int(cx[i]["fim"][3:])) >= 60 for i in range(2)), cx)
qui_, _ = pb.montar(date(2026, 10, 22), oper, cfg_st, date(2026, 10, 22))
confere("quinta (captação): 1 bloco de 15 min", [b["titulo"] for b in qui_["blocos"] if "Stories" in b["titulo"]] == ["Stories de captação de leads (3 telas)"] and qui_.get("stories_tipo") == "captacao")
confere("o plano base nasce sem pendência de stories", not any("BLOCO DIÁRIO" in m for m in mot_sex), mot_sex)
resumo([t("c1", "Stories: respostas da caixinha (parte 1)", "2026-10-23", "15:00", "15:15")])
sex2, _ = pb.montar(date(2026, 10, 23), oper, cfg_st, date(2026, 10, 23))
confere("com 15 min de caixinha já no dia, completa só os 30 que faltam", mins([b for b in sex2["blocos"] if "caixinha" in b["titulo"]]) == 45)
# dia com espaços pequenos: o tempo é quebrado em blocos menores
resumo([t("p0", "Reunião da manhã", "2026-10-21", "08:40", "14:00"), t("p1", "Reunião A", "2026-10-21", "14:00", "14:10"), t("p2", "Reunião B", "2026-10-21", "14:20", "14:30"), t("p4", "Reunião D", "2026-10-21", "14:40", "14:50"), t("p3", "Reunião C", "2026-10-21", "15:00", "19:30")])
apert, _ = pb.montar(date(2026, 10, 21), oper, cfg_st, date(2026, 10, 21))
pequenos = [b for b in apert["blocos"] if "Stories" in b["titulo"]]
confere("sem espaço de 15 min, quebra em blocos menores (mínimo 5 min) e ainda chega ao tempo do tipo", mins(pequenos) >= 30 and any(
        int(b["fim"][:2]) * 60 + int(b["fim"][3:]) - int(b["inicio"][:2]) * 60 - int(b["inicio"][3:]) < 15 for b in pequenos), pequenos)
# o vão fica numa janela de trabalho pesado (manhã): para stories qualquer vão do dia serve
resumo([t("m1", "Reunião de planejamento", "2026-10-22", "08:40", "09:20"), t("m2", "Aprovações", "2026-10-22", "09:35", "13:00"), t("m3", "Tarde cheia", "2026-10-22", "14:00", "19:00")])
cfg_cx = dict(cfg_st, rotina=dict(cfg_st["rotina"], stories={"ativo": True, "padrao_semana": {"3": "caixinha"}}))
manha, _ = pb.montar(date(2026, 10, 22), oper, cfg_cx, date(2026, 10, 22))
vao = [b for b in manha["blocos"] if "caixinha" in b["titulo"]]
confere("dia cheio à tarde: os stories entram nos vãos da manhã (9h20 às 9h35) em vez de faltar", mins(vao) >= 15 and any(b["inicio"] == "09:20" for b in vao), vao)
sys.exit(1 if falhas else 0)
