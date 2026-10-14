# Parte nova do guardião, usada pelo painel v2 (pasta hud2): modo execução com acompanhamento do tempo,
# calibragem de 30 dias (report diário + o que o guardião aprende) e POPs (os da pessoa e o catálogo da escola).
# Tudo aqui é regra local: nada chama o Claude. Os dados ficam na pasta operacional:
#   registros\execucao_AAAA-MM-DD.json  sessões de trabalho de cada bloco (trechos, avisos de tempo, extensões)
#   calibragem\estado.json, calibragem\reports\AAAA-MM-DD.json, calibragem\eventos.jsonl, calibragem\aprendizados.json
#   tempos.json                          tempo real por tipo de tarefa (o guardião do chat lê igual)
#   <memória>\pops\POP - nome.md         os POPs, no modelo de sempre
import json
import os
import re
import threading
import time
from datetime import date, datetime, timedelta

import requests

import hud_servidor as h

_trava = threading.RLock()
INTERVALO_ABERTURA = 3 * 3600  # a abertura animada completa não se repete se a janela for reaberta antes disso
MOTIVOS = ["Subestimei o tempo", "Interrupções", "Faltou informação", "Me distraí", "Sem energia", "Depende de outra pessoa"]
IMPREVISTOS = ["Ligação ou mensagem", "Pedido urgente", "Problema técnico", "Outro imprevisto"]
DICAS = {  # uma estratégia curta e prática para cada motivo, dita logo depois de anotar
    "subestimei o tempo": "Da próxima vez eu reservo mais tempo para esse tipo de tarefa.",
    "interrupcoes": "No próximo trecho, feche as notificações e avise que volta em meia hora.",
    "faltou informacao": "Peça agora o que falta, para a tarefa não travar de novo.",
    "me distrai": "Vamos em um trecho curto: 25 minutos só nisso, e eu aviso quando acabar.",
    "sem energia": "Faça só o próximo passo pequeno e pare. Já conta.",
    "depende de outra pessoa": "Cobre a pessoa agora e siga para a próxima tarefa.",
}
DIAS_CURTOS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
DIAS_INGLES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
HORAS_CALOR = list(range(8, 19))  # colunas do mapa de foco: 8h a 18h
MARCOS = (7, 14, 21, 30)


# ---------------- utilidades ----------------

def _agora_hm():
    return h.time.strftime("%H:%M")


def _agora_min():
    return h._min(_agora_hm())


def _hm(minutos):
    minutos = max(0, min(23 * 60 + 59, int(minutos)))
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def _gravar(caminho, obj):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, caminho)


def _hoje():
    return date.today().isoformat()


def _pessoa():
    nome = ((h._config().get("pessoa") or {}).get("nome") or "").strip()
    return nome.split(" ")[0] if nome else "você"


def _estados_de_hoje():
    return {b.get("id"): b for b in h._registro_de_hoje().get("blocos", [])}


def bloco_atual(plano=None):
    """O primeiro bloco pendente de hoje, na ordem do horário (é o que a tela mostra como tarefa de agora)."""
    plano = plano or h._plano_de_hoje() or {}
    reg = _estados_de_hoje()
    espera = set((h._ler_json(_arq_exec()) or {}).get("aguardando") or [])  # já marcadas como feitas na tela, só falta a frase do que foi feito
    pend = [b for b in plano.get("blocos", []) if (reg.get(b.get("id")) or {}).get("estado") not in ("feito", "adiado") and b.get("id") not in espera
            and h._hora(b.get("inicio")) and h._hora(b.get("fim"))]
    pend.sort(key=lambda b: h._min(b["inicio"]))
    return pend[0] if pend else None


# ---------------- eventos de comportamento (viram a calibragem) ----------------

def _pasta_cal():
    return os.path.join(h.OPER, "calibragem")


