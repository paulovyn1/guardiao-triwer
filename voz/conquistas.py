# Conquistas da calibragem (aba Conquistas do painel). Premiam o que melhora o plano e protege o resultado, nunca volume:
# não há ponto por tarefa feita (incentivaria quebrar tarefa à toa) e a precisão conta para os dois lados (estimar com folga demais não ganha).
# Tudo calculado em Python a partir do que o app grava. A conquista desbloqueada fica em calibragem\conquistas.json e não volta a travar.
import json
import os
import re
from collections import Counter
from datetime import date, timedelta

import calibragem_motor as cm

PESADAS = cm.PESADAS
LISTA = [
    # (id, grupo, título, regra, meta)
    ("primeiro_report", "Constância", "Primeiro report", "Mandar o primeiro report do dia.", 1),
    ("calib_7", "Constância", "Semana calibrada", "Report em 7 dias de trabalho.", 7),
    ("calib_14", "Constância", "Duas semanas", "Report em 14 dias de trabalho.", 14),
    ("calib_21", "Constância", "Três semanas", "Report em 21 dias de trabalho.", 21),
    ("calib_30", "Constância", "O Guardião te conhece", "Report em 30 dias de trabalho.", 30),
    ("calib_60", "Constância", "Calibragem contínua", "Report em 60 dias de trabalho.", 60),
    ("calib_90", "Constância", "Noventa dias", "Report em 90 dias de trabalho.", 90),
    ("primeiro_medido", "Foco", "Primeiro bloco medido", "Iniciar e concluir uma tarefa no modo execução.", 1),
    ("manha_protegida", "Foco", "Manhã protegida", "Concluir tarefa pesada (copy, decisão, criação, tráfego, dev, estudo) de manhã em 3 dias da mesma semana.", 3),
    ("duas_horas", "Foco", "Duas horas de foco", "Somar 2 horas de foco medido no mesmo dia.", 120),
    ("principal_cedo", "O que importa", "O principal primeiro", "Concluir a tarefa principal do dia antes do almoço (12h30).", 1),
    ("cinco_principais", "O que importa", "Cinco dias no que importa", "Concluir a tarefa principal em 5 dias de trabalho seguidos.", 5),
    ("destravei", "Destravar", "Destravei", "Concluir uma tarefa que tinha sido adiada 2 vezes ou mais.", 1),
    ("no_horario", "Destravar", "No horário", "Começar 5 tarefas até 5 minutos do horário no mesmo dia.", 5),
    ("estimativa_afiada", "Previsão", "Estimativa afiada", "5 tarefas medidas seguidas terminando perto do tempo planejado (até 15% para mais ou para menos).", 5),
    ("tipo_calibrado", "Previsão", "Tipo calibrado", "Ter uma natureza de tarefa com tempo real confirmado (3 medições).", 3),
    ("semana_certeira", "Previsão", "Semana certeira", "Uma semana com 80% do plano cumprido e nenhum replanejamento automático.", 1),
    ("primeira_regra", "Ensinar o Guardião", "Primeira regra", "Corrigir o Guardião e ver a correção virar uma regra no aprendizados.md.", 1),
    ("padrao_confirmado", "Ensinar o Guardião", "Padrão confirmado", "Responder sim à pergunta do dia: um padrão seu vira regra.", 1),
    ("rotina_mapeada", "Ensinar o Guardião", "Rotina mapeada", "Aceitar transformar uma tarefa que sempre aparece fora do plano em bloco fixo ou POP.", 1),
    ("semana_fechada", "Ensinar o Guardião", "Semana fechada", "Fazer o fechamento da semana com o Guardião.", 1),
]


def _arquivo(oper):
    return os.path.join(cm._pasta_cal(oper), "conquistas.json")


