"""Motor da agenda: o código monta a semana, a IA só revisa (docs/PRD-motor-agenda.md).

Monta, sem IA, os planos dos próximos dias de trabalho a partir do que já existe: plano_base.montar (fixos, tarefas do ClickUp com hora, stories)
e o que ele deixa "a encaixar" (atrasadas, sem hora, etapas de post, preparo da live, entregas com horário limite). O que não é aprovado é refeito;
plano aprovado fica como está e o que está nele não volta para a fila.

Ordem de alocação (regras da Milena, 16/10):
1. fixos, tarefas com hora e stories (já vêm do plano_base);
2. consumo antes das copies (rotina.regras.ideia_depois_de_consumo): um por dia, no começo do primeiro espaço do dia;
3. a fila, pelo limite (mais cedo primeiro) e, no mesmo limite, copy antes de design; cada item no primeiro dia e espaço do tipo certo até o limite;
4. não coube até o limite: encolhe stories daquele dia (se não for o dia de captação já mínimo) e tenta de novo; ainda não coube: hora extra de até 2h
   vira pergunta "estender o dia ou renegociar o prazo?"; mais que isso, renegociar o prazo.
Tarefa sem tempo medido usa um padrão e vai para "julgar" (a IA estima). Nada aqui chama IA.

Uso: python motor_agenda.py [--dias 5] [--gravar] [--hoje]   -> imprime o resumo; --gravar grava os dias não aprovados como "sugerido";
     --hoje inclui o plano de hoje (refaz a partir de agora se não estiver aprovado)."""
import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta

import conferencia_plano as cp
import plano_base as pb
import rota_agenda as ra
import visao_semana as vs

OPER = pb.OPER
HORA_EXTRA_MAX = 120
PADRAO_MIN = {"copy": 30, "design": 60, "manychat": 20, "relatorio": 5, "preparo": 30, "pesado": 45, "leve": 20}
CONSUMO_MIN = 30


def _norm(t):
    return cp._norm(t)


def _chave(item):
    return str(item.get("id") or _norm(item.get("titulo")))


def estimar(item, oper=OPER, ajustes=None):
    """(minutos, medido). Usa o tempo informado, o que a IA estimou, a média medida em tempos.json (3 registros confirmados ou mais) ou um padrão."""
    m = ((ajustes or {}).get("minutos") or {}).get(str(item.get("id") or "")) or ((ajustes or {}).get("minutos") or {}).get(str(item.get("titulo") or ""))
    if m:
        return int(m), True
    if item.get("minutos"):
        return int(item["minutos"]), True
    chave = item.get("etapa") or ra.tipo_de(item.get("titulo"), item.get("lista") or "")
    tipos = (vs._json(os.path.join(oper, "tempos.json")) or {}).get("tipos") or {}
    nomes = {"design": ("design_post_carrossel", "Design"), "copy": ("copy",), "relatorio": ("relatorio",)}.get(chave, ())
    for nome in nomes:
        reais = [r.get("real") for r in (tipos.get(nome) or {}).get("registros") or [] if r.get("confirmado") and (r.get("real") or 0) > 1]
        if len(reais) >= 3:
            return int(round(sum(reais) / len(reais))), True
    return PADRAO_MIN.get(chave, 45), False


def _tipo_janela(item, ajustes=None):
    forcado = item.get("tipo_forcado") or ((ajustes or {}).get("janela") or {}).get(str(item.get("id") or ""))
    if forcado in ("pesado", "design", "leve"):
        return forcado
    if item.get("etapa") == "design":
        return "design"
    if item.get("etapa") in ("copy",) or item.get("origem") == "preparo" and "tema" in _norm(item.get("titulo")):
        return "pesado"
    if item.get("etapa") in ("manychat", "relatorio"):
        return "leve"
    if item.get("origem") == "preparo":
        return "design" if "thumb" in _norm(item.get("titulo")) else "leve"
    return ra.tipo_de(item.get("titulo"), item.get("lista") or "")


def _dias(hoje, cfg, n):
    trabalho = cp._dias_de_trabalho((cfg or {}).get("rotina") or {})
    d, saida = hoje, []
    while len(saida) < n:
        if d.weekday() in trabalho:
            saida.append(d)
        d += timedelta(days=1)
    return saida


