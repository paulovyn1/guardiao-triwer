"""Plano do dia montado por código, a partir da semana já combinada (o que está agendado no ClickUp com hora) e dos fixos da semana-base.

O gerar_plano.ps1 chama isto antes do Claude:
- Se o dia já está resolvido (nada atrasado, nada do dia sem hora, nada sobreposto, sem buraco grande no expediente), grava o plano e o Claude
  NÃO é chamado (economiza a leitura diária do resumo do ClickUp, da skill e da memória).
- Se precisa de decisão, grava o plano base e um dossiê curto com os motivos, a semana e os alertas: o Claude parte dele em vez de reler tudo.
- Depois do Claude, --conferir passa o plano gravado pela mesma conferência da conversa (sobreposição, removidos, semana, prazo final).

Uso: python plano_base.py --data AAAA-MM-DD --saida plano.json [--dossie arquivo.txt]   -> sai 0 (pronto, sem Claude) ou 2 (precisa do Claude)
     python plano_base.py --conferir plano.json                                         -> sai 0 (ok) ou 1 (problemas impressos)"""
import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta

import conferencia_plano as cp
import etapas_post as ep
import gordura as gd
import preparos as pp
import rota_agenda as ra
import travas as tv
import visao_semana as vs

OPER = ra.OPER
BURACO_MAX = 90  # minutos livres no expediente acima dos quais o Claude é chamado para decidir o que entra (o dia vai até a hora de parar)


def _cfg():
    return vs._json(os.path.join(OPER, "config.json")) or {}


def _memoria(cfg):
    return (cfg.get("pastas") or {}).get("memoria")


