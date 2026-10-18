"""Calibragem semanal (decisão de produto, 2026-10-15): uma vez por semana, no sábado, o guardião olha o que os dados da semana apontam, formula
hipóteses e PERGUNTA, em vez de pesar cada requisição com a calibragem. Cada resposta vira uma ação, senão a pergunta é enfeite:
- medição: tarefas "concluídas em 1 minuto" (feitas fora do painel e marcadas depois) saem da média do tempos.json;
- desvio: o que o plano estima por frente e o que levou de verdade, com o motivo dito por ela, vira uma linha de calibragem\\regras.md,
  que o gerador do plano e o revisor leem ao estimar.
Só pergunta com amostra (3 ou mais registros na mesma direção, como a regra do tempos.json), no máximo 3 perguntas por semana, sempre com o número.
As perguntas entram no contexto da conversa só no fim de semana, até serem respondidas, e o guardião faz uma por vez no fechamento da semana.
Gerado por código, sem Claude: a conta é barata e determinística."""
import json
import os
import re
import statistics
import unicodedata
from datetime import date, timedelta

import calibragem_motor as cm
import rota_agenda as ra

OPER = ra.OPER
MAX_PERGUNTAS = 3
MIN_AMOSTRA = 3
DIAS_SEMANA = 7  # a hipótese de medição olha a semana
DIAS_DESVIO = 14  # o desvio por frente olha duas semanas, para ter amostra
LIMITE_ALTO, LIMITE_BAIXO = 1.5, 0.6
SIM = re.compile(r"\b(sim|isso|exato|fiz|fora|depois|marquei|antes|foi|aconteceu)\b")
NAO = re.compile(r"\b(nao|nunca)\b")


def _norm(t):
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower()) if unicodedata.category(c) != "Mn")


def _semana(dia):
    ano, sem, _ = dia.isocalendar()
    return f"{ano}-W{sem:02d}"


def _pasta(oper):
    return os.path.join(oper, "calibragem")


def _caminho(oper, dia):
    return os.path.join(_pasta(oper), f"perguntas_{_semana(dia)}.json")


def _conclusoes(oper, desde):
    saida = []
    try:
        with open(os.path.join(_pasta(oper), "eventos.jsonl"), encoding="utf-8") as f:
            for linha in f:
                try:
                    ev = json.loads(linha)
                except ValueError:
                    continue
                if ev.get("tipo") == "conclusao" and str(ev.get("data") or "") >= desde and isinstance(ev.get("real"), (int, float)):
                    saida.append(ev)
    except OSError:
        pass
    return saida


def analisar(oper=OPER, hoje=None):
    """Lista de perguntas (dicts) que os dados da semana levantam, a mais importante primeiro."""
    hoje = hoje or date.today()
    semana = _semana(hoje)
    perguntas = []
    recentes = _conclusoes(oper, (hoje - timedelta(days=DIAS_SEMANA)).isoformat())
    # desde a 0.11.0 o tempo marcado depois, sem medir, já sai da média sozinho (confirmado=false): só pergunta o que ainda conta
    rapidas = [e for e in recentes if e.get("real", 99) <= 2 and (e.get("planejado") or 0) >= 5 and e.get("confirmado")]
    if len(rapidas) >= 2:
        ex = "; ".join(f"{e.get('titulo')} ({e.get('planejado')} min planejados)" for e in rapidas[:3])
        perguntas.append({"id": f"medicao-{semana}", "tipo": "medicao",
                          "texto": f"{len(rapidas)} tarefas desta semana aparecem concluídas em cerca de 1 minuto no painel, por exemplo: {ex}. "
                                   "Você fez essas fora do painel e só marcou como concluída depois?",
                          "registros": [{"data": e.get("data"), "titulo": e.get("titulo")} for e in rapidas]})
    ja = {(e.get("data"), e.get("titulo")) for e in rapidas}
    por_frente = {}
    for e in _conclusoes(oper, (hoje - timedelta(days=DIAS_DESVIO)).isoformat()):
        if e.get("confirmado") and (e.get("real") or 0) >= 3 and (e.get("planejado") or 0) > 0 and (e.get("data"), e.get("titulo")) not in ja:
            chave = cm.rotulo(e["natureza"]) if e.get("natureza") else str(e.get("frente") or "sem frente")  # natureza do trabalho (0.11.0); antes, a frente
            por_frente.setdefault(chave, []).append(e)
    candidatas = []
    for frente, evs in por_frente.items():
        if len(evs) < MIN_AMOSTRA:
            continue
        razoes = [e["real"] / e["planejado"] for e in evs]
        r = statistics.median(razoes)
        sentido_igual = sum(1 for x in razoes if (x > 1) == (r > 1)) >= MIN_AMOSTRA
        if (r >= LIMITE_ALTO or r <= LIMITE_BAIXO) and sentido_igual:
            candidatas.append((abs(r - 1), frente, evs, r))
    for _peso, frente, evs, r in sorted(candidatas, key=lambda c: -c[0]):
        plan, real = round(statistics.median(e["planejado"] for e in evs)), round(statistics.median(e["real"] for e in evs))
        slug = re.sub(r"[^a-z0-9]+", "-", _norm(frente)).strip("-")[:30]
        perguntas.append({"id": f"desvio-{slug}-{semana}", "tipo": "desvio", "frente": frente, "planejado": plan, "real": real, "n": len(evs),
                          "texto": f"Em \"{frente}\", nas últimas duas semanas, {len(evs)} tarefas: o que eu planejei em cerca de {plan} min levou cerca de {real} min "
                                   f"({'mais' if r > 1 else 'menos'} do que o previsto, {round(r, 1)} vez). O que explica? "
                                   "(era mais fácil ou mais difícil que o normal, uma parte foi pulada, houve interrupção)"})
    return perguntas[:MAX_PERGUNTAS]