def _a_partir(d):
    agora = datetime.now()
    return agora.hour * 60 + agora.minute + 5 if d == agora.date() else None


def _colocar(plano, d, item, minutos, tipo, nome, memoria):
    for x, y in ra.espacos(plano, d, tipo, a_partir=_a_partir(d), memoria=memoria):
        if item.get("ate") and item.get("limite") == d:
            y = min(y, vs.hm(item["ate"]))  # entrega com horário limite: pronta ANTES do horário, no próprio dia
        if y - x >= minutos:
            bloco = {"id": pb._id_livre(plano), "inicio": vs.fmt(x), "fim": vs.fmt(x + minutos), "titulo": item["titulo"], "dono": nome,
                     "frente": item.get("lista") or "Conteúdo", "descricao": f"Encaixado pelo motor da agenda ({item.get('origem')}).",
                     "primeiro_passo": "Abra a tarefa no ClickUp e comece pelo primeiro item.",
                     "por_que_agora": (f"Precisa estar pronto até {item['limite']:%d/%m}." if item.get("limite") else "Estava atrasada.")}
            if item.get("id"):
                bloco["clickup_id"] = item["id"]
                bloco["reagendado"] = True
            if item.get("limite"):
                bloco["prazo_final"] = item["limite"].isoformat()
            if not item.get("id") and item.get("lista_id"):  # subtarefa nova (desdobrada pela IA): o servidor cria no ClickUp ao aprovar
                bloco["lista_id"] = item["lista_id"]
                if item.get("pai"):
                    bloco["pai"] = item["pai"]
            plano.setdefault("blocos", []).append(bloco)
            plano["blocos"].sort(key=lambda b: b.get("inicio") or "")
            return bloco
    return None


def _encolher_stories(plano, d, cfg):
    """Tira um bloco de stories do dia (o último criado pelo plano base), nunca abaixo de 15 min. Devolve True se tirou."""
    s = cp.config_stories(cfg)
    if not s:
        return False
    st = [b for b in plano.get("blocos") or [] if cp._eh_stories(b) and not b.get("clickup_id") and b.get("status") != "feito"]
    if sum(cp._minutos(b) for b in st) - (cp._minutos(st[-1]) if st else 0) < 15 or not st:
        return False
    plano["blocos"].remove(st[-1])
    return True


def _inserir_consumo(plano, d, cfg, nome, memoria):
    """Um consumo por dia, antes das copies, quando a regra pessoal está ligada e o dia ainda não tem."""
    if not (((cfg.get("rotina") or {}).get("regras") or {}).get("ideia_depois_de_consumo")):
        return None
    if any(pb.ROTINA.search(_norm(b.get("titulo"))) for b in (plano.get("blocos") or []) + (plano.get("fixos") or [])):
        return None
    item = {"titulo": "Consumo com a pergunta: isso pode virar post ou Substack?", "origem": "rotina", "lista": "Conteúdos"}
    for tipo in ("pesado", "leve"):
        b = _colocar(plano, d, item, CONSUMO_MIN, tipo, nome, memoria)
        if b:
            b["descricao"] = "Consumo do dia com a pergunta ligada: as ideias de post nascem daqui, por isso vem antes das copies."
            b["por_que_agora"] = "Rotina fixa, antes das copies."
            return b
    return None