def montar(dia, oper=OPER, cfg=None, hoje=None):
    """(plano, motivos): o plano base do dia e por que ele ainda precisa do Claude (lista vazia = pronto).
    hoje (padrão: a data de hoje): só é ATRASADA a tarefa que venceu antes de hoje. Tarefa de um dia entre hoje e o dia planejado pertence ao plano
    daquele dia e não entra neste (antes, o plano de um dia futuro replanejava tudo que vencia antes dele e duplicava tarefas)."""
    hoje = hoje or date.today()
    cfg = cfg if cfg is not None else _cfg()
    vs.aplicar_rotina(cfg)
    memoria = _memoria(cfg)
    nome = ((cfg.get("pessoa") or {}).get("nome")) or "Eu"
    resumo = (vs._json(os.path.join(oper, "resumo_clickup.json")) or {}).get("tarefas") or []
    iso = dia.isoformat()
    blocos, sem_hora, atrasadas, aprovar, com_prazo_hora, etapas = [], [], [], [], [], []
    maes = (vs._json(os.path.join(oper, "posts_maes.json")) or {}).get("maes") or []
    marcos_travados = tv.ids_de_marcos(_memoria(cfg))
    agendadas = tv.carregar_agendadas(oper)
    por_mae = ep.datas_por_mae(resumo, maes)
    ids_preparo = pp.ids(cfg, oper, hoje)
    for t in resumo:
        prazo = str(t.get("prazo") or "")
        if t.get("id") in ids_preparo and not (prazo == iso and t.get("inicio") and t.get("fim")):
            continue  # preparo de evento (Estrateclass): a data do ClickUp é da automação; o limite real vem de preparos.py e entra nos motivos
        if t.get("aprovar"):
            if prazo <= iso:
                aprovar.append(t)
            continue
        e = ep.info(t, maes)
        if ep.replanejar(e, tv.classe(t, cfg, marcos_travados, agendadas), t, por_mae):  # etapa de post sem trava: o prazo do ClickUp é sugestão, o guardião encaixa
            etapas.append(e)
            continue
        if prazo < min(iso, hoje.isoformat()):
            if t.get("id") not in _ids_em_outros(dia, oper, hoje):  # já tem lugar em outro plano gravado: não replaneja de novo
                atrasadas.append(t)
        elif prazo < iso:
            continue  # agendada para um dia entre hoje e este: é do plano daquele dia
        elif prazo == iso:
            if t.get("fim") and not t.get("inicio"):  # só horário limite (ex.: Substack às 9h): o trabalho é ANTES dele, não neste horário
                com_prazo_hora.append(t)
            elif t.get("inicio") and t.get("fim"):
                blocos.append({"id": f"b{len(blocos) + 1}", "inicio": t["inicio"], "fim": t["fim"], "titulo": t.get("nome"), "dono": nome,
                               "frente": t.get("lista") or "", "clickup_id": t.get("id"),
                               "descricao": "Tarefa combinada na semana para este horário. Os detalhes estão na tarefa do ClickUp.",
                               "primeiro_passo": "Abra a tarefa no ClickUp e comece pelo primeiro item dela.",
                               "por_que_agora": "Já estava agendada para este horário no planejamento da semana."})
            else:
                sem_hora.append(t)
    blocos.sort(key=lambda b: b["inicio"])
    for i, b in enumerate(blocos, 1):
        b["id"] = f"b{i}"
    marcos = [f"{slug}: {n}" for q, slug, n, _d, _s, _i in ra.marcos(oper, memoria, dia, dia + timedelta(days=7)) if q <= dia + timedelta(days=2)]
    plano = {"data": iso, "gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M"), "status": "sugerido", "modo_dia": "normal",
             "origem": "semana combinada (montado sem Claude)", "blocos": blocos, "fixos": ra.fixos_do_dia(dia, cfg), "removidos": [],
             "agenda_impoe": ("Marcos de hoje a 2 dias: " + "; ".join(marcos)) if marcos else "Nenhum marco de campanha nos próximos 2 dias."}
    motivos = []
    if atrasadas:
        motivos.append(f"{len(atrasadas)} tarefa(s) atrasada(s) precisam de lugar ou decisão: " + "; ".join(f"{t.get('nome')} ({t.get('prazo')}, id {t.get('id')})" for t in atrasadas[:8]))
    etapas = _etapas_a_encaixar(etapas, dia, oper, hoje)
    if etapas:
        motivos.append(f"ETAPAS DE POST A ENCAIXAR ({len(etapas)}): decida o dia e o horário de cada uma, dentro do limite. O prazo do ClickUp é só sugestão.\n"
                       + "\n".join(_linha_etapa(e) for e in etapas[:15]))
    motivos += pp.motivos(dia, cfg, oper, hoje, _ids_em_outros(dia, oper, hoje))
    pp.inserir_cobrancas(plano, dia, cfg, oper, nome, hoje)
    inserir_stories(plano, dia, cfg, nome)
    inserir_blocos_diarios(plano, dia, cfg, nome)
    faltam_diarios = cp.conferir_blocos_diarios(plano, dia, cfg) + cp.conferir_stories(plano, dia, cfg, None, _memoria(cfg))
    if faltam_diarios:
        motivos.append("BLOCO DIÁRIO OBRIGATÓRIO: " + " ".join(faltam_diarios))
    folga = gd.situacao(maes, cfg, hoje)
    if folga and folga["gordura"] < folga["meta"]:  # a gordura de posts está abaixo da meta: a criação à frente entra no plano
        motivos.append(gd.texto(folga))
    if com_prazo_hora:
        motivos.append(f"{len(com_prazo_hora)} entrega(s) com horário limite neste dia e sem horário de trabalho: "
                       + "; ".join(f"{t.get('nome')} (até {t.get('fim')}, id {t.get('id')})" for t in com_prazo_hora[:6])
                       + ". O trabalho precisa estar pronto ANTES do horário limite, em dia anterior ou no sábado: nunca ponha bloco depois dele. "
                         "Se o dia anterior não tem a etapa de produção, diga no aviso.")
    if sem_hora:
        motivos.append(f"{len(sem_hora)} tarefa(s) de hoje sem horário: " + "; ".join(f"{t.get('nome')} (id {t.get('id')})" for t in sem_hora[:8]))
    _mover_almoco(plano)
    problemas = cp.conferir(plano)
    if problemas:
        motivos.append("Conflitos no que está agendado: " + " ".join(problemas))
    livre, nobre = vs.livre_do_dia(plano, dia, memoria)
    if livre > BURACO_MAX:
        adiantar = candidatas_a_adiantar(dia, plano, oper, cfg)
        motivos.append(f"Sobram {vs.duracao(livre)} livres no expediente ({vs.duracao(nobre)} no nobre). Preencha até a hora de parar: primeiro adiantando "
                       "tarefa de um dia cheio" + (" (" + "; ".join(adiantar) + ")" if adiantar else " (nenhum dia cheio nos próximos dias)")
                       + "; sem isso, consumo com a pergunta, curso ou descanso programado. Não deixe um dia com hora extra e outro vazio, salvo pedido dela.")
    sem_lugar = marcos_sem_lugar(dia, oper, cfg)
    if sem_lugar:
        motivos.append(f"{len(sem_lugar)} marco(s) das campanhas nos próximos {HORIZONTE_DIAS} dias ainda sem horário ou tarefa no ClickUp. Veja o HORIZONTE "
                       "e, se o dia de hoje tem espaço, adiante o preparo deles (ou diga no aviso onde cabem): " + "; ".join(sem_lugar[:8]))
    if not blocos:
        motivos.append("Nada agendado para hoje no ClickUp: o dia precisa ser montado.")
    for item in trabalhos_do_guardiao(memoria, dia):
        motivos.append(f"Trabalho do guardião com data chegada (estado.md, seção \"Do guardião\"): {item}")
    return plano, motivos


