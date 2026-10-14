# Acha, em Python e sem gastar uma chamada ao Claude, a tarefa MÃE de cada post dos próximos dias e as etapas (subtarefas) dela.
# Por que existe: o guardião liga cada etapa de um post (copy, design...) à tarefa mãe. Procurar isso pelo Claude custa milhares de tokens,
# e o resumo do ClickUp (lido poucas vezes ao dia) fica velho. Aqui é uma consulta direta, de graça, a cada 10 minutos.
#
# Só puxa o que importa: tarefas da lista de conteúdo com prazo nos próximos dias e o campo "Onde" = "Feed". Nada de histórico.
# Liga pelo config.json:
#   "clickup": { "posts": { "lista": "Conteúdos", "campo": "Onde", "valor": "Feed", "dias_a_frente": 10, "intervalo_min": 10 } }
# Sem essa chave o recurso fica desligado. Gera <pasta operacional>\posts_maes.json (poucas linhas).
import json
import os
import re
import time
import unicodedata
from datetime import datetime, timedelta

import requests

API = "https://api.clickup.com/api/v2"
DIAS = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6}


def _config_posts(cfg):
    p = (cfg.get("clickup") or {}).get("posts")
    if not isinstance(p, dict) or not p.get("lista"):
        return None
    return {"lista": p["lista"], "campo": p.get("campo") or "Onde", "valor": p.get("valor") or "Feed",
            "dias_a_frente": int(p.get("dias_a_frente") or 10), "intervalo_min": int(p.get("intervalo_min") or 10)}


def _id_da_lista(cfg, nome):
    alvo = str(nome or "").strip().lower()
    for l in (cfg.get("clickup") or {}).get("listas") or []:
        if str(l.get("nome", "")).strip().lower() == alvo or str(l.get("id")) == str(nome):
            return str(l.get("id"))
    return None


def _norm(txt):
    return "".join(c for c in unicodedata.normalize("NFD", str(txt or "").lower()) if unicodedata.category(c) != "Mn").strip()


def _data(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000).astimezone().strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return None


def _criada_em(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000).astimezone().strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError):
        return None


def _campo_e_opcao(token, lista_id, nome_campo, nome_valor):
    """(id do campo, {id e posição da opção}) do campo suspenso, ou (None, None)."""
    r = requests.get(f"{API}/list/{lista_id}/field", headers={"Authorization": token}, timeout=30)
    r.raise_for_status()
    for f in r.json().get("fields", []):
        if _norm(f.get("name")) == _norm(nome_campo):
            for o in (f.get("type_config") or {}).get("options", []):
                if _norm(o.get("name") or o.get("label")) == _norm(nome_valor):
                    return f["id"], {str(o.get("id")), str(o.get("orderindex"))}
    return None, None


def _tarefas_da_janela(token, lista_id, dias_a_frente):
    hoje = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    ini = int((hoje - timedelta(days=1)).timestamp() * 1000)
    fim = int((hoje + timedelta(days=dias_a_frente + 1)).timestamp() * 1000)
    saida, pagina = [], 0
    while pagina < 10:
        r = requests.get(f"{API}/list/{lista_id}/task", headers={"Authorization": token}, timeout=30,
                         params={"archived": "false", "include_closed": "false", "subtasks": "false", "page": pagina,
                                 "due_date_gt": ini, "due_date_lt": fim})
        r.raise_for_status()
        dados = r.json()
        saida += dados.get("tasks", [])
        if dados.get("last_page", True) or not dados.get("tasks"):
            break
        pagina += 1
    return saida


def _etapas(token, tarefa_id):
    r = requests.get(f"{API}/task/{tarefa_id}", headers={"Authorization": token}, timeout=30, params={"include_subtasks": "true"})
    r.raise_for_status()
    return [{"id": s["id"], "nome": s.get("name"), "status": (s.get("status") or {}).get("status"), "prazo": _data(s.get("due_date"))}
            for s in r.json().get("subtasks", [])]


