# Estatísticas da calibragem (aba Estatísticas do painel). Só conta o que o app gravou, em Python, sem o Claude.
# Quatro números no topo, semana a semana (plano cumprido, tarefa principal feita, precisão das estimativas, foco medido) e o detalhe:
# atraso para começar, adiamentos e motivos, o que entra fora do plano, entregas no prazo, trabalho depois da hora, energia e foco por natureza.
# Com menos de MIN_DADOS no denominador o número fica None e a tela diz "pouco dado ainda".
from collections import Counter
from datetime import date, timedelta

import calibragem_motor as cm

SEMANAS = 8
MIN_DADOS = 3
PRECISAO = 0.2  # desvio de até 20% do planejado (ou 5 minutos, o que for maior) conta como estimativa certa


def _semana(d):
    return d - timedelta(days=d.weekday())


def _pct(a, b):
    return round(100 * a / b) if b and b >= MIN_DADOS else None


def _dias(oper, hoje):
    """Os dias com plano das últimas SEMANAS semanas, mais antigos primeiro: (data, registro, blocos de trabalho)."""
    inicio = _semana(hoje) - timedelta(weeks=SEMANAS - 1)
    saida, d = [], inicio
    while d <= hoje:
        reg = cm.registro(oper, d.isoformat())
        blocos = cm._blocos_de_trabalho(reg)
        if blocos:
            saida.append((d, reg, blocos))
        d += timedelta(days=1)
    return saida, inicio


def _certa(e):
    plan = e.get("planejado") or 0
    return abs(e.get("desvio") or 0) <= max(5, PRECISAO * plan)