def _vaos_do_dia(plano, dia, memoria, a_partir=None):
    """Todos os espaços livres do expediente, de qualquer janela (leve, pesado ou design), unidos e em ordem."""
    todos = []
    for tipo in ("leve", "pesado", "design"):
        todos += ra.espacos(plano, dia, tipo, a_partir=a_partir, memoria=memoria)
    todos.sort()
    unidos = []
    for x, y in todos:
        if unidos and x <= unidos[-1][1]:
            unidos[-1] = (unidos[-1][0], max(unidos[-1][1], y))
        else:
            unidos.append((x, y))
    return unidos


def inserir_stories(plano, dia, cfg, nome="Eu"):
    """Define o TIPO do dia (rotina.stories.padrao_semana) e completa o tempo de stories que o tipo pede (normal 30 min, caixinha 45 min, captação 15 min; em dia apertado a caixinha
    cai para 15), QUEBRADO em blocos de até 15 min na tarde, espalhados (1 h entre um e outro quando dá). Se um espaço é menor que 15 min, usa o que couber (mínimo 5 min).
    O tipo fica no plano ("stories_tipo"). Os blocos não têm clickup_id nem lista_id. Devolve os blocos criados."""
    s = cp.config_stories(cfg)
    rot = (cfg or {}).get("rotina") or {}
    if not s or dia.weekday() not in cp._dias_de_trabalho(rot):
        return []
    tipo = cp.tipo_do_dia(plano, dia, s)
    plano["stories_tipo"] = tipo
    t = s["tipos"][tipo]
    memoria = _memoria(cfg or {})
    agora = datetime.now()
    a_partir = agora.hour * 60 + agora.minute + 5 if dia == agora.date() else None  # hoje: só o que ainda não passou
    precisa = t["minutos_apertado"] if cp.dia_apertado(plano, dia, memoria) else t["minutos"]
    faltam = precisa - cp.minutos_stories_do_tipo(plano, tipo, s)
    existentes = [b for b in (plano.get("blocos") or []) + (plano.get("fixos") or []) if cp._eh_stories(b) and cp.tipo_stories(b.get("titulo"), s) == tipo]
    pref = (vs.hm("14:00"), vs.hm("18:00"))
    ultimo_fim = max([vs.hm(b["fim"]) for b in existentes if b.get("fim")] or [0]) or None
    criados = []
    while faltam >= cp.BLOCO_MINIMO_MIN and len(criados) < 8:
        alvo = min(cp.BLOCO_IDEAL_MIN, faltam)
        escolha = None
        for exigir in (True, False):
            melhor = None
            for x, y in (ra.espacos(plano, dia, "leve", a_partir=a_partir, memoria=memoria) if exigir else _vaos_do_dia(plano, dia, memoria, a_partir)):
                ini = max(x, pref[0] if exigir else x, (ultimo_fim + 60) if (exigir and ultimo_fim is not None) else x)
                if exigir and ini >= pref[1]:
                    continue
                cabe = min(y, pref[1] if exigir else y) - ini
                if cabe >= alvo:
                    melhor = (ini, alvo)
                    break
                if not exigir and cabe >= cp.BLOCO_MINIMO_MIN and (melhor is None or cabe > melhor[1]):
                    melhor = (ini, cabe)  # só se não há um vão inteiro em lugar nenhum: usa o que couber e quebra o resto
            if melhor:
                escolha = melhor
                break
        if not escolha:
            break
        ini, dur = escolha
        parte = len(existentes) + len(criados) + 1
        titulo = {"normal": f"Stories: sequência normal (parte {parte})", "caixinha": f"Stories: respostas da caixinha (parte {parte})",
                  "captacao": f"Stories de captação de leads ({t['telas']} telas)"}[tipo]
        bloco = {"id": _id_livre(plano), "inicio": vs.fmt(ini), "fim": vs.fmt(ini + dur), "titulo": titulo, "dono": nome, "frente": "Conteúdo",
                 "descricao": f"Hoje é dia de stories de {cp.NOME_TIPO_STORIES[tipo]} ({t['telas']} telas no dia, {precisa} min): blocos curtos espalhados pelo dia.",
                 "primeiro_passo": "Abra o cronograma da semana e poste a primeira tela.", "por_que_agora": "Stories é prioridade e entra todos os dias de trabalho."}
        plano.setdefault("blocos", []).append(bloco)
        plano["blocos"].sort(key=lambda b: b.get("inicio") or "")
        criados.append(bloco)
        ultimo_fim = ini + dur
        faltam -= dur
        if tipo == "captacao":
            break
    return criados


