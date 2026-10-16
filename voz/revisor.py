"""Revisor do plano: um segundo Claude, SEM o contexto de quem montou, confere o plano contra as regras, a prioridade e o horizonte das campanhas.

Por que existe: o modelo que monta o plano se audita sozinho (item 11 da auditoria) e erra de novo o que já foi corrigido. O revisor só recebe o plano, as
regras (aprendizados, extensões, SKILL 3.1 e 3.2, perfil), os fatos da pessoa (fixos, cancelados, hora de parar), as campanhas ativas e o horizonte de 14 dias.
Ele só aponta; quem corrige é o gerador, em UMA rodada. O que é regra mecânica continua em código (conferencia_plano.py): o revisor cuida do julgamento.

Só roda quando vale o custo (decisão da Milena, 2026-10-15): dia muito apertado, ou replanejamento (tarefa nova, atraso, pedido dela).

Uso (o gerar_plano.ps1 chama): python revisor.py --plano arq.json --data AAAA-MM-DD [--dossie dossie.txt] [--replanejar] [--forcar]
Sai 0 (não precisava rodar, ou aprovou, ou não deu para revisar) ou 1 (reprovou: os problemas saem impressos, um por linha)."""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
from datetime import date, timedelta

import conferencia_plano as cp
import rota_agenda as ra
import visao_semana as vs

OPER = ra.OPER
LIMITE_APERTADO = 0.9  # fração do expediente já ocupada a partir da qual o dia é "muito apertado"
TEMPO_REVISAO = 300
PEDE_REPLANEJAR = re.compile(r"atrasada|sem hor[aá]rio|replanej|tarefa nova|tarefas novas", re.I)

ITENS = [
    "Cada tarefa e campanha foi classificada na matriz de prioridade (3.1) e a ordem do plano segue a classificação?",
    "Todo bloco de copy, decisão, pensar ou estratégia cai numa faixa boa do dia (perfil.md)?",
    "O último bloco termina na hora de parar daquele dia e a sobra tem destino marcado? Se houver hora extra, o plano primeiro reagendou o adiável e simplificou uma tarefa, e deixou a hora extra como proposta sujeita à aprovação?",
    "Cada estimativa de tempo é plausível pelos registros e pelo perfil (relatório de post leva 5 minutos)?",
    "Nenhuma tarefa 'opcional' serve ao foco da semana?",
    "Existe trabalho em fim de semana que um dia útil poderia absorver?",
    "Alguma linha do aprendizados.md ou das extensões é violada pelo plano?",
    "Há bloco que depende de dia, prazo ou ordem errada (relatório antes de 24h do post, design antes da copy, etapa depois do prazo)?",
    "A campanha mais perto do fim, ou a de maior importância, ganhou tempo ANTES de tarefa que não move a campanha?",
    "Campanha pública de venda a até 3 dias do fim tem bloco que traga gente (stories, aviso no grupo, convite)?",
    "O tempo livre ou extra foi para o que move o objetivo das campanhas ativas, e não para tarefa que pode esperar?",
    "O horizonte de 14 dias mostra algum marco crítico que este plano deveria começar a preparar e não preparou?",
    "Stories: o plano define o tipo do dia (sequência normal 30 min e 10 telas, caixinha 45 min e 12 telas, captação 15 min e 3 telas; em dia apertado a caixinha cai para 15 min), "
    "com o tempo quebrado em blocos curtos espalhados pelo dia? Divulgação sozinha (replay, convite) não basta; captação só um dia por semana.",
]


def _ler(caminho):
    try:
        with open(caminho, encoding="utf-8-sig") as f:
            return f.read()
    except OSError:
        return ""


def _pasta_skill(oper=OPER):
    for c in (os.path.join(os.path.expanduser("~"), ".claude", "skills", "guardiao-triwer"),
              os.path.join(os.path.expanduser("~"), ".codex", "skills", "guardiao-triwer"),
              os.path.dirname(os.path.dirname(os.path.abspath(__file__)))):
        if os.path.exists(os.path.join(c, "SKILL.md")):
            return c
    return ""