def calcular(oper, hoje=None):
    hoje = hoje or date.today()
    dias, inicio = _dias(oper, hoje)
    evs = cm.eventos(oper, inicio.isoformat(), hoje.isoformat())
    semanas = [inicio + timedelta(weeks=i) for i in range(SEMANAS)]
    por_semana = {s: {"feitas": 0, "planejadas": 0, "principal": 0, "dias_principal": 0, "certas": 0, "medidas": 0, "foco": 0,
                      "replanejamentos": 0, "adiamentos": 0, "fora": 0, "dias": 0} for s in semanas}
    depois_da_hora = 0
    energia_cumprimento = {}
    foco_natureza = Counter()
    for d, reg, blocos in dias:
        s = por_semana[_semana(d)]
        feitas = sum(1 for b in blocos if b.get("estado") == "feito")
        s["feitas"] += feitas
        s["planejadas"] += len(blocos)
        s["dias"] += 1
        principal, _ = cm._principal(blocos)
        if principal:
            s["dias_principal"] += 1
            s["principal"] += 1 if principal.get("estado") == "feito" else 0
        fim = max((cm._minutos_hm((b.get("planejado") or {}).get("fim")) or 0) for b in blocos)
        for sessao in cm.execucao(oper, d.isoformat()).get("sessoes") or []:
            m = cm._trabalhado(sessao)
            s["foco"] += m
            foco_natureza[cm.natureza_do_bloco({"titulo": sessao.get("titulo"), "frente": sessao.get("frente")})] += m
            for t in sessao.get("trechos") or []:
                a, b = cm._minutos_hm(t.get("de")), cm._minutos_hm(t.get("ate"))
                if a is not None and b is not None and b > fim:
                    depois_da_hora += b - max(a, fim)
        r = cm.report(oper, d.isoformat())
        if r and isinstance(r.get("energia"), int):
            energia_cumprimento.setdefault(r["energia"], []).append(feitas / len(blocos))
    atrasos_faixa, motivos, entregas = {}, Counter(), Counter()
    fora_dia = Counter()
    for e in evs:
        dia = date.fromisoformat(e["data"])
        s = por_semana.get(_semana(dia))
        tipo = e.get("tipo")
        if tipo == "conclusao":
            if s is not None and e.get("confirmado") and e.get("natureza") not in cm.SEM_MEDIA and e.get("real") is not None:
                s["medidas"] += 1
                s["certas"] += 1 if _certa(e) else 0
            if e.get("prazo"):
                entregas["adiantada" if e["data"] < e["prazo"] else ("no_prazo" if e["data"] == e["prazo"] else "atrasada")] += 1
        elif tipo in cm.REPLANEJAMENTO and s is not None:
            s["replanejamentos"] += 1
        elif tipo == "adiamento" and s is not None:
            s["adiamentos"] += 1
        elif tipo in ("tarefas_novas", "imprevisto_encaixado") and s is not None:
            n = int(e.get("quantidade") or 1)
            s["fora"] += n
            fora_dia[dia.weekday()] += n
        elif tipo == "inicio_bloco" and isinstance(e.get("atraso"), (int, float)):
            f, _ = cm._faixa(cm._minutos_hm(e.get("planejado")))
            if f:
                atrasos_faixa.setdefault(f, []).append(e["atraso"])
        if e.get("motivo") and tipo in ("adiamento", "extensao", "motivo", "imprevisto"):
            motivos[e["motivo"]] += 1
    serie = []
    for sem in semanas:
        s = por_semana[sem]
        serie.append({"semana": sem.isoformat(), "rotulo": f"{sem:%d/%m}", "dias": s["dias"],
                      "cumprido": _pct(s["feitas"], s["planejadas"]), "principal": _pct(s["principal"], s["dias_principal"]),
                      "precisao": _pct(s["certas"], s["medidas"]), "foco_h": round(s["foco"] / 60, 1) if s["dias"] else None,
                      "replanejamentos": s["replanejamentos"], "adiamentos": s["adiamentos"], "fora_do_plano": s["fora"]})
    com_dados = [x for x in serie if x["dias"]]
    atual = com_dados[-1] if com_dados else None
    anterior = com_dados[-2] if len(com_dados) >= 2 else None

    def kpi(chave, rotulo, unidade, ajuda):
        v = atual.get(chave) if atual else None
        a = anterior.get(chave) if anterior else None
        return {"chave": chave, "rotulo": rotulo, "valor": v, "unidade": unidade, "anterior": a, "ajuda": ajuda,
                "variacao": (round(v - a, 1) if isinstance(v, (int, float)) and isinstance(a, (int, float)) else None),
                "serie": [x.get(chave) for x in serie]}
    kpis = [kpi("cumprido", "Plano cumprido", "%", "Tarefas feitas sobre as planejadas, na semana."),
            kpi("principal", "Tarefa principal feita", "%", "Dias em que a tarefa que mais importava saiu."),
            kpi("precisao", "Precisão das estimativas", "%", "Tarefas medidas que terminaram perto do tempo planejado."),
            kpi("foco_h", "Foco medido", "h", "Horas trabalhadas com a tarefa iniciada no modo execução.")]
    dias_semana = {}
    contagem_dias = Counter(d.weekday() for d, _, _ in dias)
    for dsem in sorted(contagem_dias):  # de segunda a domingo, só os dias em que entrou algo
        if fora_dia[dsem]:
            dias_semana[cm.DIAS_NOME[dsem]] = round(fora_dia[dsem] / contagem_dias[dsem], 1)
    utilidade = None
    if len(com_dados) >= 4:  # as duas primeiras semanas com dados contra as duas últimas
        def media(lista, chave):
            v = [x[chave] for x in lista if isinstance(x.get(chave), (int, float))]
            return round(sum(v) / len(v), 1) if v else None
        comeco, agora = com_dados[:2], com_dados[-2:]
        utilidade = [{"rotulo": r, "antes": media(comeco, c), "agora": media(agora, c), "melhor_se": m} for r, c, m in
                     (("Plano cumprido (%)", "cumprido", "maior"), ("Precisão das estimativas (%)", "precisao", "maior"),
                      ("Replanejamentos por semana", "replanejamentos", "menor"), ("Tarefas fora do plano por semana", "fora_do_plano", "menor"))]
    total_entregas = sum(entregas.values())
    try:  # o que entra fora do plano e se repete (vem do perfil da calibragem)
        repetidas = [{"exemplo": r["exemplo"], "vezes": r["vezes"], "hora": r.get("hora"), "lista": r.get("lista")} for r in (cm.atualizar_perfil(oper).get("repetidas") or [])][:5]
    except Exception:
        repetidas = []
    return {
        "repetidas": repetidas,
        "semanas": serie, "kpis": kpis, "dias_com_plano": len(dias),
        "atraso_por_faixa": [{"faixa": cm._nome_faixa(f), "mediana": round(cm._mediana(v)), "n": len(v)} for f, v in atrasos_faixa.items() if len(v) >= MIN_DADOS],
        "motivos": [{"motivo": m, "vezes": k} for m, k in motivos.most_common(5)],
        "fora_por_dia": dias_semana,
        "entregas": {k: entregas[k] for k in ("adiantada", "no_prazo", "atrasada")} if total_entregas >= MIN_DADOS else None,
        "depois_da_hora_min": depois_da_hora,
        "energia": [{"energia": e, "cumprido": round(100 * sum(v) / len(v)), "dias": len(v)} for e, v in sorted(energia_cumprimento.items())],
        "foco_por_natureza": [{"natureza": cm.rotulo(n), "horas": round(m / 60, 1)} for n, m in foco_natureza.most_common(6) if m >= 15],
        "utilidade": utilidade,
    }
