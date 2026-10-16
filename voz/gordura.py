"""Gordura de posts (decisão da Milena, 2026-10-15): os posts saem em dias fixos da semana (segunda, quarta e sexta) e o ideal é ter 1 a 2 posts JÁ PRONTOS à frente,
para um imprevisto não derrubar a postagem. Enquanto a gordura está abaixo da meta, criar copy e design à frente é prioridade; ao alcançá-la, a rotina de
criação fica previsível (copies num dia fixo, designs em outro) e o guardião propõe isso.

Liga pelo config.json: "rotina": {"posts": {"dias_semana": [0, 2, 4], "gordura_meta": 2, "gordura_minima": 1}} (0 = segunda). Sem a chave, o recurso fica desligado.
Um post está PRONTO quando a tarefa mãe tem copy e design e todos estão concluídos (posts_maes.json). Só conta post com data depois de hoje."""
from datetime import date, timedelta

import etapas_post as ep


def configuracao(cfg):
    p = ((cfg or {}).get("rotina") or {}).get("posts")
    if not isinstance(p, dict) or not p.get("dias_semana"):
        return None
    meta = int(p.get("gordura_meta") or 2)
    return {"dias": {int(d) for d in p["dias_semana"]}, "meta": meta, "minima": min(int(p.get("gordura_minima") or 1), meta)}


def _concluida(e):
    return str(e.get("status") or "").lower() in ("complete", "concluida", "concluída", "closed")


def _pronto(mae):
    etapas = [e for e in mae.get("etapas") or [] if ep.tipo_da_etapa(e.get("nome")) in ("copy", "design")]
    tipos = {ep.tipo_da_etapa(e.get("nome")) for e in etapas}
    return {"copy", "design"} <= tipos and all(_concluida(e) for e in etapas)


def situacao(maes, cfg, hoje=None, dias_a_frente=14):
    """Dict com os dias de post, quais estão prontos, a gordura atual e a meta; None se o recurso está desligado."""
    conf = configuracao(cfg)
    if not conf:
        return None
    hoje = hoje or date.today()
    por_dia = {}
    for m in maes or []:
        try:
            d = date.fromisoformat(str(m.get("prazo") or "")[:10])
        except ValueError:
            continue
        por_dia.setdefault(d, []).append(m)
    prontos, faltando = [], []
    for i in range(1, dias_a_frente + 1):
        d = hoje + timedelta(days=i)
        if d.weekday() not in conf["dias"]:
            continue
        (prontos if any(_pronto(m) for m in por_dia.get(d, [])) else faltando).append(d)
    # a gordura é a sequência de posts prontos a partir do próximo dia de post (um buraco no meio quebra a contagem)
    seguidos = 0
    for d in sorted(prontos + faltando):
        if d in prontos:
            seguidos += 1
        else:
            break
    return {"prontos": prontos, "faltando": faltando, "gordura": seguidos, "meta": conf["meta"], "minima": conf["minima"]}


def texto(s):
    """Parágrafo do dossiê do plano."""
    if not s:
        return ""
    fmt = lambda ds: ", ".join(f"{d:%d/%m}" for d in ds) or "nenhum"
    base = (f"GORDURA DE POSTS: {s['gordura']} pronto(s) em sequência à frente (meta {s['meta']}, mínimo {s['minima']}). Prontos: {fmt(s['prontos'])}. "
            f"Ainda sem copy e design concluídos: {fmt(s['faltando'][:6])}. ")
    if s["gordura"] < s["minima"]:
        return base + ("ABAIXO DO MÍNIMO: terminar o próximo post é a prioridade da criação, acima de outra tarefa que não tenha prazo máximo. "
                       "Ponha copy e design dele antes dos demais e diga no aviso quando a gordura volta ao mínimo.")
    if s["gordura"] < s["meta"]:
        return base + "Abaixo da meta: use o tempo de criação para adiantar o próximo post da sequência, sem tirar tarefa com prazo máximo."
    return base + ("Meta alcançada: a criação pode virar rotina previsível. Proponha no aviso um dia fixo da semana para as copies e outro para os designs "
                   "dos posts seguintes (a pessoa decide) e mantenha a gordura.")
