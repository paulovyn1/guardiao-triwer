"""Roteador da agenda: antes de encaixar ou mover uma tarefa, o código decide quanto o guardião precisa ler e onde a tarefa cabe.

Nível 1 (dia): cabe hoje, num espaço contínuo do tipo certo, sem tirar nada do lugar. Lê só o plano de hoje.
Nível 2 (semana): não cabe hoje, mas cabe antes da data segura nos próximos 7 dias (direto ou trocando um leve do horário nobre). Lê a VISÃO DA SEMANA.
Nível 3 (horizonte): a semana não tem espaço até a data segura, ou o prazo passa da semana. Lê o HORIZONTE impresso aqui (até 45 dias, só números e marcos).

A decisão é conta, não julgamento do modelo: duração com margem, janelas compatíveis com o tipo, maior espaço contínuo, data segura.
Uso: python rota_agenda.py --minutos 90 --tipo pesado --prazo 2026-10-16 --frente Agência --titulo "Página do Carlos" [--depende-dias 0]
(o guardião chama pelo onde_cabe.ps1 da pasta operacional)."""
import argparse
import json
import math
import os
import re
import sys
from datetime import date, datetime, timedelta

import visao_semana as vs

OPER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARGEM_PADRAO = 1.2       # sem 3 registros confirmados no tempos.json: o real costuma passar do previsto
MARGEM_MIN, MARGEM_MAX = 1.0, 1.5
COLCHAO_AGORA = 10        # minutos entre agora e o começo da tarefa encaixada hoje
HORIZONTE_SEMANA = 7
HORIZONTE_MAX = 45
FOLGA_DIAS_UTEIS = 1
PEDACO_MINIMO = 60        # trabalho longo (mais de 2h) pode ir em pedaços de pelo menos 1h; até 2h vai inteiro
OCUPACAO_ALERTA = 0.9     # dia com mais de 90% da janela ocupada entra no alerta
NOBRE_ALERTA = 15         # minutos de nobre livre abaixo dos quais o dia entra no alerta
JANELA_LONGA = 10        # prazo além da semana: procura até 10 dias úteis antes da data segura
ESTENDER = {}             # {data: minutos} hora de parar estendida que ela autorizou (--estender AAAA-MM-DD=HH:MM)
FRENTES_FLEXIVEIS = {"agencia", "agencias", "cliente", "clientes", "operacional", "operacao", "gestao", "administrativo", "admin"}

PESADO = re.compile(r"copy|roteiro|manifesto|decid|decis|estrat|ideia|dopa|rascunho|substack|p[aá]gina|aula|material|pitch|branding|escrever|planej|briefing|texto|e-?mail", re.I)
DESIGN = re.compile(r"design|arte|edi[cç][aã]o|carrossel|thumb|capa", re.I)