def atualizar(cfg, token, operacional):
    """Consulta o ClickUp e regrava posts_maes.json. Devolve {"ok", "maes", "novas_sem_etapas", "erro"}. Nunca levanta exceção."""
    vazio = {"ok": False, "maes": [], "novas_sem_etapas": []}
    conf = _config_posts(cfg)
    if not conf:
        return {**vazio, "erro": "desligado (falta clickup.posts no config.json)"}
    if not token:
        return {**vazio, "erro": "sem token do ClickUp"}
    lista_id = _id_da_lista(cfg, conf["lista"])
    if not lista_id:
        return {**vazio, "erro": f"lista '{conf['lista']}' não está em clickup.listas"}
    try:
        campo_id, opcoes = _campo_e_opcao(token, lista_id, conf["campo"], conf["valor"])
        if not campo_id:
            return {**vazio, "erro": f"não achei o campo '{conf['campo']}' = '{conf['valor']}' na lista"}
        maes = []
        for t in _tarefas_da_janela(token, lista_id, conf["dias_a_frente"]):
            if t.get("parent"):
                continue
            valor = next((c.get("value") for c in (t.get("custom_fields") or []) if c.get("id") == campo_id), None)
            if valor is None or str(valor) not in opcoes:
                continue
            etapas = _etapas(token, t["id"])
            maes.append({"id": t["id"], "nome": t.get("name"), "prazo": _data(t.get("due_date")), "criada_em": _criada_em(t.get("date_created")),
                         "status": (t.get("status") or {}).get("status"), "url": t.get("url"), "sem_etapas": not etapas, "etapas": etapas})
    except requests.RequestException as erro:
        return {**vazio, "erro": f"ClickUp não respondeu: {erro}"}
    maes.sort(key=lambda m: (m["prazo"] or "9999-99-99", m["nome"] or ""))

    with open(os.path.join(operacional, "posts_maes.json"), "w", encoding="utf-8") as f:
        json.dump({"gerado_em": time.strftime("%Y-%m-%d %H:%M"), "filtro": f"{conf['lista']} / {conf['campo']} = {conf['valor']} / próximos {conf['dias_a_frente']} dias",
                   "maes": maes}, f, ensure_ascii=False, indent=1)

    vistos_arq = os.path.join(operacional, "logs", "posts_vistos.json")  # só avisa uma vez por post novo; a primeira consulta só registra
    try:
        with open(vistos_arq, encoding="utf-8") as f:
            vistos = set(json.load(f))
    except (OSError, ValueError):
        vistos = None
    novas = [m for m in maes if vistos is not None and m["id"] not in vistos and m["sem_etapas"]]
    try:
        os.makedirs(os.path.dirname(vistos_arq), exist_ok=True)
        with open(vistos_arq, "w", encoding="utf-8") as f:
            json.dump(sorted((vistos or set()) | {m["id"] for m in maes}), f)
    except OSError:
        pass
    return {"ok": True, "maes": maes, "novas_sem_etapas": novas, "erro": None}


def data_do_post(texto, hoje=None):
    """'quinta', 'quinta-feira' ou '2026-10-15' viram AAAA-MM-DD (o próximo dia da semana com esse nome, hoje incluso). None se não entender."""
    t = _norm(texto)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
        return t
    for nome, n in DIAS.items():
        if t.startswith(nome):
            hoje = hoje or datetime.now().astimezone()
            return (hoje + timedelta(days=(n - hoje.weekday()) % 7)).strftime("%Y-%m-%d")
    return None


def achar_mae(operacional, post, hoje=None):
    """Id da tarefa mãe do post de 'quinta' (ou de uma data), lendo posts_maes.json. None se não achar ou se houver duas no mesmo dia."""
    data = data_do_post(post, hoje)
    try:
        with open(os.path.join(operacional, "posts_maes.json"), encoding="utf-8") as f:
            maes = json.load(f).get("maes", [])
    except (OSError, ValueError):
        return None
    certas = [m for m in maes if data and m.get("prazo") == data]
    return certas[0]["id"] if len(certas) == 1 else None


