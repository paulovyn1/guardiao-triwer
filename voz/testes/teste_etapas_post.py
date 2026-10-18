"""Etapas de post (2026-10-15): o guardião manda na data, o ClickUp só sugere. Copy e design terminam até o dia anterior à postagem (pela tarefa mãe ou pelo
título "posta seg 26"); relatório só 24h depois; etapa não vira bloco fixo no ClickUp nem "atrasada"; a conferência barra etapa que passa do limite e etapa
vencida que ficou fora dos planos."""
import json
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conferencia_plano as cp
import etapas_post as ep
import plano_base as pb
import visao_semana as vs

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHA"), nome, "" if ok else extra)
    falhas += 0 if ok else 1


maes = [{"id": "M1", "nome": "Mudanças que se eu pudesse", "prazo": "2026-10-21", "etapas": [{"id": "E1"}, {"id": "E2"}, {"id": "E3"}]}]
t = lambda i, nome, prazo, ini=None, fim=None, **x: dict(id=i, nome=nome, prazo=prazo, inicio=ini, fim=fim, lista="Conteúdos", **x)

copy = ep.info(t("E1", "Copy | Mudanças que se eu pudesse", "2026-10-14"), maes)
confere("copy: limite é o dia anterior ao post da tarefa mãe, e a sugestão do ClickUp só informa", copy["tipo"] == "copy" and copy["limite"] == date(2026, 10, 20) and copy["sugestao"] == date(2026, 10, 14), copy)
confere("design e manychat também", ep.info(t("E2", "[DESIGN] Mudanças", "2026-10-20"), maes)["limite"] == date(2026, 10, 20)
        and ep.info(t("E3", "Manychat do post", "2026-10-20"), maes)["tipo"] == "manychat")
rel = ep.info(t("R1", "Preencher relatório do post", "2026-10-21"), [{"id": "M1", "prazo": "2026-10-21", "etapas": [{"id": "R1"}]}])
confere("relatório não tem limite e só abre 24h depois do post", rel["tipo"] == "relatorio" and rel["limite"] is None and rel["abre"] == date(2026, 10, 22), rel)
tit = ep.info(t("X1", "Design do post de aquecimento 1 (posta seg 26)", "2026-10-23"), [])
confere("sem tarefa mãe, a data do post vem do título (posta seg 26)", tit["post"] == date(2026, 10, 26) and tit["limite"] == date(2026, 10, 25), tit)
sem = ep.info(t("X2", "Copy da página do produto Halloween", "2026-10-26"), [])
confere("sem data de post em lugar nenhum, o prazo do ClickUp vira o limite por falta de informação melhor", sem["post"] is None and sem["limite"] == date(2026, 10, 26))
confere("tarefa que não é etapa não é tocada", ep.info(t("Z", "Aprovações do Vitor", "2026-10-20", "16:00", "16:30"), maes) is None)

oper = tempfile.mkdtemp()
os.makedirs(os.path.join(oper, "planos"))
with open(os.path.join(oper, "posts_maes.json"), "w", encoding="utf-8") as f:
    json.dump({"maes": maes}, f)
tarefas = [t("E1", "Copy | Mudanças que se eu pudesse", "2026-10-16", "09:00", "10:00"), t("E2", "Design | Mudanças que se eu pudesse", "2026-10-17", "11:00", "13:00"),
           t("H1", "Hotseat", "2026-10-19", "09:00", "14:00")]
with open(os.path.join(oper, "resumo_clickup.json"), "w", encoding="utf-8") as f:
    json.dump({"tarefas": tarefas}, f)