def _norm(t):
    import unicodedata
    t = unicodedata.normalize("NFD", str(t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()


def tipo_de(titulo, frente=""):
    """pesado (copy, decisão, ideia, estratégia), design ou leve. Design vem antes: "Design | copy..." é design."""
    t = f"{titulo} {frente}"
    if DESIGN.search(str(titulo)) or _norm(frente) == "design":
        return "design"
    if PESADO.search(t):
        return "pesado"
    return "leve"


def parar_em(dia, memoria=None):
    return max(vs.hora_de_parar(dia, memoria), ESTENDER.get(dia, 0))


def janelas(tipo, parar):
    """Onde cada tipo pode cair (minutos). Pesado só no nobre; design no nobre e na tarde de 14h a 16h; leve em qualquer hora."""
    m1, m2 = vs.NOBRE_MANHA
    noite = (vs.NOBRE_NOITE_INICIO, parar)
    if tipo == "pesado":
        return [(m1, m2), noite]
    if tipo == "design":
        return [(m1, m2), (14 * 60, 16 * 60), noite]
    return [(vs.CHEGADA, parar)]


def _config():
    return vs._json(os.path.join(OPER, "config.json")) or {}


def fixos_do_dia(dia, cfg=None):
    """Compromissos fixos de um dia sem plano gravado: rotina.fixos_semana (por dia da semana) e rotina.fixos_datas (datas avulsas)."""
    rotina = (cfg or _config()).get("rotina") or {}
    fixos = []
    for f in rotina.get("fixos_semana") or []:
        if dia.weekday() in (f.get("dias") or []):
            fixos.append(f)
    for f in rotina.get("fixos_datas") or []:
        if f.get("data") == dia.isoformat():
            fixos.append(f)
    for f in rotina.get("cancelados") or []:  # exceção a um fixo da semana (ex.: unha que não vai acontecer)
        if f.get("data") == dia.isoformat():
            fixos = [x for x in fixos if _norm(x.get("titulo")) != _norm(f.get("titulo"))]
    if not fixos and rotina.get("almoco"):
        ini = vs.hm(rotina["almoco"])
        fixos.append({"inicio": vs.fmt(ini), "fim": vs.fmt(ini + 60), "titulo": "Almoço"})
    return fixos


def plano_efetivo(dia, planos, cfg=None):
    """O plano gravado do dia; sem ele, o pré-plano do ClickUp mais os fixos da semana-base."""
    p = planos.get(dia.isoformat())
    if p and p.get("origem") != "clickup":
        return p
    base = dict(p or {"data": dia.isoformat(), "blocos": [], "status": "sem plano"})
    base["fixos"] = list(base.get("fixos") or []) + fixos_do_dia(dia, cfg)
    return base


def espacos(plano, dia, tipo, a_partir=None, memoria=None, ignorar=()):
    """Espaços livres contínuos (ini, fim) nas janelas do tipo, descontando blocos e fixos."""
    parar = parar_em(dia, memoria)
    ocupados = vs._intervalos(plano, ignorar)
    livres = []
    for a, b in janelas(tipo, parar):
        a = max(a, a_partir or 0)
        cursor = a
        for x, y in ocupados:
            if y <= cursor:
                continue
            if x >= b:
                break
            if x > cursor:
                livres.append((cursor, min(x, b)))
            cursor = max(cursor, y)
        if cursor < b:
            livres.append((cursor, b))
    return [(x, y) for x, y in livres if y - x >= 5]


def _no_nobre(minuto):
    return vs.NOBRE_MANHA[0] <= minuto < vs.NOBRE_MANHA[1] or minuto >= vs.NOBRE_NOITE_INICIO


def margem(oper=OPER):
    """Margem de tempo: mediana de real/planejado dos registros confirmados do tempos.json (3 ou mais), entre 1,0 e 1,5."""
    dados = vs._json(os.path.join(oper, "tempos.json")) or {}
    razoes = sorted(r["real"] / r["planejado"] for t in (dados.get("tipos") or {}).values() for r in t.get("registros") or []
                    if r.get("confirmado") and r.get("planejado") and r.get("real"))
    if len(razoes) < 3:
        return MARGEM_PADRAO, len(razoes)
    meio = razoes[len(razoes) // 2]
    return min(MARGEM_MAX, max(MARGEM_MIN, meio)), len(razoes)


def dias_uteis_antes(d, n):
    while n > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def data_segura(prazo, hoje, depende_dias=0):
    """Último dia para ela terminar: prazo menos os dias úteis de quem depende dela, menos 1 dia útil de folga (nunca antes de hoje)."""
    if not prazo:
        return None
    d = dias_uteis_antes(prazo, depende_dias + FOLGA_DIAS_UTEIS)
    return max(d, hoje) if prazo >= hoje else prazo


def _leves_no_nobre(plano, dia, memoria):
    """Blocos leves no horário nobre que podem ir para a tarde do mesmo dia (preferência dela: tirar o leve do nobre, não empurrar a copy)."""
    tarde = espacos(plano, dia, "leve", memoria=memoria)
    tarde = [(a, b) for a, b in tarde if a >= 14 * 60 and b <= vs.NOBRE_NOITE_INICIO]
    troca = []
    for b in plano.get("blocos") or []:
        try:
            ini, fim = vs.hm(b["inicio"]), vs.hm(b["fim"])
        except (KeyError, ValueError, TypeError):
            continue
        nobre = vs.NOBRE_MANHA[0] <= ini < vs.NOBRE_MANHA[1] or ini >= vs.NOBRE_NOITE_INICIO
        if nobre and tipo_de(b.get("titulo"), b.get("frente")) == "leve" and any(y - x >= fim - ini for x, y in tarde):
            troca.append(b)
    return troca


def decidir(minutos, tipo, prazo=None, frente="", titulo="", hoje=None, agora=None, depende_dias=0, oper=OPER, memoria=None):
    hoje = hoje or date.today()
    agora_min = agora if agora is not None else datetime.now().hour * 60 + datetime.now().minute
    cfg = _config() if oper == OPER else (vs._json(os.path.join(oper, "config.json")) or {})
    memoria = memoria or ((cfg.get("pastas") or {}).get("memoria"))
    fator, n_reg = margem(oper)
    precisa = int(math.ceil(minutos * fator / 5) * 5)
    contiguo = precisa if precisa <= 120 else PEDACO_MINIMO
    segura = data_segura(prazo, hoje, depende_dias)
    flexivel = _norm(frente) in FRENTES_FLEXIVEIS
    planos = vs.planos_da_semana(oper, hoje)
    r = {"nivel": None, "precisa": precisa, "margem": fator, "registros": n_reg, "tipo": tipo, "data_segura": segura, "candidatos": [], "motivos": [], "alertas": []}
    if prazo and prazo < hoje:
        r["motivos"].append(f"O prazo final ({prazo:%d/%m}) já passou: diga isso a ela antes de encaixar.")

    def candidatos_no_dia(dia, a_partir=None):
        plano = plano_efetivo(dia, planos, cfg)
        livres = espacos(plano, dia, tipo, a_partir, memoria)
        maior = max((y - x for x, y in livres), default=0)
        total = sum(y - x for x, y in livres)
        cands = []
        if maior >= contiguo and total >= precisa:
            cabem = [e for e in livres if e[1] - e[0] >= contiguo]
            # pesado só tem janelas nobres; leve e design deixam o nobre para o pesado: primeiro o espaço fora do nobre, depois o mais cedo
            x, y = min(cabem, key=lambda e: (tipo != "pesado" and _no_nobre(e[0]), e[0]))
            if flexivel:  # tarefa com folga vai para o fim do espaço: fica adiável e não toma o começo do nobre
                x = max(x, y - precisa) if precisa <= y - x else x
            cands.append({"dia": dia, "inicio": x, "fim": min(y, x + precisa), "como": "espaço livre"})
        elif tipo == "pesado":
            for b in _leves_no_nobre(plano, dia, memoria):
                sem = espacos(plano, dia, tipo, a_partir, memoria, ignorar={b.get("id")})
                if max((y - x for x, y in sem), default=0) >= contiguo and sum(y - x for x, y in sem) >= precisa:
                    x, y = max(sem, key=lambda e: e[1] - e[0])
                    cands.append({"dia": dia, "inicio": x, "fim": min(y, x + precisa), "como": f"tirando o leve \"{b.get('titulo')}\" do nobre para a tarde do mesmo dia"})
                    break
        return cands, maior, plano

    # nível 1: hoje, a partir de agora
    c_hoje, maior_hoje, _ = candidatos_no_dia(hoje, agora_min + COLCHAO_AGORA)
    if c_hoje and c_hoje[0]["como"] == "espaço livre" and (not segura or hoje <= segura or hoje <= prazo):
        r.update(nivel=1, candidatos=c_hoje)
        r["motivos"].append(f"Cabe hoje: maior espaço {tipo} livre a partir de agora é {vs.duracao(maior_hoje)} e a tarefa pede {vs.duracao(precisa)}.")
    else:
        r["motivos"].append(f"Não cabe hoje sem mexer em nada: maior espaço {tipo} livre a partir de agora é {vs.duracao(maior_hoje)}, a tarefa pede {vs.duracao(precisa)}.")
        fim_semana = hoje + timedelta(days=HORIZONTE_SEMANA)
        ate = min(segura, fim_semana) if segura else fim_semana
        cands = list(c_hoje)  # troca de leve hoje também vale
        d = hoje + timedelta(days=1)
        while d <= ate:
            if d.weekday() < 5:
                cands += candidatos_no_dia(d)[0]
            d += timedelta(days=1)
        if not cands and prazo and segura and segura < prazo <= fim_semana:  # sem espaço com folga: o próprio prazo, sem folga
            d = segura + timedelta(days=1)
            while d <= prazo:
                if d.weekday() < 5 or d in ESTENDER:
                    for c in candidatos_no_dia(d)[0]:
                        cands.append(dict(c, como=c["como"] + ", SEM FOLGA (no limite do prazo; diga isso a ela)"))
                d += timedelta(days=1)
        if prazo and prazo > fim_semana:
            r["nivel"] = 3
            r["motivos"].append(f"O prazo final ({prazo:%d/%m}) passa da semana: o encaixe sai do horizonte, de trás para frente a partir da data segura ({segura:%d/%m}).")
            criticos = {q for q, _s, _n, _d, _st, imp in marcos(oper, memoria, hoje, segura) if imp == "critica"}
            cands, d, vistos = [], segura, 0
            while d > hoje and vistos < JANELA_LONGA:  # os dias úteis até a data segura, de trás para frente
                if d.weekday() < 5:
                    vistos += 1
                    c = candidatos_no_dia(d)[0][:1]
                    if c:
                        c[0]["nobre_livre"] = vs.livre_do_dia(plano_efetivo(d, planos, cfg), d, memoria)[1]
                        c[0]["critico"] = d in criticos
                        if c[0]["critico"]:
                            c[0]["como"] += " (dia com marco de campanha crítica: só se não houver outro)"
                        cands += c
                d -= timedelta(days=1)
            # 1º dia sem marco crítico; 2º perto da data segura (até 5 dias úteis antes vale igual) com mais nobre livre; 3º o mais tarde
            perto = dias_uteis_antes(segura, 5)
            cands.sort(key=lambda c: (c["critico"], c["dia"] < perto, -c["nobre_livre"], -c["dia"].toordinal()))
        elif cands:
            r["nivel"] = 2
        else:
            r["nivel"] = 3
            r["motivos"].append("A semana não tem espaço até a data segura, nem trocando um leve do nobre: precisa decidir o que sai, olhando o horizonte inteiro.")
        importante = not flexivel
        if r["nivel"] != 3 or not (prazo and prazo > fim_semana):
            cands.sort(key=lambda c: (c["como"] != "espaço livre", c["dia"] if importante else -c["dia"].toordinal(), c["inicio"]))
        r["candidatos"] = cands[:4]
    r["alertas"] = alertas(planos, hoje, cfg, memoria, oper)
    if r["nivel"] == 3:
        r["horizonte"] = horizonte(hoje, max(filter(None, [prazo, hoje + timedelta(days=14)])), planos, cfg, memoria, oper)
    return r


def ocupacao(plano, dia, memoria):
    parar = vs.hora_de_parar(dia, memoria)
    janela = parar - vs.CHEGADA
    livre = vs._livre_em((vs.CHEGADA, parar), vs._intervalos(plano))
    return (janela - livre) / janela if janela > 0 else 1.0, livre


SEMANA_PT = {"seg": 0, "ter": 1, "qua": 2, "qui": 3, "sex": 4, "sab": 5, "dom": 6}


def _data_do_texto(texto, ini):
    """ "Ter 20, 8h55", "Seg 2/11", "Qua 28 a sex 30" -> a primeira data. Sem mês: o primeiro mês, a partir do início da campanha, em que o dia da semana bate."""
    m = re.search(r"(\d{1,2})(?:/(\d{1,2}))?", texto)
    if not m:
        return None
    dia, mes = int(m.group(1)), m.group(2)
    sem = re.search(r"\b(seg|ter|qua|qui|sex|sab|dom)", _norm(texto[:m.start()] or texto))
    alvo = SEMANA_PT.get(sem.group(1)) if sem else None
    cands = []
    if mes:
        try:
            cands = [date(ini.year + (1 if int(mes) < ini.month - 6 else 0), int(mes), dia)]
        except ValueError:
            return None
    else:
        for k in range(0, 4):
            y, mm = ini.year + (ini.month - 1 + k) // 12, (ini.month - 1 + k) % 12 + 1
            try:
                cands.append(date(y, mm, dia))
            except ValueError:
                continue
    for c in cands:
        if c >= ini - timedelta(days=7) and (alvo is None or c.weekday() == alvo):
            return c
    return cands[0] if cands else None


def marcos(oper, memoria, hoje, ate):
    """Marcos com data das campanhas ativas: tabelas da seção "3. Marcos e tarefas" de cada nota (colunas achadas pelo cabeçalho).
    A data vem do ClickUp quando o id está no resumo (é a data agendada hoje); senão, do texto da tabela.
    Devolve (data, slug, nome, dono, situação, importância); situação: "agendado", "sem horário", "a criar", "fora do resumo" ou "sem tarefa"."""
    import conferencia_plano as cp
    resumo = {t.get("id"): t for t in (vs._json(os.path.join(oper, "resumo_clickup.json")) or {}).get("tarefas") or []}
    saida = []
    if not memoria:
        return saida
    for slug in cp.campanhas_ativas(memoria, hoje):
        caminho = os.path.join(memoria, "campanhas", slug + ".md")
        cab = cp._cabecalho(caminho)
        try:
            with open(caminho, encoding="utf-8-sig") as f:
                texto = f.read()
        except OSError:
            continue
        secao = re.search(r"^## 3\..*?$(.*?)(?=^## |\Z)", texto, re.M | re.S)
        if not secao:
            continue
        try:
            ini = date.fromisoformat(cab.get("data_inicio", ""))
        except ValueError:
            ini = hoje
        col = None
        for linha in secao.group(1).splitlines():
            if not linha.strip().startswith("|"):
                col = None
                continue
            cols = [c.strip() for c in linha.strip().strip("|").split("|")]
            nomes = [_norm(c) for c in cols]
            if "data" in nomes:  # cabeçalho de uma tabela
                col = {"data": nomes.index("data"),
                       "dono": next((i for i, n in enumerate(nomes) if n.startswith("dono")), None),
                       "nome": next((i for i, n in enumerate(nomes) if re.match(r"marco|mae|tarefa|o que", n)), 1 if nomes.index("data") == 0 else 0)}
                continue
            if col is None or all(set(c) <= set("-: ") for c in cols) or len(cols) <= col["data"]:
                continue
            ids = re.findall(r"\b(?=[0-9a-z]*\d)(?=[0-9a-z]*[a-z])[0-9a-z]{9,13}\b", linha)
            t = resumo.get(ids[0]) if ids else None
            quando = date.fromisoformat(t["prazo"]) if t and t.get("prazo") else _data_do_texto(cols[col["data"]], ini)
            if not quando or not (hoje <= quando <= ate):
                continue
            if t:
                situacao = "agendado" if t.get("inicio") else "sem horário"
            else:
                situacao = "a criar" if "criar" in _norm(linha) else ("fora do resumo" if ids else "sem tarefa")
            dono = cols[col["dono"]] if col["dono"] is not None and col["dono"] < len(cols) else ""
            nome = re.sub(r"\s*\((?:mae: )?[0-9a-z]{9,13}\)", "", re.sub(r"\*+", "", cols[col["nome"]]))[:80]
            saida.append((quando, slug, nome, dono, situacao, _norm(cab.get("importancia"))))
    return sorted(saida)


def alertas(planos, hoje, cfg, memoria, oper, dias=10, pular_hoje=False):
    """Antecipar: dia útil com mais de 90% da janela ocupada, tarefa sem hora em dia já cheio, marco perto sem horário no ClickUp."""
    out = []
    resumo = (vs._json(os.path.join(oper, "resumo_clickup.json")) or {}).get("tarefas") or []
    d = hoje + timedelta(days=1 if pular_hoje else 0)  # pular_hoje: no prompt fixo, hoje muda a cada turno e quebraria o cache
    for _ in range(dias):
        if d.weekday() < 5:
            p = plano_efetivo(d, planos, cfg)
            oc, livre = ocupacao(p, d, memoria)
            sem_hora = [t for t in resumo if t.get("prazo") == d.isoformat() and not t.get("inicio") and not t.get("aprovar")]
            nobre = vs.livre_do_dia(p, d, memoria)[1]
            if oc <= OCUPACAO_ALERTA and nobre < NOBRE_ALERTA and p.get("blocos"):
                out.append(f"{vs.DIAS[d.weekday()]} {d:%d/%m} está sem horário nobre livre ({vs.duracao(nobre)}): copy ou decisão nova ali tira outra coisa do lugar.")
            if oc > OCUPACAO_ALERTA:
                out.append(f"{vs.DIAS[d.weekday()]} {d:%d/%m} está {round(oc * 100)}% ocupado (livre {vs.duracao(livre)})"
                           + (f" e ainda tem {len(sem_hora)} tarefa(s) sem hora" if sem_hora else "") + ": qualquer atraso ali empurra outro dia.")
        d += timedelta(days=1)
    limite = hoje + timedelta(days=7)
    for quando, slug, nome, dono, situacao, _imp in marcos(oper, memoria, hoje, limite):
        if situacao in ("sem horário", "a criar") and (not dono or "milena" in _norm(dono)):
            out.append(f"Marco de {slug} em {quando:%d/%m} {situacao}: \"{nome}\".")
    vistos = []
    for a in out:
        if a not in vistos:
            vistos.append(a)
    if len(vistos) > 6:
        vistos = vistos[:6] + [f"(mais {len(vistos) - 6} alertas parecidos)"]
    out[:] = vistos
    return out


def horizonte(hoje, ate, planos, cfg, memoria, oper):
    """Do dia seguinte até a última data relevante (máx. 45 dias): uma linha por dia útil com o livre e o livre nobre, e os marcos das campanhas."""
    import conferencia_plano as cp
    fim_campanhas = []
    for slug in cp.campanhas_ativas(memoria or "", hoje):
        try:
            fim_campanhas.append(date.fromisoformat(cp._cabecalho(os.path.join(memoria, "campanhas", slug + ".md")).get("data_fim", "")))
        except ValueError:
            pass
    ate = min(max([ate] + fim_campanhas), hoje + timedelta(days=HORIZONTE_MAX))
    por_dia = {}
    for quando, slug, nome, dono, situacao, imp in marcos(oper, memoria, hoje, ate):
        por_dia.setdefault(quando, []).append(f"{slug}{' (crítica)' if imp == 'critica' else ''}: {nome}" + ("" if situacao == "agendado" else f" ({situacao})"))
    linhas = [f"HORIZONTE até {ate:%d/%m} (livre total / livre nobre por dia útil; marcos das campanhas ativas):"]
    d = hoje + timedelta(days=1)
    while d <= ate:
        marca = f" | {'; '.join(por_dia[d])}" if d in por_dia else ""
        if d.weekday() < 5:
            p = plano_efetivo(d, planos, cfg)
            total, nobre = vs.livre_do_dia(p, d, memoria)
            linhas.append(f"{vs.DIAS[d.weekday()]} {d:%d/%m}: {vs.duracao(total)} / {vs.duracao(nobre)}{marca}")
        elif marca:
            linhas.append(f"{vs.DIAS[d.weekday()]} {d:%d/%m}: fim de semana, sem capacidade{marca}")
        d += timedelta(days=1)
    return "\n".join(linhas)


def texto(r, titulo=""):
    nomes = {1: "1 (dia): leia só o plano de hoje", 2: "2 (semana): use a VISÃO DA SEMANA do contexto", 3: "3 (horizonte): use o HORIZONTE abaixo e a VISÃO DA SEMANA"}
    linhas = [f"ROTA{' de ' + repr(titulo) if titulo else ''}: nível {nomes[r['nivel']]}."]
    origem = f"mediana de {r['registros']} registros reais" if r["registros"] >= 3 else "padrão, ainda sem 3 registros reais"
    linhas.append(f"Tempo: {vs.duracao(r['precisa'])} com a margem de {str(round(r['margem'], 2)).replace('.', ',')} ({origem}). Tipo {r['tipo']}.")
    if r["data_segura"]:
        linhas.append(f"Data segura para terminar: {vs.DIAS[r['data_segura'].weekday()]} {r['data_segura']:%d/%m} (prazo menos dependências menos 1 dia útil de folga).")
    linhas += r["motivos"]
    if r["candidatos"]:
        linhas.append("Onde cabe, na ordem que eu recomendo:")
        for i, c in enumerate(r["candidatos"], 1):
            linhas.append(f"  {i}) {vs.DIAS[c['dia'].weekday()]} {c['dia']:%d/%m} {vs.fmt(c['inicio'])}-{vs.fmt(c['fim'])}, {c['como']}")
    else:
        linhas.append("Nenhum espaço encontrado: decida o que sai pela prioridade das campanhas e diga a ela, com a conta.")
    if r["alertas"]:
        linhas.append("ALERTAS (antecipe e diga a ela em uma frase, se mexerem com esta decisão):")
        linhas += [f"  - {a}" for a in r["alertas"]]
    if r.get("horizonte"):
        linhas.append(r["horizonte"])
    linhas.append("Grave o bloco com \"prazo_final\" quando houver prazo. Se escolher outro horário que não o 1, diga por quê.")
    return "\n".join(linhas)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutos", type=int, required=True)
    ap.add_argument("--tipo", choices=["pesado", "design", "leve", "auto"], default="auto")
    ap.add_argument("--prazo", default="")
    ap.add_argument("--frente", default="")
    ap.add_argument("--titulo", default="")
    ap.add_argument("--depende-dias", type=int, default=0)
    ap.add_argument("--estender", action="append", default=[], help="AAAA-MM-DD=HH:MM: ela autorizou trabalhar até essa hora nesse dia")
    a = ap.parse_args(argv)
    for e in a.estender:
        d, h = e.split("=")
        ESTENDER[date.fromisoformat(d.strip())] = vs.hm(h.strip())
    prazo = date.fromisoformat(a.prazo) if a.prazo else None
    tipo = tipo_de(a.titulo, a.frente) if a.tipo == "auto" else a.tipo
    r = decidir(a.minutos, tipo, prazo, a.frente, a.titulo, depende_dias=a.depende_dias)
    sys.stdout.reconfigure(encoding="utf-8")
    print(texto(r, a.titulo))


if __name__ == "__main__":
    main()