def rendimento(maes, dia, de_hhmm, ate_hhmm):
    """Posts (tarefas mãe) criados no dia entre de_hhmm e ate_hhmm. É o que um bloco de criação rendeu."""
    ini, fim = f"{dia} {de_hhmm}", f"{dia} {ate_hhmm}"
    return [m for m in maes if m.get("criada_em") and ini <= m["criada_em"] <= fim]


def _id_dono(cfg, dono):
    clickup = cfg.get("clickup") or {}
    for m in clickup.get("membros") or []:
        if m.get("nome") and dono and m["nome"].lower() in str(dono).lower():
            return int(m["id"])
    return int(clickup["user_id"])


def _planos_com_reservas(operacional):
    """[(caminho, plano)] do plano de hoje e dos planos de outros dias que têm bloco reservado (`reserva_post`)."""
    achados = []
    candidatos = [os.path.join(operacional, "plano_do_dia.json")]
    pasta = os.path.join(operacional, "planos")
    if os.path.isdir(pasta):
        candidatos += [os.path.join(pasta, n) for n in sorted(os.listdir(pasta)) if re.fullmatch(r"plano_\d{4}-\d{2}-\d{2}\.json", n)]
    for caminho in candidatos:
        try:
            with open(caminho, encoding="utf-8-sig") as f:
                plano = json.load(f)
        except (OSError, ValueError):
            continue
        if not plano.get("data"):
            m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(caminho))
            plano["data"] = m.group(1) if m else None
        if plano.get("data") and any(b.get("reserva_post") and not b.get("clickup_id") for b in plano.get("blocos", [])):
            achados.append((caminho, plano))
    return achados


def lancar_etapas(cfg, token, operacional, maes):
    """Para cada post (tarefa mãe) que acabou de nascer, troca os blocos reservados do plano (`reserva_post` = data da postagem, `etapa` = Copy ou Design)
    por subtarefas reais da mãe, com o horário que já estava reservado. Post sem reserva ou reserva sem post não cria nada: volta no resultado para o guardião tratar.
    Nunca cria tarefa solta: sem mãe, sem lista ou sem token, não faz nada."""
    conf = _config_posts(cfg)
    lista_id = _id_da_lista(cfg, conf["lista"]) if conf else None
    resultado = {"criadas": [], "posts_sem_reserva": [], "reservas_sem_post": 0}
    if not (lista_id and token and maes):
        return resultado
    planos = _planos_com_reservas(operacional)
    usados = set()
    for mae in sorted(maes, key=lambda m: (m.get("prazo") or "", m.get("criada_em") or "")):
        achou = False
        for etapa in ("Copy", "Design"):
            for caminho, plano in planos:
                bloco = next((b for b in plano["blocos"] if b.get("reserva_post") == mae.get("prazo") and str(b.get("etapa", "")).lower() == etapa.lower()
                              and not b.get("clickup_id") and id(b) not in usados), None)
                if not bloco:
                    continue
                usados.add(id(bloco))
                achou = True
                try:
                    ini = datetime.strptime(f"{plano['data']} {bloco['inicio']}", "%Y-%m-%d %H:%M").astimezone()
                    fim = datetime.strptime(f"{plano['data']} {bloco['fim']}", "%Y-%m-%d %H:%M").astimezone()
                    nome = f"{etapa} | {mae['nome']}"
                    r = requests.post(f"{API}/list/{lista_id}/task", headers={"Authorization": token}, timeout=30, json={
                        "name": nome, "parent": mae["id"], "assignees": [_id_dono(cfg, bloco.get("dono"))],
                        "start_date": int(ini.timestamp() * 1000), "start_date_time": True,
                        "due_date": int(fim.timestamp() * 1000), "due_date_time": True,
                        "time_estimate": int((fim - ini).total_seconds() * 1000),
                        "markdown_description": f"**O que é:** {etapa.lower()} do post, no tempo que o guardião reservou.\n\n*Criada pelo guardião ao fechar o bloco de ideias.*"})
                    r.raise_for_status()
                    bloco.update({"titulo": nome, "clickup_id": r.json()["id"], "pai": mae["id"]})
                    bloco.pop("reserva_post", None)
                    with open(caminho, "w", encoding="utf-8") as f:
                        json.dump(plano, f, ensure_ascii=False, indent=2)
                    resultado["criadas"].append({"post": mae["nome"], "etapa": etapa, "id": r.json()["id"], "dia": plano["data"], "inicio": bloco["inicio"]})
                except Exception as erro:
                    resultado.setdefault("erros", []).append(f"{etapa} de {mae.get('nome')}: {erro}")
                break
        if not achou:
            resultado["posts_sem_reserva"].append(mae.get("nome"))
    resultado["reservas_sem_post"] = sum(1 for _, p in planos for b in p["blocos"] if b.get("reserva_post") and not b.get("clickup_id"))
    return resultado


