# Servidor local da tela do guardião (http://localhost:8767). Só aceita pedidos da própria máquina.
# Entrega a interface (pasta hud), um fluxo de eventos ao vivo (/eventos), os dados do plano (/plano) e as ações da tela:
# aprovar o plano, concluir, adiar ou reabrir um bloco, e abrir uma tarefa do ClickUp no navegador.
# Substitui a tela antiga do plano (servidor_tela.ps1, porta 8766) e grava no mesmo registro, para o guardião ler igual.
import json
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import webbrowser
import winreg
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
HUD = os.path.join(BASE, "hud")
HUD2 = os.path.join(BASE, "hud2")  # painel novo, servido em /v2/ ao lado do atual
OPER = os.path.dirname(BASE)
PORTA = 8767

TIPOS = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".woff2": "font/woff2",
    ".svg": "image/svg+xml",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


def _v2():
    """Parte nova (modo execução, calibragem, POPs). Importada só quando usada, porque ela também importa este arquivo."""
    import guardiao_v2
    return guardiao_v2


class Barramento:
    """Leva os eventos do guardião (ouvindo, falando, texto...) para a tela e traz os comandos da tela."""

    def __init__(self):
        self.assinantes = set()
        self.trava = threading.Lock()
        self.comandos = queue.Queue()
        self.ultimos = {}
        self.portao_saudacao = threading.Event()  # a saudação só começa a falar quando a abertura da tela termina
        self.cancelar_escuta = threading.Event()  # a tela pediu para parar de ouvir (clique no microfone enquanto ouvia)
        self.ao_ficar_sem_janela = None  # função chamada quando a última janela do painel fecha (o guardiao_voz usa para parar a fala)

    def emitir(self, tipo, /, **dados):
        ev = {"t": tipo, **dados}
        if tipo in ("estado", "saude", "metricas", "revisao", "completo"):
            self.ultimos[tipo] = ev
        with self.trava:
            for q in list(self.assinantes):
                try:
                    q.put_nowait(ev)
                except queue.Full:
                    # fila cheia: descarta o evento mais antigo (quase sempre um nível de som) e guarda o novo
                    try:
                        q.get_nowait()
                        q.put_nowait(ev)
                    except (queue.Empty, queue.Full):
                        pass

    def assinar(self):
        q = queue.Queue(maxsize=600)
        with self.trava:
            self.assinantes.add(q)
        for ev in self.ultimos.values():
            q.put_nowait(ev)
        return q

    def sair(self, q):
        with self.trava:
            self.assinantes.discard(q)
            ficou_vazio = not self.assinantes
        if ficou_vazio and self.ao_ficar_sem_janela:
            try:
                self.ao_ficar_sem_janela()
            except Exception:
                pass


bus = Barramento()


def _ler_json(caminho):
    try:
        with open(caminho, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _min(hhmm):
    h, m = str(hhmm).split(":")[:2]
    return int(h) * 60 + int(m)


def _config():
    return _ler_json(os.path.join(OPER, "config.json")) or {}


# ---------------- preferências da tela e do guardião (o painel de configurações) ----------------

def pessoa():
    """Como o guardião chama a pessoa, a partir de pessoa.nome e pessoa.artigo ("o" ou "a", opcional) do config.json.
    Com artigo "o": {"o": "o Rafa", "do": "do Rafa", "ao": "ao Rafa"}. Sem artigo: "Rafa", "de Rafa", "a Rafa"."""
    p = _config().get("pessoa") or {}
    nome = str(p.get("nome") or "").strip()
    if not nome:  # sem nome configurado (não deveria acontecer depois do onboarding)
        return {"nome": "você", "primeiro": "Você", "o": "a pessoa", "do": "da pessoa", "ao": "à pessoa"}
    primeiro = nome.split()[0]
    art = str(p.get("artigo") or "").strip().lower()
    if art not in ("o", "a"):
        return {"nome": nome, "primeiro": primeiro, "o": primeiro, "do": f"de {primeiro}", "ao": f"a {primeiro}"}
    return {"nome": nome, "primeiro": primeiro, "o": f"{art} {primeiro}", "do": f"d{art} {primeiro}", "ao": f"ao {primeiro}" if art == "o" else f"à {primeiro}"}


def assinatura():
    """Assinatura dos comentários no ClickUp: agente.assinatura do config.json ou, sem ela, o nome do agente e o da pessoa."""
    agente = _config().get("agente") or {}
    return "— " + (str(agente.get("assinatura") or "").strip() or f"{agente.get('nome') or 'Guardião'} {pessoa()['do']}")


ARQ_PREFS = os.path.join(BASE, "preferencias.json")
PREFS_PADRAO = {
    "sons": True,              # chave geral dos sons
    "volume": 0.7,             # 0 a 1
    "som_digitacao": True,     # um toque por letra enquanto o texto é digitado
    "som_movimento": True,     # cartão indo e voltando, painéis, seleção, ajustes do plano, rascunho
    "som_toques": True,        # clique em botões e itens
    "som_avisos": True,        # confirmação, erro, envio e o aviso de microfone aberto
    "som_abertura": True,      # a trilha da abertura
    "mic_sempre_ligado": False,  # OPÇÃO: escuta contínua ("Ei guardião"). Desligada, o microfone só abre num clique e fecha no fim da gravação
    "escuta_aberta": True,     # o microfone reabre sozinho quando o guardião espera resposta (só vale com a escuta contínua)
    # painel novo (v2)
    "som_estados": True,       # sininhos enquanto ele pensa, ligando e desligando quando a conexão cai ou volta
    "voz_guardiao": True,      # o guardião fala em voz alta; desligado, ele só escreve (o microfone continua valendo)
    "voz_velocidade": 1.0,     # 1, 1.5 ou 2 vezes
    "execucao_ao_abrir": True,  # com o plano aprovado, as aberturas do dia vão direto para a tarefa de agora (substitui abrir_em_execucao, que nascia desligada)
    "modo_leve": False,        # menos animação, sem vidro e bolinha 2D, para computador fraco
    "sessao": False,           # a conversa vira uma sessão do Claude Code: lembra do que foi dito e usa conectores, skills e agentes
    "bolinha": "N",            # N = Núcleo 3D, A = Relógio (o instrumento clássico)
}
PREFS_OPCOES = {"bolinha": ("N", "A")}


def _pref_valida(k, v):
    padrao = PREFS_PADRAO[k]
    if isinstance(padrao, bool):
        return v if isinstance(v, bool) else None
    if k == "volume":
        return round(min(1.0, max(0.0, float(v))), 2) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    if k == "voz_velocidade":
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and float(v) in (1.0, 1.5, 2.0) else None
    if k in PREFS_OPCOES:
        return v if v in PREFS_OPCOES[k] else None
    return None


def preferencias():
    """Preferências salvas, sempre completas: o que faltar ou vier inválido volta ao padrão."""
    salvas = _ler_json(ARQ_PREFS) or {}
    saida = dict(PREFS_PADRAO)
    for k in PREFS_PADRAO:
        v = _pref_valida(k, salvas.get(k))
        if v is not None:
            saida[k] = v
    return saida


def salvar_preferencias(novas):
    """Atualiza só as chaves conhecidas e com o tipo certo (o resto é ignorado), grava e avisa as telas abertas."""
    atual = preferencias()
    for k, v in (novas or {}).items():
        if k not in PREFS_PADRAO:
            continue
        v = _pref_valida(k, v)
        if v is not None:
            atual[k] = v
    with open(ARQ_PREFS, "w", encoding="utf-8") as f:
        json.dump(atual, f, ensure_ascii=False, indent=2)
    bus.emitir("preferencias", **atual)
    return atual


def _plano_e_caminho():
    """O plano de hoje e o arquivo onde ele está (plano_do_dia.json ou planos\\plano_AAAA-MM-DD.json)."""
    hoje_txt = date.today().isoformat()
    c1 = os.path.join(OPER, "plano_do_dia.json")
    p = _ler_json(c1)
    if p and p.get("data") == hoje_txt:
        return p, c1
    c2 = os.path.join(OPER, "planos", f"plano_{hoje_txt}.json")
    p = _ler_json(c2)
    if p:
        return p, c2
    return None, None


def _plano_de_hoje():
    return _plano_e_caminho()[0]


def _registro_de_hoje():
    return _ler_json(os.path.join(OPER, "registros", f"registro_{date.today().isoformat()}.json")) or {}


def montar_plano():
    hoje = date.today()
    hoje_txt = hoje.isoformat()
    plano = _plano_de_hoje()
    registro = _registro_de_hoje()
    por_id = {b.get("id"): b for b in registro.get("blocos", [])}
    blocos = []
    try:  # painel novo: o que já foi trabalhado em cada bloco no modo execução
        trabalhado, execucao = _v2().exec_por_bloco(), _v2().estado_exec()
    except Exception:
        trabalhado, execucao = {}, None
    if plano:
        for b in plano.get("blocos", []):
            reg = por_id.get(b.get("id"), {})
            cid = b.get("clickup_id")
            blocos.append({
                "id": b.get("id"), "inicio": b.get("inicio"), "fim": b.get("fim"), "titulo": b.get("titulo"),
                "descricao": b.get("descricao"), "primeiro_passo": b.get("primeiro_passo"),
                "por_que_agora": b.get("por_que_agora"), "frente": b.get("frente"), "dono": b.get("dono"),
                "clickup_id": cid, "url": f"https://app.clickup.com/t/{cid}" if cid else None,
                "estado": reg.get("estado", "pendente"), "real": reg.get("real"),
                "vezes_adiada": reg.get("vezes_adiada", 0), "clickup": reg.get("clickup"),
                "lista_id": b.get("lista_id"), "estendido_min": b.get("estendido_min") or 0, "exec": trabalhado.get(b.get("id")),
            })
    ultimo_plano = None
    if not plano:
        anterior = _ler_json(os.path.join(OPER, "plano_do_dia.json"))
        ultimo_plano = (anterior or {}).get("data")
    futuros = []
    pasta = os.path.join(OPER, "planos")
    limite = (hoje + timedelta(days=3)).isoformat()
    if os.path.isdir(pasta):
        for nome in sorted(os.listdir(pasta)):
            m = re.match(r"plano_(\d{4}-\d{2}-\d{2})\.json$", nome)
            if not m or not (hoje_txt < m.group(1) <= limite):
                continue
            p = _ler_json(os.path.join(pasta, nome)) or {}
            futuros.append({
                "data": m.group(1), "modo_dia": p.get("modo_dia"),
                "blocos": [{"id": b.get("id"), "inicio": b.get("inicio"), "fim": b.get("fim"), "titulo": b.get("titulo"),
                            "descricao": b.get("descricao"), "primeiro_passo": b.get("primeiro_passo"), "por_que_agora": b.get("por_que_agora"),
                            "frente": b.get("frente")} for b in p.get("blocos", [])],
            })
    tarefas = []
    resumo = _ler_json(os.path.join(OPER, "resumo_clickup.json")) or {}
    for t in resumo.get("tarefas", []):
        if hoje_txt <= t.get("prazo", "") <= limite:
            tarefas.append({"id": t.get("id"), "prazo": t["prazo"], "inicio": t.get("inicio"), "nome": t.get("nome"),
                            "lista": t.get("lista"), "status": t.get("status"), "url": t.get("url")})
    p = plano or {}
    return {
        "hoje": {
            "data": hoje_txt, "status": p.get("status"), "modo_dia": p.get("modo_dia"), "aviso": p.get("aviso"),
            "gerado_em": p.get("gerado_em"), "exemplo": bool(p.get("exemplo")), "blocos": blocos,
            "fixos": [{"inicio": f.get("inicio"), "fim": f.get("fim"), "titulo": f.get("titulo")} for f in p.get("fixos", [])],
        },
        "ultimo_plano": ultimo_plano,
        "agente": (_config().get("agente") or {}).get("nome") or "Guardião",
        "futuros": futuros,
        "tarefas": tarefas[:10],
        "execucao": execucao,
        "agora": time.strftime("%H:%M"),
    }


# ---------------- ações da tela ----------------

def _token_clickup():
    nome = (_config().get("clickup") or {}).get("token_variavel") or "CLICKUP_API_TOKEN"
    valor = os.environ.get(nome)
    if valor:
        return valor
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return winreg.QueryValueEx(k, nome)[0]
    except OSError:
        return None


def _id_dono(cfg, dono):
    """Id do ClickUp de quem recebe a tarefa; sem achar o nome na equipe, é a própria pessoa."""
    clickup = cfg.get("clickup") or {}
    for m in clickup.get("membros") or []:
        if m.get("nome") and dono and m["nome"].lower() in str(dono).lower():
            return int(m["id"])
    return int(clickup["user_id"])


def _gravar_registro(plano, bloco, estado, real=None, nao_confirmado=False, status_clickup=None, adiou=False):
    """Grava no mesmo arquivo e formato da tela antiga do plano, para o guardião ler igual."""
    hoje_txt = date.today().isoformat()
    pasta = os.path.join(OPER, "registros")
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, f"registro_{hoje_txt}.json")
    registro = _ler_json(caminho) or {}
    por_id = {b.get("id"): b for b in registro.get("blocos", [])}
    for b in plano.get("blocos", []):
        if b.get("id") in por_id:
            continue
        minutos = _min(b["fim"]) - _min(b["inicio"])
        por_id[b["id"]] = {
            "id": b["id"], "titulo": b.get("titulo"), "dono": b.get("dono"), "frente": b.get("frente"),
            "clickup_id": b.get("clickup_id"), "estado": "pendente",
            "planejado": {"inicio": b["inicio"], "fim": b["fim"], "minutos": minutos},
            "real": None, "desvio_minutos": None, "clickup": None, "vezes_adiada": 0,
        }
    entrada = por_id[bloco["id"]]
    entrada["estado"] = estado
    if adiou:
        entrada["vezes_adiada"] = int(entrada.get("vezes_adiada") or 0) + 1
    if estado == "feito" and real:
        minutos_real = (_min(real["fim"]) - _min(real["inicio"])) % 1440
        entrada["real"] = {"inicio": real["inicio"], "fim": real["fim"], "minutos": minutos_real}
        entrada["desvio_minutos"] = minutos_real - entrada["planejado"]["minutos"]
        entrada["nao_confirmado"] = bool(nao_confirmado)
    else:
        entrada["real"] = None
        entrada["desvio_minutos"] = None
        entrada.pop("nao_confirmado", None)
    if status_clickup:
        entrada["clickup"] = "concluida" if estado == "feito" else "reaberta"
    registro["data"] = hoje_txt
    registro["salvo_em"] = datetime.now().astimezone().isoformat()
    registro["blocos"] = [por_id[b["id"]] for b in plano.get("blocos", []) if b["id"] in por_id]
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(registro, f, ensure_ascii=False, indent=2)
    return entrada