def inserir_blocos_diarios(plano, dia, cfg, nome="Eu"):
    """Põe no plano os blocos diários obrigatórios (rotina.blocos_diarios) que faltarem, num espaço livre: primeiro na janela preferida da regra
    (padrão 14h às 18h, a tarde de stories e tarefas leves), depois em qualquer espaço do dia. O bloco não tem clickup_id nem lista_id: fica só no plano.
    Devolve os blocos criados. Se não houver espaço, não cria (a conferência acusa)."""
    rot = (cfg or {}).get("rotina") or {}
    memoria = _memoria(cfg or {})
    criados = []
    for r in rot.get("blocos_diarios") or []:
        so_esta = {"rotina": dict(rot, blocos_diarios=[r])}
        if not cp.conferir_blocos_diarios(plano, dia, so_esta) or dia.weekday() not in cp._dias_de_trabalho(rot):
            continue
        minutos = int(r.get("minutos_minimos") or 15)
        pref = r.get("janela") or ["14:00", "18:00"]
        pref = (vs.hm(pref[0]), vs.hm(pref[1]))
        espacos = ra.espacos(plano, dia, "leve", memoria=memoria)
        escolha = None
        for x, y in espacos:  # primeiro na janela preferida
            ini = max(x, pref[0])
            if ini + minutos <= min(y, pref[1]):
                escolha = ini
                break
        if escolha is None:
            escolha = next((x for x, y in espacos if y - x >= minutos), None)
        if escolha is None:
            continue
        nome_bloco = r.get("titulo_padrao") or f"{str(r.get('nome') or 'Bloco').capitalize()} do dia"
        bloco = {"id": _id_livre(plano), "inicio": vs.fmt(escolha), "fim": vs.fmt(escolha + minutos), "titulo": nome_bloco,
                 "dono": nome, "frente": "Conteúdo",
                 "descricao": f"Bloco diário obrigatório: {r.get('nome')} todo dia de trabalho, antes de tarefa que dispute o horário.",
                 "primeiro_passo": "Abra o cronograma da semana e poste a primeira tela.",
                 "por_que_agora": f"{str(r.get('nome') or 'Isso').capitalize()} é prioridade e entra todos os dias."}
        plano.setdefault("blocos", []).append(bloco)
        plano["blocos"].sort(key=lambda b: b.get("inicio") or "")
        criados.append(bloco)
    return criados


def _linha_etapa(e):
    limite = (f"terminar até {e['limite']:%d/%m}" if e["limite"] else f"só a partir de {e['abre']:%d/%m}" if e["abre"] else "sem limite")
    return (f"- [{e['tipo']}] {str(e['titulo'])[:70]} | " + (f"post de {e['post']:%d/%m} | " if e["post"] else "") + limite
            + (f" | sugestão do ClickUp {e['sugestao']:%d/%m}" if e["sugestao"] else "") + f" | id {e['id']}")