def _secao(texto, de, ate):
    m = re.search(rf"^{re.escape(de)}.*?(?=^{re.escape(ate)}|\Z)", texto, re.M | re.S)
    return m.group(0).strip() if m else ""


def deve_revisar(plano, dia, oper=OPER, cfg=None, replanejar=False, forcar=False, dossie=""):
    """Por que o revisor deve rodar neste plano (texto), ou None se não vale o custo."""
    if forcar:
        return "pedido direto"
    if replanejar:
        return "replanejamento"
    if dossie and PEDE_REPLANEJAR.search(dossie):
        return "replanejamento (tarefa nova ou atraso no dossiê)"
    cfg = cfg if cfg is not None else (vs._json(os.path.join(oper, "config.json")) or {})
    memoria = (cfg.get("pastas") or {}).get("memoria")
    vs.aplicar_rotina(cfg)
    ocupado = ra.ocupacao(plano, dia, memoria)[0]
    if ocupado >= LIMITE_APERTADO:
        return f"dia muito apertado ({round(ocupado * 100)}% ocupado)"
    return None


def montar_prompt(plano, dia, motivo, oper=OPER, cfg=None):
    cfg = cfg if cfg is not None else (vs._json(os.path.join(oper, "config.json")) or {})
    memoria = (cfg.get("pastas") or {}).get("memoria") or ""
    skill = _pasta_skill(oper)
    texto_skill = (_ler(os.path.join(skill, "references", "planejar.md")) or _ler(os.path.join(skill, "SKILL.md"))) if skill else ""  # 3.1 e 3.2 moraram no SKILL.md até a v0.10.6
    regras = _secao(texto_skill, "## 3.1", "## 4.") or "(regras de planejamento não encontradas)"
    extensoes = "\n\n".join(_ler(c) for c in sorted(glob.glob(os.path.join(skill, "extensoes-*.md")))) if skill else ""
    campanhas = []
    for slug in cp.campanhas_ativas(memoria, dia):
        c = cp._cabecalho(os.path.join(memoria, "campanhas", slug + ".md"))
        ficha = re.search(r"- O que é e objetivo:(.*)", _ler(os.path.join(memoria, "campanhas", slug + ".md")))
        campanhas.append(f"- {c.get('nome') or slug} | tipo {c.get('tipo')} | importância {c.get('importancia')} | de {c.get('data_inicio')} a {c.get('data_fim')}"
                         f" | objetivo:{(ficha.group(1).strip() if ficha else '')[:400]}")
    rotina = cfg.get("rotina") or {}
    try:
        horizonte = ra.horizonte(dia, dia + timedelta(days=14), vs.planos_da_semana(oper, dia), cfg, memoria, oper)
    except Exception:
        horizonte = ""
    fatos = json.dumps({"dia": dia.isoformat(), "dia_da_semana": vs.DIAS[dia.weekday()], "hora_de_parar": vs.fmt(vs.hora_de_parar(dia, memoria)),
                        "fixos_da_semana": rotina.get("fixos_semana"), "fixos_por_data": rotina.get("fixos_datas"), "cancelados": rotina.get("cancelados"),
                        "dias_de_trabalho": rotina.get("dias_trabalho")}, ensure_ascii=False)
    numerados = "\n".join(f"{i}. {t}" for i, t in enumerate(ITENS, 1))
    return (
        "Você é o REVISOR de um plano do dia. Você NÃO montou este plano e não conhece a conversa que o gerou. Procure falhas, com evidência no próprio plano. "
        "Só reprove um item quando conseguir apontar o bloco e a regra. Na dúvida, aprove. Não reescreva o plano e não proponha estratégia de conteúdo.\n"
        f"Motivo desta revisão: {motivo}.\n\n"
        f"REGRAS (SKILL, seções 3.1 e 3.2):\n{regras}\n\n"
        f"APRENDIZADOS (regras que a pessoa ensinou corrigindo):\n{_ler(os.path.join(memoria, 'aprendizados.md'))}\n\n"
        f"EXTENSÕES DA PESSOA:\n{extensoes}\n\n"
        f"PERFIL:\n{_ler(os.path.join(memoria, 'perfil.md'))}\n\n"
        f"CALIBRAGEM (o que ela confirmou sobre tempos reais; use ao julgar estimativas):\n{_ler(os.path.join(oper, 'calibragem', 'regras.md'))}\n\n"
        f"FATOS (use estes; o estado.md pode estar velho):\n{fatos}\n\n"
        f"CAMPANHAS ATIVAS:\n" + "\n".join(campanhas) + f"\n\nHORIZONTE:\n{horizonte}\n\n"
        f"PLANO A REVISAR:\n{json.dumps(plano, ensure_ascii=False, indent=1)}\n\n"
        f"Responda os itens abaixo. Saída: SOMENTE um JSON, sem texto antes ou depois, no formato "
        '{"itens": [{"n": 1, "ok": true, "motivo": ""}]}. "motivo" só quando ok for false: diga o bloco (título e horário) e a regra violada, em uma frase.\n'
        f"{numerados}"
    )


