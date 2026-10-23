"""Quais tarefas o guardião NÃO pode mover (decisão de produto, 2026-10-15). Todas as outras são dele: pode e deve mexer para os objetivos serem alcançados.

- FIXA: reunião, aula, compromisso com hora de outra pessoa. Data e horário não mudam. Vem da lista (padrão "Reuniões Gerais") ou da tag "fixo".
- LIMITE: o prazo é o MÁXIMO (data de entrega, combinado com cliente, marco de campanha com a data de ir ao ar). Dá para fazer ANTES, nunca depois, porque
  mudar exige renegociar. Vem da tag ("prazo máximo", "entrega", "cliente") ou de estar na tabela de marcos de uma campanha ativa.
- ESTABELECIDA: o guardião já avaliou e marcou aquela data (tarefa criada por ele, ou movida por ele ao aprovar um plano). Fica, salvo necessidade.
- SUGESTAO: o resto. O prazo do ClickUp é sugestão (sobretudo de copy e design criados por automação); o guardião replaneja.
Listas e tags saem de config.json (rotina.travas.listas_fixas, tags_fixas, tags_limite); sem elas valem os padrões abaixo."""
import json
import os
import re
import unicodedata

FIXA, LIMITE, ESTABELECIDA, SUGESTAO = "fixa", "limite", "estabelecida", "sugestao"
LISTAS_FIXAS = ("Reuniões Gerais",)
TAGS_FIXAS = ("fixo", "fixa", "fixo na agenda")
TAGS_LIMITE = ("prazo máximo", "prazo maximo", "prazo-maximo", "prazo fixo", "entrega", "cliente", "combinado com cliente")
ID_CLICKUP = re.compile(r"\b(?=[0-9a-z]*\d)(?=[0-9a-z]*[a-z])[0-9a-z]{9,13}\b")


def _norm(t):
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower()) if unicodedata.category(c) != "Mn").strip()


def carregar_agendadas(oper):
    """{id: {data, inicio, fim}} do que o guardião moveu ao aprovar um plano."""
    try:
        with open(os.path.join(oper, "agendadas_guardiao.json"), encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def registrar_agendada(oper, id_tarefa, data, inicio, fim):
    dados = carregar_agendadas(oper)
    dados[str(id_tarefa)] = {"data": data, "inicio": inicio, "fim": fim}
    try:
        with open(os.path.join(oper, "agendadas_guardiao.json"), "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def ids_de_marcos(memoria):
    """Ids de tarefa citados na tabela "3. Marcos e tarefas" das campanhas ativas: a data de cada marco é o limite da campanha."""
    import conferencia_plano as cp
    ids = set()
    for slug in cp.campanhas_ativas(memoria) if memoria else []:
        try:
            with open(os.path.join(memoria, "campanhas", slug + ".md"), encoding="utf-8-sig") as f:
                texto = f.read()
        except OSError:
            continue
        secao = re.search(r"^## 3\..*?$(.*?)(?=^## |\Z)", texto, re.M | re.S)
        if secao:
            ids.update(ID_CLICKUP.findall(secao.group(1)))
    return ids


def classe(tarefa, cfg=None, marcos=(), agendadas=None):
    conf = ((cfg or {}).get("rotina") or {}).get("travas") or {}
    listas = {_norm(x) for x in conf.get("listas_fixas", LISTAS_FIXAS)}
    tags = {_norm(x) for x in tarefa.get("tags") or []}
    if _norm(tarefa.get("lista")) in listas or tags & {_norm(x) for x in conf.get("tags_fixas", TAGS_FIXAS)}:
        return FIXA
    if tags & {_norm(x) for x in conf.get("tags_limite", TAGS_LIMITE)} or tarefa.get("id") in marcos:
        return LIMITE
    mov = (agendadas or {}).get(str(tarefa.get("id")))
    if tarefa.get("criada_pelo_guardiao") or (mov and mov.get("data") == tarefa.get("prazo") and mov.get("inicio") == tarefa.get("inicio") and mov.get("fim") == tarefa.get("fim")):
        return ESTABELECIDA
    return SUGESTAO