def texto_realizado(real, nota=""):
    """A nota que vai no ClickUp ao concluir: o horário realizado (o combinado fica nos campos da tarefa) e, se houver, o que a pessoa contou."""
    duracao = (_min(real["fim"]) - _min(real["inicio"])) % (24 * 60)
    horas, minutos = divmod(duracao, 60)
    tempo = (f"{horas} h " if horas else "") + (f"{minutos} min" if minutos or not horas else "")
    texto = f"Realizado: das {real['inicio']} às {real['fim']} ({tempo.strip()})."
    return texto + (f"\n{nota.strip()}" if (nota or "").strip() else "")


def concluir_bloco(dados):
    """Conclui (ou reabre) um bloco do plano de hoje. Com tarefa no ClickUp: comenta, assinando, e muda o status."""
    try:
        import manter_planos
        manter_planos.pedir()  # concluir pode fechar o dia: a janela dos próximos planos anda
    except Exception:
        pass
    plano = _plano_de_hoje()
    bloco = next((b for b in (plano or {}).get("blocos", []) if b.get("id") == dados.get("id")), None)
    if not bloco:
        return {"ok": False, "erro": "Esse bloco não está no plano de hoje."}
    concluido = bool(dados.get("concluido", True))
    nota = str(dados.get("nota") or "").strip()
    real = None
    if concluido:
        ini = str(dados.get("inicio") or bloco["inicio"])
        fim = str(dados.get("fim") or time.strftime("%H:%M"))
        if not (re.fullmatch(r"\d{1,2}:\d{2}", ini) and re.fullmatch(r"\d{1,2}:\d{2}", fim)):
            return {"ok": False, "erro": "Horário inválido."}
        # bloco de 23:00 concluído às 00:10 atravessou a meia-noite (o fim "menor" só vale se for bem menor, mais de 12 horas)
        if _min(fim) == _min(ini) or (_min(fim) < _min(ini) and _min(ini) - _min(fim) < 720):
            return {"ok": False, "erro": "Confira os horários: o fim precisa ser depois do começo."}
        real = {"inicio": ini, "fim": fim}
    status = None
    cid = bloco.get("clickup_id")
    if cid:
        token = _token_clickup()
        if not token:
            return {"ok": False, "erro": "Não achei o token do ClickUp neste computador."}
        cab = {"Authorization": token}
        try:
            # o horário combinado (início e prazo) da tarefa fica intacto; o realizado vai num comentário, depois de mudar o status (decisão de produto, 13/10/2026)
            tarefa = requests.get(f"https://api.clickup.com/api/v2/task/{cid}", headers=cab, timeout=20)
            tarefa.raise_for_status()
            lista = requests.get(f"https://api.clickup.com/api/v2/list/{tarefa.json()['list']['id']}", headers=cab, timeout=20)
            lista.raise_for_status()
            estados = lista.json().get("statuses", [])
            if concluido:
                alvo = next((s for s in estados if s.get("type") == "closed"), None)
            else:
                abertos = (_config().get("clickup") or {}).get("status_abertos") or []
                alvo = next((s for s in estados if abertos and s.get("status") == abertos[0]), None) or next((s for s in estados if s.get("type") == "open"), None)
            if not alvo:
                return {"ok": False, "erro": "A lista dessa tarefa não tem um status de destino."}
            r = requests.put(f"https://api.clickup.com/api/v2/task/{cid}", headers=cab, json={"status": alvo["status"]}, timeout=20)
            r.raise_for_status()
            status = alvo["status"]
        except requests.RequestException as erro:
            return {"ok": False, "erro": f"O ClickUp não aceitou: {erro}"}
        if concluido:  # o realizado vira nota; se o comentário falhar, a tarefa continua concluída
            try:
                requests.post(f"https://api.clickup.com/api/v2/task/{cid}/comment", headers=cab, timeout=20,
                              json={"comment_text": texto_realizado(real, nota) + f"\n\n{assinatura()}"}).raise_for_status()
            except requests.RequestException as erro:
                print("  (concluí no ClickUp, mas o comentário com o horário realizado não foi:", erro, ")")
    _gravar_registro(plano, bloco, "feito" if concluido else "pendente", real, bool(dados.get("nao_confirmado")), status)
    try:  # fecha a sessão do modo execução e soma o tempo real por tipo de tarefa
        _v2().ao_concluir(bloco, real, bool(dados.get("nao_confirmado")), concluido)
    except Exception as erro:
        print("  (não consegui registrar o tempo da tarefa:", erro, ")")
    if concluido and bloco.get("posts_previstos"):  # bloco de criação de posts: mede o que rendeu (posts previstos x que apareceram), uma vez
        try:
            import posts_maes
            threading.Thread(target=posts_maes.registrar_rendimento, args=(_config(), _token_clickup(), OPER, bloco, real, _v2().registrar_evento), kwargs={"ao_mudar": lambda: bus.emitir("plano")}, daemon=True).start()
        except Exception as erro:
            print("  (rendimento do bloco não rodou:", erro, ")")
    bus.emitir("plano")
    return {"ok": True, "status": status}