def _ids_em_outros(dia, oper, hoje):
    """Ids de tarefa já colocados em blocos de OUTROS planos gravados (de hoje em diante)."""
    try:
        return {b.get("clickup_id") for d, p in vs.carregar_planos(oper, hoje).items() if d != dia.isoformat()
                for b in p.get("blocos") or [] if b.get("clickup_id") and b.get("id") is not None}
    except Exception:
        return set()


def _etapas_a_encaixar(etapas, dia, oper, hoje):
    """Etapas de post ainda sem lugar em outro plano gravado e perto de vencer (limite em até 10 dias) ou já abertas (relatório)."""
    em_outros = _ids_em_outros(dia, oper, hoje)
    limite_horizonte = dia + timedelta(days=10)
    return [e for e in etapas if e["id"] not in em_outros and (e["limite"] is None or e["limite"] <= limite_horizonte)
            and (e["abre"] is None or e["abre"] <= dia + timedelta(days=1))]


HORIZONTE_DIAS = 14  # quantos dias à frente o plano do dia olha as campanhas (o plano do mês), não só o ClickUp


def marcos_sem_lugar(dia, oper=OPER, cfg=None):
    """Marcos das campanhas ativas, dela ou sem dono, nos próximos HORIZONTE_DIAS dias, que não têm horário, tarefa ou ainda serão criados.
    São as necessidades futuras que o ClickUp sozinho não mostra. 'fora do resumo' não entra: o marco pode estar numa lista que o resumo não traz."""
    cfg = cfg if cfg is not None else _cfg()
    memoria = _memoria(cfg)
    eu = (ra._norm(((cfg.get("pessoa") or {}).get("nome")) or "").split() or [""])[0]
    saida = []
    for quando, slug, nome, dono, situacao, _imp in ra.marcos(oper, memoria, dia, dia + timedelta(days=HORIZONTE_DIAS)):
        if situacao in ("sem horário", "a criar", "sem tarefa") and (not dono or not eu or eu in ra._norm(dono)):
            saida.append(f"{quando:%d/%m} {slug}: {nome} ({situacao})")
    return saida


def candidatas_a_adiantar(dia, plano, oper=OPER, cfg=None, dias_uteis=5, cheio_min=60):
    """Tarefas agendadas nos próximos dias úteis que estão apertados (menos de 1 h livre) e que cabem num espaço livre de hoje, no tipo certo."""
    cfg = cfg if cfg is not None else _cfg()
    memoria = _memoria(cfg)
    planos = vs.planos_da_semana(oper, dia)
    saida, d, vistos = [], dia + timedelta(days=1), 0
    while vistos < dias_uteis:
        if d.weekday() < 5:
            vistos += 1
            outro = ra.plano_efetivo(d, planos, cfg)
            if vs.livre_do_dia(outro, d, memoria)[0] < cheio_min:
                for b in outro.get("blocos") or []:
                    try:
                        dur = vs.hm(b["fim"]) - vs.hm(b["inicio"])
                    except (KeyError, ValueError, TypeError):
                        continue
                    tipo = ra.tipo_de(b.get("titulo"), b.get("frente"))
                    if any(y - x >= dur for x, y in ra.espacos(plano, dia, tipo, memoria=memoria)):
                        saida.append(f"{b.get('titulo')} de {vs.DIAS[d.weekday()]} {d:%d/%m}, {dur} min" + (f", id {b['clickup_id']}" if b.get("clickup_id") else ""))
        d += timedelta(days=1)
    return saida[:5]