def registrar_rendimento(cfg, token, operacional, bloco, real, registrar_evento, ao_mudar=None):
    """Roda UMA vez, quando um bloco de criação de posts (com `posts_previstos`) é concluído: consulta o ClickUp e grava o que o bloco rendeu
    no registro de eventos (posts previstos x posts que apareceram). Sem Claude, sem vigia: só acontece quando a pessoa conclui o bloco."""
    try:
        r = atualizar(cfg, token, operacional)
        if not r["ok"]:
            registrar_evento("posts_criados", bloco, previstos=bloco.get("posts_previstos"), achados=None, erro=r["erro"])
            return r
        dia = time.strftime("%Y-%m-%d")
        ini = (real or {}).get("inicio") or bloco["inicio"]
        fim = (real or {}).get("fim") or time.strftime("%H:%M")
        h, m = int(ini[:2]), int(ini[3:])
        de = f"{max(0, h * 60 + m - 90) // 60:02d}:{max(0, h * 60 + m - 90) % 60:02d}"  # a criação pode ter começado antes do horário planejado
        achados = rendimento(r["maes"], dia, de, fim)
        registrar_evento("posts_criados", bloco, previstos=bloco.get("posts_previstos"), achados=len(achados),
                         nomes=[m_["nome"] for m_ in achados], prazos=[m_["prazo"] for m_ in achados], janela=f"{de}-{fim}")
        etapas = lancar_etapas(cfg, token, operacional, achados)  # troca os blocos reservados pelas subtarefas reais
        if etapas["criadas"] or etapas["posts_sem_reserva"] or etapas.get("erros"):
            registrar_evento("etapas_lancadas", bloco, **etapas)
            if ao_mudar and etapas["criadas"]:
                ao_mudar()
        return {"ok": True, "achados": achados, "etapas": etapas}
    except Exception as erro:  # nunca atrapalha o concluir
        print("  (não consegui medir o rendimento do bloco:", erro, ")")
        return {"ok": False, "erro": str(erro)}


if __name__ == "__main__":  # à mão: python posts_maes.py            (atualiza e lista)
    import sys                #       python posts_maes.py quinta     (só a mãe do dia, a partir do arquivo)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import hud_servidor as h
    if len(sys.argv) > 1:
        print(achar_mae(h.OPER, sys.argv[1]) or "não achei (ou há mais de um post nesse dia)")
    else:
        r = atualizar(h._config(), h._token_clickup(), h.OPER)
        print(("ok" if r["ok"] else "erro: " + str(r["erro"])), "|", len(r["maes"]), "posts")
        for m in r["maes"][:12]:
            print(f"  {m['prazo']} | {m['id']} | {'SEM ETAPAS' if m['sem_etapas'] else str(len(m['etapas'])) + ' etapa(s)'} | {(m['nome'] or '')[:60]}")