_ULTIMA_SINCRONIA = {}
ULTIMAS_NOVAS = []  # tarefas que apareceram no ClickUp e que o guardião ainda não anunciou


def sincronizar_com_clickup(espaco=20):
    """Reconcilia o plano de hoje com o ClickUp numa só passada: renova o resumo (tarefas novas) e fecha o bloco pendente cuja tarefa já foi concluída lá vira "feito" aqui, sem aviso de tempo e sem pergunta.
    Só confere os blocos que já começaram (quem chama decide o momento: viradas do plano), no máximo uma vez por `espaco` segundos cada. Devolve os títulos que fechou."""
    plano = _plano_de_hoje()
    if not plano or plano.get("status") != "aprovado":
        return []
    token = _token_clickup()
    if not token:
        return []
    def ids_do_resumo():
        return {t.get("id") for t in (_ler_json(os.path.join(OPER, "resumo_clickup.json")) or {}).get("tarefas", []) if t.get("id")}
    antes = ids_do_resumo()
    renovou = atualizar_resumo_clickup()  # a mesma chamada traz as tarefas novas que apareceram desde a última leitura
    abertas = ids_do_resumo() if renovou else set()
    novas = (abertas - antes) if (renovou and antes) else set()
    if novas:
        no_plano = {b.get("clickup_id") for b in plano.get("blocos", [])}
        tarefas = (_ler_json(os.path.join(OPER, "resumo_clickup.json")) or {}).get("tarefas", [])
        ULTIMAS_NOVAS.extend(t for t in tarefas if t.get("id") in novas and t.get("id") not in no_plano and not t.get("aprovar"))
    if novas:
        print(f"  ({len(novas)} tarefa(s) nova(s) no ClickUp desde a última leitura)")
        try:
            _v2().registrar_evento("tarefas_novas", None, quantidade=len(novas))
        except Exception:
            pass
    estados = {b.get("id"): b.get("estado") for b in _registro_de_hoje().get("blocos", [])}
    agora, fechados = time.time(), []
    limite = _min(time.strftime("%H:%M"))
    for b in plano.get("blocos", []):
        cid = b.get("clickup_id")
        if not cid or estados.get(b.get("id")) in ("feito", "adiado") or not _hora(b.get("inicio")) or _min(b["inicio"]) > limite:
            continue
        if cid in abertas or agora - _ULTIMA_SINCRONIA.get(cid, 0) < espaco:  # na leitura que acabou de sair = ainda aberta, sem chamada extra
            continue
        _ULTIMA_SINCRONIA[cid] = agora
        try:
            r = requests.get(f"https://api.clickup.com/api/v2/task/{cid}", headers={"Authorization": token}, timeout=10)
            r.raise_for_status()
            status = r.json().get("status") or {}
        except (requests.RequestException, ValueError):
            continue
        if status.get("type") != "closed":
            continue
        _gravar_registro(plano, b, "feito", None, True, status.get("status") or "concluída")
        try:
            _v2().ao_concluir(b, None, True, True)
            _v2().registrar_evento("conclusao_clickup", b, status=status.get("status"))
        except Exception as erro:
            print("  (não consegui fechar a sessão do bloco concluído no ClickUp:", erro, ")")
        fechados.append(b.get("titulo"))
    if fechados or novas:
        bus.emitir("plano")
    return fechados


def adiar_bloco(dados):
    """Marca o bloco como adiado e conta quantas vezes. Na terceira, o guardião vai perguntar o motivo."""
    plano = _plano_de_hoje()
    bloco = next((b for b in (plano or {}).get("blocos", []) if b.get("id") == dados.get("id")), None)
    if not bloco:
        return {"ok": False, "erro": "Esse bloco não está no plano de hoje."}
    entrada = _gravar_registro(plano, bloco, "adiado", adiou=True)
    bus.emitir("plano")
    return {"ok": True, "vezes": entrada["vezes_adiada"]}


_PALAVRAS_FRACAS = {"para", "com", "das", "dos", "uma", "que", "por", "sobre", "ate", "como", "mais", "fazer", "enviar", "preparar"}


def atualizar_resumo_clickup():
    """Confere o ClickUp ao vivo antes de criar tarefa: roda o mesmo script das leituras agendadas (ler_clickup.ps1), sem Claude e sem
    conector. Devolve True se o resumo foi regravado agora. Se falhar, o resumo antigo segue valendo e o motivo vai para o terminal."""
    script = os.path.join(OPER, "ler_clickup.ps1")
    if not os.path.exists(script):
        return False
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script], capture_output=True, timeout=90,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0:
            print("  (a leitura ao vivo do ClickUp falhou, uso o resumo antigo:", r.stderr.decode("utf-8", "replace")[:200], ")")
        else:
            _renovar_posts_se_velho()
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError) as erro:
        print("  (não consegui rodar a leitura ao vivo do ClickUp, uso o resumo antigo:", erro, ")")
        return False


POSTS_VELHO_HORAS = 3


def _renovar_posts_se_velho():
    """Carona na leitura do ClickUp: o posts_maes.json (mães dos posts e datas) só era refeito ao aprovar o plano e chegou a ficar 2 dias velho,
    e é por ele que o guardião acha "o post de quinta". Se tem mais de 3 h, é refeito em segundo plano, sem segurar quem pediu a leitura."""
    arq = os.path.join(OPER, "posts_maes.json")
    try:
        if os.path.exists(arq) and time.time() - os.path.getmtime(arq) < POSTS_VELHO_HORAS * 3600:
            return
    except OSError:
        return
    token = _token_clickup()
    if not token:
        return

    def renovar():
        try:
            import posts_maes
            posts_maes.atualizar(_config(), token, OPER)
        except Exception as erro:
            print("  (não consegui renovar as mães dos posts:", erro, ")")
    threading.Thread(target=renovar, daemon=True).start()


def _palavras_do_titulo(titulo):
    return {p[:5] for p in _norm(titulo).split() if len(p) >= 4 and p not in _PALAVRAS_FRACAS}


def _marca_do_titulo(titulo):
    """O que separa tarefas irmãs: a letra solta (carrossel A, B) e os números entre parênteses (posta qua 14)."""
    t = str(titulo or "")
    return set(re.findall(r"\b[A-Z]\b", t)) | {n for trecho in re.findall(r"\(([^)]*)\)", t) for n in re.findall(r"\d+", trecho)}


def achar_parecida(titulo, tarefas):
    """Procura no resumo uma tarefa aberta que parece ser a mesma do título. Devolve (tarefa, exata): exata = mesmo título.
    Parecida = o mesmo assunto com outras palavras: 3 palavras em comum e a mesma "marca" (a letra do carrossel, o número do dia).
    "Copy do carrossel A" e "Copy do carrossel B", ou "Copy" e "Design" do mesmo carrossel, são tarefas diferentes e não contam."""
    alvo = _palavras_do_titulo(titulo)
    marca = _marca_do_titulo(titulo)
    melhor = None
    for t in tarefas:
        if _norm(t.get("nome")).split() == _norm(titulo).split():
            return t, True
        if _marca_do_titulo(t.get("nome")) != marca:
            continue
        comuns = len(alvo & _palavras_do_titulo(t.get("nome")))
        if comuns >= 3 and (not melhor or comuns > melhor[0]):
            melhor = (comuns, t)
    return (melhor[1], False) if melhor else (None, False)


def eh_etapa_de_post(nome, etapa=None):
    """Copy, design, manychat e roteiro de um post: só existem como subtarefa da mãe. Stories, caixinha, material de aula e cronograma são tarefas próprias e ficam soltas."""
    return bool(etapa) or bool(re.match(r"\s*(\[design\]|(?:copy|design|manychat|roteiro)\b)", str(nome or ""), re.I))


def lista_conteudos_id():
    """Id da lista de conteúdos (config.clickup.posts.lista): nela toda tarefa é subtarefa de uma mãe, nunca solta."""
    c = _config().get("clickup") or {}
    nome = (c.get("posts") or {}).get("lista") or "Conteúdos"
    return next((str(l["id"]) for l in c.get("listas", []) if l.get("nome") == nome), "")