cfg = {"pessoa": {"nome": "Ana"}, "pastas": {"memoria": tempfile.mkdtemp()}, "rotina": {}}
dia = date(2026, 10, 19)
plano, motivos = pb.montar(dia, oper, cfg, date(2026, 10, 15))
confere("o plano base NÃO põe a etapa no horário que o ClickUp sugeriu; só o compromisso fixo entra", [b["clickup_id"] for b in plano["blocos"]] == ["H1"], plano["blocos"])
texto = " ".join(motivos)
confere("as etapas vão ao dossiê como 'a encaixar', com limite, post e sugestão", "ETAPAS DE POST A ENCAIXAR (2)" in texto and "terminar até 20/10" in texto and "post de 21/10" in texto and "sugestão do ClickUp 16/10" in texto, texto)
confere("o dossiê leva as regras das etapas", "REGRAS DAS ETAPAS" in pb.dossie(dia, plano, motivos, oper, cfg))
pre = vs.pre_planos_do_clickup(oper, {}, date(2026, 10, 15))
confere("o pré-plano do ClickUp não trata a etapa como agenda combinada", all(b["clickup_id"] != "E1" for p in pre.values() for b in p["blocos"] + p["sem_hora"]))

# conferência: limite, cobertura
mapa = {x["id"]: x for x in tarefas}
passou = {"blocos": [{"id": "a", "inicio": "09:00", "fim": "10:00", "titulo": "Copy | Mudanças", "clickup_id": "E1"}]}
confere("etapa depois do limite é barrada", len(cp.conferir_etapas(passou, date(2026, 10, 21), mapa, maes, {})) >= 1
        and any("passa do limite" in x for x in cp.conferir_etapas(passou, date(2026, 10, 21), mapa, maes, {})))
confere("etapa antes do limite passa", [x for x in cp.conferir_etapas(passou, date(2026, 10, 17), mapa, maes, {}) if "passa do limite" in x] == [])
vazio = {"blocos": []}
confere("etapa que chegou ao limite e não está em plano nenhum é cobrada; se está em outro plano, não", any("não está em nenhum plano" in x for x in cp.conferir_etapas(vazio, date(2026, 10, 20), mapa, maes, {}))
        and not any("E1" in x or "Copy" in x for x in cp.conferir_etapas(vazio, date(2026, 10, 20), mapa, maes, {"2026-10-18": {"blocos": [{"id": "b1", "clickup_id": "E1"}]}})))
# etapa já estabelecida pelo guardião: fica, a não ser que a data passe do limite da postagem (caso real: design de post de 21/10 marcado para 22/10)
tar_ok, tar_ruim = t("E2", "Design | Mudanças", "2026-10-20"), t("E2", "Design | Mudanças", "2026-10-22")
confere("etapa estabelecida dentro do limite fica; passando do limite volta a ser do guardião; sugestão é sempre dele",
        not ep.replanejar(ep.info(tar_ok, maes), "estabelecida", tar_ok) and ep.replanejar(ep.info(tar_ruim, maes), "estabelecida", tar_ruim)
        and ep.replanejar(ep.info(tar_ok, maes), "sugestao", tar_ok) and not ep.replanejar(ep.info(tar_ok, maes), "limite", tar_ok))
# atrasada que já tem lugar em outro plano gravado não é replanejada de novo (a copy do dia 14 aparecia na sexta e na segunda)
oper3 = tempfile.mkdtemp()
os.makedirs(os.path.join(oper3, "planos"))
with open(os.path.join(oper3, "resumo_clickup.json"), "w", encoding="utf-8") as f:
    json.dump({"tarefas": [t("A1", "Pendência de verdade", "2026-10-14", "09:00", "10:00")]}, f)
with open(os.path.join(oper3, "planos", "plano_2026-10-16.json"), "w", encoding="utf-8") as f:
    json.dump({"data": "2026-10-16", "blocos": [{"id": "b1", "inicio": "09:00", "fim": "10:00", "titulo": "Pendência de verdade", "clickup_id": "A1"}]}, f)
_, mot3 = pb.montar(date(2026, 10, 19), oper3, cfg, date(2026, 10, 15))
confere("tarefa atrasada que já está no plano de sexta não volta a ser atrasada no plano de segunda", "Pendência de verdade" not in " ".join(mot3), mot3)
_, mot3b = pb.montar(date(2026, 10, 16), oper3, cfg, date(2026, 10, 15))
confere("mas no próprio plano de sexta ela continua sendo atrasada", "Pendência de verdade" in " ".join(mot3b), mot3b)
sys.exit(1 if falhas else 0)
