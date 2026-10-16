"""Conferência do plano antes de gravar: o guardião só grava o plano depois de ler as campanhas ativas, e o plano não pode se contradizer.

Usado por guardiao_sessao (o pedido de gravar plano_do_dia.json ou planos\\plano_*.json passa por aqui). Sem rede e sem Claude."""
import json
import os
import re
import unicodedata
from datetime import date, timedelta

ENCERRADAS = {"concluida", "concluido", "arquivada", "arquivado", "cancelada", "cancelado", "encerrada", "encerrado"}
ANTECEDENCIA_DIAS = 14  # campanha que começa daqui a mais que isso ainda não pesa no plano de hoje


def _norm(texto):
    t = unicodedata.normalize("NFD", str(texto or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


def _cabecalho(arquivo):
    campos, dentro = {}, False
    try:
        with open(arquivo, encoding="utf-8-sig") as f:
            for linha in f:
                if linha.strip() == "---":
                    if dentro:
                        break
                    dentro = True
                    continue
                m = re.match(r"^([a-z_]+):\s*(.*)$", linha.strip()) if dentro else None
                if m:
                    campos[m.group(1)] = m.group(2).strip()
    except OSError:
        return {}
    return campos


def campanhas_ativas(pasta_memoria, hoje=None):
    """Slugs das campanhas que pesam no plano de hoje: não encerradas, com fim a partir de hoje e início em até 14 dias.
    Quando a campanha acaba (data_fim passou ou status encerrado) ela sai sozinha."""
    hoje = hoje or date.today()
    pasta = os.path.join(pasta_memoria, "campanhas")
    try:
        nomes = sorted(os.listdir(pasta))
    except OSError:
        return []
    ativas = []
    for n in nomes:
        if not n.endswith(".md") or n.startswith("_"):
            continue
        c = _cabecalho(os.path.join(pasta, n))
        try:
            ini = date.fromisoformat(c.get("data_inicio", ""))
            fim = date.fromisoformat(c.get("data_fim", ""))
        except ValueError:
            ativas.append(n[:-3])  # sem datas legíveis: melhor ler do que ignorar
            continue
        if _norm(c.get("status")) in ENCERRADAS or fim < hoje or ini > hoje + timedelta(days=ANTECEDENCIA_DIAS):
            continue
        ativas.append(c.get("slug") or n[:-3])
    return ativas


def slug_lido(nome, entrada, pasta_memoria):
    """Se esta chamada de ferramenta leu uma nota de campanha, devolve o slug. Vale Read do arquivo ou o script ler_campanha.ps1."""
    entrada = entrada or {}
    if nome == "Read":
        caminho = str(entrada.get("file_path") or "").replace("\\", "/")
        m = re.search(r"/campanhas/([^/]+)\.md$", caminho, re.I)
        return m.group(1) if m else None
    if nome in ("Bash", "PowerShell"):
        comando = str(entrada.get("command") or "")
        if "ler_campanha" in comando.lower():
            m = re.search(r"-Slug\s+[\"']?([\w\-]+)", comando, re.I)
            return m.group(1) if m else None
    return None


def eh_arquivo_de_plano(caminho):
    c = str(caminho or "").replace("\\", "/").lower()
    return c.endswith("/plano_do_dia.json") or bool(re.search(r"/planos/plano_\d{4}-\d{2}-\d{2}\.json$", c))


def _min(hhmm):
    h, m = str(hhmm).split(":")[:2]
    return int(h) * 60 + int(m)


def conferir(plano, anterior=None, feitos=()):
    """Problemas do plano que está para ser gravado. Lista vazia = pode gravar.
    anterior = plano que está em disco (guarda a lista de removidos); feitos = ids de blocos já concluídos (registro de hoje)."""
    problemas = []
    if not isinstance(plano, dict) or not isinstance(plano.get("blocos"), list):
        return ["O plano precisa ser um JSON com a lista \"blocos\"."]
    if not str(plano.get("agenda_impoe") or "").strip():
        problemas.append("Falta o campo \"agenda_impoe\": uma frase com o que a agenda das campanhas impõe a este dia "
                         "(prazo, dependência de outra pessoa, folga). Escreva depois de ler as campanhas.")
    removidos = {_norm(t) for t in list((anterior or {}).get("removidos") or []) + list(plano.get("removidos") or []) if str(t).strip()}
    itens = []
    for b in plano["blocos"]:
        if b.get("id") in feitos:
            continue
        titulo = _norm(b.get("titulo"))
        for r in removidos:
            if r and (r in titulo or titulo in r):
                problemas.append(f"O bloco \"{b.get('titulo')}\" foi tirado pela pessoa hoje (lista \"removidos\"). Não o recoloque.")
        try:
            itens.append((_min(b["inicio"]), _min(b["fim"]), b.get("titulo")))
        except (KeyError, ValueError, TypeError):
            problemas.append(f"O bloco \"{b.get('titulo')}\" está sem início ou fim válidos.")
    for f in plano.get("fixos") or []:
        try:
            itens.append((_min(f["inicio"]), _min(f["fim"]), f.get("titulo")))
        except (KeyError, ValueError, TypeError):
            pass
    itens.sort()
    for (i1, f1, t1), (i2, f2, t2) in zip(itens, itens[1:]):
        if i2 < f1:
            problemas.append(f"\"{t1}\" ({i1 // 60:02d}h{i1 % 60:02d} às {f1 // 60:02d}h{f1 % 60:02d}) se sobrepõe a \"{t2}\" (começa {i2 // 60:02d}h{i2 % 60:02d}).")
    return problemas


FRENTES_FLEXIVEIS = {"agencia", "agencias", "cliente", "clientes", "operacional", "operacao", "gestao", "administrativo", "admin"}


def data_do_plano(caminho, plano, hoje=None):
    """A data a que o plano se refere: a do nome do arquivo (planos/plano_AAAA-MM-DD.json), a do campo "data" ou hoje."""
    m = re.search(r"plano_(\d{4}-\d{2}-\d{2})\.json$", str(caminho or "").replace("\\", "/"))
    for cand in (m.group(1) if m else "", str((plano or {}).get("data") or "")):
        try:
            return date.fromisoformat(cand)
        except ValueError:
            continue
    return hoje or date.today()


def _chave_bloco(b):
    return b.get("clickup_id") or re.sub(r"\s+", " ", str(b.get("titulo") or "").lower()).strip()


def conferir_semana(plano, dia, anterior=None, outros=None, pendentes=None, feitos=(), memoria=None):
    """Conferência da semana: o plano de um dia não pode quebrar os outros. Lista vazia = pode gravar.
    outros = {AAAA-MM-DD: plano} dos demais dias gravados; pendentes = ids de tarefas ainda abertas no ClickUp (None = não sei)."""
    import visao_semana as vs
    problemas = []
    outros = outros or {}
    iso = dia.isoformat()
    novos = {_chave_bloco(b) for b in plano.get("blocos") or []}
    em_outros = {_chave_bloco(b) for d, p in outros.items() if d != iso for b in (p.get("blocos") or [])}
    removidos = {_norm(t) for t in list((anterior or {}).get("removidos") or []) + list(plano.get("removidos") or []) if str(t).strip()}
    # 1. nada some: bloco que estava neste dia e não está mais precisa estar em outro dia (ou em removidos, se ela mandou tirar)
    for b in (anterior or {}).get("blocos") or []:
        if b.get("id") in feitos:
            continue
        cid = b.get("clickup_id")
        if cid and pendentes is not None and cid not in pendentes:
            continue  # já concluída no ClickUp
        chave = _chave_bloco(b)
        titulo = _norm(b.get("titulo"))
        if chave in novos or chave in em_outros or any(r and (r in titulo or titulo in r) for r in removidos):
            continue
        problemas.append(f"O bloco \"{b.get('titulo')}\" saiu de {iso} e não está em nenhum outro dia da semana. Tarefa não some: coloque-a no dia certo "
                         "(grave primeiro o plano do dia que recebe, em planos/plano_AAAA-MM-DD.json, depois este) ou, se ela mandou tirar, ponha o título em \"removidos\".")
    antigos = {_chave_bloco(b): b for b in (anterior or {}).get("blocos") or []}
    for d, p in outros.items():
        if d != iso:
            antigos.update({_chave_bloco(b): b for b in p.get("blocos") or [] if b.get("prazo_final")})
    prime_livre = None
    for b in plano.get("blocos") or []:
        if b.get("id") in feitos:
            continue
        final = str(b.get("prazo_final") or antigos.get(_chave_bloco(b), {}).get("prazo_final") or "")
        # 2. o prazo final manda: bloco nunca cai depois dele
        if final and final < iso:
            problemas.append(f"\"{b.get('titulo')}\" está em {iso}, depois do prazo final ({final}). Traga para antes do prazo ou diga a ela que não cabe.")
        # 3. o prazo final acompanha o bloco quando ele muda de dia
        if not b.get("prazo_final") and antigos.get(_chave_bloco(b), {}).get("prazo_final"):
            problemas.append(f"\"{b.get('titulo')}\" tinha prazo final {antigos[_chave_bloco(b)]['prazo_final']} e o campo \"prazo_final\" sumiu ao mudar de dia. Mantenha.")
        # 4. tarefa de agência ou operacional com folga não toma o horário nobre de um dia cheio
        if final and final > iso and _norm(b.get("frente")) in FRENTES_FLEXIVEIS:
            try:
                comeca = vs.hm(b["inicio"])
            except (KeyError, ValueError, TypeError):
                continue
            if vs.NOBRE_MANHA[0] <= comeca < vs.NOBRE_MANHA[1]:
                if prime_livre is None:  # o que sobra livre na manhã nobre com esse bloco dentro
                    prime_livre = vs._livre_em(vs.NOBRE_MANHA, vs._intervalos(plano, feitos))
                if prime_livre < 30:
                    problemas.append(f"\"{b.get('titulo')}\" tem prazo final em {final} (folga) e está no horário nobre da manhã de {iso}, que ficou cheia. "
                                     "O nobre é do que é importante e urgente: mova para o fim do dia ou para um dia mais perto do prazo, e diga o que isso desloca.")
    return problemas


ETAPA_COPY = re.compile(r"^\s*(\[?copy\]?\b|roteiro\b|legenda\b)", re.I)
ETAPA_DESIGN = re.compile(r"^\s*(\[?design\]?\b|arte\b)", re.I)
LETRA_NO_NOME = re.compile(r"\b(carrossel|post|reels?|story|stories)\s+[A-Z]\b(?!\w)")


RELATORIO = re.compile(r"^\s*\[?preencher relat[óo]rio|^\s*\[?relat[óo]rio\b", re.I)


def _data_do_relatorio_pelo_titulo(bloco, maes):
    """Data de postagem pelo título "Preencher relatório (Manychat -) <nome do post>" comparado ao nome da mãe."""
    t = _norm(re.sub(r"^\s*\[?preencher relat[óo]rio( manychat)?\s*[-:|]?\s*(do )?", "", str(bloco.get("titulo") or ""), flags=re.I))
    if len(t) < 12:
        return None
    for m in maes:
        if _norm(m.get("nome"))[:25] == t[:25]:
            return str(m.get("prazo") or "") or None
    return None


def _etapa(bloco):
    """'copy', 'design' ou None, pelo campo etapa ou pelo começo do título ("Copy | ...", "[DESIGN] ...", "Design: ...")."""
    e = _norm(bloco.get("etapa"))
    if e in ("copy", "design"):
        return e
    t = str(bloco.get("titulo") or "")
    if ETAPA_COPY.match(t):
        return "copy"
    if ETAPA_DESIGN.match(t):
        return "design"
    return None


def _post_do_bloco(bloco, maes):
    """(chave do post, data de postagem) do bloco de etapa, ou (None, None). Vem de reserva_post, da tarefa mãe (posts_maes.json, pelo id da
    etapa) ou do título depois do "|" comparado ao nome da mãe."""
    if bloco.get("reserva_post"):
        return "reserva:" + str(bloco["reserva_post"]), str(bloco["reserva_post"])
    cid = bloco.get("clickup_id")
    for m in maes:
        if cid and any(e.get("id") == cid for e in m.get("etapas") or []):
            return m.get("id"), str(m.get("prazo") or "")
    titulo = str(bloco.get("titulo") or "")
    resto = _norm(titulo.split("|", 1)[1] if "|" in titulo else re.sub(r"^\s*\[?\w+\]?\s*[:|-]?\s*", "", titulo))[:25]
    if len(resto) >= 12:
        for m in maes:
            if _norm(m.get("nome"))[:25] == resto:
                return m.get("id"), str(m.get("prazo") or "")
    return None, None


def conferir_regras(plano, dia, outros=None, maes=(), fixos_semana=(), lote=False, consumo_antes_de_ideia=False):
    """Regras de conteúdo e rotina que viraram conta (2026-10-14). Gerais: a copy de um post antes do design dele; etapas do mesmo tipo na ordem
    das datas de postagem; o almoço da rotina não some; post não se chama por letra. Pessoal (só com rotina.regras.etapas_em_lote no config):
    copies juntas e designs juntos, nunca copy, design, copy no mesmo dia."""
    problemas = []
    iso = dia.isoformat()
    for b in plano.get("blocos") or []:
        if LETRA_NO_NOME.search(str(b.get("titulo") or "")):
            problemas.append(f"\"{b.get('titulo')}\": post se chama pelo título, não por letra. Use o título do post (e a data, se ajudar).")
    tem_almoco = any("almo" in _norm(f.get("titulo")) and dia.weekday() in (f.get("dias") or []) for f in fixos_semana or [])
    if tem_almoco and not any("almo" in _norm(f.get("titulo")) for f in (plano.get("fixos") or []) + (plano.get("blocos") or [])):
        problemas.append("O almoço sumiu do plano. Ele nunca some: mova o horário se precisar, mas mantenha.")
    etapas = []  # (dia, início, etapa, chave do post, data do post, título)
    for d, p in list((outros or {}).items()) + [(iso, plano)]:
        if d != iso and p is plano:
            continue
        if d == iso and p is not plano:
            continue
        for b in p.get("blocos") or []:
            e = _etapa(b)
            if not e:
                continue
            chave, data_post = _post_do_bloco(b, maes)
            etapas.append((d, str(b.get("inicio") or ""), e, chave, data_post, b.get("titulo")))
    for d, p in list((outros or {}).items()) + [(iso, plano)]:
        if d != iso or p is not plano:
            continue
        for b in p.get("blocos") or []:  # relatório de post só 24h depois da postagem: no mínimo no dia seguinte
            if RELATORIO.search(str(b.get("titulo") or "")):
                _chave, data_post = _post_do_bloco(b, maes)
                if not data_post:
                    data_post = _data_do_relatorio_pelo_titulo(b, maes)
                if data_post and d <= data_post:
                    problemas.append(f"\"{b.get('titulo')}\" ({d}) vem antes de 24h da postagem (post de {data_post}). "
                                     f"Relatório de post só 24h depois: ponha no dia seguinte ao post ou depois, nunca no mesmo dia.")
    etapas.sort()
    for i, (d1, h1, e1, k1, p1, t1) in enumerate(etapas):
        for d2, h2, e2, k2, p2, t2 in etapas[i + 1:]:
            if iso not in (d1, d2):
                continue  # só acusa o que envolve o dia que está sendo gravado
            if k1 and k1 == k2 and e1 == "design" and e2 == "copy":
                problemas.append(f"\"{t1}\" ({d1} {h1}) vem antes da copy do mesmo post (\"{t2}\", {d2} {h2}). A copy vem antes do design.")
            if e1 == e2 and p1 and p2 and k1 != k2 and p1 > p2 and d2 <= p2:
                problemas.append(f"\"{t1}\" (post de {p1}) está antes de \"{t2}\" (post de {p2}, que sai primeiro). "
                                 f"Etapas do mesmo tipo vão na ordem das datas de postagem.")
    if consumo_antes_de_ideia:  # pessoal (rotina.regras.ideia_depois_de_consumo): a ideia nasce do consumo com a pergunta, nunca solta
        ordem = sorted(plano.get("blocos") or [], key=lambda x: str(x.get("inicio") or ""))
        for i, b in enumerate(ordem):
            t = _norm(b.get("titulo"))
            if re.search(r"\bideia|\bdopa\b", t) and not re.search(r"encaix|calendario", t) and not any("consumo" in _norm(x.get("titulo")) for x in ordem[:i]):
                problemas.append(f"\"{b.get('titulo')}\" é bloco de ideia sem um bloco de consumo antes no mesmo dia. A ideia nasce do consumo: ponha o consumo com a pergunta antes.")
    if lote:
        do_dia = [e for d, _h, e, _k, _p, _t in etapas if d == iso]
        for a, b, c in zip(do_dia, do_dia[1:], do_dia[2:]):
            if a == c != b:
                problemas.append("Neste dia há copy, design e copy alternados. Agrupe: copies juntas, depois designs juntos.")
                break
    return problemas


CONSUMO = re.compile(r"consumo|recarga")


def conferir_consumo(plano):
    """Um bloco de consumo/recarga por dia. A sobra do dia não vira um segundo (caso real 15/10: 'Recarga' às 9h20 e 'Consumo com a pergunta' às 16h30)."""
    blocos = [x for x in (plano.get("blocos") or []) + (plano.get("fixos") or []) if CONSUMO.search(_norm(x.get("titulo")))]
    if len(blocos) > 1:
        return ["O dia tem " + str(len(blocos)) + " blocos de consumo/recarga (" + "; ".join(f"{x.get('titulo')} {x.get('inicio')}" for x in blocos)
                + "). Deixe um só: a sobra vai para outra coisa ou fica como pausa."]
    return []


def conferir_duplicadas(plano, dia, outros):
    """Tarefa do ClickUp (clickup_id) em mais de um dia. Cada tarefa tem um dia só; o outro plano é quem manda."""
    iso = dia.isoformat()
    problemas = []
    for b in plano.get("blocos") or []:
        cid = b.get("clickup_id")
        if not cid:
            continue
        for d, p in (outros or {}).items():
            if d != iso and any(x.get("clickup_id") == cid and x.get("id") is not None for x in p.get("blocos") or []):
                problemas.append(f"\"{b.get('titulo')}\" já está no plano de {d[8:10]}/{d[5:7]}. Uma tarefa tem um dia só: deixe-a em um dos dois.")
                break
    return problemas


def conferir_prazos(plano, dia, tarefas):
    """Bloco de tarefa que só tem horário limite no ClickUp (sem início) nunca termina depois do limite nem vai para depois do dia do prazo.
    Caso real 15/10: 'Substack - Newsletter' (publica segunda às 9h) foi para segunda 17h10."""
    iso = dia.isoformat()
    problemas = []
    for b in plano.get("blocos") or []:
        t = (tarefas or {}).get(b.get("clickup_id"))
        if not t or t.get("inicio") or t.get("aprovar"):
            continue
        prazo, limite = str(t.get("prazo") or ""), str(t.get("fim") or "")
        if prazo and (iso > prazo or (iso == prazo and limite and str(b.get("fim") or "") > limite)):
            problemas.append(f"\"{b.get('titulo')}\" ({iso[8:10]}/{iso[5:7]} {b.get('inicio')} a {b.get('fim')}) fica depois do prazo da tarefa "
                             f"({prazo[8:10]}/{prazo[5:7]}{' ' + limite if limite else ''}). O trabalho vai ANTES do prazo, em dia anterior ou no sábado.")
    return problemas


# Alavancas: o que move a métrica de uma campanha PÚBLICA de venda (mais gente entrando na venda). Campanha interna não tem.
# A nota da campanha pode listar as suas no cabeçalho ("alavancas: stories, aviso no Daily"); sem a lista, vale esta.
ALAVANCAS_PADRAO = ("stories", "story", "daily", "grupo", "antecipa", "convite", "lembrete", "aviso")
JANELA_ALAVANCA_DIAS = 3


def conferir_alavancas(plano, dia, memoria, janela=JANELA_ALAVANCA_DIAS):
    """Campanha pública de venda (tipo "venda...") que termina em até `janela` dias exige, no plano de cada um desses dias, pelo menos um bloco
    que mova a métrica dela (stories, aviso no grupo, convite). Sem isso o tempo sobrando vai para tarefa que não traz gente."""
    if not memoria:
        return []
    problemas = []
    titulos = [_norm(x.get("titulo")) for x in (plano.get("blocos") or []) + (plano.get("fixos") or [])]
    for slug in campanhas_ativas(memoria, dia):
        c = _cabecalho(os.path.join(memoria, "campanhas", slug + ".md"))
        if not _norm(c.get("tipo")).startswith("venda") or _norm(c.get("publica")) in ("nao", "interna"):
            continue
        try:
            fim = date.fromisoformat(c.get("data_fim", ""))
        except ValueError:
            continue
        if not 0 <= (fim - dia).days <= janela:
            continue
        palavras = [_norm(p) for p in re.split(r"[,;]", c.get("alavancas") or "") if _norm(p)] or list(ALAVANCAS_PADRAO)
        if not any(p in t for p in palavras for t in titulos):
            problemas.append(f"\"{c.get('nome') or slug}\" é venda pública e termina em {fim:%d/%m}: o plano de {dia:%d/%m} não tem nenhum bloco que traga gente "
                             f"({', '.join(palavras[:4])}). Ponha um bloco assim antes de qualquer tarefa que não mova a campanha.")
    return problemas


def texto_do_plano(entrada):
    """O JSON que o Write vai gravar, ou None se não dá para saber (Edit parcial)."""
    c = (entrada or {}).get("content")
    if not isinstance(c, str):
        return None
    try:
        return json.loads(c.lstrip("﻿"))
    except ValueError:
        return None


def conferir_regras_da_pasta(plano, dia, outros, oper):
    """conferir_regras com o que está na pasta operacional: mães dos posts, fixos da rotina e as regras pessoais ligadas no config.json."""
    try:
        with open(os.path.join(oper, "posts_maes.json"), encoding="utf-8-sig") as f:
            maes = json.load(f).get("maes") or []
    except (OSError, ValueError):
        maes = []
    try:
        with open(os.path.join(oper, "config.json"), encoding="utf-8-sig") as f:
            rotina = json.load(f).get("rotina") or {}
    except (OSError, ValueError):
        rotina = {}
    regras = rotina.get("regras") or {}
    try:
        with open(os.path.join(oper, "config.json"), encoding="utf-8-sig") as f:
            memoria = (json.load(f).get("pastas") or {}).get("memoria")
    except (OSError, ValueError):
        memoria = None
    try:
        with open(os.path.join(oper, "resumo_clickup.json"), encoding="utf-8-sig") as f:
            tarefas = {t.get("id"): t for t in json.load(f).get("tarefas") or []}
    except (OSError, ValueError):
        tarefas = {}
    return (conferir_regras(plano, dia, outros, maes, rotina.get("fixos_semana") or [], bool(regras.get("etapas_em_lote")),
                            bool(regras.get("ideia_depois_de_consumo"))) + conferir_alavancas(plano, dia, memoria)
            + conferir_consumo(plano) + conferir_duplicadas(plano, dia, outros) + conferir_prazos(plano, dia, tarefas))