def _levar_ao_clickup(plano):
    """Leva o plano ao ClickUp: bloco movido (reagendado) muda de hora na tarefa existente; bloco novo (lista_id sem clickup_id) vira tarefa.
    Usado ao aprovar e ao ajustar um plano já aprovado (imprevisto no meio do dia): os dois caminhos fazem a mesma coisa."""
    cfg = _config()
    agente = (cfg.get("agente") or {}).get("nome") or "Guardião"
    criadas, reagendadas, erros = 0, 0, []
    if not plano.get("exemplo"):
        token = _token_clickup()
        if any(b.get("lista_id") and not b.get("clickup_id") for b in plano.get("blocos", [])):
            atualizar_resumo_clickup()  # outra pessoa ou outra automação pode ter criado a tarefa depois da última leitura agendada
        abertas = (_ler_json(os.path.join(OPER, "resumo_clickup.json")) or {}).get("tarefas", [])
        for b in plano.get("blocos", []):  # título igual ao de uma tarefa aberta: o bloco passa a usar ela (e ela muda de hora abaixo)
            if b.get("lista_id") and not b.get("clickup_id") and not b.get("post"):
                achada, exata = achar_parecida(b.get("titulo"), abertas)
                if achada and exata:
                    b["clickup_id"], b["reagendado"] = achada["id"], True
        for b in plano.get("blocos", []):
            if b.get("clickup_id") and b.get("reagendado"):  # movido na revisão: a tarefa existente muda de hora no ClickUp
                try:
                    if not token:
                        raise RuntimeError("token do ClickUp não encontrado")
                    ini = datetime.strptime(f"{plano['data']} {b['inicio']}", "%Y-%m-%d %H:%M").astimezone()
                    fim = datetime.strptime(f"{plano['data']} {b['fim']}", "%Y-%m-%d %H:%M").astimezone()
                    r = requests.put(f"https://api.clickup.com/api/v2/task/{b['clickup_id']}", headers={"Authorization": token}, timeout=30, json={
                        "start_date": int(ini.timestamp() * 1000), "start_date_time": True,
                        "due_date": int(fim.timestamp() * 1000), "due_date_time": True,
                        "time_estimate": int((fim - ini).total_seconds() * 1000)})
                    r.raise_for_status()
                    b.pop("reagendado", None)
                    reagendadas += 1
                except Exception as erro:
                    erros.append(f"{b.get('titulo')} (novo horário): {erro}")
                continue
            if b.get("post") and not b.get("pai") and not b.get("clickup_id") and b.get("lista_id"):
                # etapa de um post (copy, design...): o app acha a tarefa mãe sozinho, em Python, e a etapa vira subtarefa dela
                mae = None
                try:
                    import posts_maes
                    mae = posts_maes.achar_mae(OPER, b["post"])
                    if not mae and token:
                        posts_maes.atualizar(cfg, token, OPER)
                        mae = posts_maes.achar_mae(OPER, b["post"])
                except Exception as erro:
                    print("  (não consegui achar a tarefa mãe do post:", erro, ")")
                if mae:
                    b["pai"] = mae
                else:
                    erros.append(f"{b.get('titulo')}: não achei a tarefa mãe do post '{b['post']}' e não criei uma tarefa solta.")
                    continue
            if b.get("clickup_id") or not b.get("lista_id"):
                continue
            if lista_conteudos_id() and str(b["lista_id"]) == lista_conteudos_id() and not b.get("pai") and eh_etapa_de_post(b.get("titulo"), b.get("etapa")):
                erros.append(f"{b.get('titulo')}: etapa de post sem tarefa mãe (campo pai ou post). Não criei uma tarefa solta.")
                continue
            existente, _ = achar_parecida(b.get("titulo"), abertas)
            if existente:  # mesmo assunto com outras palavras: não cria, a pessoa decide se é a mesma
                erros.append(f"{b.get('titulo')}: não criei porque já existe uma tarefa parecida no ClickUp ({existente.get('nome')}: {existente.get('url')}). "
                             f"Se for a mesma, peça para usar ela; se for outra, peça para criar.")
                continue
            try:
                if not token:
                    raise RuntimeError("token do ClickUp não encontrado")
                ini = datetime.strptime(f"{plano['data']} {b['inicio']}", "%Y-%m-%d %H:%M").astimezone()
                fim = datetime.strptime(f"{plano['data']} {b['fim']}", "%Y-%m-%d %H:%M").astimezone()
                desc = (f"**O que é:** {b.get('descricao', '')}\n\n**Comece por:** {b.get('primeiro_passo', '')}\n\n"
                        f"**Por que agora:** {b.get('por_que_agora', '')}\n\n*Criada por {agente} ao aprovar o plano de {plano['data']}.*")
                corpo = {
                    "name": b["titulo"], "markdown_description": desc, "assignees": [_id_dono(cfg, b.get("dono"))],
                    "start_date": int(ini.timestamp() * 1000), "start_date_time": True,
                    "due_date": int(fim.timestamp() * 1000), "due_date_time": True,
                    "time_estimate": int((fim - ini).total_seconds() * 1000),
                }
                if b.get("pai"):
                    corpo["parent"] = b["pai"]
                r = requests.post(f"https://api.clickup.com/api/v2/list/{b['lista_id']}/task", headers={"Authorization": token}, json=corpo, timeout=30)
                r.raise_for_status()
                b["clickup_id"] = r.json()["id"]
                criadas += 1
            except Exception as erro:  # um bloco com problema não impede os outros
                erros.append(f"{b.get('titulo')}: {erro}")
    return criadas, reagendadas, erros


def aprovar_plano():
    """Aprova o plano de hoje. Cada bloco novo (com lista_id e sem clickup_id) vira tarefa no ClickUp, com dono, hora e estimativa."""
    plano, caminho = _plano_e_caminho()
    if not plano:
        return {"ok": False, "erro": "Não há plano para hoje."}
    if plano.get("status") == "aprovado":
        return {"ok": True, "criadas": 0, "erros": []}
    criadas, reagendadas, erros = _levar_ao_clickup(plano)
    plano["status"] = "aprovado"
    plano["aprovado_em"] = time.strftime("%Y-%m-%d %H:%M")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(plano, f, ensure_ascii=False, indent=2)
    HISTORICO_PLANO.clear()
    bus.emitir("plano")
    try:  # aprovou, entra em execução sozinho (a tarefa só começa a contar quando a pessoa clica em Iniciar)
        _v2().entrar()
    except Exception as erro:
        print("  (não consegui entrar em execução depois de aprovar:", erro, ")")
    return {"ok": True, "criadas": criadas, "reagendadas": reagendadas, "erros": erros}


def aprovar_plano_de_outro_dia(data_iso):
    """Aprova o plano de outro dia (planos/plano_AAAA-MM-DD.json) já agora: o ClickUp recebe os horários na hora, em vez de ficar com a agenda
    antiga até o dia chegar (o plano dizia uma coisa e o ClickUp outra). Não entra em execução: isso acontece quando o dia chega."""
    if data_iso == date.today().isoformat():
        return aprovar_plano()
    caminho = os.path.join(OPER, "planos", f"plano_{data_iso}.json")
    plano = _ler_json(caminho)
    if not plano:
        return {"ok": False, "erro": f"Não há plano gravado para {data_iso}."}
    if data_iso < date.today().isoformat():
        return {"ok": False, "erro": "Esse dia já passou."}
    if plano.get("status") == "aprovado":
        return {"ok": True, "criadas": 0, "reagendadas": 0, "erros": []}
    plano["data"] = data_iso
    criadas, reagendadas, erros = _levar_ao_clickup(plano)
    plano["status"] = "aprovado"
    plano["aprovado_em"] = time.strftime("%Y-%m-%d %H:%M")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(plano, f, ensure_ascii=False, indent=2)
    bus.emitir("plano")
    return {"ok": True, "criadas": criadas, "reagendadas": reagendadas, "erros": erros, "data": data_iso}


# ---------------- revisão do plano do dia (o guardião ajusta o plano junto com a pessoa) ----------------

HISTORICO_PLANO = []  # fotos do plano antes de cada ajuste, para "desfazer"
CAMPOS_TEXTO = ("titulo", "descricao", "primeiro_passo", "por_que_agora", "dono", "frente")


def _hora(txt):
    """'9:05', '09:05', '9h', '9h05' e '9' viram 'HH:MM'. Devolve None se não for uma hora de verdade."""
    m = re.fullmatch(r"\s*(\d{1,2})(?:[:h](\d{2}))?\s*h?\s*", str(txt or ""))
    if not m or int(m.group(1)) > 23 or int(m.group(2) or 0) > 59:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2) or '00'}"


def conflitos_do_plano(plano=None):
    """Blocos pendentes (e compromissos fixos) de hoje cujos horários se sobrepõem."""
    plano = plano or _plano_de_hoje() or {}
    registro = {b.get("id"): b.get("estado") for b in _registro_de_hoje().get("blocos", [])}
    itens = [(b["inicio"], b["fim"], b.get("titulo"), b.get("id")) for b in plano.get("blocos", []) if registro.get(b.get("id")) not in ("feito", "adiado")]
    itens += [(f["inicio"], f["fim"], f.get("titulo"), None) for f in plano.get("fixos", [])]
    itens = [i for i in itens if _hora(i[0]) and _hora(i[1])]
    itens.sort(key=lambda i: _min(i[0]))
    saida = []
    for i, a in enumerate(itens):
        for b in itens[i + 1:]:
            if _min(b[0]) < _min(a[1]):
                saida.append({"a": a[3], "b": b[3], "texto": f"{a[2]} ({a[0]} às {a[1]}) bate com {b[2]} ({b[0]} às {b[1]})"})
    return saida