def _desdobrar(fila, desdobrar, cfg, delegar=None):
    """Troca a entrega pelas subtarefas que a IA propôs. Entrega que não está na fila (marco sem tarefa, "dd/mm slug: nome") ganha o limite do texto."""
    import re
    listas = {_norm(l.get("nome")): l.get("id") for l in ((cfg.get("clickup") or {}).get("listas") or [])}
    padrao = next((l.get("id") for l in ((cfg.get("clickup") or {}).get("listas") or []) if "conteud" in _norm(l.get("nome"))), None)
    for chave, subs in (desdobrar or {}).items():
        item = fila.pop(chave, None) or fila.pop(_norm(chave), None)
        limite = item.get("limite") if item else None
        if not item:
            m = re.match(r"\s*(\d{1,2})/(\d{1,2})", chave)
            if m:
                hoje = date.today()
                limite = date(hoje.year + (1 if int(m.group(2)) < hoje.month else 0), int(m.group(2)), int(m.group(1)))
        eu = _norm(((cfg.get("pessoa") or {}).get("nome")) or "").split(" ")[0]
        for s in subs:
            if s.get("dono") and eu and eu not in _norm(s["dono"]):  # de outra pessoa: delegação, fora da agenda dela
                if delegar is not None:
                    delegar.append({"titulo": s["titulo"], "dono": s["dono"], "pai": (item or {}).get("id")})
                continue
            lim = limite - timedelta(days=int(s.get("dias_antes") or 0)) if limite else None
            novo = {"id": None, "titulo": str(s["titulo"])[:120], "limite": lim, "origem": "desdobrado pela IA", "minutos": int(s.get("minutos") or 45),
                    "tipo_forcado": s.get("tipo"), "pai": (item or {}).get("id"), "lista": (item or {}).get("lista"),
                    "lista_id": listas.get(_norm((item or {}).get("lista"))) or padrao}
            fila[_norm(novo["titulo"])] = novo


def _parecido(a, b):
    a, b = _norm(a), _norm(b)
    return bool(a and b) and (a in b or b in a or a[:25] == b[:25])


def _feitos_do_registro(oper, iso):
    reg = vs._json(os.path.join(oper, "registros", f"registro_{iso}.json")) or {}
    return [b for b in reg.get("blocos") or [] if b.get("estado") == "feito"]


def _sobrepoe(b, ocupado):
    return any(x < vs.hm(b["fim"]) and vs.hm(b["inicio"]) < y for x, y in ocupado)


def _refazer_hoje(plano, d, oper, ajustes, fila):
    """Hoje a partir de agora (pedido dela ou atraso): o que já foi feito fica como feito; o que passou sem ser feito volta para a fila; imprevistos e
    refeições com horário dito por ela entram como fixos e liberam o que estava por baixo; o que ela mandou tirar sai; stories já feitos contam."""
    iso = d.isoformat()
    agora = _a_partir(d) or 0
    aj = ajustes or {}
    feitos_reg = _feitos_do_registro(oper, iso)
    feitos_ia = aj.get("feitos") or []
    for imp in aj.get("imprevistos") or []:
        fixos = plano.setdefault("fixos", [])
        mesmo = next((f for f in fixos if _parecido(f.get("titulo"), imp["titulo"])), None)
        if mesmo:
            mesmo.update(inicio=imp["inicio"], fim=imp["fim"])
        else:
            fixos.append(dict(imp, imprevisto=True))
    ocupado = [(vs.hm(f["inicio"]), vs.hm(f["fim"])) for f in plano.get("fixos") or [] if f.get("inicio") and f.get("fim")]
    eh_stories = lambda t: "stor" in _norm(t) or "caixinha" in _norm(t)
    stories_feitos = sum((f.get("minutos") or 15) for f in feitos_ia if eh_stories(f["titulo"]))
    feitos_ia = [f for f in feitos_ia if not eh_stories(f["titulo"]) and len(_norm(f["titulo"])) >= 10]  # stories feitos só descontam minutos
    for b in list(plano.get("blocos") or []):
        titulo = b.get("titulo")
        feito_reg = any(_parecido(titulo, f.get("titulo")) or (b.get("clickup_id") and b.get("clickup_id") == f.get("clickup_id")) for f in feitos_reg)
        if feito_reg or (not cp._eh_stories(b) and any(_parecido(titulo, f["titulo"]) for f in feitos_ia)):
            b["status"] = "feito"
            continue
        if any(_parecido(titulo, t) for t in aj.get("tirar") or []):
            plano["blocos"].remove(b)
            plano.setdefault("removidos", []).append(titulo)
            fila.pop(b.get("clickup_id") or _norm(titulo), None)
            continue
        if cp._eh_stories(b) and not b.get("clickup_id"):
            if stories_feitos > 0:
                stories_feitos -= cp._minutos(b)
                plano["blocos"].remove(b)
            elif vs.hm(b["inicio"]) < agora or _sobrepoe(b, ocupado):
                plano["blocos"].remove(b)  # stories que passou ou bate num fixo: o plano base repõe no que sobra
            continue
        if vs.hm(b["inicio"]) < agora or _sobrepoe(b, ocupado):
            plano["blocos"].remove(b)  # passou sem ser feito, ou está por baixo de um fixo: volta para a fila
            limite = None
            try:
                limite = date.fromisoformat(str(b.get("prazo_final") or ""))
            except ValueError:
                pass
            fila.setdefault(b.get("clickup_id") or _norm(titulo), {"id": b.get("clickup_id"), "titulo": titulo, "limite": limite,
                                                                   "origem": "replanejado hoje", "minutos": max(5, cp._minutos(b)), "lista": b.get("frente")})
    for f in feitos_ia:  # o que ela fez fora do plano sai da fila
        for chave, item in list(fila.items()):
            if _parecido(item.get("titulo"), f["titulo"]):
                fila.pop(chave)