def gerar(oper=OPER, hoje=None):
    """Grava as perguntas da semana (uma vez por semana). Devolve o caminho."""
    hoje = hoje or date.today()
    caminho = _caminho(oper, hoje)
    if os.path.exists(caminho):
        return caminho
    os.makedirs(_pasta(oper), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump({"semana": _semana(hoje), "geradas_em": hoje.isoformat(), "perguntas": analisar(oper, hoje), "respostas": {}}, f, ensure_ascii=False, indent=1)
    return caminho


def gerar_se_sabado(oper=OPER, hoje=None):
    hoje = hoje or date.today()
    if hoje.weekday() >= 5:  # sábado ou domingo (se o computador estava desligado no sábado)
        return gerar(oper, hoje)
    return None


def _ler(oper, hoje):
    try:
        with open(_caminho(oper, hoje), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def pendentes(oper=OPER, hoje=None):
    hoje = hoje or date.today()
    dados = _ler(oper, hoje) or {}
    return [p for p in dados.get("perguntas") or [] if p["id"] not in (dados.get("respostas") or {})]


def contexto(oper=OPER, hoje=None):
    """Bloco do contexto da conversa: só no fim de semana e enquanto houver pergunta sem resposta."""
    hoje = hoje or date.today()
    if hoje.weekday() < 5:
        return ""
    ps = pendentes(oper, hoje)
    if not ps:
        return ""
    return ("PERGUNTAS DA CALIBRAGEM DA SEMANA (os dados levantaram hipóteses; só ela pode confirmar). Faça UMA por vez, no fechamento da semana ou quando ela abrir o assunto, "
            "nunca no meio de uma tarefa. Diga o número, pergunte com as palavras do texto e não sugira a resposta. Só depois que ela responder, use a marca "
            "{{calibrar:ID|resposta dela, com as palavras dela}}. Pendentes:\n" + "\n".join(f"- {p['id']}: {p['texto']}" for p in ps))


def _descartar(oper, registros):
    """Tira da média os registros que ela disse terem sido feitos fora do painel: confirmado=false e descartado=true."""
    caminho = os.path.join(oper, "tempos.json")
    try:
        with open(caminho, encoding="utf-8-sig") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        return 0
    alvo = {(r.get("data"), r.get("titulo")) for r in registros}
    n = 0
    for info in (dados.get("tipos") or {}).values():
        for r in info.get("registros") or []:
            if (r.get("data"), r.get("titulo")) in alvo and not r.get("descartado"):
                r["confirmado"], r["descartado"] = False, True
                n += 1
        cm.recalcular(info)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    return n


def registrar_resposta(oper, id_pergunta, texto, hoje=None):
    """Guarda a resposta dela e aplica a ação. Devolve (ok, nota para o guardião)."""
    hoje = hoje or date.today()
    dados = _ler(oper, hoje)
    pergunta = next((p for p in (dados or {}).get("perguntas") or [] if p["id"] == id_pergunta), None)
    if not pergunta:
        return False, f"não achei a pergunta {id_pergunta} desta semana"
    texto = str(texto or "").strip()
    if not texto:
        return False, "falta a resposta dela"
    nota = "resposta guardada"
    if pergunta["tipo"] == "medicao":
        t = _norm(texto)
        if SIM.search(t) and not NAO.search(t):
            n = _descartar(oper, pergunta.get("registros") or [])
            nota = f"{n} registro(s) saíram da média do tempos.json (foram feitos fora do painel)"
        else:
            nota = "ela disse que esses tempos curtos são reais: os registros ficam na média"
    elif pergunta["tipo"] == "desvio":
        os.makedirs(_pasta(oper), exist_ok=True)
        with open(os.path.join(_pasta(oper), "regras.md"), "a", encoding="utf-8") as f:
            f.write(f"- {pergunta['frente']}: o planejado de cerca de {pergunta['planejado']} min levou cerca de {pergunta['real']} min "
                    f"({pergunta['n']} tarefas). Motivo dito por ela em {hoje:%d/%m}: {texto}. Use ao estimar tempo nesta frente.\n")
        nota = "o motivo virou uma linha de calibragem\\regras.md, que o plano passa a ler"
    dados.setdefault("respostas", {})[id_pergunta] = {"texto": texto, "em": hoje.isoformat()}
    with open(_caminho(oper, hoje), "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    return True, nota


def regras_texto(oper=OPER):
    """O que a calibragem confirmou com ela (calibragem\\regras.md), para o plano e o revisor lerem."""
    try:
        with open(os.path.join(_pasta(oper), "regras.md"), encoding="utf-8-sig") as f:
            return f.read().strip()
    except OSError:
        return ""