def _dias_com_plano(oper, hoje, janela=400):
    saida = []
    for i in range(janela, -1, -1):
        d = hoje - timedelta(days=i)
        blocos = cm._blocos_de_trabalho(cm.registro(oper, d.isoformat()))
        if blocos:
            saida.append((d, blocos))
    return saida


def _reports(oper):
    try:
        return sorted(n[:10] for n in os.listdir(os.path.join(cm._pasta_cal(oper), "reports")) if re.match(r"\d{4}-\d{2}-\d{2}\.json$", n))
    except OSError:
        return []


def _regras_no_aprendizados(memoria):
    try:
        with open(os.path.join(memoria, "aprendizados.md"), encoding="utf-8-sig") as f:
            texto = f.read()
    except (OSError, TypeError):
        return 0
    parte = texto.split("## Regras", 1)[-1]
    return sum(1 for linha in parte.splitlines() if linha.strip().startswith(("- ", "* ", "1")) and "nenhuma ainda" not in linha.lower())


def progresso(oper, memoria=None, hoje=None):
    """{id: valor atual} de cada conquista (o maior já alcançado, para a barra de progresso)."""
    hoje = hoje or date.today()
    evs = cm.eventos(oper, (hoje - timedelta(days=400)).isoformat())
    p = {}
    n_reports = len(_reports(oper))
    for cid in ("primeiro_report", "calib_7", "calib_14", "calib_21", "calib_30", "calib_60", "calib_90"):
        p[cid] = n_reports
    conclusoes = [e for e in evs if e.get("tipo") == "conclusao"]
    p["primeiro_medido"] = sum(1 for e in conclusoes if e.get("medido"))
    # manhã protegida: dias da mesma semana com tarefa pesada concluída de manhã
    por_semana = Counter()
    dias_vistos = set()
    for e in conclusoes:
        ini = cm._minutos_hm(e.get("inicio_planejado"))
        if e.get("natureza") in PESADAS and ini is not None and ini < 12 * 60 and (e["data"]) not in dias_vistos:
            dias_vistos.add(e["data"])
            d = date.fromisoformat(e["data"])
            por_semana[d - timedelta(days=d.weekday())] += 1
    p["manha_protegida"] = max(por_semana.values(), default=0)
    # foco por dia
    focos = []
    for e_dia in {e["data"] for e in evs}:
        focos.append(sum(cm._trabalhado(s) for s in cm.execucao(oper, e_dia).get("sessoes") or []))
    p["duas_horas"] = max(focos, default=0)
    # tarefa principal
    dias = _dias_com_plano(oper, hoje)
    conclusao_por_dia_bloco = {(e["data"], e.get("bloco")): e for e in conclusoes}
    cedo, seq, melhor = 0, 0, 0
    for d, blocos in dias:
        principal, _ = cm._principal(blocos)
        if not principal:
            continue
        feita = principal.get("estado") == "feito"
        seq = seq + 1 if feita else 0
        melhor = max(melhor, seq)
        c = conclusao_por_dia_bloco.get((d.isoformat(), principal.get("id")))
        if feita and c and (cm._minutos_hm(c.get("hora")) or 9999) <= 12 * 60 + 30:
            cedo += 1
    p["principal_cedo"] = cedo
    p["cinco_principais"] = melhor
    # destravar
    adiadas = Counter()
    destravou = 0
    for e in sorted(evs, key=lambda x: x.get("ts", "")):
        if e.get("tipo") == "adiamento" and e.get("titulo"):
            adiadas[e["titulo"]] += 1
        elif e.get("tipo") == "conclusao" and adiadas.get(e.get("titulo"), 0) >= 2:
            destravou += 1
    p["destravei"] = destravou
    no_horario = Counter(e["data"] for e in evs if e.get("tipo") == "inicio_bloco" and isinstance(e.get("atraso"), (int, float)) and abs(e["atraso"]) <= 5)
    p["no_horario"] = max(no_horario.values(), default=0)
    # previsão
    seq, melhor = 0, 0
    for e in sorted(conclusoes, key=lambda x: x.get("ts", "")):
        if not e.get("medido") or e.get("natureza") in cm.SEM_MEDIA or e.get("real") is None:
            continue
        plan = e.get("planejado") or 0
        seq = seq + 1 if plan and abs(e.get("desvio") or 0) <= 0.15 * plan else 0
        melhor = max(melhor, seq)
    p["estimativa_afiada"] = melhor
    cm.garantir_tempos(oper)
    tempos = (cm._ler(os.path.join(oper, "tempos.json")) or {}).get("tipos") or {}
    p["tipo_calibrado"] = max((sum(1 for r in t.get("registros") or [] if r.get("confirmado")) for n, t in tempos.items() if n not in cm.SEM_MEDIA), default=0)
    semanas = {}
    for d, blocos in dias:
        s = semanas.setdefault(d - timedelta(days=d.weekday()), [0, 0, 0])
        s[0] += sum(1 for b in blocos if b.get("estado") == "feito")
        s[1] += len(blocos)
        s[2] += 1
    replan = Counter(date.fromisoformat(e["data"]) - timedelta(days=date.fromisoformat(e["data"]).weekday()) for e in evs if e.get("tipo") in cm.REPLANEJAMENTO)
    p["semana_certeira"] = 1 if any(dias_s >= 3 and plan and feitas / plan >= 0.8 and not replan.get(sem) and sem < hoje - timedelta(days=hoje.weekday())
                                    for sem, (feitas, plan, dias_s) in semanas.items()) else 0
    # ensinar o guardião
    p["primeira_regra"] = _regras_no_aprendizados(memoria)
    p["padrao_confirmado"] = sum(1 for c in cm._confirmacoes(oper).values() if c.get("resposta") == "sim")
    p["rotina_mapeada"] = sum(1 for e in evs if e.get("tipo") == "rotina_aceita")
    escrito = cm._ler(os.path.join(cm._pasta_cal(oper), "aprendizados.json")) or {}
    p["semana_fechada"] = 1 if (escrito.get("atualizado_em") or any(e.get("tipo") == "fechamento_semanal" for e in evs)) else 0
    return p