def montar_semana(oper=OPER, cfg=None, hoje=None, dias=5, incluir_hoje=False, ajustes=None):
    """{"dias": {iso: plano}, "aprovados": [iso], "nao_coube": [...], "julgar": [...], "problemas": {iso: [graves]}}."""
    cfg = cfg if cfg is not None else pb._cfg()
    hoje = hoje or date.today()
    memoria = pb._memoria(cfg)
    nome = ((cfg.get("pessoa") or {}).get("nome")) or "Eu"
    existentes = vs.carregar_planos(oper, hoje)
    rascunho, aprovados, fila = {}, [], {}
    acrescimo = {}  # dia aprovado: o motor só ACRESCENTA em espaço livre (nunca move o que ela aprovou) e o dia volta para aprovação
    for d in _dias(hoje, cfg, dias):
        iso = d.isoformat()
        ex = existentes.get(iso)
        if d == hoje and not incluir_hoje:
            aprovados.append(iso)
            continue
        if (ex or {}).get("status") == "aprovado" and d != hoje:  # hoje, com incluir_hoje, é refeito a partir de agora (ela pediu)
            aprovados.append(iso)
            acrescimo[iso] = json.loads(json.dumps(ex))
            acrescimo[iso]["_n"] = len(ex.get("blocos") or [])
            continue
        base, _motivos = pb.montar(d, oper, cfg, hoje, so_aprovados=True)
        base["origem"] = "motor da agenda (sem IA)"
        rascunho[iso] = base
        for item in pb.PENDENCIAS.get(iso, []):
            chave = item.get("id") or _norm(item.get("titulo"))
            if chave and chave not in fila:
                fila[chave] = item
        if d == hoje:
            _refazer_hoje(base, d, oper, ajustes, fila)
        parar = ra.parar_em(d, memoria)
        for b in list(base.get("blocos") or []):  # nada passa da hora de parar: o que ficou depois dela (de um plano antigo) volta para a fila
            if b.get("status") != "feito" and b.get("fim") and vs.hm(b["fim"]) > parar:
                base["blocos"].remove(b)
                fila.setdefault(b.get("clickup_id") or _norm(b.get("titulo")), {"id": b.get("clickup_id"), "titulo": b.get("titulo"), "limite": None,
                                                                                "origem": "depois da hora de parar", "minutos": max(5, cp._minutos(b)),
                                                                                "lista": b.get("frente")})
    delegar = []
    _desdobrar(fila, (ajustes or {}).get("desdobrar"), cfg, delegar)
    prioridade = (ajustes or {}).get("prioridade") or {}
    ja = {b.get("clickup_id") for p in acrescimo.values() for b in p.get("blocos") or [] if b.get("clickup_id")}
    fila = {k: v for k, v in fila.items() if not v.get("id") or v["id"] not in ja}
    rascunho.update(acrescimo)
    rascunho = dict(sorted(rascunho.items()))
    ordem = {"copy": 0, "pesado": 1, "manychat": 2, "design": 3, "leve": 4, "relatorio": 5}
    itens = sorted(fila.values(), key=lambda i: (i.get("limite") or date.max, prioridade.get(str(i.get("id") or ""), 4),
                                                 ordem.get(i.get("etapa") or _tipo_janela(i, ajustes), 4), str(i.get("titulo"))))
    for iso, plano in rascunho.items():
        if any(i.get("etapa") == "copy" for i in itens):
            _inserir_consumo(plano, date.fromisoformat(iso), cfg, nome, memoria)
    nao_coube, julgar, adiados = [], [], []
    ultimo_dia = max(rascunho) if rascunho else hoje.isoformat()
    for item in itens:
        minutos, medido = estimar(item, oper, ajustes)
        if not medido:
            julgar.append({"id": item.get("id"), "titulo": item.get("titulo"), "minutos_padrao": minutos})
        tipo = _tipo_janela(item, ajustes)
        validos = [iso for iso in rascunho if (not item.get("limite") or iso <= item["limite"].isoformat())
                   and (not item.get("abre") or iso >= item["abre"].isoformat())]
        posto = None
        for iso in validos:
            posto = _colocar(rascunho[iso], date.fromisoformat(iso), item, minutos, tipo, nome, memoria)
            if posto:
                break
        while not posto and validos and _encolher_stories(rascunho[validos[-1]], date.fromisoformat(validos[-1]), cfg):  # stories só encolhe se não há para onde mover
            posto = _colocar(rascunho[validos[-1]], date.fromisoformat(validos[-1]), item, minutos, tipo, nome, memoria)
        if posto:
            continue
        if item.get("limite") and item["limite"].isoformat() > ultimo_dia:  # vence depois do horizonte: fica para os próximos dias, não é "não coube"
            adiados.append({"id": item.get("id"), "titulo": item.get("titulo"), "limite": item["limite"].isoformat() if item.get("limite") else None})
            continue
        ultimo = validos[-1] if validos else None
        livre = max([y - x for x, y in ra.espacos(rascunho[ultimo], date.fromisoformat(ultimo), tipo, memoria=memoria)] or [0]) if ultimo else 0  # o maior espaço contínuo
        falta = max(0, minutos - livre)
        pergunta = (f"\"{item['titulo']}\" não cabe até {item['limite']:%d/%m}" if item.get("limite") else f"\"{item['titulo']}\" não cabe nos próximos dias")
        if ultimo and falta <= HORA_EXTRA_MAX:
            pergunta += f". Você prefere estender o dia {ultimo[8:10]}/{ultimo[5:7]} em {falta} min ou renegociar o prazo?"
        else:
            pergunta += ". Precisa renegociar o prazo com quem combinou."
        nao_coube.append({"id": item.get("id"), "titulo": item.get("titulo"), "limite": item.get("limite").isoformat() if item.get("limite") else None,
                          "minutos": minutos, "pergunta": pergunta})
    for iso, plano in list(acrescimo.items()):
        novos = [b["titulo"] for b in plano["blocos"] if b.get("descricao", "").startswith("Encaixado pelo motor")]
        if len(plano["blocos"]) == plano.pop("_n"):
            del rascunho[iso]  # nada acrescentado: o aprovado fica como está
            continue
        plano["aviso"] = f"Acrescentei ao plano aprovado, sem mexer no que estava: {'; '.join(novos)}. Aprove de novo. " + str(plano.get("aviso") or "")
        plano.pop("aprovado_em", None)
    for iso, plano in rascunho.items():  # stories tirados ou que passaram: o plano base repõe no que sobrou do dia
        pb.inserir_stories(plano, date.fromisoformat(iso), cfg, nome)
    problemas = {}
    for iso, plano in rascunho.items():
        d = date.fromisoformat(iso)
        outros = {k: v for k, v in {**existentes, **rascunho}.items() if k != iso}
        graves, avisos = pb.conferir_plano(plano, d, oper, cfg, outros)
        cp.anotar_avisos(plano, avisos)
        if graves:
            problemas[iso] = graves
        dele = [n["pergunta"] for n in nao_coube if n.get("limite") and n["limite"] >= iso]
        plano["aviso"] = ("Montei pelo motor da agenda, sem IA. " + (" ".join(dele[:3]) + " " if dele else "") + str(plano.get("aviso") or "")).strip()
        plano["status"] = "sugerido"
        plano["gerado_em"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    return {"dias": rascunho, "aprovados": aprovados, "nao_coube": nao_coube, "julgar": julgar, "problemas": problemas, "adiados": adiados, "delegar": delegar}


def planejar(oper=OPER, cfg=None, hoje=None, dias=5, incluir_hoje=False, ia=True, pedido=None):
    """O fluxo inteiro: o motor monta; se há o que julgar (tempo sem medida, não coube, marco sem tarefa), a IA revisa UMA vez e o motor remonta
    com as instruções. Devolve o resultado com "perguntas" (para a pessoa) e "explicacao"."""
    cfg = cfg if cfg is not None else pb._cfg()
    hoje = hoje or date.today()
    r = montar_semana(oper, cfg, hoje, dias, incluir_hoje)
    marcos = []
    try:
        marcos = pb.marcos_sem_lugar(hoje, oper, cfg)
    except Exception:
        pass
    aj = None
    if ia and (pedido or r["julgar"] or r["nao_coube"] or marcos):
        import revisor_ia
        try:
            atual = vs._json(os.path.join(oper, "plano_do_dia.json")) if pedido else None
            aj = revisor_ia.ajustes(revisor_ia.interpretar(revisor_ia.chamar(revisor_ia.montar_prompt(r, cfg, marcos, pedido, atual), oper)))
            r = montar_semana(oper, cfg, hoje, dias, incluir_hoje, aj)
        except Exception as erro:  # sem IA o rascunho do motor continua valendo
            print(f"(motor: a revisão da IA falhou, fica o rascunho: {erro})", file=sys.stderr)
    r["perguntas"] = list(dict.fromkeys(((aj or {}).get("perguntas") or []) + [n["pergunta"] for n in r["nao_coube"]]))
    r["explicacao"] = " ".join((aj or {}).get("explicar") or [])
    if r["explicacao"]:
        for plano in r["dias"].values():
            plano["aviso"] = r["explicacao"] + " " + str(plano.get("aviso") or "")
    return r


def gravar(resultado, oper=OPER, hoje=None, hoje_mesmo_aprovado=False):
    """Grava os dias montados (nunca um aprovado). Hoje vai para plano_do_dia.json e para planos/plano_<hoje>.json."""
    hoje = hoje or date.today()
    os.makedirs(os.path.join(oper, "planos"), exist_ok=True)
    gravados = []
    for iso, plano in resultado["dias"].items():
        destinos = [os.path.join(oper, "planos", f"plano_{iso}.json")] + ([os.path.join(oper, "plano_do_dia.json")] if iso == hoje.isoformat() else [])
        for caminho in destinos:
            atual = vs._json(caminho)
            if isinstance(atual, dict) and atual.get("status") == "aprovado" and not (hoje_mesmo_aprovado and iso == hoje.isoformat()) \
                    and "Acrescentei ao plano aprovado" not in str(plano.get("aviso") or ""):
                continue  # aprovado só volta para aprovação quando ela pediu para refazer hoje, ou quando o motor acrescentou algo
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(plano, f, ensure_ascii=False, indent=2)
            gravados.append(caminho)
    return gravados


def resumo(resultado):
    linhas = []
    for iso, plano in resultado["dias"].items():
        linhas.append(f"{iso}: {len(plano.get('blocos') or [])} blocos" + (f" | GRAVES: {' | '.join(resultado['problemas'][iso])}" if iso in resultado["problemas"] else ""))
    linhas += [f"não coube: {n['pergunta']}" for n in resultado["nao_coube"]]
    linhas += [f"julgar (tempo padrão {j['minutos_padrao']} min): {j['titulo']}" for j in resultado["julgar"]]
    linhas += [f"aprovado, não mexi: {iso}" for iso in resultado["aprovados"]]
    linhas += [f"fica para depois (vence {a['limite']}): {a['titulo']}" for a in resultado.get("adiados") or []]
    linhas += [f"delegar a {d['dono']}: {d['titulo']}" for d in resultado.get("delegar") or []]
    return "\n".join(linhas)


def main(argv=None):
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=5)
    ap.add_argument("--gravar", action="store_true")
    ap.add_argument("--hoje", action="store_true")
    ap.add_argument("--ia", action="store_true")  # a IA revisa o rascunho (uma chamada)
    a = ap.parse_args(argv)
    r = planejar(dias=a.dias, incluir_hoje=a.hoje, ia=a.ia)
    print(resumo(r))
    for p in r.get("perguntas") or []:
        print("pergunta: " + p)
    if a.gravar:
        print("gravei: " + "; ".join(gravar(r)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