def _log_acao(tipo, ref, titulo, texto, dados, ok, erro=None):
    try:
        pasta = os.path.join(OPER, "logs")
        os.makedirs(pasta, exist_ok=True)
        with open(os.path.join(pasta, "acoes.log"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"quando": time.strftime("%Y-%m-%d %H:%M:%S"), "tipo": tipo, "ref": ref, "titulo": titulo, "texto": texto,
                                "dados": dados or None, "ok": bool(ok), "erro": erro}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def resumo_aprovacao():
    """O que aprovar o plano de hoje vai fazer (para mostrar na tela e para o guardião falar)."""
    plano = _plano_de_hoje() or {}
    blocos = plano.get("blocos", [])
    novos = [b for b in blocos if b.get("lista_id") and not b.get("clickup_id")]
    movidos = [b for b in blocos if b.get("clickup_id") and b.get("reagendado")]
    return {"status": plano.get("status"), "blocos": len(blocos), "novos": len(novos), "reagendadas": len(movidos),
            "removidos": len(plano.get("removidos", [])), "titulos_novos": [b.get("titulo") for b in novos][:6]}


def editar_plano(op, ref=None, dados=None):
    """Ajusta o plano de hoje: mover, editar, remover, adicionar ou desfazer o último ajuste.
    Plano já aprovado também aceita ajuste (imprevisto no meio do dia: reunião de emergência, tarefa de última hora). Ele continua aprovado,
    a execução segue, e o que mudou vai ao ClickUp na hora (_levar_ao_clickup). Antes isso era recusado e o guardião se negava a replanejar."""
    dados = dados or {}
    plano, caminho = _plano_e_caminho()
    if not plano:
        return {"ok": False, "erro": "Não há plano para hoje."}
    aprovado = plano.get("status") == "aprovado"
    blocos = plano.setdefault("blocos", [])

    def achar():
        return next((b for b in blocos if b.get("id") == ref), None)

    antes = json.dumps(plano, ensure_ascii=False)
    titulo = None
    depois = None
    if op == "desfazer":
        if not HISTORICO_PLANO:
            return {"ok": False, "erro": "Não há nada para desfazer."}
        plano = json.loads(HISTORICO_PLANO.pop())
        antes = None
        titulo = "último ajuste"
    elif op == "mover":
        b = achar()
        if not b:
            return {"ok": False, "erro": "Esse bloco não está no plano de hoje."}
        m = re.fullmatch(r"\s*([\d:h]+)\s*(?:-|a|às|ate|até)?\s*([\d:h]*)\s*", str(dados.get("horario") or ""))
        ini = _hora(m.group(1)) if m else None
        fim = _hora(m.group(2)) if m and m.group(2) else None
        if not ini:
            return {"ok": False, "erro": "Horário inválido. Use o formato 14:30."}
        if not fim:  # só o começo: mantém a duração
            fim_min = _min(ini) + (_min(b["fim"]) - _min(b["inicio"]))
            fim = f"{fim_min // 60:02d}:{fim_min % 60:02d}" if fim_min < 24 * 60 else None
        if not fim or _min(fim) <= _min(ini):
            return {"ok": False, "erro": "O fim precisa ser depois do começo."}
        titulo = b.get("titulo")
        depois = f"{ini} às {fim}"
        b["inicio"], b["fim"] = ini, fim
        if b.get("clickup_id"):
            b["reagendado"] = True
    elif op == "editar":
        b = achar()
        if not b:
            return {"ok": False, "erro": "Esse bloco não está no plano de hoje."}
        mudou = False
        for k in CAMPOS_TEXTO:
            if str(dados.get(k) or "").strip():
                b[k] = str(dados[k]).strip()
                mudou = True
        if not mudou:
            return {"ok": False, "erro": "Nada para mudar."}
        titulo = b.get("titulo")
        depois = ", ".join(k for k in CAMPOS_TEXTO if str(dados.get(k) or "").strip())
    elif op == "remover":
        b = achar()
        if not b:
            return {"ok": False, "erro": "Esse bloco não está no plano de hoje."}
        blocos.remove(b)
        plano.setdefault("removidos", []).append({"id": b.get("id"), "titulo": b.get("titulo"), "clickup_id": b.get("clickup_id"), "removido_em": time.strftime("%Y-%m-%d %H:%M")})
        titulo = b.get("titulo")
        depois = "fora do plano de hoje"
    elif op == "adicionar":
        origem = str(dados.get("id") or "").strip()
        alvo = resolver_ref(origem) if origem else None
        if origem and not alvo:
            return {"ok": False, "erro": "Não achei essa tarefa para trazer para hoje."}
        if alvo and alvo.get("cid") and any(x.get("clickup_id") == alvo["cid"] for x in blocos):
            return {"ok": False, "erro": "Essa tarefa já está no plano de hoje."}
        antigo = (alvo or {}).get("bloco") or {}
        nome = str(dados.get("titulo") or (alvo or {}).get("titulo") or "").strip()
        ini, fim = _hora(dados.get("inicio")), _hora(dados.get("fim"))
        if not nome or not ini or not fim:
            return {"ok": False, "erro": "Para incluir um bloco preciso de título, começo e fim (por exemplo, 14:00 e 14:30)."}
        if _min(fim) <= _min(ini):
            return {"ok": False, "erro": "O fim precisa ser depois do começo."}
        numeros = [int(x["id"][1:]) for x in blocos if re.fullmatch(r"b\d+", str(x.get("id")))]
        novo_id = f"b{(max(numeros) if numeros else 0) + 1}"
        lista = resolver_lista(dados.get("lista"))
        novo = {
            "id": novo_id, "inicio": ini, "fim": fim, "titulo": nome,
            "dono": str(dados.get("dono") or "").strip() or next((x["dono"] for x in blocos if x.get("dono")), pessoa()["nome"]),
            "frente": str(dados.get("frente") or "").strip() or antigo.get("frente") or ((alvo or {}).get("tarefa") or {}).get("lista") or "Guardião",
            "descricao": str(dados.get("descricao") or "").strip() or antigo.get("descricao")
                         or ("Tarefa que estava atrasada e você trouxe para hoje." if alvo else "Bloco incluído por você na revisão do plano."),
            "primeiro_passo": str(dados.get("primeiro_passo") or "").strip() or antigo.get("primeiro_passo") or "Comece pelo que você já sabe que precisa ser feito.",
            "por_que_agora": str(dados.get("por_que_agora") or "").strip() or ("Estava atrasada e você decidiu resolver hoje." if alvo else "Você pediu para incluir este bloco hoje."),
        }
        if alvo and alvo.get("cid"):  # a tarefa já existe no ClickUp: nada de duplicar; ela muda de data quando o plano for aprovado
            novo["clickup_id"] = alvo["cid"]
            novo["reagendado"] = True
        elif antigo.get("lista_id"):
            novo["lista_id"] = antigo["lista_id"]
        elif lista:
            novo["lista_id"] = lista["id"]
        blocos.append(novo)
        blocos.sort(key=lambda x: _min(x["inicio"]))
        ref, titulo, depois = novo_id, nome, f"{ini} às {fim}"
    else:
        return {"ok": False, "erro": f"Ajuste desconhecido: {op}"}

    if antes:
        HISTORICO_PLANO.append(antes)
        del HISTORICO_PLANO[:-12]
    erros_clickup = []
    if aprovado and plano.get("status") == "aprovado":
        _, _, erros_clickup = _levar_ao_clickup(plano)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(plano, f, ensure_ascii=False, indent=2)
    conflitos = [c["texto"] for c in conflitos_do_plano(plano) if ref in (c["a"], c["b"])] if op in ("mover", "adicionar") else []
    bus.emitir("plano_editado", op=op, ref=ref, titulo=titulo, depois=depois, conflitos=conflitos)
    bus.emitir("plano")
    _log_acao("plano:" + op, ref, titulo, depois, dados, True)
    return {"ok": True, "ref": ref, "titulo": titulo, "depois": depois, "conflitos": conflitos, **({"erros_clickup": erros_clickup} if erros_clickup else {})}


# ---------------- ações pedidas pelo guardião (com animação na tela) ----------------



def _norm(s):
    s = str(s or "").lower()
    for a, b in (("áàãâä", "a"), ("éèêë", "e"), ("íìîï", "i"), ("óòõôö", "o"), ("úùûü", "u"), ("ç", "c")):
        for ch in a:
            s = s.replace(ch, b)
    return re.sub(r"[^a-z0-9 ]+", " ", s)


def _plano_do_dia_data(data):
    """Plano de uma data: o de hoje (pode estar em plano_do_dia.json) ou o guardado em planos\\."""
    p = _ler_json(os.path.join(OPER, "plano_do_dia.json"))
    if p and p.get("data") == data:
        return p
    return _ler_json(os.path.join(OPER, "planos", f"plano_{data}.json"))


def resolver_ref(ref):
    """Traduz o que o guardião cita (b2, AAAA-MM-DD:b1, cu:ID) para a tarefa de verdade. None se não existir."""
    ref = str(ref or "").strip()
    if re.fullmatch(r"[\w-]+", ref):  # o id do bloco pode ser b1, b2... ou um nome (pensar, copy_a): vale o que existe no plano de hoje
        plano = _plano_de_hoje() or {}
        b = next((x for x in plano.get("blocos", []) if x.get("id") == ref), None)
        if b:
            return {"ref": ref, "tipo": "bloco", "bloco": b, "cid": b.get("clickup_id"), "titulo": b.get("titulo")}
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2}):([\w-]+)", ref)
    if m:
        plano = _plano_do_dia_data(m.group(1)) or {}
        b = next((x for x in plano.get("blocos", []) if x.get("id") == m.group(2)), None)
        if b:
            return {"ref": ref, "tipo": "bloco_futuro", "bloco": b, "cid": b.get("clickup_id"), "titulo": b.get("titulo")}
    m = re.fullmatch(r"cu:([\w-]+)", ref)
    if m:
        resumo = _ler_json(os.path.join(OPER, "resumo_clickup.json")) or {}
        t = next((x for x in resumo.get("tarefas", []) if x.get("id") == m.group(1)), None)
        if t:
            return {"ref": ref, "tipo": "clickup", "cid": t["id"], "titulo": t.get("nome"), "tarefa": t}
    return None