def registrar_evento(tipo, bloco=None, **extra):
    """Uma linha por fato observado (aviso de tempo, extensão, adiamento, conclusão, imprevisto). É a matéria-prima do que o guardião aprende."""
    linha = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "data": _hoje(), "hora": _agora_hm(), "tipo": tipo}
    if bloco:
        linha.update({"bloco": bloco.get("id"), "titulo": bloco.get("titulo"), "frente": bloco.get("frente")})
    linha.update({k: v for k, v in extra.items() if v is not None})
    try:
        os.makedirs(_pasta_cal(), exist_ok=True)
        with _trava, open(os.path.join(_pasta_cal(), "eventos.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return linha


def _eventos(dias=45):
    limite = (date.today() - timedelta(days=dias)).isoformat()
    saida = []
    try:
        with open(os.path.join(_pasta_cal(), "eventos.jsonl"), encoding="utf-8") as f:
            for linha in f:
                try:
                    ev = json.loads(linha)
                except ValueError:
                    continue
                if ev.get("data", "") >= limite:
                    saida.append(ev)
    except OSError:
        pass
    return saida


# ---------------- modo execução ----------------

CHECKIN = None  # aviso de tempo esperando resposta: {"id", "bloco", "titulo", "faltam", "fim", "passo", "quando", "dados"}


def _arq_exec(dia=None):
    return os.path.join(h.OPER, "registros", f"execucao_{dia or _hoje()}.json")


def _ler_exec():
    d = h._ler_json(_arq_exec()) or {}
    if d.get("data") != _hoje():
        d = {}
    d.setdefault("data", _hoje())
    d.setdefault("modo", {"ativo": False})
    d.setdefault("sessoes", [])
    d.setdefault("avisados", [])
    d.setdefault("aguardando", [])
    return d


def _sessao(d, bloco_id, criar_de=None):
    for s in reversed(d["sessoes"]):
        if s.get("bloco") == bloco_id and not s.get("resultado"):
            return s
    if not criar_de:
        return None
    b = criar_de
    s = {"bloco": b.get("id"), "titulo": b.get("titulo"), "frente": b.get("frente"),
         "planejado": {"inicio": b.get("inicio"), "fim": b.get("fim"), "minutos": h._min(b["fim"]) - h._min(b["inicio"])},
         "trechos": [], "checkins": [], "extensoes": [], "resultado": None, "motivo": None}
    d["sessoes"].append(s)
    return s


def _abrir_trecho(d, bloco):
    s = _sessao(d, bloco.get("id"), criar_de=bloco)
    if not s["trechos"] or s["trechos"][-1].get("ate"):
        s["trechos"].append({"de": _agora_hm(), "ate": None})
        return True
    return False


def _fechar_trechos(d, bloco_id=None):
    for s in d["sessoes"]:
        if bloco_id and s.get("bloco") != bloco_id:
            continue
        for t in s["trechos"]:
            if not t.get("ate"):
                t["ate"] = _agora_hm()


def _minutos(s):
    total = 0
    for t in s.get("trechos", []):
        fim = t.get("ate") or _agora_hm()
        total += max(0, (h._min(fim) - h._min(t["de"])) % 1440)
    return total


def _publico_checkin():
    c = CHECKIN
    if not c:
        return None
    return {k: c.get(k) for k in ("id", "bloco", "titulo", "faltam", "fim", "passo", "texto", "opcoes")}


def estado_exec():
    """O que a tela precisa saber: se o modo execução está ligado, a sessão do bloco de agora e o aviso de tempo em aberto."""
    d = _ler_exec()
    b = bloco_atual()
    sessao = None
    if b:
        s = _sessao(d, b.get("id"))
        if s and s["trechos"]:
            sessao = {"bloco": b.get("id"), "inicio": s["trechos"][0]["de"], "minutos": _minutos(s), "aberto": not s["trechos"][-1].get("ate")}
    return {"ativo": bool(d["modo"].get("ativo")), "desde": d["modo"].get("desde"), "bloco": b.get("id") if b else None,
            "sessao": sessao, "checkin": _publico_checkin()}


def exec_por_bloco():
    """Para /plano: o que já foi trabalhado em cada bloco de hoje."""
    d = _ler_exec()
    saida = {}
    for s in d["sessoes"]:
        if not s.get("trechos"):
            continue
        saida[s["bloco"]] = {"inicio": s["trechos"][0]["de"], "minutos": _minutos(s), "aberto": not s["trechos"][-1].get("ate") and not s.get("resultado")}
    return saida


def _avisar_tela():
    h.bus.emitir("execucao", **estado_exec())


def entrar(iniciar=False):
    """Liga o modo execução. O relógio do bloco começa a contar se o horário dele já chegou (ou se a pessoa pediu para começar já)."""
    global CHECKIN
    with _trava:
        d = _ler_exec()
        plano = h._plano_de_hoje() or {}
        b = bloco_atual(plano)
        ja = bool(d["modo"].get("ativo"))
        d["modo"] = {"ativo": True, "desde": d["modo"].get("desde") if ja else _agora_hm()}
        if b and plano.get("status") == "aprovado" and (iniciar or _agora_min() >= h._min(b["inicio"])):
            _abrir_trecho(d, b)
        _gravar(_arq_exec(), d)
    if not ja:
        registrar_evento("execucao_inicio", b)
    _avisar_tela()
    return {"ok": True, **estado_exec()}


def sair():
    global CHECKIN
    with _trava:
        d = _ler_exec()
        era = bool(d["modo"].get("ativo"))
        _fechar_trechos(d)
        d["modo"] = {"ativo": False}
        _gravar(_arq_exec(), d)
        CHECKIN = None
    if era:
        registrar_evento("execucao_fim")
    h.bus.emitir("checkin_fim", motivo="saiu")
    _avisar_tela()
    return {"ok": True, **estado_exec()}


def aguardar(bloco_id, esperar=True):
    """A pessoa marcou a tarefa como feita na tela e falta só a frase do comentário: o relógio dela para e os avisos de tempo também.
    Com esperar=False (Desfazer), a tarefa volta a ser a de agora."""
    global CHECKIN
    with _trava:
        d = _ler_exec()
        if esperar:
            _fechar_trechos(d, bloco_id)
            if bloco_id not in d["aguardando"]:
                d["aguardando"].append(bloco_id)
        else:
            d["aguardando"] = [x for x in d["aguardando"] if x != bloco_id]
        _gravar(_arq_exec(), d)
        if esperar and CHECKIN and CHECKIN.get("bloco") == bloco_id:
            CHECKIN = None
            h.bus.emitir("checkin_fim", motivo="concluido")
    _tique()
    _avisar_tela()
    return {"ok": True}


def ao_concluir(bloco, real, nao_confirmado, concluido):
    """Chamado pelo servidor sempre que um bloco é concluído ou reaberto: fecha a sessão e alimenta o tempos.json."""
    global CHECKIN
    if not concluido:
        return
    with _trava:
        d = _ler_exec()
        s = _sessao(d, bloco.get("id"))
        trabalhado = None
        if s:
            _fechar_trechos(d, bloco.get("id"))
            trabalhado = _minutos(s) if s["trechos"] else None
            s["resultado"] = "concluido"
            s["minutos"] = trabalhado
            s["fim"] = _agora_hm()
        if s or bloco.get("id") in d["aguardando"]:
            d["aguardando"] = [x for x in d["aguardando"] if x != bloco.get("id")]
            _gravar(_arq_exec(), d)
        if CHECKIN and CHECKIN.get("bloco") == bloco.get("id"):
            CHECKIN = None
            h.bus.emitir("checkin_fim", motivo="concluido")
    planejado = h._min(bloco["fim"]) - h._min(bloco["inicio"]) - int(bloco.get("estendido_min") or 0)
    relogio = (h._min(real["fim"]) - h._min(real["inicio"])) % 1440 if real else None
    medido = trabalhado if trabalhado and trabalhado >= 1 else None
    minutos = medido if medido is not None else relogio
    confirmado = medido is not None or not nao_confirmado
    if minutos is not None:
        _somar_tempo(bloco.get("frente") or "Geral", bloco.get("titulo"), planejado, minutos, confirmado)
        registrar_evento("conclusao", bloco, planejado=planejado, real=minutos, desvio=minutos - planejado, confirmado=confirmado,
                         medido=medido is not None, estendido=int(bloco.get("estendido_min") or 0) or None)
    _avisar_tela()


def _somar_tempo(tipo, titulo, planejado, real, confirmado):
    """tempos.json: os 10 últimos registros por tipo de tarefa e a média (só vale com 3 execuções confirmadas)."""
    caminho = os.path.join(h.OPER, "tempos.json")
    with _trava:
        dados = h._ler_json(caminho) or {}
        tipos = dados.setdefault("tipos", {})
        t = tipos.setdefault(tipo, {"registros": [], "media": None})
        t.setdefault("registros", []).append({"data": _hoje(), "titulo": titulo, "planejado": planejado, "real": real, "confirmado": bool(confirmado)})
        t["registros"] = t["registros"][-10:]
        validos = [r["real"] for r in t["registros"] if r.get("confirmado")]
        t["media"] = round(sum(validos) / len(validos)) if len(validos) >= 3 else None
        t["media_planejado"] = round(sum(r["planejado"] for r in t["registros"]) / len(t["registros"]))
        _gravar(caminho, dados)


def estender_bloco(bloco_id, minutos, motivo=None):
    """Dá mais tempo ao bloco de hoje (muda o fim no plano). Não mexe no ClickUp nem empurra os blocos seguintes: avisa se encostar no próximo."""
    try:
        minutos = int(minutos)
    except (TypeError, ValueError):
        return {"ok": False, "erro": "Não entendi quantos minutos."}
    if not 1 <= minutos <= 240:
        return {"ok": False, "erro": "A extensão precisa ficar entre 1 minuto e 4 horas."}
    with _trava:
        plano, caminho = h._plano_e_caminho()
        bloco = next((b for b in (plano or {}).get("blocos", []) if b.get("id") == bloco_id), None)
        if not bloco:
            return {"ok": False, "erro": "Esse bloco não está no plano de hoje."}
        base = max(h._min(bloco["fim"]), _agora_min())  # tarefa que já passou do horário: o tempo a mais conta a partir de agora
        novo = min(23 * 60 + 59, base + minutos)
        bloco["fim"] = _hm(novo)
        bloco["estendido_min"] = int(bloco.get("estendido_min") or 0) + minutos
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(plano, f, ensure_ascii=False, indent=2)
        d = _ler_exec()
        s = _sessao(d, bloco_id, criar_de=bloco)
        s["extensoes"].append({"hora": _agora_hm(), "minutos": minutos, "motivo": motivo})
        _gravar(_arq_exec(), d)
    conflito = None
    reg = _estados_de_hoje()
    seguintes = [(x["inicio"], x.get("titulo")) for x in plano.get("blocos", []) if x.get("id") != bloco_id and (reg.get(x.get("id")) or {}).get("estado") not in ("feito", "adiado")]
    seguintes += [(x["inicio"], x.get("titulo")) for x in plano.get("fixos", [])]
    for ini, titulo in sorted(seguintes, key=lambda i: h._min(i[0])):
        if h._min(bloco["inicio"]) < h._min(ini) < novo:
            conflito = f"Isso encosta em {titulo}, que começa às {ini}."
            break
    registrar_evento("extensao", bloco, minutos=minutos, motivo=motivo, novo_fim=bloco["fim"])
    h._log_acao("execucao:estender", bloco_id, bloco.get("titulo"), f"+{minutos} min, até {bloco['fim']}", {"motivo": motivo}, True)
    h.bus.emitir("plano")
    _avisar_tela()
    return {"ok": True, "fim": bloco["fim"], "conflito": conflito, "titulo": bloco.get("titulo")}


def adiar_com_motivo(bloco_id, motivo=None):
    """Adia o bloco (como o botão Adiar) e guarda o porquê na calibragem."""
    global CHECKIN
    plano = h._plano_de_hoje() or {}
    bloco = next((b for b in plano.get("blocos", []) if b.get("id") == bloco_id), None)
    r = h.adiar_bloco({"id": bloco_id})
    if not r.get("ok"):
        return r
    with _trava:
        d = _ler_exec()
        s = _sessao(d, bloco_id)
        if s:
            _fechar_trechos(d, bloco_id)
            s["resultado"], s["motivo"], s["minutos"], s["fim"] = "adiado", motivo, _minutos(s), _agora_hm()
            _gravar(_arq_exec(), d)
        if CHECKIN and CHECKIN.get("bloco") == bloco_id:
            CHECKIN = None
            h.bus.emitir("checkin_fim", motivo="adiado")
    registrar_evento("adiamento", bloco, motivo=motivo, vezes=r.get("vezes"))
    _avisar_tela()
    return r


def registrar_motivo(bloco_id, motivo, contexto="motivo"):
    plano = h._plano_de_hoje() or {}
    bloco = next((b for b in plano.get("blocos", []) if b.get("id") == bloco_id), None)
    registrar_evento(contexto, bloco, motivo=str(motivo or "").strip()[:200])
    return {"ok": True}


def _curto(titulo, n=70):
    titulo = str(titulo or "").strip()
    return titulo if len(titulo) <= n else titulo[:n].rsplit(" ", 1)[0]


def _texto_checkin(titulo, faltam, trabalhado=None):
    t = _curto(titulo)
    if trabalhado is not None:  # começou depois do horário reservado: a conta é pelo tempo trabalhado
        return f"Você está há {trabalhado} minutos em {t}, que era o tempo previsto. Concluiu, quer mais tempo ou prefere reprogramar?"
    if faltam > 15:
        return f"Faltam {faltam} minutos para o fim de {t}. Como está o andamento? Vai dar para terminar no horário?"
    if faltam > 0:
        return f"Faltam {faltam} minutos para {t}. Dá para fechar ou você precisa de mais tempo?"
    if faltam == 0:
        return f"O horário de {t} acabou. Você concluiu ou quer mais tempo?"
    return f"Já passaram {-faltam} minutos do horário de {t}. Concluiu, quer mais tempo ou prefere reprogramar?"


def _opcoes_checkin(faltam):
    if faltam > 0:
        return [{"rotulo": "Termino no horário", "resposta": "no_prazo"}, {"rotulo": "Preciso de mais tempo", "resposta": "mais_tempo"},
                {"rotulo": "Surgiu um imprevisto", "resposta": "imprevisto"}, {"rotulo": "Reprogramar", "resposta": "reprogramar"}]
    return [{"rotulo": "Concluí", "resposta": "concluir"}, {"rotulo": "Mais 15 min", "resposta": "estender", "minutos": 15},
            {"rotulo": "Mais 30 min", "resposta": "estender", "minutos": 30}, {"rotulo": "Reprogramar", "resposta": "reprogramar"}]


def _marcas(duracao):
    if duracao >= 60:
        return [30, 10]
    if duracao >= 25:
        return [10]
    if duracao >= 15:
        return [5]
    return []


def _tique():
    """Uma olhada no relógio: abre a sessão do bloco quando o horário dele chega e dispara os avisos de tempo."""
    global CHECKIN
    plano = h._plano_de_hoje()
    if not plano or plano.get("status") != "aprovado":
        return None
    with _trava:
        d = _ler_exec()
        if not d["modo"].get("ativo"):
            return None
        b = bloco_atual(plano)
        if not b:
            return None
        agora, ini, fim = _agora_min(), h._min(b["inicio"]), h._min(b["fim"])
        s = _sessao(d, b.get("id"))
        mudou = False
        if agora >= ini and (not s or not s["trechos"] or s["trechos"][-1].get("ate")):
            mudou = _abrir_trecho(d, b)
            s = _sessao(d, b.get("id"))
        if not s or not s["trechos"]:
            if mudou:
                _gravar(_arq_exec(), d)
            return None
        if CHECKIN and (CHECKIN.get("bloco") != b.get("id") or time.time() - CHECKIN["quando"] > 900):
            CHECKIN = None  # o aviso era de outro bloco ou ficou velho
        faltam = fim - agora
        base = f"{b.get('id')}|{b.get('fim')}"
        marcas = _marcas(fim - ini)
        # tarefa que só começou depois do horário reservado: nada de cobrar na largada; o aviso vem quando o tempo previsto tiver sido trabalhado
        tardio = h._min(s["trechos"][0]["de"]) >= fim and not s.get("extensoes")
        if tardio:
            faltam, base, marcas = (fim - ini) - _minutos(s), f"{b.get('id')}|tardio", []
        chave = None
        if faltam > 0:
            cabiveis = [m for m in marcas if faltam <= m]
            if cabiveis and _minutos(s) >= 3:  # nada de aviso no instante em que a pessoa entra em execução
                m = min(cabiveis)
                chave = f"{base}|{m}"
                for maior in marcas:
                    if maior >= m and f"{base}|{maior}" not in d["avisados"] and maior != m:
                        d["avisados"].append(f"{base}|{maior}")
        else:
            n = (-faltam) // 20
            chave = f"{base}|fim" if n == 0 else (f"{base}|atraso{n}" if n <= 3 else None)
            if chave and n > 0 and f"{base}|fim" not in d["avisados"]:
                d["avisados"].append(f"{base}|fim")
        disparar = bool(chave) and chave not in d["avisados"] and not CHECKIN
        if disparar:
            d["avisados"].append(chave)
            s["checkins"].append({"hora": _agora_hm(), "faltam": faltam, "resposta": None})
        if disparar or mudou:
            _gravar(_arq_exec(), d)
        if not disparar:
            if mudou:
                threading.Thread(target=_avisar_tela, daemon=True).start()
            return None
        CHECKIN = {"id": f"{base}|{chave.rsplit('|', 1)[1]}|{int(time.time())}", "bloco": b.get("id"), "titulo": b.get("titulo"), "faltam": faltam,
                   "fim": b.get("fim"), "passo": "inicio", "quando": time.time(), "dados": {},
                   "texto": _texto_checkin(b.get("titulo"), faltam, _minutos(s) if tardio else None), "opcoes": _opcoes_checkin(faltam)}
        c = dict(CHECKIN)
    registrar_evento("checkin", b, faltam=faltam)
    h.bus.emitir("checkin", **_publico_checkin())
    h.bus.comandos.put(("checkin", {"texto": c["texto"], "id": c["id"]}))
    return c


_REFEICOES = ("almoco", "almoço", "jantar", "cafe", "café", "lanche", "descanso", "pausa", "intervalo")


def _tique_fixos():
    """Compromisso fixo sem tarefa no ClickUp (triagem do WhatsApp, por exemplo) não tem como ser marcado lá: quando o horário passa, pergunta uma vez se foi feito."""
    global CHECKIN
    plano = h._plano_de_hoje()
    if not plano or plano.get("status") != "aprovado" or CHECKIN:
        return None
    with _trava:
        d = _ler_exec()
        if not d["modo"].get("ativo"):
            return None
        agora = _agora_min()
        for f in plano.get("fixos", []):
            if not (h._hora(f.get("inicio")) and h._hora(f.get("fim"))) or any(r in h._norm(f.get("titulo")) for r in _REFEICOES):
                continue
            passou = agora - h._min(f["fim"])
            chave = f"fixo|{f['inicio']}|{f.get('titulo')}"
            if not 1 <= passou <= 90 or chave in d["avisados"]:
                continue
            d["avisados"].append(chave)
            _gravar(_arq_exec(), d)
            texto = f"O horário de {_curto(f.get('titulo'))} passou. Você fez?"
            CHECKIN = {"id": f"{chave}|{int(time.time())}", "bloco": "fixo", "titulo": f.get("titulo"), "faltam": 0, "fim": f["fim"], "passo": "inicio",
                       "quando": time.time(), "dados": {}, "texto": texto,
                       "opcoes": [{"rotulo": "Fiz", "resposta": "fixo_feito"}, {"rotulo": "Não fiz", "resposta": "fixo_nao"}]}
            c = dict(CHECKIN)
            break
        else:
            return None
    registrar_evento("checkin_fixo", {"id": "fixo", "titulo": f.get("titulo")}, passou=passou)
    h.bus.emitir("checkin", **_publico_checkin())
    h.bus.comandos.put(("checkin", {"texto": c["texto"], "id": c["id"]}))
    return c


_viradas_vistas = set()


def _virada_do_plano():
    """True uma vez a cada virada do plano: começo e fim de cada bloco pendente e os pontos em que o aviso de tempo sairia (faltam 30 ou 10 min).
    É só nesses momentos que vale conferir o ClickUp. Na primeira volta (app recém-aberto) confere uma vez e dá o passado por visto."""
    plano = h._plano_de_hoje()
    if not plano or plano.get("status") != "aprovado":
        return False
    agora = _agora_min()
    reg = _estados_de_hoje()
    chaves, primeira = set(), not _viradas_vistas
    for b in plano.get("blocos", []):
        if (reg.get(b.get("id")) or {}).get("estado") in ("feito", "adiado") or not (h._hora(b.get("inicio")) and h._hora(b.get("fim"))):
            continue
        ini, fim = h._min(b["inicio"]), h._min(b["fim"])
        momentos = [("ini", ini), ("fim", fim)] + [(f"m{m}", fim - m) for m in _marcas(fim - ini)]
        chaves.update((_hoje(), b.get("id"), nome, t) for nome, t in momentos if t <= agora)
    novas = chaves - _viradas_vistas
    _viradas_vistas.update(chaves)
    return bool(novas) or primeira


_vigia_ligado = False


def ligar_vigia():
    global _vigia_ligado
    if _vigia_ligado:
        return
    _vigia_ligado = True

    def laco():
        while True:
            try:
                if _virada_do_plano():
                    h.sincronizar_com_clickup(espaco=0)  # só nas viradas: o que ela já concluiu no ClickUp não é cobrado
                _tique()
                _tique_fixos()
            except Exception as erro:  # o vigia nunca pode derrubar o guardião
                print("  (vigia da execução falhou:", erro, ")")
            time.sleep(15)

    threading.Thread(target=laco, daemon=True).start()


def _fecho(texto, falar=True, **extra):
    """Encerra o aviso de tempo: conta à tela e manda o guardião falar a frase final."""
    global CHECKIN
    CHECKIN = None
    h.bus.emitir("checkin_fim", motivo="respondido", texto=texto)
    if falar and texto:
        h.bus.comandos.put(("dizer", texto))
    _avisar_tela()
    return {"ok": True, "fim": True, "texto": texto, **extra}


def _passo(passo, texto, opcoes):
    CHECKIN.update({"passo": passo, "texto": texto, "opcoes": opcoes, "quando": time.time()})
    h.bus.emitir("checkin", **_publico_checkin())
    h.bus.comandos.put(("dizer", texto))
    return {"ok": True, "fim": False, **_publico_checkin()}


def _dica(motivo):
    return DICAS.get(h._norm(motivo).strip(), "")


def responder_checkin(dados):
    """Resposta pelos botões da tela ao aviso de tempo. Cada resposta leva ao próximo passo, sem passar pelo Claude."""
    global CHECKIN
    resposta = str(dados.get("resposta") or "")
    with _trava:
        c = CHECKIN
        bloco_id = (c or {}).get("bloco") or dados.get("bloco")
        if not bloco_id:
            return {"ok": False, "erro": "Não há aviso de tempo em aberto."}
        if bloco_id == "fixo" and resposta in ("fixo_feito", "fixo_nao"):
            titulo = (c or {}).get("titulo")
            registrar_evento("checkin_fixo_resposta", {"id": "fixo", "titulo": titulo}, resposta="feito" if resposta == "fixo_feito" else "nao_fez")
            return _fecho("Anotei." if resposta == "fixo_feito" else "Anotei. Fica para o fim do dia a gente ver onde encaixa.")
        if not c:  # a pessoa respondeu depois de o aviso sair da memória: segue valendo para o bloco citado
            c = CHECKIN = {"id": "tardio", "bloco": bloco_id, "titulo": dados.get("titulo"), "faltam": 0, "fim": None, "passo": "inicio", "quando": time.time(), "dados": {}}
        d = _ler_exec()
        s = _sessao(d, bloco_id)
        if s and s["checkins"] and resposta in ("no_prazo", "mais_tempo", "imprevisto", "reprogramar", "concluir", "estender") and not s["checkins"][-1].get("resposta"):
            s["checkins"][-1]["resposta"] = resposta
            _gravar(_arq_exec(), d)
        guardado = c["dados"]
        mais_tempo = [{"rotulo": "Mais 15 min", "resposta": "estender", "minutos": 15}, {"rotulo": "Mais 30 min", "resposta": "estender", "minutos": 30},
                      {"rotulo": "Mais 1 hora", "resposta": "estender", "minutos": 60}]
        motivos = [{"rotulo": m, "resposta": "motivo", "motivo": m} for m in MOTIVOS]

        if resposta == "no_prazo":
            registrar_evento("checkin_resposta", {"id": bloco_id, "titulo": c.get("titulo")}, resposta="no_prazo")
            return _fecho("Combinado. Sigo acompanhando.")
        if resposta == "concluir":
            CHECKIN = None
            h.bus.emitir("checkin_fim", motivo="concluir")
            return {"ok": True, "fim": True, "acao": "concluir", "bloco": bloco_id}
        if resposta == "mais_tempo":
            return _passo("quanto", "Quanto tempo a mais você precisa?", mais_tempo)
        if resposta == "imprevisto":
            guardado["imprevisto"] = True
            return _passo("qual", "O que apareceu?", [{"rotulo": m, "resposta": "motivo", "motivo": m} for m in IMPREVISTOS])
        if resposta == "reprogramar":
            guardado["reprogramar"] = True
            return _passo("motivo", "Por que não deu para finalizar?", motivos)
        if resposta == "estender":
            guardado["minutos"] = int(dados.get("minutos") or 15)
            if guardado.get("motivo"):
                resposta = "aplicar"
            else:
                return _passo("motivo", "O que fez o tempo passar?", motivos)
        if resposta == "motivo":
            guardado["motivo"] = str(dados.get("motivo") or "").strip()[:200]
            if guardado.get("imprevisto") and not guardado.get("minutos") and not guardado.get("reprogramar"):
                return _passo("decisao", "Anotei. Quer mais tempo ou prefere reprogramar?", mais_tempo[:2] + [{"rotulo": "Reprogramar", "resposta": "reprogramar_ja"}])
            resposta = "aplicar"
        if resposta == "reprogramar_ja":
            guardado["reprogramar"] = True
            resposta = "aplicar"
        if resposta != "aplicar":
            return {"ok": False, "erro": "Resposta desconhecida."}
        motivo = guardado.get("motivo")
        tipo_evento = "imprevisto" if guardado.get("imprevisto") else None
    if tipo_evento:
        registrar_motivo(bloco_id, motivo, "imprevisto")
    dica = _dica(motivo)
    if guardado.get("reprogramar"):
        r = adiar_com_motivo(bloco_id, motivo)
        if not r.get("ok"):
            return _fecho(r.get("erro") or "Não consegui reprogramar.", ok=False)
        return _fecho(" ".join(x for x in ("Anotei. Marquei como adiada e no fim do dia a gente remarca.", dica) if x))
    r = estender_bloco(bloco_id, guardado.get("minutos") or 15, motivo)
    if not r.get("ok"):
        return _fecho(r.get("erro") or "Não consegui estender.")
    return _fecho(" ".join(x for x in (f"Anotei. Você tem até as {r['fim']}.", r.get("conflito"), dica) if x))


def fechar_checkin(como="voz"):
    """O aviso foi resolvido pela conversa (o Claude usou uma marca): some da tela."""
    global CHECKIN
    if CHECKIN:
        CHECKIN = None
        h.bus.emitir("checkin_fim", motivo=como)
        _avisar_tela()


def contexto_voz():
    """Linhas para o prompt do guardião: modo execução e aviso de tempo em aberto (vão junto da pergunta, não no prompt fixo)."""
    e = estado_exec()
    if not e["ativo"]:
        return ""
    linhas = []
    b = bloco_atual()
    if b:
        s = e.get("sessao")
        linhas.append(f"MODO EXECUCAO: ligado desde {e.get('desde')}. Tarefa em foco: {b['id']} ({b.get('titulo')}), das {b['inicio']} às {b['fim']}"
                      + (f", {s['minutos']} minutos trabalhados." if s else ", ainda não começou."))
    else:
        linhas.append(f"MODO EXECUCAO: ligado desde {e.get('desde')}. Não sobrou tarefa pendente hoje.")
    c = CHECKIN
    if c:
        linhas.append(f"AVISO DE TEMPO EM ABERTO: você acabou de perguntar {h.pessoa()['ao']} \"{c.get('texto')}\" sobre a tarefa {c.get('bloco')}. "
                      "A próxima fala dele provavelmente responde a isso: siga as regras de ACOMPANHAMENTO DA EXECUÇÃO.")
    return "\n".join(linhas)


def acao_execucao(dados):
    acao = str(dados.get("acao") or "")
    if acao == "entrar":
        return entrar()
    if acao == "iniciar":
        return entrar(iniciar=True)
    if acao == "sair":
        return sair()
    if acao == "checkin":
        return responder_checkin(dados)
    if acao in ("aguardar", "retomar"):
        return aguardar(dados.get("id"), acao == "aguardar")
    if acao == "estender":
        return estender_bloco(dados.get("id"), dados.get("minutos"), dados.get("motivo"))
    if acao == "motivo":
        return registrar_motivo(dados.get("id"), dados.get("motivo"), "motivo")
    if acao == "estado":
        return {"ok": True, **estado_exec()}
    return {"ok": False, "erro": f"Ação desconhecida: {acao}"}


# ---------------- sessão da janela (abertura animada) ----------------

def sessao(marcar=False):
    """Dados para a janela começar: se a abertura completa deve rodar (1ª vez do dia ou reaberta depois de 3 horas) e quem é quem."""
    arq = os.path.join(h.OPER, "logs", "abertura.json")
    ultimo = (h._ler_json(arq) or {}).get("ts", 0)
    passou = time.time() - ultimo > INTERVALO_ABERTURA or datetime.fromtimestamp(ultimo).date() != date.today()
    if marcar:
        try:
            _gravar(arq, {"ts": time.time()})
        except OSError:
            pass
    cfg = h._config()
    return {"abertura": bool(passou), "pessoa": _pessoa(), "agente": (cfg.get("agente") or {}).get("nome") or "Guardião",
            "rotina": {k: (cfg.get("rotina") or {}).get(k) for k in ("chegada", "almoco", "fim")},
            "saude": h.bus.ultimos.get("saude"), "estado": (h.bus.ultimos.get("estado") or {}).get("v"),
            "revisao": bool((h.bus.ultimos.get("revisao") or {}).get("ativa")), "execucao": estado_exec(), "preferencias": h.preferencias()}


# ---------------- calibragem ----------------

def _arq_estado_cal():
    return os.path.join(_pasta_cal(), "estado.json")


def _report_de(dia):
    return h._ler_json(os.path.join(_pasta_cal(), "reports", f"{dia}.json"))


def _dias_de_trabalho():
    nomes = (h._config().get("rotina") or {}).get("dias_trabalho") or DIAS_INGLES[:5]
    return {DIAS_INGLES.index(n) for n in nomes if n in DIAS_INGLES} or {0, 1, 2, 3, 4}


def salvar_report(campos, origem="tela"):
    """Guarda o report do dia (4 respostas). O primeiro report marca o dia 1 da calibragem."""
    chaves = ("ajustes", "picos", "funcionou", "ultima_hora")
    campos = [str(c or "").strip()[:1200] for c in (list(campos or []) + ["", "", "", ""])[:4]]
    if not any(campos):
        return {"ok": False, "erro": "Escreva pelo menos uma das respostas."}
    with _trava:
        estado = h._ler_json(_arq_estado_cal()) or {}
        if not estado.get("inicio"):
            estado = {"inicio": _hoje(), "ciclo": int(estado.get("ciclo") or 0) + 1}
            _gravar(_arq_estado_cal(), estado)
        _gravar(os.path.join(_pasta_cal(), "reports", f"{_hoje()}.json"),
                {"data": _hoje(), "enviado_em": time.strftime("%Y-%m-%d %H:%M"), "origem": origem, **dict(zip(chaves, campos))})
    visao = calibragem()
    h.bus.emitir("calibragem", dia=visao["dia"], estado=visao["estado"])
    return {"ok": True, "dia": visao["dia"], "estado": visao["estado"], "marco": visao["estado"] == "milestone"}


def reiniciar_calibragem():
    with _trava:
        estado = h._ler_json(_arq_estado_cal()) or {}
        _gravar(_arq_estado_cal(), {"inicio": None, "ciclo": int(estado.get("ciclo") or 1), "encerrado_em": _hoje()})
    h.bus.emitir("calibragem", dia=1, estado="d1")
    return {"ok": True}


def _sessoes_recentes(dias=28):
    saida = []
    for i in range(dias):
        dia = (date.today() - timedelta(days=i)).isoformat()
        d = h._ler_json(_arq_exec(dia))
        if d:
            saida.append((dia, d.get("sessoes") or []))
    return saida


def _mapa_de_foco():
    """Minutos trabalhados em modo execução por dia da semana e hora (8h a 18h), nas últimas 4 semanas."""
    grade = [[0.0] * len(HORAS_CALOR) for _ in range(5)]
    dias_com_dado = 0
    for dia, sessoes in _sessoes_recentes():
        semana = date.fromisoformat(dia).weekday()
        teve = False
        for s in sessoes:
            for t in s.get("trechos", []):
                if not t.get("ate"):
                    continue
                a, b = h._min(t["de"]), h._min(t["ate"])
                if b <= a or semana > 4:
                    continue
                teve = True
                for i, hora in enumerate(HORAS_CALOR):
                    grade[semana][i] += max(0, min(b, hora * 60 + 60) - max(a, hora * 60))
        dias_com_dado += 1 if teve else 0
    pico = max(max(l) for l in grade)
    if pico <= 0:
        return None, 0, None
    por_hora = [sum(grade[d][i] for d in range(5)) for i in range(len(HORAS_CALOR))]
    melhor = max(range(len(HORAS_CALOR)), key=lambda i: por_hora[i])
    ini = fim = melhor
    while ini > 0 and por_hora[ini - 1] >= 0.6 * por_hora[melhor]:
        ini -= 1
    while fim < len(HORAS_CALOR) - 1 and por_hora[fim + 1] >= 0.6 * por_hora[melhor]:
        fim += 1
    faixa = f"{HORAS_CALOR[ini]}h às {HORAS_CALOR[fim] + 1}h"
    return [{"d": DIAS_CURTOS[d], "celulas": [round(v / pico, 2) for v in grade[d]]} for d in range(5)], dias_com_dado, faixa


def _fmt_min(m):
    m = int(round(m))
    return f"{m} min" if m < 60 else (f"{m // 60}h" if m % 60 == 0 else f"{m // 60}h{m % 60:02d}")


def _aprendizados(eventos, faixa, dias_foco):
    """Cartões do que já dá para afirmar com os dados medidos, e dicas práticas. O que o guardião do chat escrever em aprendizados.json vem primeiro."""
    escrito = h._ler_json(os.path.join(_pasta_cal(), "aprendizados.json")) or {}
    cartoes = [{"k": str(c.get("k") or ""), "v": str(c.get("v") or ""), "d": str(c.get("d") or "")} for c in (escrito.get("cartoes") or []) if c.get("v")][:4]
    dicas = [str(x) for x in (escrito.get("dicas") or []) if x][:4]
    mudancas = [str(x) for x in (escrito.get("mudancas") or []) if x][:4]
    if faixa and dias_foco >= 2:
        cartoes.append({"k": "Seus melhores picos", "v": faixa, "d": f"Onde você mais trabalhou focado em {dias_foco} dias medidos."})
    tempos = (h._ler_json(os.path.join(h.OPER, "tempos.json")) or {}).get("tipos") or {}
    pior = None
    for tipo, t in tempos.items():
        regs = [r for r in t.get("registros", []) if r.get("confirmado")]
        if len(regs) >= 2:
            desvio = sum(r["real"] - r["planejado"] for r in regs) / len(regs)
            if pior is None or desvio > pior[1]:
                pior = (tipo, desvio, len(regs), sum(r["real"] for r in regs) / len(regs))
    if pior and pior[1] >= 5:
        cartoes.append({"k": "Onde o tempo estoura", "v": f"{pior[0]}: {_fmt_min(pior[1])} a mais", "d": f"Média de {pior[2]} execuções medidas."})
        dicas.append(f"Reserve {_fmt_min(pior[3])} para {pior[0]}: é o tempo que essas tarefas levam de verdade.")
    motivos = {}
    for ev in eventos:
        if ev.get("motivo") and ev.get("tipo") in ("extensao", "adiamento", "imprevisto", "motivo"):
            motivos[ev["motivo"]] = motivos.get(ev["motivo"], 0) + 1
    if motivos:
        nome, vezes = max(motivos.items(), key=lambda i: i[1])
        cartoes.append({"k": "Por que as tarefas atrasam", "v": nome, "d": f"Citado {vezes} {'vez' if vezes == 1 else 'vezes'} nos últimos 45 dias."})
        if vezes >= 2 and _dica(nome):
            dicas.append(_dica(nome))
    feitas = [ev for ev in eventos if ev.get("tipo") == "conclusao" and ev.get("medido")]
    if len(feitas) >= 3:
        no_prazo = sum(1 for ev in feitas if (ev.get("desvio") or 0) <= 5)
        cartoes.append({"k": "Concluídas no horário", "v": f"{no_prazo} de {len(feitas)}", "d": "Tarefas medidas em modo execução."})
    adiadas = {}
    for ev in eventos:
        if ev.get("tipo") == "adiamento" and ev.get("titulo"):
            adiadas[ev["titulo"]] = adiadas.get(ev["titulo"], 0) + 1
    repetida = next((t for t, n in adiadas.items() if n >= 3), None)
    if repetida:
        dicas.append(f"\"{_curto(repetida, 50)}\" foi adiada 3 vezes ou mais. Quebre em um primeiro passo de 10 minutos e comece por ele.")
    return cartoes[:4], list(dict.fromkeys(dicas))[:4], mudancas


def calibragem():
    """Tudo que a tela Calibragem mostra: dia da trilha, report de hoje e o que foi aprendido."""
    estado = h._ler_json(_arq_estado_cal()) or {}
    inicio = estado.get("inicio")
    hoje = date.today()
    trabalho = _dias_de_trabalho()
    eventos = _eventos()
    calor, dias_foco, faixa = _mapa_de_foco()
    cartoes, dicas, mudancas = _aprendizados(eventos, faixa, dias_foco)
    base = {"total": 30, "hoje": None, "campos": ["", "", "", ""], "aprendizados": cartoes, "dicas": dicas, "mudancas": mudancas,
            "calor": calor, "horas": [f"{x}h" for x in HORAS_CALOR], "dias_medidos": dias_foco, "reports": 0, "perdido": None}
    if not inicio:
        return {**base, "estado": "d1", "dia": 1, "trilha": [{"d": i + 1, "estado": "hoje" if i == 0 else "futuro", "marco": (i + 1) in MARCOS} for i in range(30)]}
    dias = []
    d = date.fromisoformat(inicio)
    while d <= hoje and len(dias) < 30:
        if d.weekday() in trabalho or _report_de(d.isoformat()) or d == hoje:
            dias.append(d)
        d += timedelta(days=1)
    trilha, feitos, perdido = [], 0, None
    for i in range(30):
        if i < len(dias):
            dia = dias[i]
            tem = bool(_report_de(dia.isoformat()))
            feitos += 1 if tem else 0
            if dia == hoje:
                est = "ok" if tem else "hoje"
            else:
                est = "ok" if tem else "miss"
            trilha.append({"d": i + 1, "estado": est, "marco": (i + 1) in MARCOS})
        else:
            trilha.append({"d": i + 1, "estado": "futuro", "marco": (i + 1) in MARCOS})
    n = len(dias)
    hoje_na_trilha = bool(dias) and dias[-1] == hoje
    rep = _report_de(hoje.isoformat())
    if n >= 2 and hoje_na_trilha and trilha[n - 2]["estado"] == "miss":
        perdido = n - 1
    if n >= 30 and (rep or not hoje_na_trilha):  # 30º dia com report, ou os 30 dias já ficaram para trás
        est = "final"
    elif rep:
        est = "milestone" if n in MARCOS else "sent"
    else:
        est = "missed" if perdido else "pending"
    return {**base, "estado": est, "dia": max(1, n), "trilha": trilha, "reports": feitos, "perdido": perdido,
            "hoje": rep, "campos": [str((rep or {}).get(k) or "") for k in ("ajustes", "picos", "funcionou", "ultima_hora")]}


# ---------------- POPs ----------------

_CACHE_CATALOGO = {}


def _pasta_pops():
    memoria = ((h._config().get("pastas") or {}).get("memoria")) or os.path.join(h.OPER, "memoria")
    if not os.path.isdir(memoria):
        memoria = os.path.join(h.OPER, "memoria")
    return os.path.join(memoria, "pops")


def _arq_usos():
    return os.path.join(h.OPER, "pops_uso.json")


def _secao(texto, titulo):
    m = re.search(r"^##\s*" + titulo + r"[^\n]*\n(.*?)(?=^##\s|\Z)", texto, re.S | re.M | re.I)
    return (m.group(1).strip() if m else "")


def _ler_pop(caminho):
    try:
        with open(caminho, encoding="utf-8-sig") as f:
            texto = f.read()
    except OSError:
        return None
    m = re.search(r"^#\s*POP\s*[|\-:]\s*(.+)$", texto, re.M)
    nome = (m.group(1).strip() if m else os.path.splitext(os.path.basename(caminho))[0].replace("POP - ", ""))
    v = re.search(r"^Vers[aã]o:\s*([^.\n]+)", texto, re.M)
    frente = re.search(r"^Frente:\s*(.+)$", texto, re.M)
    origem = re.search(r"^Origem:\s*(.+)$", texto, re.M)
    etapas = []
    for linha in _secao(texto, "Etapas").splitlines():
        cels = [c.strip() for c in linha.strip().strip("|").split("|")]
        if len(cels) < 2 or not cels[0].isdigit() or not cels[1]:
            continue
        dono = cels[2] if len(cels) > 2 else ""
        tempo = cels[3] if len(cels) > 3 else ""
        etapas.append({"t": cels[1], "dono": dono, "tempo": tempo, "m": " · ".join(x for x in (dono or "Você", tempo) if x)})
    minutos = [int(x.group(1)) for x in (re.match(r"(\d+)\s*min", e["tempo"]) for e in etapas) if x]
    usos = (h._ler_json(_arq_usos()) or {}).get("usos") or {}
    arquivo = os.path.basename(caminho)
    return {"id": "meu:" + arquivo, "arquivo": arquivo, "nome": nome, "proposito": re.sub(r"\s+", " ", _secao(texto, "O que é")),
            "frente": frente.group(1).strip() if frente else "Geral", "versao": re.sub(r"[()]", "", v.group(1)).strip() if v else "v1",
            "etapas": etapas, "tempo_medio": _fmt_min(sum(minutos)) if etapas and len(minutos) == len(etapas) else None,
            "usos": int(usos.get(arquivo) or 0), "criterio": _secao(texto, "Critério de pronto"), "prazo": _secao(texto, "Prazo-limite"),
            "atencao": _secao(texto, "Pontos de atenção"), "fontes": _secao(texto, "Fontes"), "meu": True, "de": origem.group(1).strip() if origem else None}


def meus_pops():
    pasta = _pasta_pops()
    saida = []
    if os.path.isdir(pasta):
        for nome in sorted(os.listdir(pasta)):
            if nome.lower().endswith(".md") and not nome.startswith("_"):
                p = _ler_pop(os.path.join(pasta, nome))
                if p:
                    saida.append(p)
    return saida


ARQ_CATALOGO_PADRAO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalogo_pops.json")  # de onde vem o catálogo da escola, sem configurar nada


def _fonte_do_catalogo():
    """De onde ler os POPs da escola: (endereço ou arquivo, cabeçalhos). Vale pops.catalogo do config.json, se a pessoa quiser outro catálogo;
    sem isso, o catálogo da escola (catalogo_pops.json: endereço e chave pública do Supabase da escola, que só deixa ler os POPs publicados)."""
    fonte = ((h._config().get("pops") or {}).get("catalogo") or "").strip()
    if fonte:
        return fonte, {}
    padrao = h._ler_json(ARQ_CATALOGO_PADRAO) or {}
    if not (padrao.get("url") and padrao.get("chave") and padrao.get("schema")):
        return "", {}
    url = padrao["url"] + "?select=*&publicado=eq.true&order=ordem.asc,nome.asc"
    return url, {"apikey": padrao["chave"], "Accept-Profile": padrao["schema"], "Accept": "application/json"}


def _catalogo():
    """POPs da escola (veja _fonte_do_catalogo). Sem fonte nenhuma, a tela diz que o catálogo ainda não existe; sem rede, mostra o último que veio."""
    fonte, cabecalhos = _fonte_do_catalogo()
    if not fonte:
        return {"ok": False, "motivo": "nao_configurado", "itens": []}
    guardado = _CACHE_CATALOGO.get(fonte)
    if guardado and time.time() - guardado[0] < 600:
        return guardado[1]
    try:
        if re.match(r"https?://", fonte):
            r = requests.get(fonte, headers=cabecalhos, timeout=8)
            r.raise_for_status()
            dados = r.json()
        else:
            dados = h._ler_json(fonte if os.path.isabs(fonte) else os.path.join(h.OPER, fonte))
            if dados is None:
                raise ValueError("arquivo não encontrado")
    except (requests.RequestException, ValueError, OSError):
        return guardado[1] if guardado else {"ok": False, "motivo": "indisponivel", "itens": []}
    itens = []
    for i, p in enumerate((dados.get("pops") if isinstance(dados, dict) else dados) or []):
        if not isinstance(p, dict) or not p.get("nome"):
            continue
        etapas = []
        for e in p.get("etapas") or []:
            if isinstance(e, str):
                e = {"t": e}
            if e.get("t"):
                m = e.get("m") or " · ".join(str(x) for x in (e.get("dono") or "Você", e.get("pronto"), e.get("prazo"), e.get("tempo"), e.get("dica")) if x)
                etapas.append({"t": str(e["t"]), "dono": str(e.get("dono") or ""), "tempo": str(e.get("tempo") or ""), "m": m})
        itens.append({"id": "escola:" + str(p.get("id") or i + 1), "nome": str(p["nome"]), "proposito": str(p.get("proposito") or ""),
                      "frente": str(p.get("frente") or "Geral"), "versao": str(p.get("versao") or "v1"), "etapas": etapas,
                      "tempo_medio": p.get("tempo_medio"), "usos": int(p.get("usos") or 0), "meu": False,
                      "criterio": str(p.get("criterio") or ""), "prazo": str(p.get("prazo") or ""), "atencao": str(p.get("atencao") or ""), "fontes": str(p.get("fontes") or "")})
    resposta = {"ok": True, "itens": itens}
    _CACHE_CATALOGO[fonte] = (time.time(), resposta)
    return resposta


def _sugestao_de_pop(meus):
    """Tarefa concluída 3 vezes ou mais (últimos 45 dias) que ainda não tem POP."""
    pasta = os.path.join(h.OPER, "registros")
    contagem, exemplo = {}, {}
    dispensadas = set((h._ler_json(_arq_usos()) or {}).get("dispensadas") or [])
    limite = (date.today() - timedelta(days=45)).isoformat()
    if os.path.isdir(pasta):
        for nome in os.listdir(pasta):
            m = re.fullmatch(r"registro_(\d{4}-\d{2}-\d{2})\.json", nome)
            if not m or m.group(1) < limite:
                continue
            for b in (h._ler_json(os.path.join(pasta, nome)) or {}).get("blocos", []):
                if b.get("estado") == "feito" and b.get("titulo"):
                    chave = h._norm(b["titulo"]).strip()
                    contagem[chave] = contagem.get(chave, 0) + 1
                    exemplo[chave] = b["titulo"]
    nomes = [h._norm(p["nome"]).strip() for p in meus]
    for chave, n in sorted(contagem.items(), key=lambda i: -i[1]):
        if n >= 3 and chave not in dispensadas and not any(x and (x in chave or chave in x) for x in nomes):
            return {"titulo": exemplo[chave], "vezes": n}
    return None


def pops():
    meus = meus_pops()
    escola = _catalogo()
    instalados = {p.get("de") for p in meus if p.get("de")}
    for p in escola["itens"]:
        p["instalado"] = p["id"] in instalados
    frentes = list(dict.fromkeys(p["frente"] for p in meus + escola["itens"] if p.get("frente")))
    return {"meus": meus, "escola": escola, "frentes": frentes, "sugestao": _sugestao_de_pop(meus)}


def _nome_de_arquivo(nome):
    limpo = re.sub(r'[\\/:*?"<>|]+', " ", str(nome)).strip()
    return "POP - " + re.sub(r"\s+", " ", limpo)[:80] + ".md"


def _texto_do_pop(p):
    linhas = [f"# POP | {p['nome']}", "",
              f"Versão: v1 (em validação). Criado em {_hoje()}. Revisar na 3ª execução, junto com a média de tempo.",
              f"Frente: {p.get('frente') or 'Geral'}"]
    if p.get("de"):
        linhas.append(f"Origem: {p['de']}")
    linhas += ["", "## O que é e quando usar", p.get("proposito") or "Descrever em uma ou duas frases.", "", "## Etapas",
               "| # | Etapa | Dono | Tempo (deixar em branco na 1ª execução) |", "|---|---|---|---|"]
    for i, e in enumerate(p.get("etapas") or [], 1):
        linhas.append(f"| {i} | {str(e.get('t') or '').replace('|', '/')} | {str(e.get('dono') or _pessoa()).replace('|', '/')} | {str(e.get('tempo') or '').replace('|', '/')} |")
    linhas += ["", "## Critério de pronto", p.get("criterio") or "O que precisa existir para o processo estar terminado.", "",
               "## Prazo-limite relativo", p.get("prazo") or "Em relação à data final.", "",
               "## Pontos de atenção", p.get("atencao") or "O que costuma dar errado.", "",
               "## Fontes", p.get("fontes") or "Criado pela tela do guardião.", ""]
    return "\n".join(linhas)


def salvar_pop(dados):
    nome = str(dados.get("nome") or "").strip()
    etapas = [{"t": str(e.get("t") or "").strip(), "dono": str(e.get("dono") or "").strip(), "tempo": str(e.get("tempo") or "").strip()}
              for e in (dados.get("etapas") or []) if isinstance(e, dict) and str(e.get("t") or "").strip()]
    if not nome:
        return {"ok": False, "erro": "O POP precisa de um nome."}
    if not etapas:
        return {"ok": False, "erro": "O POP precisa de pelo menos uma etapa."}
    pasta = _pasta_pops()
    os.makedirs(pasta, exist_ok=True)
    arquivo = _nome_de_arquivo(nome)
    caminho = os.path.join(pasta, arquivo)
    if os.path.exists(caminho) and not dados.get("substituir"):
        return {"ok": False, "erro": "Já existe um POP com esse nome."}
    pop = {"nome": nome, "proposito": str(dados.get("proposito") or "").strip(), "frente": str(dados.get("frente") or "").strip() or "Geral",
           "etapas": etapas, "criterio": str(dados.get("criterio") or "").strip(), "prazo": str(dados.get("prazo") or "").strip(),
           "atencao": str(dados.get("atencao") or "").strip(), "fontes": str(dados.get("fontes") or "").strip(), "de": dados.get("de")}
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(_texto_do_pop(pop))
    h.bus.emitir("pops")
    return {"ok": True, "id": "meu:" + arquivo, "arquivo": arquivo}


def instalar_pop(dados):
    """Copia um POP do catálogo da escola para a pasta de POPs da pessoa."""
    alvo = next((p for p in _catalogo()["itens"] if p["id"] == dados.get("id")), None)
    if not alvo:
        return {"ok": False, "erro": "Não achei esse POP no catálogo da escola."}
    if any(p.get("de") == alvo["id"] for p in meus_pops()):
        return {"ok": False, "erro": "Esse POP já está em Meus POPs."}
    return salvar_pop({**alvo, "de": alvo["id"], "fontes": alvo.get("fontes") or "Instalado do catálogo da escola."})


def rascunho_pop(dados):
    """Monta um rascunho para a pessoa revisar: a partir de um bloco de hoje (com as subtarefas do ClickUp, se houver) ou de uma busca."""
    bloco_id = dados.get("bloco")
    plano = h._plano_de_hoje() or {}
    b = next((x for x in plano.get("blocos", []) if x.get("id") == bloco_id), None) if bloco_id else None
    titulo = str(dados.get("titulo") or "").strip()
    if not b and titulo:
        b = next((x for x in plano.get("blocos", []) if h._norm(x.get("titulo")).strip() == h._norm(titulo).strip()), None)
    if b:
        etapas = []
        cid = b.get("clickup_id")
        cu = h._clickup_tarefa(cid) if cid else None
        for s in (cu or {}).get("subtasks") or []:
            if s.get("name"):
                etapas.append({"t": s["name"], "dono": "", "tempo": ""})
        descricao = str(b.get("descricao") or "")
        pronto = re.search(r"[Ee]st[aá] pront[oa] quando\s+(.+?)[.]?$", descricao.strip())
        if not etapas:
            if b.get("primeiro_passo"):
                etapas.append({"t": str(b["primeiro_passo"]).rstrip("."), "dono": "", "tempo": ""})
            etapas.append({"t": "Fazer a parte principal: " + _curto(b.get("titulo"), 60), "dono": "", "tempo": ""})
            etapas.append({"t": "Conferir se está pronto" + (": " + pronto.group(1) if pronto else ""), "dono": "", "tempo": ""})
        return {"ok": True, "rascunho": {"nome": b.get("titulo"), "proposito": re.sub(r"\s*[Ee]st[aá] pront[oa] quando.*$", "", descricao).strip() or descricao,
                                         "frente": b.get("frente") or "Geral", "etapas": etapas, "criterio": pronto.group(1).strip().rstrip(".") + "." if pronto else "",
                                         "fontes": f"Tarefa \"{b.get('titulo')}\" do plano de {_hoje()}."}}
    nome = titulo or str(dados.get("busca") or "").strip() or "Novo POP"
    return {"ok": True, "rascunho": {"nome": nome[:1].upper() + nome[1:], "proposito": "Rascunho para você completar.", "frente": "Geral",
                                     "etapas": [{"t": "Definir o objetivo em uma frase", "dono": "", "tempo": ""}, {"t": "Listar as etapas na ordem", "dono": "", "tempo": ""},
                                                {"t": "Testar uma vez e ajustar", "dono": "", "tempo": ""}],
                                     "criterio": "", "fontes": "Criado pela tela do guardião."}}


def usar_pop(dados):
    """Conta o uso e devolve o POP, para a tela pedir ao guardião que guie pelas etapas."""
    arquivo = str(dados.get("arquivo") or "")
    caminho = os.path.join(_pasta_pops(), os.path.basename(arquivo))
    p = _ler_pop(caminho) if arquivo and os.path.isfile(caminho) else None
    if not p:
        return {"ok": False, "erro": "Não achei esse POP."}
    with _trava:
        d = h._ler_json(_arq_usos()) or {}
        usos = d.setdefault("usos", {})
        usos[p["arquivo"]] = int(usos.get(p["arquivo"]) or 0) + 1
        _gravar(_arq_usos(), d)
    h.bus.emitir("pops")
    return {"ok": True, "pop": p}


def dispensar_sugestao(dados):
    titulo = h._norm(dados.get("titulo")).strip()
    if titulo:
        with _trava:
            d = h._ler_json(_arq_usos()) or {}
            d["dispensadas"] = sorted(set(d.get("dispensadas") or []) | {titulo})
            _gravar(_arq_usos(), d)
    return {"ok": True}


# ---------------- rotas (chamadas pelo servidor da tela) ----------------

def rota_get(caminho, consulta):
    if caminho == "/sessao":
        return sessao(marcar=(consulta.get("marcar") or ["0"])[0] == "1")
    if caminho == "/calibragem":
        return calibragem()
    if caminho == "/pops":
        return pops()
    if caminho == "/execucao":
        return {"ok": True, **estado_exec()}
    return None


def rota_post(caminho, dados):
    if caminho == "/execucao":
        return acao_execucao(dados)
    if caminho == "/calibragem/report":
        return salvar_report(dados.get("campos"), "tela")
    if caminho == "/calibragem/reiniciar":
        return reiniciar_calibragem()
    if caminho == "/pops/salvar":
        return salvar_pop(dados)
    if caminho == "/pops/instalar":
        return instalar_pop(dados)
    if caminho == "/pops/rascunho":
        return rascunho_pop(dados)
    if caminho == "/pops/usar":
        return usar_pop(dados)
    if caminho == "/pops/dispensar":
        return dispensar_sugestao(dados)
    if caminho == "/roteiro":
        h.bus.comandos.put(("roteiro", str(dados.get("id") or "report")))
        return {"ok": True}
    if caminho == "/ditar":
        h.bus.comandos.put(("ditar", dados.get("campo")))
        return {"ok": True}
    return None