def trabalhos_do_guardiao(memoria, dia):
    """Itens "a fazer" da seção "Do guardião" do estado.md cujo início já chegou: o plano automático precisa do Claude para fazê-los."""
    import re
    try:
        with open(os.path.join(memoria, "estado.md"), encoding="utf-8-sig") as f:
            texto = f.read()
    except (OSError, TypeError):
        return []
    secao = re.search(r"^## Do guardi.*?$(.*?)(?=^## |\Z)", texto, re.M | re.S)
    itens = []
    for linha in (secao.group(1).splitlines() if secao else []):
        if not linha.strip().startswith("-") or "a fazer" not in ra._norm(linha):
            continue
        m = re.search(r"in[ií]cio:[^|]*?(\d{1,2})/(\d{1,2})(?:/(\d{4}))?", linha)
        if not m:
            continue
        try:
            quando = date(int(m.group(3) or dia.year), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
        if quando <= dia:
            itens.append(re.sub(r"\*+", "", linha.strip("- ").split("|")[0]).strip())
    return itens


def _mover_almoco(plano):
    """Almoço nunca some: se um compromisso agendado cobre o horário (hotseat de segunda), o almoço vai para o fim dele, até 15h."""
    for f in plano.get("fixos") or []:
        if "almoco" not in ra._norm(f.get("titulo")):
            continue
        ini, fim = vs.hm(f["inicio"]), vs.hm(f["fim"])
        for b in plano.get("blocos") or []:
            bi, bf = vs.hm(b["inicio"]), vs.hm(b["fim"])
            if bi < fim and ini < bf and bf <= 15 * 60:
                f["inicio"], f["fim"] = vs.fmt(bf), vs.fmt(bf + (fim - ini))
                ini, fim = bf, bf + (fim - ini)


def dossie(dia, plano, motivos, oper=OPER, cfg=None):
    """O que o Claude precisa para decidir, já calculado: motivos, plano base, semana e alertas. Substitui ler o resumo do ClickUp inteiro."""
    cfg = cfg if cfg is not None else _cfg()
    memoria = _memoria(cfg)
    planos = vs.planos_da_semana(oper, dia)
    partes = ["POR QUE O PLANO PRECISA DE VOCÊ (resolva só isto; o resto já está decidido):", *[f"- {m}" for m in motivos],
              *(["", ep.regras_texto()] if any("ETAPAS DE POST" in m for m in motivos) else []),
              *(["", gd.texto(gd.situacao((vs._json(os.path.join(oper, "posts_maes.json")) or {}).get("maes") or [], cfg, dia))]
                if gd.configuracao(cfg) and not any(m.startswith("GORDURA DE POSTS") for m in motivos) else []),
              "", "PLANO BASE (a semana combinada; mantenha estes blocos e horários, salvo conflito):", json.dumps(plano, ensure_ascii=False, indent=1),
              "", vs.texto(oper, memoria, hoje=dia, incluir_hoje=False),
              "", ra.horizonte(dia, dia + timedelta(days=HORIZONTE_DIAS), planos, cfg, memoria, oper)]
    alertas = ra.alertas(planos, dia, cfg, memoria, oper)
    if alertas:
        partes += ["", "ALERTAS:", *[f"- {a}" for a in alertas]]
    return "\n".join(partes)


def _outros(dia, oper):
    """Os demais planos de hoje em diante (inclui os dias ANTES deste e o pré-plano do ClickUp nos dias sem plano gravado)."""
    return {d: p for d, p in vs.planos_da_semana(oper, min(dia, date.today())).items() if d != dia.isoformat()}


ROTINA = cp.CONSUMO  # bloco de rotina que se repete em vários dias com a mesma tarefa do ClickUp (consumo, recarga)


def consertar(plano, dia, oper=OPER, cfg=None, outros=None):
    """Conserta por código o que é mecânico, ANTES da conferência, em vez de devolver ao modelo (cada volta relia tudo e custava minutos):
    consumo/recarga repetido no dia; tarefa de rotina com o mesmo id em dois dias; tarefa que outro plano já tem pela data do ClickUp; preparo de
    evento dela que chegou ao limite sem lugar; stories e blocos diários que faltam. Altera o plano e devolve a lista do que mudou."""
    cfg = cfg if cfg is not None else _cfg()
    nome = ((cfg.get("pessoa") or {}).get("nome")) or "Eu"
    outros = _outros(dia, oper) if outros is None else outros
    iso = dia.isoformat()
    feito = []
    blocos = plano.setdefault("blocos", [])
    memoria = _memoria(cfg)
    if not str(plano.get("agenda_impoe") or "").strip():  # a frase que a conferência exige: o código sabe montar
        marcos = [f"{slug}: {n}" for q, slug, n, _d, _s, _i in ra.marcos(oper, memoria, dia, dia + timedelta(days=7)) if q <= dia + timedelta(days=2)]
        plano["agenda_impoe"] = ("Marcos de hoje a 2 dias: " + "; ".join(marcos)) if marcos else "Nenhum marco de campanha nos próximos 2 dias."
        feito.append("completei agenda_impoe")
    # 1. um consumo/recarga por dia: fica o que tem tarefa no ClickUp (ou o primeiro); os outros sem tarefa saem
    cons = [b for b in blocos if ROTINA.search(cp._norm(b.get("titulo")))]
    if len(cons) > 1:
        fica = next((b for b in cons if b.get("clickup_id")), cons[0])
        for b in cons:
            if b is not fica and not b.get("clickup_id") and b.get("status") != "feito":
                blocos.remove(b)
                feito.append(f"tirei o segundo bloco de consumo/recarga ({b.get('titulo')} {b.get('inicio')})")
    # 2. a mesma tarefa do ClickUp em outro dia
    prazos = {t.get("id"): str(t.get("prazo") or "") for t in (vs._json(os.path.join(oper, "resumo_clickup.json")) or {}).get("tarefas") or []}
    for b in list(blocos):
        cid = b.get("clickup_id")
        if not cid or b.get("status") == "feito":
            continue
        onde = [d for d, p in outros.items() if d != iso and any(x.get("clickup_id") == cid and x.get("id") is not None for x in p.get("blocos") or [])]
        if not onde:
            continue
        if ROTINA.search(cp._norm(b.get("titulo"))) and prazos.get(cid) != iso:
            b.pop("clickup_id", None)  # rotina: o bloco fica neste dia, a tarefa do ClickUp fica no dia dela
            feito.append(f"\"{b.get('titulo')}\" ficou neste dia sem ligar à tarefa do ClickUp, que é do dia {onde[0][8:10]}/{onde[0][5:7]}")
        elif prazos.get(cid) in onde or any((outros.get(d) or {}).get("status") == "aprovado" for d in onde):
            blocos.remove(b)  # o outro dia é o da data do ClickUp ou já foi aprovado: ele manda
            feito.append(f"tirei \"{b.get('titulo')}\", que já está no plano de {onde[0][8:10]}/{onde[0][5:7]}")
    # 3. preparo de evento (Estrateclass) que chegou ao limite e não está em nenhum plano: entra no primeiro espaço que caiba
    agora = datetime.now()
    a_partir = agora.hour * 60 + agora.minute + 5 if dia == agora.date() else None
    no_plano = {b.get("clickup_id") for b in blocos} | {b.get("clickup_id") for d, p in outros.items() for b in p.get("blocos") or []}
    for e in pp.da_pessoa(cfg, oper):
        if not e["id"] or e["id"] in no_plano or e["limite"] > dia:
            continue
        minutos = 30
        vao = next(((x, y) for x, y in _vaos_do_dia(plano, dia, memoria, a_partir) if y - x >= minutos), None)
        if not vao:
            continue
        blocos.append({"id": _id_livre(plano), "inicio": vs.fmt(vao[0]), "fim": vs.fmt(vao[0] + minutos), "titulo": e["titulo"], "dono": nome, "frente": "Conteúdo",
                       "clickup_id": e["id"], "reagendado": True, "descricao": f"Preparo da {e['evento']}: {e['rotulo']} até {e['limite']:%d/%m}.",
                       "primeiro_passo": "Abra a tarefa no ClickUp e comece pelo primeiro item.", "por_que_agora": "Chegou ao limite do preparo da live."})
        blocos.sort(key=lambda b: b.get("inicio") or "")
        feito.append(f"pus \"{e['titulo']}\" às {vs.fmt(vao[0])} (limite do preparo da live)")
    # 4. stories e blocos diários que faltam
    for b in inserir_stories(plano, dia, cfg, nome) + inserir_blocos_diarios(plano, dia, cfg, nome):
        feito.append(f"pus \"{b['titulo']}\" às {b['inicio']}")
    for b in blocos:
        if not b.get("id"):
            b["id"] = _id_livre(plano)
    return feito


def _id_livre(plano):
    usados = {str(b.get("id")) for b in plano.get("blocos") or []}
    n = len(usados) + 1
    while f"b{n}" in usados:
        n += 1
    return f"b{n}"


def conferir_plano(plano, dia, oper=OPER, cfg=None, outros=None):
    """(graves, avisos) do plano: graves barram a gravação; avisos vão para o "aviso" do plano (conferencia_plano.separar)."""
    cfg = cfg if cfg is not None else _cfg()
    outros = _outros(dia, oper) if outros is None else outros
    resumo = (vs._json(os.path.join(oper, "resumo_clickup.json")) or {}).get("tarefas")
    pendentes = {t.get("id") for t in resumo} if resumo is not None else None
    base, _ = montar(dia, oper, cfg)  # o que a semana combinada punha neste dia: nada dela pode sumir sem ir para outro dia
    base["blocos"] = [b for b in base.get("blocos") or [] if b.get("clickup_id")]  # blocos criados pelo próprio plano base (stories) não são tarefa do ClickUp
    graves, avisos = cp.separar(cp.conferir(plano) + cp.conferir_semana(plano, dia, base, outros, pendentes, (), _memoria(cfg)))
    g2, a2 = cp.conferir_regras_da_pasta(plano, dia, outros, oper, com_avisos=True)
    return graves + g2, avisos + a2


def preparar(plano, dia, oper=OPER, cfg=None):
    """Conserta, confere e anota os avisos. Devolve (graves, consertos). Plano sem graves pode ser gravado como está (já com o aviso anotado)."""
    outros = _outros(dia, oper)
    consertos = consertar(plano, dia, oper, cfg, outros)
    graves, avisos = conferir_plano(plano, dia, oper, cfg, outros)
    cp.anotar_avisos(plano, avisos)
    return graves, consertos


def conferir_arquivo(caminho, oper=OPER, cfg=None):
    """Só os problemas graves do plano gravado (os avisos não barram)."""
    plano = vs._json(caminho)
    if not isinstance(plano, dict):
        return ["O plano gravado não é um JSON válido."]
    return conferir_plano(plano, cp.data_do_plano(caminho, plano), oper, cfg)[0]


def preparar_arquivo(caminho, oper=OPER, cfg=None):
    """preparar() no arquivo: grava o plano consertado e com os avisos anotados. Devolve (graves, consertos)."""
    plano = vs._json(caminho)
    if not isinstance(plano, dict):
        return ["O plano gravado não é um JSON válido."], []
    antes = json.dumps(plano, ensure_ascii=False, sort_keys=True)
    graves, consertos = preparar(plano, cp.data_do_plano(caminho, plano), oper, cfg)
    if json.dumps(plano, ensure_ascii=False, sort_keys=True) != antes:
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(plano, f, ensure_ascii=False, indent=2)
    return graves, consertos


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    ap.add_argument("--saida")
    ap.add_argument("--dossie")
    ap.add_argument("--conferir")
    ap.add_argument("--completar")  # insere no plano gravado os blocos diários que faltam (sem Claude)
    a = ap.parse_args(argv)
    if a.conferir:  # conserta o que é mecânico, anota os avisos no plano e só reprova pelo que é grave
        problemas, consertos = preparar_arquivo(a.conferir)
        if consertos:
            print("consertado por código: " + "; ".join(consertos))
        print("\n".join(f"- {p}" for p in problemas) if problemas else "ok")
        return 1 if problemas else 0
    if a.completar:
        arquivo = vs._json(a.completar)
        dia = cp.data_do_plano(a.completar, arquivo)
        nome_p = ((_cfg().get("pessoa") or {}).get("nome")) or "Eu"
        criados = inserir_stories(arquivo, dia, _cfg(), nome_p) + inserir_blocos_diarios(arquivo, dia, _cfg(), nome_p)
        if criados:
            with open(a.completar, "w", encoding="utf-8") as f:
                json.dump(arquivo, f, ensure_ascii=False, indent=2)
        print("; ".join(f"{b['titulo']} {b['inicio']} a {b['fim']}" for b in criados) or "nada a completar")
        return 0
    dia = date.fromisoformat(a.data) if a.data else date.today()
    plano, motivos = montar(dia)
    if not motivos:
        plano["aviso"] = "Montei o dia a partir da semana combinada, sem mudanças. Confira e aprove."
    with open(a.saida, "w", encoding="utf-8") as f:
        json.dump(plano, f, ensure_ascii=False, indent=2)
    if motivos and a.dossie:
        with open(a.dossie, "w", encoding="utf-8") as f:
            f.write(dossie(dia, plano, motivos))
    print("pronto" if not motivos else "precisa do Claude:\n" + "\n".join(f"- {m}" for m in motivos))
    return 0 if not motivos else 2


if __name__ == "__main__":
    sys.exit(main())
