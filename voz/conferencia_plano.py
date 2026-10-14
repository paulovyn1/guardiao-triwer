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


def texto_do_plano(entrada):
    """O JSON que o Write vai gravar, ou None se não dá para saber (Edit parcial)."""
    c = (entrada or {}).get("content")
    if not isinstance(c, str):
        return None
    try:
        return json.loads(c.lstrip("﻿"))
    except ValueError:
        return None
