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
sys.exit(1 if falhas else 0)