def interpretar(saida):
    """Problemas (uma frase cada) do JSON do revisor. Saída ilegível: nenhum problema (não bloqueia o plano por falha do revisor)."""
    texto = str(saida or "")
    m = re.search(r"\{.*\}", texto, re.S)
    if not m:
        return []
    try:
        itens = json.loads(m.group(0)).get("itens") or []
    except ValueError:
        return []
    problemas = []
    for it in itens:
        if isinstance(it, dict) and it.get("ok") is False and str(it.get("motivo") or "").strip():
            n = int(it.get("n") or 0)
            problemas.append(f"Item {n}" + (f" ({ITENS[n - 1][:60]}...)" if 1 <= n <= len(ITENS) else "") + f": {str(it['motivo']).strip()}")
    return problemas


def _chamar_claude(prompt, oper=OPER):
    try:
        with open(os.path.join(oper, "voz", "preferencias.json"), encoding="utf-8-sig") as arquivo:
            provedor = (json.load(arquivo) or {}).get("provedor_ia")
    except (OSError, ValueError):
        provedor = "claude"
    if provedor == "codex":
        import guardiao_codex
        return guardiao_codex.executar(prompt, oper, timeout=TEMPO_REVISAO)[0]
    import guardiao_sessao
    base = guardiao_sessao.comando_do_claude()
    if not base:
        raise RuntimeError("Claude Code não encontrado")
    modelo = os.environ.get("GUARDIAO_MODELO") or "claude-sonnet-5-5"
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)
    # o prompt vai pelo stdin: com tudo dentro (regras, campanhas, horizonte) ele passa do limite da linha de comando do Windows
    r = subprocess.run([*base, "-p", "--model", modelo, "--allowedTools", "Read", "--max-turns", "3", "--output-format", "json"], input=prompt,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=oper, timeout=TEMPO_REVISAO,
                       creationflags=getattr(guardiao_sessao, "FLAGS_CLAUDE", 0))
    return str((json.loads(r.stdout) or {}).get("result") or "")


def revisar(plano, dia, motivo, oper=OPER, cfg=None, executar=_chamar_claude):
    """Os problemas que o revisor aponta. Falha ao chamar o Claude: lista vazia (o plano segue sem revisão)."""
    try:
        return interpretar(executar(montar_prompt(plano, dia, motivo, oper, cfg), oper))
    except Exception as erro:
        print(f"(revisor: não consegui revisar: {erro})", file=sys.stderr)
        return []


def texto_da_correcao(problemas, caminho):
    return (f"Um revisor independente apontou problemas no plano que você gravou em {caminho}. Corrija SÓ isto e grave de novo, sem mexer no resto, "
            "mantendo o formato e o status 'sugerido':\n" + "\n".join(f"- {p}" for p in problemas))


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--plano", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--dossie")
    ap.add_argument("--replanejar", action="store_true")
    ap.add_argument("--forcar", action="store_true")
    a = ap.parse_args(argv)
    dia = date.fromisoformat(a.data)
    plano = vs._json(a.plano)
    if not isinstance(plano, dict):
        return 0
    motivo = deve_revisar(plano, dia, replanejar=a.replanejar, forcar=a.forcar, dossie=_ler(a.dossie) if a.dossie else "")
    if not motivo:
        return 0
    problemas = revisar(plano, dia, motivo)
    print("\n".join(problemas))
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