def refs_conhecidas():
    """Texto com os ids que o guardião pode citar (vai no prompt dele)."""
    linhas = []
    hoje = date.today().isoformat()
    plano = _plano_de_hoje() or {}
    reg = {b.get("id"): b.get("estado") for b in _registro_de_hoje().get("blocos", [])}
    for b in plano.get("blocos", []):
        linhas.append(f"{b['id']} | hoje {b['inicio']}-{b['fim']} | {b.get('titulo')} | {reg.get(b['id'], 'pendente')}")
    pasta = os.path.join(OPER, "planos")
    limite = (date.today() + timedelta(days=3)).isoformat()
    if os.path.isdir(pasta):
        for nome in sorted(os.listdir(pasta)):
            m = re.match(r"plano_(\d{4}-\d{2}-\d{2})\.json$", nome)
            if m and hoje < m.group(1) <= limite:
                for b in (_ler_json(os.path.join(pasta, nome)) or {}).get("blocos", []):
                    linhas.append(f"{m.group(1)}:{b['id']} | {m.group(1)} {b.get('inicio')}-{b.get('fim')} | {b.get('titulo')}")
    resumo = _ler_json(os.path.join(OPER, "resumo_clickup.json")) or {}
    for t in resumo.get("tarefas", []):
        if hoje <= t.get("prazo", "") <= limite:
            linhas.append(f"cu:{t['id']} | prazo {t['prazo']} {t.get('inicio') or ''} | {t.get('nome')} | {t.get('lista', '')}")
    return "\n".join(linhas[:40])


def pendencias(limite=20):
    """O que ficou para trás: tarefas do ClickUp com o prazo vencido e blocos dos últimos dias que não foram concluídos.
    As mais recentes primeiro. Tudo local (resumo_clickup.json, planos e registros): não chama o ClickUp."""
    hoje = date.today()
    plano = _plano_de_hoje() or {}
    no_plano = {b.get("clickup_id") for b in plano.get("blocos", []) if b.get("clickup_id")}
    itens, vistos = [], set()
    resumo = _ler_json(os.path.join(OPER, "resumo_clickup.json")) or {}
    for t in resumo.get("tarefas", []):
        prazo = str(t.get("prazo") or "")
        try:
            dias = (hoje - date.fromisoformat(prazo)).days
        except ValueError:
            continue
        if dias <= 0:
            continue
        vistos.add(t.get("id"))
        itens.append({"ref": f"cu:{t.get('id')}", "titulo": t.get("nome"), "prazo": prazo, "dias": dias, "lista": t.get("lista") or "",
                      "no_plano": t.get("id") in no_plano, "url": t.get("url") or ""})
    for n in range(1, 5):  # blocos sem tarefa no ClickUp que ficaram sem concluir nos últimos 4 dias
        dia = (hoje - timedelta(days=n)).isoformat()
        antigo = _ler_json(os.path.join(OPER, "planos", f"plano_{dia}.json"))
        if not antigo:
            continue
        estados = {b.get("id"): b.get("estado") for b in (_ler_json(os.path.join(OPER, "registros", f"registro_{dia}.json")) or {}).get("blocos", [])}
        for b in antigo.get("blocos", []):
            if estados.get(b.get("id")) == "feito" or b.get("clickup_id"):  # com tarefa no ClickUp, quem diz se está atrasada é o resumo
                continue
            itens.append({"ref": f"{dia}:{b.get('id')}", "titulo": b.get("titulo"), "prazo": dia, "dias": n, "lista": b.get("frente") or "", "no_plano": False, "url": ""})
    itens.sort(key=lambda i: i["dias"])
    return itens[:limite]


def pendencias_texto():
    """As pendências em texto, para o guardião da voz (vai no contexto só quando a conversa toca no assunto)."""
    itens = pendencias()
    if not itens:
        return "TAREFAS ATRASADAS OU NÃO CONCLUÍDAS: nenhuma. Não há tarefa com prazo vencido no resumo do ClickUp nem bloco sem concluir nos últimos dias."
    linhas = []
    for i in itens:
        d = date.fromisoformat(i["prazo"])
        quando = f"{DIAS_SEMANA[d.weekday()]} {d.day:02d}/{d.month:02d}, há {i['dias']} dia{'s' if i['dias'] != 1 else ''}"
        linhas.append(f"{i['ref']} | venceu {quando} | {i['titulo']} | {i['lista']}" + (" | JÁ ESTÁ NO PLANO DE HOJE" if i["no_plano"] else ""))
    resumo = _ler_json(os.path.join(OPER, "resumo_clickup.json")) or {}
    return (f"TAREFAS ATRASADAS OU NÃO CONCLUÍDAS ({len(itens)}; id | quando venceu | título | lista; resumo do ClickUp lido em {resumo.get('gerado_em') or '?'}):\n"
            + "\n".join(linhas))


def resolver_lista(nome):
    """Escolhe a lista do ClickUp pelo nome que o guardião falou. Sem achar, usa a primeira lista do config.json."""
    listas = (_config().get("clickup") or {}).get("listas") or []
    alvo = _norm(nome).strip()
    if alvo:
        for l in listas:
            if alvo in _norm(l["nome"]) or _norm(l["nome"]) in alvo:
                return l
        palavras = set(alvo.split())
        melhor = max(listas, key=lambda l: len(palavras & set(_norm(l["nome"] + " " + l.get("quando_usar", "")).split())), default=None)
        if melhor and palavras & set(_norm(melhor["nome"] + " " + melhor.get("quando_usar", "")).split()):
            return melhor
    return next((l for l in listas if "rotineiras" in _norm(l["nome"])), listas[0] if listas else None)


# ---------------- detalhes de uma tarefa (o mesmo que a tela mostra ao clicar, mais o que vem do ClickUp) ----------------

DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
MESES_NOME = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
PRIORIDADES = {"urgent": "urgente", "high": "alta", "normal": "normal", "low": "baixa"}
_CACHE_TAREFA = {}


def _quando(dt, com_hora):
    """'hoje, 17:15', 'amanhã', 'sábado, 12 de outubro, 09:00'."""
    d = dt.date()
    hoje = date.today()
    if d == hoje:
        base = "hoje"
    elif d == hoje + timedelta(days=1):
        base = "amanhã"
    elif d == hoje - timedelta(days=1):
        base = "ontem"
    else:
        base = f"{DIAS_SEMANA[d.weekday()]}, {d.day} de {MESES_NOME[d.month - 1]}"
    return base + (f", {dt:%H:%M}" if com_hora else "")


def _clickup_tarefa(cid):
    """Dados atuais da tarefa no ClickUp (guardados por 60 s, para não repetir a chamada a cada clique)."""
    agora = time.time()
    guardado = _CACHE_TAREFA.get(cid)
    if guardado and agora - guardado[0] < 60:
        return guardado[1]
    token = _token_clickup()
    if not token:
        return None
    try:
        r = requests.get(f"https://api.clickup.com/api/v2/task/{cid}", params={"include_subtasks": "true"}, headers={"Authorization": token}, timeout=8)
        r.raise_for_status()
        dados = r.json()
    except (requests.RequestException, ValueError):
        return None
    _CACHE_TAREFA[cid] = (agora, dados)
    return dados


def _nome_da_lista(lista_id):
    for l in (_config().get("clickup") or {}).get("listas") or []:
        if str(l.get("id")) == str(lista_id):
            return l.get("nome")
    return None


def detalhes_extra(ref):
    """Linhas a mais para o cartão e para a gaveta: vencimento, situação no ClickUp, responsável, subtarefas, descrição."""
    info = resolver_ref(ref)
    if not info:
        return {"ok": False, "erro": "Não achei essa tarefa."}
    linhas = []
    b = info.get("bloco")
    cid = info.get("cid")
    cu = _clickup_tarefa(cid) if cid else None
    venc = None
    if cu and cu.get("due_date"):
        try:
            venc = _quando(datetime.fromtimestamp(int(cu["due_date"]) / 1000).astimezone(), bool(cu.get("due_date_time")))
        except (ValueError, OSError):
            venc = None
    if not venc and b:
        if info["tipo"] == "bloco":
            venc = f"hoje, {b.get('fim')}"
        else:
            dia = datetime.strptime(str(ref).split(":")[0], "%Y-%m-%d")
            venc = _quando(dia, False) + f", {b.get('fim')}"
    if not venc and info["tipo"] == "clickup":
        t = info["tarefa"]
        try:
            venc = _quando(datetime.strptime(t["prazo"], "%Y-%m-%d"), False) + (f", {t['fim']}" if t.get("fim") else "")
        except (KeyError, ValueError):
            venc = None
    if venc:
        linhas.append(["Vencimento", venc])
    if cu:
        st = (cu.get("status") or {}).get("status")
        lista = (cu.get("list") or {}).get("name")
        if st or lista:
            linhas.append(["No ClickUp", " · ".join(x for x in (st, lista) if x)])
        nomes = [a.get("username") for a in (cu.get("assignees") or []) if a.get("username")]
        if nomes:
            linhas.append(["Responsável", ", ".join(nomes)])
        prio = (cu.get("priority") or {}).get("priority")
        if prio:
            linhas.append(["Prioridade", PRIORIDADES.get(prio, prio)])
        subs = cu.get("subtasks") or []
        if subs:
            feitas = sum(1 for x in subs if (x.get("status") or {}).get("type") == "closed")
            linhas.append(["Subtarefas", f"{feitas} de {len(subs)} concluídas"])
        etiquetas = [t.get("name") for t in (cu.get("tags") or []) if t.get("name")]
        if etiquetas:
            linhas.append(["Etiquetas", ", ".join(etiquetas)])
        texto = re.sub(r"\s+", " ", str(cu.get("text_content") or cu.get("description") or "")).strip()
        if texto:
            linhas.append(["Descrição no ClickUp", texto[:260] + ("…" if len(texto) > 260 else "")])
    elif info["tipo"] == "clickup":
        t = info["tarefa"]
        if t.get("status") or t.get("lista"):
            linhas.append(["No ClickUp", " · ".join(x for x in (t.get("status"), t.get("lista")) if x)])
    elif b and b.get("lista_id") and not b.get("clickup_id"):
        nome = _nome_da_lista(b["lista_id"]) or "do ClickUp"
        linhas.append(["No ClickUp", f"Será criada na lista {nome} quando o plano for aprovado"])
    return {"ok": True, "ref": ref, "linhas": linhas, "url": (cu or {}).get("url") or (info.get("tarefa") or {}).get("url")}