def calcular(oper, memoria=None, hoje=None):
    """A lista para a tela e as que acabaram de ser desbloqueadas. Na primeira vez (sem conquistas.json), o que já estava cumprido entra
    como retroativo, sem anúncio: ninguém quer ouvir oito conquistas de uma vez ao atualizar o guardião."""
    hoje = hoje or date.today()
    caminho = _arquivo(oper)
    salvo = cm._ler(caminho)
    primeira_vez = salvo is None
    salvo = salvo or {}
    prog = progresso(oper, memoria, hoje)
    lista, novas = [], []
    for cid, grupo, titulo, regra, meta in LISTA:
        valor = int(prog.get(cid) or 0)
        if valor >= meta and cid not in salvo:
            salvo[cid] = {"data": hoje.isoformat(), "retroativa": primeira_vez}
            if not primeira_vez:
                novas.append({"id": cid, "titulo": titulo})
        info = salvo.get(cid)
        unidade = "min" if cid == "duas_horas" else ("dias" if cid.startswith("calib_") or cid in ("cinco_principais", "manha_protegida") else "")
        lista.append({"id": cid, "grupo": grupo, "titulo": titulo, "regra": regra, "meta": meta, "progresso": min(valor, meta), "unidade": unidade,
                      "desbloqueada": (info or {}).get("data"), "nova": bool(info and info.get("data") == hoje.isoformat() and not info.get("retroativa"))})
    if (novas or primeira_vez) and cm.pode_gravar(oper):
        os.makedirs(cm._pasta_cal(oper), exist_ok=True)
        cm._gravar(caminho, salvo)
    return {"lista": lista, "novas": novas, "total": len(LISTA), "desbloqueadas": sum(1 for c in lista if c["desbloqueada"])}
