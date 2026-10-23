# Tutorial guiado do primeiro acesso: o texto dos passos (tutorial.json, que vai no pacote e se edita sem mexer no painel), o estado da pessoa
# (tutorial_estado.json na pasta operacional, fora do pacote) e as dicas de uma frase que aparecem uma vez, na hora em que a pessoa encontra o recurso.
# Nada aqui chama o Claude: o tour é todo por código e funciona sem internet.
#
# Quem recebe o convite automático: só instalação nova. O configurar.ps1 cria o arquivo de estado com "convidar": true ao fim do onboarding.
# Quem já usava o guardião não tem o arquivo: vê só o botão "Rever o tutorial" nas Preferências.
import json
import os
import threading
import time

BASE = os.path.dirname(os.path.abspath(__file__))
ARQ_TEXTO = os.path.join(BASE, "tutorial.json")
NOME_ESTADO = "tutorial_estado.json"
MAX_CONVITES = 3  # o convite aparece até 3 aberturas seguidas sem resposta; depois a pessoa só o acha em Preferências
_TRAVA = threading.Lock()  # o painel manda duas ações quase juntas (iniciar e cartão): ler, mudar e gravar não pode se cruzar
PADRAO = {"convidar": False, "convites": 0, "aceito": False, "recusado": False, "cartao": 0, "iniciado_em": None, "concluido": None, "dicas": []}


def _oper(oper=None):
    if oper:
        return oper
    import hud_servidor as h
    return h.OPER