def clickup_comentar(cid, texto):
    token = _token_clickup()
    if not token:
        raise RuntimeError("Não achei o token do ClickUp neste computador.")
    r = requests.post(f"https://api.clickup.com/api/v2/task/{cid}/comment", headers={"Authorization": token}, timeout=20,
                      json={"comment_text": f"{texto}\n\n{assinatura()}"})
    r.raise_for_status()


def clickup_mudar_status(cid, concluido):
    token = _token_clickup()
    if not token:
        raise RuntimeError("Não achei o token do ClickUp neste computador.")
    cab = {"Authorization": token}
    tarefa = requests.get(f"https://api.clickup.com/api/v2/task/{cid}", headers=cab, timeout=20)
    tarefa.raise_for_status()
    lista = requests.get(f"https://api.clickup.com/api/v2/list/{tarefa.json()['list']['id']}", headers=cab, timeout=20)
    lista.raise_for_status()
    estados = lista.json().get("statuses", [])
    if concluido:
        alvo = next((s for s in estados if s.get("type") == "closed"), None)
    else:
        abertos = (_config().get("clickup") or {}).get("status_abertos") or []
        alvo = next((s for s in estados if abertos and s.get("status") == abertos[0]), None) or next((s for s in estados if s.get("type") == "open"), None)
    if not alvo:
        raise RuntimeError("A lista dessa tarefa não tem um status de destino.")
    requests.put(f"https://api.clickup.com/api/v2/task/{cid}", headers=cab, json={"status": alvo["status"]}, timeout=20).raise_for_status()
    return alvo["status"]


def criar_tarefa(dados):
    """Cria uma tarefa no ClickUp. Só é chamada depois do sim da pessoa."""
    titulo = str(dados.get("titulo") or "").strip()
    if not titulo:
        return {"ok": False, "erro": "A tarefa precisa de um título."}
    token = _token_clickup()
    if not token:
        return {"ok": False, "erro": "Não achei o token do ClickUp neste computador."}
    cfg = _config()
    lista = resolver_lista(dados.get("lista"))
    if not lista:
        return {"ok": False, "erro": "Não achei nenhuma lista do ClickUp na configuração."}
    if not dados.get("forcar"):  # confere o ClickUp ao vivo: alguém pode ter criado a mesma tarefa minutos atrás
        atualizar_resumo_clickup()
        achada, _ = achar_parecida(titulo, (_ler_json(os.path.join(OPER, "resumo_clickup.json")) or {}).get("tarefas", []))
        if achada:
            return {"ok": False, "erro": f"Já existe uma tarefa parecida no ClickUp: {achada.get('nome')} ({achada.get('url')}). Não criei outra. "
                                         f"Se for a mesma, use ela; se for outra, peça para criar mesmo assim."}
    corpo = {
        "name": titulo,
        "markdown_description": f"{str(dados.get('descricao') or '').strip()}\n\n*Criada pelo Guardião a pedido {pessoa()['do']}.*".strip(),
        "assignees": [_id_dono(cfg, dados.get("dono"))],
    }
    prazo = str(dados.get("prazo") or "").strip()
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(?: (\d{1,2}:\d{2}))?", prazo)
    if m:
        dt = datetime.strptime(f"{m.group(1)} {m.group(2) or '12:00'}", "%Y-%m-%d %H:%M").astimezone()
        corpo["due_date"] = int(dt.timestamp() * 1000)
        corpo["due_date_time"] = bool(m.group(2))
    try:
        r = requests.post(f"https://api.clickup.com/api/v2/list/{lista['id']}/task", headers={"Authorization": token}, json=corpo, timeout=30)
        r.raise_for_status()
        nova = r.json()
    except requests.RequestException as erro:
        return {"ok": False, "erro": f"O ClickUp não aceitou: {erro}"}
    return {"ok": True, "id": nova.get("id"), "url": nova.get("url") or f"https://app.clickup.com/t/{nova.get('id')}", "lista": lista["nome"]}


def _digitando(texto, base=0.9, cps=42.0):
    """Tempo que a tela leva para 'digitar' um texto. A tela usa a mesma conta, para o envio sair junto com a animação."""
    return base + len(texto or "") / cps


