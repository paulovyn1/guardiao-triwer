"""Preparo de evento recorrente (a Estrateclass da Milena: live toda terça às 13h).

Caso real 16/10: a live de terça 20 estava no ClickUp sem tema, sem thumb e sem agendamento, e o guardião não pôs nada disso no plano. As datas das
subtarefas vêm da automação do ClickUp (thumb e agendamento 7 dias antes, tema num domingo) e não seguem a regra dela: tema, thumb e live agendada
até a QUARTA anterior; mensagem de antecipação no grupo (Paulo) até a QUINTA, e ela só sai com o link pronto.

A tarefa mãe tem a tag do evento (config "clickup.eventos": ["live semanal"]) e a data do evento; o ler_clickup.ps1 guarda as mães e as subtarefas
(com dono e status) em resumo_clickup.json, chave "eventos". Este módulo calcula o limite de cada etapa pela regra do config:

    "rotina": {"preparos": [{"nome": "Estrateclass", "tag": "live semanal", "etapas": [
        {"palavras": ["definir tema"], "dias_antes": 6, "rotulo": "tema definido"},
        {"palavras": ["thumb"], "dias_antes": 6, "rotulo": "thumb pronta"},
        {"palavras": ["agendar"], "dias_antes": 6, "rotulo": "live agendada"},
        {"palavras": ["mensagem no grupo", "antecipa"], "dias_antes": 5, "rotulo": "antecipação no grupo"}]}]}

Etapa dela vira "etapa a encaixar" (o guardião decide o dia, dentro do limite; o prazo do ClickUp é só sugestão). Etapa de outra pessoa vira cobrança:
a partir do limite, um bloco curto "Conferir com <dono>" no plano dela. Sem "rotina.preparos" no config, nada disso roda."""
import json
import os
import re
import unicodedata
from datetime import date, timedelta

HORIZONTE_DIAS = 14
ABRE_DIAS = 3  # etapa entra no dossiê só quando o limite está a até 3 dias (antes disso só aparece no horizonte)
DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
FEITO = {"complete", "completo", "concluida", "concluido", "closed", "fechada", "done", "feito"}


def _norm(texto):
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