def _ler(caminho):
    try:
        with open(caminho, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def texto():
    """Os passos, o convite, as dicas e a lista do que fica de fora do tour (tutorial.json)."""
    return _ler(ARQ_TEXTO) or {"passos": [], "dicas": [], "convite": {}, "total_passos": 0, "fora_do_tour": {}}


def _arquivo(oper=None):
    return os.path.join(_oper(oper), NOME_ESTADO)


def existe(oper=None):
    return os.path.isfile(_arquivo(oper))


def estado(oper=None):
    """O estado da pessoa, sempre completo: o que faltar no arquivo volta ao padrão."""
    salvo = _ler(_arquivo(oper)) or {}
    saida = {}
    for k, padrao in PADRAO.items():
        v = salvo.get(k, padrao)
        if k in ("iniciado_em", "concluido"):
            ok = v is None or isinstance(v, str)
        elif isinstance(padrao, bool):
            ok = isinstance(v, bool)
        elif isinstance(padrao, int):
            ok = isinstance(v, int) and not isinstance(v, bool)
        else:
            ok = isinstance(v, list)
        saida[k] = v if ok else padrao
    saida["dicas"] = [str(x) for x in saida["dicas"]]
    return saida


def _gravar(est, oper=None):
    caminho = _arquivo(oper)
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(est, f, ensure_ascii=False, indent=2)


def concluido(oper=None):
    return bool(estado(oper).get("concluido"))


def convidar(oper=None):
    """O painel deve oferecer o tour agora: instalação nova, ainda sem resposta e sem ter passado do limite de convites."""
    est = estado(oper)
    return bool(est["convidar"] and not est["concluido"] and not est["recusado"] and est["convites"] < MAX_CONVITES)


def continuar(oper=None):
    """A pessoa começou o tour e fechou a janela no meio (sair pelo botão ou pelo Esc zera o cartão): na próxima abertura o painel oferece continuar."""
    est = estado(oper)
    return bool(est["iniciado_em"] and not est["concluido"] and est["cartao"] > 0)


def publico(oper=None):
    t = texto()
    est = estado(oper)
    return {"passos": t.get("passos") or [], "total_passos": t.get("total_passos") or 0, "convite": t.get("convite") or {}, "convite_continuar": t.get("convite_continuar") or {},
            "dicas": t.get("dicas") or [], "estado": est, "convidar": convidar(oper), "continuar": continuar(oper), "pessoal": existe(oper)}


def _agente():
    try:
        import hud_servidor as h
        return str((h._config().get("agente") or {}).get("nome") or "").strip() or "Guardião"
    except Exception:
        return "Guardião"


def _com_nome(frase):
    return str(frase or "").replace("{agente}", _agente())


def _card(cid):
    for c in texto().get("passos") or []:
        if c.get("id") == cid:
            return c
    return None


def _anunciar_conquista():
    try:
        import guardiao_v2 as v2
        v2.verificar_conquistas(True)
    except Exception as erro:  # a conquista nunca pode derrubar o tour
        print("  (não consegui conferir a conquista do tutorial:", erro, ")")


def falar(frase):
    """O guardião fala a frase do cartão (só se a voz estiver ligada). O que ainda esperava na fila de um cartão anterior é descartado."""
    import hud_servidor as h
    if not h.preferencias().get("voz_guardiao", True):
        return False
    guardar = []
    while not h.bus.comandos.empty():
        try:
            c = h.bus.comandos.get_nowait()
        except Exception:
            break
        if c[0] != "narrar":
            guardar.append(c)
    for c in guardar:
        h.bus.comandos.put(c)
    h.bus.comandos.put(("narrar", _com_nome(frase)))
    return True


def calar():
    """A pessoa saiu do tour: a narração que ainda espera na fila não é dita."""
    import hud_servidor as h
    guardar = []
    while not h.bus.comandos.empty():
        try:
            c = h.bus.comandos.get_nowait()
        except Exception:
            break
        if c[0] != "narrar":
            guardar.append(c)
    for c in guardar:
        h.bus.comandos.put(c)
    if getattr(h.bus, "narrando", False):
        try:
            import controle_fala
            controle_fala._parar_som()
        except Exception:
            pass


def agir(dados, oper=None):
    """Ações do painel: convite (resposta), iniciar, cartao (onde a pessoa está), concluir, sair, dica (texto a mostrar uma vez) e falar."""
    with _TRAVA:
        return _agir(dados, oper)


def _agir(dados, oper=None):
    acao = str((dados or {}).get("acao") or "")
    est = estado(oper)
    agora = time.strftime("%Y-%m-%d")
    if acao == "convite_mostrado":
        est["convites"] += 1
    elif acao == "convite":
        resposta = str(dados.get("resposta") or "")
        est["convidar"] = False
        est["aceito"] = resposta == "aceitou"
        est["recusado"] = resposta == "recusou"
        if est["aceito"] and not est["iniciado_em"]:
            est["iniciado_em"] = agora
    elif acao == "iniciar":
        est["convidar"] = False
        est["cartao"] = 0
        est["iniciado_em"] = est["iniciado_em"] or agora
    elif acao == "cartao":
        n = dados.get("n")
        est["cartao"] = n if isinstance(n, int) and not isinstance(n, bool) and 0 <= n <= 99 else est["cartao"]
    elif acao == "concluir":
        est["convidar"] = False
        primeira = not est["concluido"]
        est["concluido"] = est["concluido"] or agora
        est["cartao"] = 0
        _gravar(est, oper)
        calar()
        if primeira:
            _anunciar_conquista()
        return {"ok": True, "estado": est}
    elif acao == "sair":  # saiu de propósito: não oferece continuar na próxima abertura
        est["cartao"] = 0
        calar()
    elif acao == "dica":
        cid = str(dados.get("id") or "")
        dica = next((d for d in texto().get("dicas") or [] if d.get("id") == cid), None)
        if not dica or not existe(oper) or cid in est["dicas"]:
            return {"ok": True, "texto": None}
        est["dicas"].append(cid)
        _gravar(est, oper)
        return {"ok": True, "texto": _com_nome(dica.get("texto"))}
    elif acao == "falar":
        cid = str(dados.get("id") or "")
        card = _card(cid)
        frase = (card or {}).get("fala") or ((texto().get("convite") or {}).get("fala") if cid == "convite" else "")
        return {"ok": True, "falou": bool(frase) and falar(frase)}
    else:
        return {"ok": False, "erro": "ação desconhecida"}
    _gravar(est, oper)
    return {"ok": True, "estado": est}