def agir(tipo, ref=None, texto=None, dados=None):
    """Executa o que o guardião pediu (concluir, reabrir, comentar ou criar) e conta à tela, passo a passo, para ela animar."""
    dados = dados or {}
    info = resolver_ref(ref) if ref else None
    if tipo not in ("criar", "aprovar") and not info:
        return {"ok": False, "erro": "Não achei essa tarefa."}
    titulo = (info or {}).get("titulo") or dados.get("titulo")
    outro_dia = tipo == "aprovar" and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(ref or ""))) and ref != date.today().isoformat()
    if tipo == "aprovar":
        titulo, dados = (f"Plano de {ref}", {}) if outro_dia else ("Plano de hoje", resumo_aprovacao())
    bus.emitir("acao", tipo=tipo, ref=ref, titulo=titulo, texto=texto, dados=dados if tipo in ("criar", "aprovar") else None)
    if bus.assinantes:  # a animação digita o texto antes de enviar; sem tela aberta não há o que esperar
        # criar: o rascunho já foi "digitado" quando foi proposto; falta só o clique de enviar
        time.sleep(1.2 if tipo == "aprovar" else 1.0 if tipo == "criar" else _digitando(texto, 1.1 if tipo != "reabrir" else 0.9))
    try:
        if tipo == "aprovar":
            r = aprovar_plano_de_outro_dia(ref) if outro_dia else aprovar_plano()
        elif tipo == "criar":
            r = criar_tarefa(dados)
        elif tipo in ("concluir", "reabrir"):
            concluir = tipo == "concluir"
            if info["tipo"] == "bloco" and info["bloco"]:
                r = concluir_bloco({"id": ref, "concluido": concluir, "nota": texto, "nao_confirmado": True,
                                    "inicio": info["bloco"].get("inicio"), "fim": time.strftime("%H:%M")})
            else:
                if not info.get("cid"):
                    r = {"ok": False, "erro": "Essa tarefa não existe no ClickUp."}
                else:
                    r = {"ok": True, "status": clickup_mudar_status(info["cid"], concluir)}  # sem comentário de status: o ClickUp já registra quando fechou
        elif tipo == "comentar":
            if not info.get("cid"):
                r = {"ok": False, "erro": "Essa tarefa não existe no ClickUp."}
            elif not (texto or "").strip():
                r = {"ok": False, "erro": "Falta o texto da anotação."}
            else:
                clickup_comentar(info["cid"], f"Anotação: {texto.strip()}")
                r = {"ok": True}
        else:
            r = {"ok": False, "erro": f"Ação desconhecida: {tipo}"}
    except (requests.RequestException, RuntimeError, ValueError) as erro:
        r = {"ok": False, "erro": str(erro)}
    bus.emitir("acao_fim", tipo=tipo, ref=ref, titulo=titulo, ok=bool(r.get("ok")), erro=r.get("erro"), url=r.get("url"), lista=r.get("lista"),
               criadas=r.get("criadas"), reagendadas=r.get("reagendadas"), erros=r.get("erros"))
    if r.get("ok"):
        bus.emitir("plano")
    try:  # trilha de tudo que o guardião fez por conta própria
        pasta = os.path.join(OPER, "logs")
        os.makedirs(pasta, exist_ok=True)
        with open(os.path.join(pasta, "acoes.log"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"quando": time.strftime("%Y-%m-%d %H:%M:%S"), "tipo": tipo, "ref": ref, "titulo": titulo, "texto": texto,
                                "dados": dados or None, "ok": bool(r.get("ok")), "erro": r.get("erro")}, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return r


def abrir_no_navegador(url):
    """Abre uma tarefa do ClickUp no navegador padrão. Só aceita endereços do próprio ClickUp."""
    if not isinstance(url, str) or not re.fullmatch(r"https://app\.clickup\.com/[\w\-./?=&%#]+", url):
        return False
    webbrowser.open(url)
    return True


COMANDO_POPUP = None  # os testes trocam por uma função (dados) que só anota


def mostrar_popup(dados):
    """Abre o aviso próprio do guardião (popup.py, preto e dourado, sem roubar o foco) e não espera ele fechar.
    Usado quando o painel está escondido e precisa avisar algo (o aviso de tempo do modo execução)."""
    d = {k: str((dados or {}).get(k) or "")[:300] for k in ("titulo", "texto", "kicker", "tag", "bloco")}
    if not d["titulo"]:
        return False
    if COMANDO_POPUP:
        return COMANDO_POPUP(d)
    import sys
    import tempfile
    exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = exe if os.path.exists(exe) else sys.executable
    arq = os.path.join(tempfile.gettempdir(), f"guardiao_aviso_{os.getpid()}_{int(time.time() * 1000)}.json")
    with open(arq, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    try:
        subprocess.Popen([exe, os.path.join(BASE, "popup.py"), "--json", arq], cwd=BASE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError:
        return False
    return True


class Pedido(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # silencioso
        pass

    def _host_ok(self):
        return self.headers.get("Host") in (f"localhost:{PORTA}", f"127.0.0.1:{PORTA}")

    def _responder(self, codigo, tipo, corpo):
        dados = corpo if isinstance(corpo, bytes) else corpo.encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(dados)

    def _json(self, codigo, obj):
        self._responder(codigo, "application/json; charset=utf-8", json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        if not self._host_ok():
            return self._responder(403, "text/plain", "proibido")
        caminho = self.path.split("?", 1)[0]
        if caminho == "/eventos":
            return self._eventos()
        if caminho == "/plano":
            return self._json(200, montar_plano())
        if caminho == "/preferencias":
            return self._json(200, preferencias())
        if caminho == "/detalhe":
            ref = (parse_qs(urlparse(self.path).query).get("ref") or [""])[0]
            return self._json(200, detalhes_extra(ref))
        if caminho == "/versao":  # versão instalada e aviso de versão nova (olha o repositório uma vez por dia)
            import guardiao_atualizacao
            return self._json(200, guardiao_atualizacao.ao_abrir())
        if caminho == "/pendencias":
            return self._json(200, {"itens": pendencias()})
        if caminho == "/conversas":  # modo sessão: a conversa atual e as anteriores
            import guardiao_sessao
            return self._json(200, dict(guardiao_sessao.resumo(), modo=bool(preferencias().get("sessao"))))
        if caminho == "/conversas/mensagens":  # o que foi dito numa conversa, para reabri-la na tela
            import guardiao_sessao
            cid = (parse_qs(urlparse(self.path).query).get("id") or [""])[0]
            return self._json(200, {"id": cid, "mensagens": guardiao_sessao.mensagens(cid)})
        if caminho in ("/sessao", "/calibragem", "/pops", "/execucao"):  # painel novo
            return self._json(200, _v2().rota_get(caminho, parse_qs(urlparse(self.path).query)))
        raiz = HUD
        if caminho == "/v2":  # sem a barra no fim os arquivos da pasta não seriam achados
            self.send_response(302)
            self.send_header("Location", "/v2/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if caminho.startswith("/v2/"):
            raiz, caminho = HUD2, caminho[3:]
        elif caminho == "/" and not os.path.isdir(HUD):  # instalação só com o painel novo: a raiz leva a ele
            self.send_response(302)
            self.send_header("Location", "/v2/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if caminho == "/":
            caminho = "/index.html"
        alvo = os.path.normpath(os.path.join(raiz, caminho.lstrip("/")))
        if not alvo.startswith(raiz + os.sep) or not os.path.isfile(alvo):
            return self._responder(404, "text/plain", "nao encontrado")
        tipo = TIPOS.get(os.path.splitext(alvo)[1].lower(), "application/octet-stream")
        with open(alvo, "rb") as f:
            self._responder(200, tipo, f.read())

    def do_POST(self):
        if not self._host_ok():
            return self._responder(403, "text/plain", "proibido")
        origem = self.headers.get("Origin")
        if origem and origem not in (f"http://localhost:{PORTA}", f"http://127.0.0.1:{PORTA}"):
            return self._responder(403, "text/plain", "proibido")
        tamanho = int(self.headers.get("Content-Length") or 0)
        if tamanho > 20000:
            return self._responder(413, "text/plain", "grande demais")
        corpo = self.rfile.read(tamanho) if tamanho else b""
        try:
            dados = json.loads(corpo.decode("utf-8")) if corpo else {}
        except ValueError:
            return self._responder(400, "text/plain", "json invalido")
        caminho = self.path.split("?", 1)[0]
        if caminho == "/perguntar":
            texto = str(dados.get("texto", "")).strip()
            if not texto:
                return self._responder(400, "text/plain", "texto vazio")
            bus.comandos.put(("perguntar", texto))
            return self._json(202, {"ok": True})
        if caminho == "/acionar":
            bus.comandos.put(("acionar", None))
            return self._json(202, {"ok": True})
        if caminho == "/escuta":  # cancelar a escuta em andamento (o Esc do teclado é lido direto pelo programa de voz)
            bus.cancelar_escuta.set()
            return self._json(202, {"ok": True})
        if caminho == "/preferencias":
            return self._json(200, salvar_preferencias(dados))
        if caminho == "/saudacao":  # a tela pede a abertura do dia (fase 'preparar', no começo da animação) e libera a fala (fase 'liberar', no fim dela)
            fase = str(dados.get("fase") or "preparar")
            if fase == "liberar":
                bus.portao_saudacao.set()
            else:
                bus.portao_saudacao.clear()
                bus.comandos.put(("abertura", {"primeira": bool(dados.get("primeira"))}))
            return self._json(202, {"ok": True})
        if caminho == "/popup":  # o painel escondido pede um aviso na tela, no visual do guardião
            return self._json(202, {"ok": mostrar_popup(dados)})
        if caminho == "/esc":  # Esc no painel: tira uma camada por vez (leitura do plano, voz, resposta, trabalho em segundo plano)
            import controle_fala
            return self._json(200, {"ok": True, "camada": controle_fala.esc()})
        if caminho == "/concluir":
            return self._json(200, concluir_bloco(dados))
        if caminho == "/adiar":
            if "motivo" in dados:  # painel novo: o porquê do adiamento vai para a calibragem
                return self._json(200, _v2().adiar_com_motivo(dados.get("id"), str(dados.get("motivo") or "").strip()[:200] or None))
            return self._json(200, adiar_bloco(dados))
        if caminho in ("/execucao", "/roteiro", "/ditar") or caminho.startswith(("/calibragem/", "/pops/")):  # painel novo
            resposta = _v2().rota_post(caminho, dados)
            if resposta is None:
                return self._responder(404, "text/plain", "nao encontrado")
            return self._json(200, resposta)
        if caminho == "/janela":  # janela compacta: por cima das outras, no canto da tela
            import guardiao_janela
            return self._json(200, guardiao_janela.rota(dados))
        if caminho.startswith("/versao/"):
            import guardiao_atualizacao
            resposta = guardiao_atualizacao.rota_post(caminho)
            if resposta is None:
                return self._responder(404, "text/plain", "nao encontrado")
            return self._json(200, resposta)
        if caminho == "/conversas":  # conversa nova ou volta a uma anterior: o programa de voz troca quando estiver livre
            acao = "abrir" if dados.get("acao") == "abrir" else "nova"
            bus.comandos.put(("conversa", {"acao": acao, "id": str(dados.get("id") or "")[:64]}))
            return self._json(202, {"ok": True})
        if caminho == "/permissao":  # resposta ao pedido de permissão pelos botões do cartão; a escuta em andamento para na hora
            decisao = str(dados.get("decisao") or "")
            if decisao not in ("sim", "sempre", "nao"):
                return self._responder(400, "text/plain", "decisao invalida")
            bus.comandos.put(("permissao", decisao))
            bus.cancelar_escuta.set()
            return self._json(202, {"ok": True})
        if caminho == "/completo":  # pedido que precisa do guardião completo (a skill inteira), feito pela tela
            pedido = str(dados.get("pedido", "")).strip()[:600]
            if not pedido:
                return self._responder(400, "text/plain", "pedido vazio")
            bus.comandos.put(("completo", pedido))
            return self._json(202, {"ok": True})
        if caminho == "/aprovar":
            return self._json(200, aprovar_plano())
        if caminho == "/abrir":
            ok = abrir_no_navegador(dados.get("url"))
            return self._json(200 if ok else 400, {"ok": ok})
        self._responder(404, "text/plain", "nao encontrado")

    def _eventos(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = bus.assinar()
        try:
            self.wfile.write(b"retry: 1500\n\n")
            self.wfile.flush()
            while True:
                try:
                    ev = q.get(timeout=15)
                    self.wfile.write(("data: " + json.dumps(ev, ensure_ascii=False) + "\n\n").encode("utf-8"))
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            bus.sair(q)


class ServidorExclusivo(ThreadingHTTPServer):
    """O servidor do painel, dono único da porta. O padrão do Python liga SO_REUSEADDR, e no Windows isso deixa um segundo programa ocupar a
    mesma porta sem erro nenhum (caso real de 15/10/2026: dois guardiões ligados juntos no logon, o painel ouvindo um e o Esc e o texto
    digitado indo para o outro). Com SO_EXCLUSIVEADDRUSE o segundo recebe erro ao ligar e desiste."""
    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return  # o painel fechou ou recarregou no meio de uma resposta: é normal, e o registro só serviria para esconder os erros de verdade
        super().handle_error(request, client_address)


def iniciar_servidor(porta=PORTA):
    """Sobe a tela numa thread. Devolve o servidor (ou None se a porta já estiver em uso)."""
    global PORTA
    PORTA = porta
    try:
        servidor = ServidorExclusivo(("127.0.0.1", porta), Pedido)
    except OSError:
        return None
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        _v2().ligar_vigia()  # avisos de tempo do modo execução
    except Exception as erro:
        print("  (o acompanhamento do modo execução não ligou:", erro, ")")
    return servidor