def _json(caminho):
    try:
        with open(caminho, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _id_livre(plano):
    usados = {str(b.get("id")) for b in plano.get("blocos") or []}
    n = len(usados) + 1
    while f"b{n}" in usados:
        n += 1
    return f"b{n}"


def regras(cfg):
    p = ((cfg or {}).get("rotina") or {}).get("preparos")
    return [r for r in p if isinstance(r, dict) and r.get("etapas")] if isinstance(p, list) else []


def eventos(oper):
    return ((_json(os.path.join(oper, "resumo_clickup.json")) or {}).get("eventos")) or []


def _data(txt):
    try:
        return date.fromisoformat(str(txt or "")[:10])
    except ValueError:
        return None


def _regra_do_evento(ev, rs):
    tags = {_norm(t) for t in ev.get("tags") or []}
    for r in rs:
        if _norm(r.get("tag")) in tags or (r.get("palavras_mae") and any(_norm(p) in _norm(ev.get("nome")) for p in r["palavras_mae"])):
            return r
    return rs[0] if len(rs) == 1 and not ev.get("tags") else None


def etapas(cfg, oper, hoje=None, horizonte=HORIZONTE_DIAS):
    """Todas as etapas abertas de preparo dos eventos dos próximos dias: dict com id, titulo, evento, data_evento, rotulo, limite, dono, eu (bool),
    sugestao (prazo do ClickUp). Inclui o tema que falta quando a mãe ainda se chama "Definir tema" e não há subtarefa de tema aberta."""
    rs = regras(cfg)
    if not rs:
        return []
    hoje = hoje or date.today()
    eu = _norm(((cfg.get("pessoa") or {}).get("nome")) or "").split(" ")[0]
    saida = []
    for ev in eventos(oper):
        quando = _data(ev.get("data"))
        r = _regra_do_evento(ev, rs)
        if not r or not quando or not hoje <= quando <= hoje + timedelta(days=horizonte):
            continue
        nome_ev = re.sub(r"\s*[—-]\s*definir tema\s*$", "", str(ev.get("nome") or r.get("nome") or "evento"), flags=re.I).strip()
        abertas = [s for s in ev.get("etapas") or [] if _norm(s.get("status")) not in FEITO]
        vistas = set()
        for regra in r["etapas"]:
            palavras = [_norm(p) for p in regra.get("palavras") or []]
            limite = quando - timedelta(days=int(regra.get("dias_antes") or 0))
            for s in abertas:
                if s.get("id") in vistas or not any(p in _norm(s.get("nome")) for p in palavras):
                    continue
                vistas.add(s.get("id"))
                donos = [str(d) for d in s.get("donos") or []]
                saida.append({"id": s.get("id"), "titulo": s.get("nome"), "evento": nome_ev, "data_evento": quando, "rotulo": regra.get("rotulo") or palavras[0],
                              "limite": limite, "dono": ", ".join(donos) or "sem dono", "eu": (not donos) or any(eu and eu in _norm(d) for d in donos),
                              "sugestao": _data(s.get("prazo"))})
            if "tema" in " ".join(palavras) and "definir tema" in _norm(ev.get("nome")) and not any("tema" in _norm(s.get("nome")) for s in abertas):
                saida.append({"id": None, "titulo": f"Definir o tema da {nome_ev}", "evento": nome_ev, "data_evento": quando, "rotulo": "tema definido",
                              "limite": limite, "dono": "sem tarefa", "eu": True, "sugestao": None})
    saida.sort(key=lambda e: (e["limite"], str(e["titulo"])))
    return saida


def da_pessoa(cfg, oper, hoje=None):
    return [e for e in etapas(cfg, oper, hoje) if e["eu"]]


def ids(cfg, oper, hoje=None):
    """Ids das etapas dela: o plano base não as trata como tarefa comum com data (o prazo do ClickUp é da automação)."""
    return {e["id"] for e in da_pessoa(cfg, oper, hoje) if e["id"]}


def linha(e):
    dia_ev = f"{DIAS[e['data_evento'].weekday()]} {e['data_evento']:%d/%m}"
    return (f"- [preparo] {str(e['titulo'])[:70]} | {e['evento'][:60]} ({dia_ev}) | {e['rotulo']} até {DIAS[e['limite'].weekday()]} {e['limite']:%d/%m}"
            + (f" | dono {e['dono']}" if not e["eu"] else "") + (f" | sugestão do ClickUp {e['sugestao']:%d/%m}" if e["sugestao"] else "")
            + (f" | id {e['id']}" if e["id"] else " | ainda sem tarefa no ClickUp"))


def motivos(dia, cfg, oper, hoje=None, ids_em_outros=()):
    """Linhas para o dossiê do plano de `dia`: etapas dela com limite a até ABRE_DIAS dias e ainda sem lugar em outro plano; cobranças vencidas."""
    hoje = hoje or date.today()
    todas = etapas(cfg, oper, hoje)
    minhas = [e for e in todas if e["eu"] and e["limite"] <= dia + timedelta(days=ABRE_DIAS) and e["id"] not in set(ids_em_outros)]
    outras = [e for e in todas if not e["eu"] and e["limite"] <= dia]
    saida = []
    if minhas:
        saida.append(f"PREPARO DE EVENTO A ENCAIXAR ({len(minhas)}): cada etapa termina ATÉ o limite (regra dela; o prazo do ClickUp é da automação). "
                     "Ponha neste dia ou num dia anterior ao limite, no horário que o tipo pede (tema = decisão, faixa boa; thumb = design).\n"
                     + "\n".join(linha(e) for e in minhas))
    if outras:
        saida.append(f"COBRAR NO PREPARO ({len(outras)}): etapas de outra pessoa que chegaram ao limite e seguem abertas. Sem elas a divulgação não sai. "
                     "Um bloco curto (5 min) para conferir com o dono já está no plano base.\n" + "\n".join(linha(e) for e in outras))
    return saida


def inserir_cobrancas(plano, dia, cfg, oper, nome="Eu", hoje=None):
    """Bloco de 5 min "Conferir com <dono>: <etapa>" no plano do dia em que a etapa de outra pessoa venceu (ou depois, enquanto aberta). Sem clickup_id."""
    import rota_agenda as ra
    import visao_semana as vs
    memoria = ((cfg or {}).get("pastas") or {}).get("memoria")
    criados = []
    titulos = {_norm(b.get("titulo")) for b in plano.get("blocos") or []}
    for e in etapas(cfg, oper, hoje or dia):
        if e["eu"] or e["limite"] > dia:
            continue
        titulo = f"Conferir com {e['dono'].split(',')[0]}: {e['rotulo']} da {e['evento'][:50]}"
        if _norm(titulo) in titulos:
            continue
        vaos = [(x, y) for x, y in ra.espacos(plano, dia, "leve", memoria=memoria) if y - x >= 5]
        if not vaos:
            continue
        ini = vaos[0][0]
        plano.setdefault("blocos", []).append({"id": _id_livre(plano), "inicio": vs.fmt(ini), "fim": vs.fmt(ini + 5), "titulo": titulo, "dono": nome,
                                               "frente": "Conteúdo", "cobranca_de": e["id"],
                                               "descricao": f"{e['titulo']} ({e['dono']}) devia estar pronta até {e['limite']:%d/%m}. Sem isso a antecipação da live não sai.",
                                               "primeiro_passo": f"Mande uma mensagem para {e['dono'].split(',')[0]} perguntando se já está feito e quando fica.",
                                               "por_que_agora": "A etapa venceu e a live depende dela."})
        plano["blocos"].sort(key=lambda b: b.get("inicio") or "")
        titulos.add(_norm(titulo))
        criados.append(plano["blocos"][-1])
    return criados


def conferir(plano, dia, cfg, oper, outros=None, hoje=None):
    """Etapa dela num dia depois do limite; etapa dela com limite já chegado (hoje ou antes) fora de qualquer plano."""
    hoje = hoje or date.today()
    minhas = da_pessoa(cfg, oper, hoje)
    if not minhas:
        return []
    iso = dia.isoformat()
    no_plano = {b.get("clickup_id") for b in plano.get("blocos") or [] if b.get("clickup_id")}
    em_outros = {b.get("clickup_id") for d, p in (outros or {}).items() if d != iso for b in p.get("blocos") or [] if b.get("clickup_id")}
    problemas = []
    for e in minhas:
        if e["id"] in no_plano and dia > e["limite"]:
            problemas.append(f"\"{e['titulo']}\" ({iso[8:10]}/{iso[5:7]}) passa do limite do preparo da {e['evento'][:50]}: {e['rotulo']} até "
                             f"{DIAS[e['limite'].weekday()]} {e['limite']:%d/%m}. Mova para antes.")
        elif e["id"] and e["limite"] <= dia and e["id"] not in no_plano and e["id"] not in em_outros:
            problemas.append(f"O preparo \"{e['titulo']}\" da {e['evento'][:50]} chegou ao limite ({e['limite']:%d/%m}) e não está em nenhum plano. "
                             "Ponha neste dia ou antes.")
    return problemas
