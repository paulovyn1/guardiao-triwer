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
import rota_agenda as ra
import visao_semana as vs

OPER = ra.OPER
BURACO_MAX = 90  # minutos livres no expediente acima dos quais o Claude é chamado para decidir o que entra (o dia vai até a hora de parar)


def _cfg():
    return vs._json(os.path.join(OPER, "config.json")) or {}


def _memoria(cfg):
    return (cfg.get("pastas") or {}).get("memoria")


def montar(dia, oper=OPER, cfg=None):
    """(plano, motivos): o plano base do dia e por que ele ainda precisa do Claude (lista vazia = pronto)."""
    cfg = cfg if cfg is not None else _cfg()
    memoria = _memoria(cfg)
    nome = ((cfg.get("pessoa") or {}).get("nome")) or "Eu"
    resumo = (vs._json(os.path.join(oper, "resumo_clickup.json")) or {}).get("tarefas") or []
    iso = dia.isoformat()
    blocos, sem_hora, atrasadas, aprovar = [], [], [], []
    for t in resumo:
        prazo = str(t.get("prazo") or "")
        if t.get("aprovar"):
            if prazo <= iso:
                aprovar.append(t)
            continue
        if prazo < iso:
            atrasadas.append(t)
        elif prazo == iso:
            if t.get("inicio") and t.get("fim"):
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
    if not blocos:
        motivos.append("Nada agendado para hoje no ClickUp: o dia precisa ser montado.")
    for item in trabalhos_do_guardiao(memoria, dia):
        motivos.append(f"Trabalho do guardião com data chegada (estado.md, seção \"Do guardião\"): {item}")
    return plano, motivos


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
              "", "PLANO BASE (a semana combinada; mantenha estes blocos e horários, salvo conflito):", json.dumps(plano, ensure_ascii=False, indent=1),
              "", vs.texto(oper, memoria, hoje=dia, incluir_hoje=False)]
    alertas = ra.alertas(planos, dia, cfg, memoria, oper)
    if alertas:
        partes += ["", "ALERTAS:", *[f"- {a}" for a in alertas]]
    return "\n".join(partes)


def conferir_arquivo(caminho, oper=OPER, cfg=None):
    cfg = cfg if cfg is not None else _cfg()
    plano = vs._json(caminho)
    if not isinstance(plano, dict):
        return ["O plano gravado não é um JSON válido."]
    dia = cp.data_do_plano(caminho, plano)
    outros = {d: p for d, p in vs.planos_da_semana(oper, dia).items() if d != dia.isoformat()}
    resumo = (vs._json(os.path.join(oper, "resumo_clickup.json")) or {}).get("tarefas")
    pendentes = {t.get("id") for t in resumo} if resumo is not None else None
    base, _ = montar(dia, oper, cfg)  # o que a semana combinada punha neste dia: nada dela pode sumir sem ir para outro dia
    return cp.conferir(plano) + cp.conferir_semana(plano, dia, base, outros, pendentes, (), _memoria(cfg))


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    ap.add_argument("--saida")
    ap.add_argument("--dossie")
    ap.add_argument("--conferir")
    a = ap.parse_args(argv)
    if a.conferir:
        problemas = conferir_arquivo(a.conferir)
        print("\n".join(f"- {p}" for p in problemas) if problemas else "ok")
        return 1 if problemas else 0
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
