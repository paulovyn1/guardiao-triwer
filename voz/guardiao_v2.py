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

import calibragem_motor as cm
import hud_servidor as h

_trava = threading.RLock()
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
MARCOS = (7, 14, 21, 30, 60, 90, 180, 365)  # depois do dia 30 a calibragem continua (decisão de produto, 15/10/2026)
TRILHA = 30


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


# ---------------- atraso e folga do dia (regra do replanejamento, decisão de produto de 13/10/2026) ----------------
# Replaneja só se o atraso passar de 30 minutos E o resto do dia não tiver folga para absorver. Dia todo fechado = sem folga.
ATRASO_PARA_REPLANEJAR = 30  # minutos
TEMPO_PARA_FECHAR_A_ATUAL = 15  # minutos que a tarefa atrasada ainda deve levar (estimativa; ela ainda não acabou)


def avaliar_atraso(plano=None):
    """{"atraso", "folga", "precisa", "bloco", "fim_do_dia"} em minutos. atraso = quanto a tarefa de agora passou do fim previsto.
    folga = tempo livre que sobra até o fim do dia depois de tudo que ainda falta (tarefas pendentes, compromissos fixos e o resto da atual)."""
    plano = plano or h._plano_de_hoje() or {}
    atual = bloco_atual(plano)
    agora = _agora_min()
    vazio = {"atraso": 0, "folga": None, "precisa": False, "bloco": atual, "fim_do_dia": None}
    if not atual or plano.get("status") != "aprovado":
        return vazio
    atraso = max(0, agora - h._min(atual["fim"]))
    fim_cfg = (h._config().get("rotina") or {}).get("fim")
    fins = [h._min(b["fim"]) for b in plano.get("blocos", []) if h._hora(b.get("fim"))] + [h._min(f["fim"]) for f in plano.get("fixos", []) if h._hora(f.get("fim"))]
    fim_do_dia = (h._min(h._hora(plano.get("fim_do_dia"))) if h._hora(plano.get("fim_do_dia"))
                  else h._min(h._hora(fim_cfg)) if h._hora(fim_cfg) else max(fins or [agora]))
    reg = _estados_de_hoje()
    pendentes = [b for b in plano.get("blocos", []) if b.get("id") != atual.get("id") and (reg.get(b.get("id")) or {}).get("estado") not in ("feito", "adiado")
                 and h._hora(b.get("inicio")) and h._hora(b.get("fim")) and h._min(b["fim"]) > agora]
    fixos = [f for f in plano.get("fixos", []) if h._hora(f.get("inicio")) and h._hora(f.get("fim")) and h._min(f["fim"]) > agora]
    ocupado = sum(h._min(b["fim"]) - h._min(b["inicio"]) for b in pendentes) + sum(h._min(f["fim"]) - max(h._min(f["inicio"]), agora) for f in fixos)
    ocupado += TEMPO_PARA_FECHAR_A_ATUAL if atraso else max(0, h._min(atual["fim"]) - agora)
    folga = fim_do_dia - agora - ocupado
    return {"atraso": atraso, "folga": folga, "precisa": atraso > ATRASO_PARA_REPLANEJAR and folga < 0, "bloco": atual, "fim_do_dia": _hm(fim_do_dia)}


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


def _repetido(tipo, bloco_id, segundos):
    """O mesmo fato (tipo e bloco) já foi gravado há menos de `segundos`? Lê só o fim do arquivo."""
    try:
        with open(os.path.join(_pasta_cal(), "eventos.jsonl"), "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 8192))
            linhas = f.read().decode("utf-8", errors="ignore").splitlines()[-40:]
    except OSError:
        return False
    agora = time.time()
    for linha in reversed(linhas):
        try:
            ev = json.loads(linha)
        except ValueError:
            continue
        if ev.get("tipo") == tipo and ev.get("bloco") == bloco_id:
            try:
                return agora - time.mktime(time.strptime(ev["ts"], "%Y-%m-%d %H:%M:%S")) < segundos
            except (KeyError, ValueError):
                return False
    return False


def registrar_evento(tipo, bloco=None, unico_por=None, **extra):
    """Uma linha por fato observado (aviso de tempo, extensão, adiamento, conclusão, imprevisto). É a matéria-prima do que o guardião aprende.
    Bloco do plano leva a natureza (o tipo de trabalho) e a marca de tarefa principal. Com `unico_por` (segundos), o mesmo fato do mesmo bloco não se repete."""
    linha = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "data": _hoje(), "hora": _agora_hm(), "tipo": tipo}
    if bloco:
        linha.update({"bloco": bloco.get("id"), "titulo": bloco.get("titulo"), "frente": bloco.get("frente")})
        if bloco.get("inicio"):  # bloco de verdade do plano (o "fixo" e o "novas" dos avisos não têm horário)
            linha["natureza"] = cm.natureza_do_bloco(bloco)
            if bloco.get("principal"):
                linha["principal"] = True
    linha.update({k: v for k, v in extra.items() if v is not None})
    try:
        os.makedirs(_pasta_cal(), exist_ok=True)
        with _trava:
            if unico_por and _repetido(tipo, linha.get("bloco"), unico_por):
                return None
            with open(os.path.join(_pasta_cal(), "eventos.jsonl"), "a", encoding="utf-8") as f:
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
    d.setdefault("contados", [])  # blocos de hoje cujo tempo já foi somado no tempos.json
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


def comecou(d, bloco_id):
    """A pessoa já iniciou este bloco (clicou em Iniciar) e ele ainda não terminou?"""
    s = _sessao(d, bloco_id)
    return bool(s and s["trechos"])


def entrar(iniciar=False):
    """Liga o modo execução. O relógio do bloco só conta depois que a pessoa inicia a tarefa (iniciar=True, o botão Iniciar):
    chegar o horário não basta, senão o tempo medido seria o do relógio e não o do trabalho. Tarefa já iniciada e pausada volta a contar."""
    global CHECKIN
    with _trava:
        d = _ler_exec()
        plano = h._plano_de_hoje() or {}
        b = bloco_atual(plano)
        ja = bool(d["modo"].get("ativo"))
        d["modo"] = {"ativo": True, "desde": d["modo"].get("desde") if ja else _agora_hm()}
        primeira_vez = False
        if b and plano.get("status") == "aprovado" and (iniciar or comecou(d, b.get("id"))):
            primeira_vez = not comecou(d, b.get("id"))
            _abrir_trecho(d, b)
        _gravar(_arq_exec(), d)
    if not ja:
        registrar_evento("execucao_inicio", b)
    if primeira_vez:  # o atraso para começar é o melhor sinal de procrastinação: hora do bloco contra o clique em Iniciar
        registrar_evento("inicio_bloco", b, planejado=b.get("inicio"), atraso=_agora_min() - h._min(b["inicio"]))
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
            plano = h._plano_de_hoje() or {}
            bloco = next((b for b in plano.get("blocos", []) if b.get("id") == bloco_id), None)
            if bloco and d["modo"].get("ativo") and comecou(d, bloco_id):  # Desfazer: a tarefa que já tinha começado volta a contar
                _abrir_trecho(d, bloco)
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
        ja_contado = bloco.get("id") in d.setdefault("contados", [])  # concluído duas vezes (tela e ClickUp, ou reaberto e concluído de novo): conta uma vez
        s = _sessao(d, bloco.get("id"))
        trabalhado = None
        if s:
            _fechar_trechos(d, bloco.get("id"))
            trabalhado = _minutos(s) if s["trechos"] else None
            s["resultado"] = "concluido"
            s["minutos"] = trabalhado
            s["fim"] = _agora_hm()
        if not ja_contado:
            d["contados"].append(bloco.get("id"))
        d["aguardando"] = [x for x in d["aguardando"] if x != bloco.get("id")]
        _gravar(_arq_exec(), d)
        if CHECKIN and CHECKIN.get("bloco") == bloco.get("id"):
            CHECKIN = None
            h.bus.emitir("checkin_fim", motivo="concluido")
    if ja_contado:
        _avisar_tela()
        return
    planejado = h._min(bloco["fim"]) - h._min(bloco["inicio"]) - int(bloco.get("estendido_min") or 0)
    relogio = (h._min(real["fim"]) - h._min(real["inicio"])) % 1440 if real else None
    medido = trabalhado if trabalhado and trabalhado >= cm.MIN_MEDIDO else None  # Iniciar e concluir no mesmo minuto não é trabalho medido
    minutos = medido if medido is not None else relogio
    confirmado = cm.tempo_confiavel(planejado, minutos, medido is not None, not nao_confirmado)
    natureza = cm.natureza_do_bloco(bloco)
    prazo = None
    if bloco.get("clickup_id"):  # o prazo final da tarefa: diz se a entrega saiu adiantada, no prazo ou atrasada
        tarefa = next((t for t in (h._ler_json(os.path.join(h.OPER, "resumo_clickup.json")) or {}).get("tarefas", []) if t.get("id") == bloco["clickup_id"]), None)
        prazo = (tarefa or {}).get("prazo")
    if minutos is not None:
        _somar_tempo(natureza, bloco.get("titulo"), planejado, minutos, confirmado, frente=bloco.get("frente"), medido=medido is not None)
    registrar_evento("conclusao", bloco, planejado=planejado, real=minutos, desvio=(minutos - planejado) if minutos is not None else None, confirmado=confirmado,
                     medido=medido is not None, estendido=int(bloco.get("estendido_min") or 0) or None, inicio_planejado=bloco.get("inicio"), prazo=prazo)
    verificar_conquistas()
    _avisar_tela()


def _somar_tempo(natureza, titulo, planejado, real, confirmado, frente=None, medido=False):
    """tempos.json: os 10 últimos registros por natureza da tarefa e a média (só vale com 3 execuções confirmadas). Folga não entra."""
    caminho = os.path.join(h.OPER, "tempos.json")
    with _trava:
        cm.garantir_tempos(h.OPER)
        dados = h._ler_json(caminho) or {}
        cm.somar(dados, natureza, {"data": _hoje(), "titulo": titulo, "frente": frente, "planejado": planejado, "real": real,
                                   "confirmado": bool(confirmado), "medido": bool(medido)})
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
    """Uma olhada no relógio: dispara os avisos de tempo da tarefa que a pessoa iniciou. Não inicia tarefa sozinho (só o botão Iniciar)."""
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
        if not s or not s["trechos"] or s["trechos"][-1].get("ate"):  # ainda não iniciada, ou pausada: nada de aviso de tempo
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


def _data_curta(iso):
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%d/%m")
    except ValueError:
        return str(iso)


def _avisar_tarefas_novas():
    """Tarefa que apareceu no ClickUp desde a última leitura. Só a que vence hoje (ou já venceu) abre a pergunta de replanejar o dia, e mesmo assim o guardião
    confere se é urgente antes de mexer. Tarefa de data futura NUNCA mexe em hoje: a pergunta é só onde encaixar na semana ou no mês. Não mexe no plano sozinho."""
    global CHECKIN
    if not h.ULTIMAS_NOVAS or CHECKIN:
        return None  # com um aviso de tempo aberto, espera a vez
    with _trava:
        novas = list(h.ULTIMAS_NOVAS)
        del h.ULTIMAS_NOVAS[:]
        d = _ler_exec()
        novas = [t for t in novas if f"nova|{t.get('id')}" not in d["avisados"]]
        if not novas:
            return None
        d["avisados"] += [f"nova|{t.get('id')}" for t in novas]
        _gravar(_arq_exec(), d)
        hoje = _hoje()
        de_hoje = [t for t in novas if not t.get("prazo") or str(t["prazo"])[:10] <= hoje]
        futuras = [t for t in novas if t not in de_hoje]
        nomes = [_curto(t.get("nome"), 60) for t in novas]
        lista = lambda ts: "; ".join(f"{_curto(t.get('nome'), 60)} ({_data_curta(t.get('prazo'))})" for t in ts[:3]) + (f" e mais {len(ts) - 3}" if len(ts) > 3 else "")
        if de_hoje:
            n = len(de_hoje)
            texto = (f"Apareceu {n} tarefa nova no ClickUp com data para hoje: {lista(de_hoje)}. Quer que eu veja se é urgente e replaneje o dia?" if n == 1
                     else f"Apareceram {n} tarefas novas no ClickUp com data para hoje: {lista(de_hoje)}. Quer que eu veja se são urgentes e replaneje o dia?")
            pedido = ("Sim, quero replanejar o dia. Apareceram tarefas novas no ClickUp com data para hoje: " + "; ".join(_curto(t.get("nome"), 60) for t in de_hoje)
                      + ". Abra cada tarefa e confira se é mesmo urgente hoje. Se não for, NÃO mexa em hoje: proponha outra data no planejamento da semana ou do mês (rode onde_cabe.ps1) e me pergunte antes de gravar. "
                      "Só puxe para hoje o que for urgente e só se couber; se hoje já passa da minha hora de parar, adiante o que está estourando em hoje antes de pôr tarefa de outro dia. Não aprove nada sem eu ver.")
            if futuras:
                pedido += " Tarefas com data futura (" + "; ".join(_curto(t.get("nome"), 60) for t in futuras) + "): não mexa em hoje, só proponha o dia de encaixe."
            opcoes = [{"rotulo": "Replanejar", "resposta": "novas_replanejar"}, {"rotulo": "Depois", "resposta": "novas_depois"}]
        else:
            n = len(futuras)
            texto = (f"Apareceu {n} tarefa nova no ClickUp para outra data: {lista(futuras)}. Não mexo em hoje. Quer que eu proponha onde encaixar?" if n == 1
                     else f"Apareceram {n} tarefas novas no ClickUp para outras datas: {lista(futuras)}. Não mexo em hoje. Quer que eu proponha onde encaixar?")
            pedido = ("Apareceram tarefas novas no ClickUp com data futura: " + "; ".join(f"{_curto(t.get('nome'), 60)} ({_data_curta(t.get('prazo'))})" for t in futuras)
                      + ". NÃO altere o plano de hoje. Rode onde_cabe.ps1 e proponha o dia de encaixe no planejamento da semana ou do mês, respeitando o prazo e a folga. "
                      "Me pergunte antes de gravar no ClickUp.")
            opcoes = [{"rotulo": "Propor encaixe", "resposta": "novas_replanejar"}, {"rotulo": "Depois", "resposta": "novas_depois"}]
        CHECKIN = {"id": f"novas|{int(time.time())}", "bloco": "novas", "titulo": "Tarefas novas", "faltam": 0, "fim": None, "passo": "inicio", "quando": time.time(),
                   "dados": {"pedido": pedido}, "texto": texto, "opcoes": opcoes}
        c = dict(CHECKIN)
    registrar_evento("checkin_novas", None, quantidade=len(nomes), de_hoje=len(de_hoje), futuras=len(futuras))
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
                _avisar_tarefas_novas()
                _tique_report()
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
        if bloco_id == "novas" and resposta in ("novas_replanejar", "novas_depois"):
            pedido = (c or {}).get("dados", {}).get("pedido")
            CHECKIN = None
            h.bus.emitir("checkin_fim", motivo="respondido")
            _avisar_tela()
            if resposta == "novas_replanejar" and pedido:
                h.bus.comandos.put(("perguntar", pedido))  # entra na conversa como se ela tivesse escrito: o guardião refaz o plano
            return {"ok": True, "fim": True, "texto": "Combinado." if resposta == "novas_replanejar" else "Combinado. As tarefas novas ficam para depois."}
        if bloco_id == "report" and resposta in ("report_agora", "report_depois"):  # convite do report na hora de parar
            CHECKIN = None
            h.bus.emitir("checkin_fim", motivo="respondido")
            registrar_evento("convite_report_resposta", None, resposta="agora" if resposta == "report_agora" else "depois")
            _avisar_tela()
            if resposta == "report_agora":
                return {"ok": True, "fim": True, "acao": "report"}
            return _fecho("Combinado. Amanhã tem mais.", falar=True)
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
        b = bloco_atual()
        if dados.get("id") and (not b or b.get("id") != dados.get("id")):  # o aviso era de uma tarefa que já não é a de agora
            return {"ok": False, "erro": "Essa tarefa não é a de agora."}
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
    """Dados para a janela começar: a abertura animada roda sempre (Esc pula); primeira_do_dia diz se é a primeira abertura de hoje,
    a que monta e revisa o plano. As outras do mesmo dia vão direto para a execução."""
    arq = os.path.join(h.OPER, "logs", "abertura.json")
    ultimo = (h._ler_json(arq) or {}).get("ts", 0)
    primeira = datetime.fromtimestamp(ultimo).date() != date.today()
    if marcar:
        try:
            _gravar(arq, {"ts": time.time()})
        except OSError:
            pass
    cfg = h._config()
    return {"abertura": True, "primeira_do_dia": bool(primeira), "pessoa": _pessoa(), "agente": (cfg.get("agente") or {}).get("nome") or "Guardião",
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


def _mtime_semana_base():
    memoria = ((h._config().get("pastas") or {}).get("memoria")) or os.path.join(h.OPER, "memoria")
    try:
        return int(os.path.getmtime(os.path.join(memoria, "semana-base.md")))
    except OSError:
        return None


def _report_v2(dados):
    """O report de toques (0.11.0): energia de 1 a 5, o que atrapalhou e o que ajudou (chips), a resposta à hipótese do dia e um campo aberto."""
    try:
        energia = int(dados.get("energia")) if dados.get("energia") not in (None, "") else None
    except (TypeError, ValueError):
        energia = None
    energia = energia if energia and 1 <= energia <= 5 else None
    escolhas = lambda chave, validos: [c for c in dict.fromkeys(str(x) for x in (dados.get(chave) or [])) if c in validos][:8]  # noqa: E731
    hip = dados.get("hipotese") or {}
    resposta = str(hip.get("resposta") or "") if isinstance(hip, dict) else ""
    return {"energia": energia, "atrapalhou": escolhas("atrapalhou", cm.ATRAPALHOU), "ajudou": escolhas("ajudou", cm.AJUDOU),
            "hipotese": {"id": str(hip.get("id") or ""), "texto": str(hip.get("texto") or "")[:300], "resposta": resposta} if resposta in cm.RESPOSTAS else None,
            "nota": str(dados.get("nota") or "").strip()[:1500]}


def salvar_report(campos, origem="tela"):
    """Guarda o report do dia. O formato novo (dicionário) é o de toques; a lista de 4 respostas abertas ainda é aceita (relatos antigos e
    integrações). O primeiro report marca o dia 1 da calibragem. Depois de gravar, a calibragem é recalculada na hora."""
    if isinstance(campos, dict):
        r = _report_v2(campos)
        if not (r["energia"] or r["atrapalhou"] or r["ajudou"] or r["hipotese"] or r["nota"]):
            return {"ok": False, "erro": "Marque pelo menos uma resposta."}
        conteudo = {"versao": 2, **r, "resumo": cm.resumo_do_dia(h.OPER)}
    else:
        chaves = ("ajustes", "picos", "funcionou", "ultima_hora")
        campos = [str(c or "").strip()[:1200] for c in (list(campos or []) + ["", "", "", ""])[:4]]
        if not any(campos):
            return {"ok": False, "erro": "Escreva pelo menos uma das respostas."}
        conteudo = dict(zip(chaves, campos))
    with _trava:
        estado = h._ler_json(_arq_estado_cal()) or {}
        if not estado.get("inicio"):
            estado = {"inicio": _hoje(), "ciclo": int(estado.get("ciclo") or 0) + 1, "semana_base_mtime": _mtime_semana_base()}
            _gravar(_arq_estado_cal(), estado)
        _gravar(os.path.join(_pasta_cal(), "reports", f"{_hoje()}.json"),
                {"data": _hoje(), "enviado_em": time.strftime("%Y-%m-%d %H:%M"), "origem": origem, **conteudo})
    hip = conteudo.get("hipotese")
    if hip and hip.get("id"):
        achado = next((a for a in (cm.atualizar_perfil(h.OPER).get("achados") or []) if a["id"] == hip["id"]), {})
        cm.registrar_resposta(h.OPER, hip["id"], hip["resposta"], n=achado.get("n"), texto=hip.get("texto"))
        if hip["id"].startswith("rotina:") and hip["resposta"] == "sim":  # o que se repete fora do plano passa a ter horário reservado
            registrar_evento("rotina_aceita", None, id=hip["id"], texto=hip.get("texto"))
    cm.atualizar_perfil(h.OPER, forcar=True)
    _fechar_convite_report()
    verificar_conquistas()
    visao = calibragem()
    h.bus.emitir("calibragem", dia=visao["dia"], estado=visao["estado"])
    return {"ok": True, "dia": visao["dia"], "estado": visao["estado"], "marco": visao["estado"] == "milestone"}


def reiniciar_calibragem():
    """Recomeça a contagem (a rotina mudou). Os achados e as respostas ficam: o que já foi aprendido continua valendo até os dados novos dizerem outra coisa."""
    with _trava:
        estado = h._ler_json(_arq_estado_cal()) or {}
        _gravar(_arq_estado_cal(), {"inicio": None, "ciclo": int(estado.get("ciclo") or 1), "encerrado_em": _hoje()})
    h.bus.emitir("calibragem", dia=1, estado="d1")
    return {"ok": True}


# ---------------- conquistas e estatísticas ----------------

def _memoria():
    return ((h._config().get("pastas") or {}).get("memoria")) or os.path.join(h.OPER, "memoria")


def verificar_conquistas(anunciar=True):
    """Confere as conquistas depois de algo que pode desbloquear uma (concluir, mandar o report). A nova vai para a tela e para a voz, uma vez."""
    try:
        import conquistas
        r = conquistas.calcular(h.OPER, _memoria())
    except Exception as erro:  # a calibragem nunca pode derrubar o guardião
        print("  (não consegui conferir as conquistas:", erro, ")")
        return {"lista": [], "novas": [], "total": 0, "desbloqueadas": 0}
    for c in r["novas"]:
        registrar_evento("conquista", None, id=c["id"], titulo=c["titulo"])
        h.bus.emitir("conquista", id=c["id"], titulo=c["titulo"])
        if anunciar:
            h.bus.comandos.put(("dizer", f"Conquista desbloqueada: {c['titulo']}."))
    return r


def estatisticas():
    try:
        import estatisticas as est
        return est.calcular(h.OPER)
    except Exception as erro:
        print("  (não consegui calcular as estatísticas:", erro, ")")
        return None


# ---------------- convite do report na hora de parar ----------------

def _fim_do_plano(plano):
    fim_cfg = (h._config().get("rotina") or {}).get("fim")
    fins = [h._min(b["fim"]) for b in plano.get("blocos", []) if h._hora(b.get("fim"))] + [h._min(f["fim"]) for f in plano.get("fixos", []) if h._hora(f.get("fim"))]
    if h._hora(plano.get("fim_do_dia")):
        return h._min(h._hora(plano.get("fim_do_dia")))
    return max(fins) if fins else (h._min(h._hora(fim_cfg)) if h._hora(fim_cfg) else None)


def _tique_report():
    """Na hora de parar (ou quando o dia já acabou antes), convida para o report uma vez, se ele ainda não veio. Pela tela e pela voz."""
    global CHECKIN
    plano = h._plano_de_hoje()
    if not plano or plano.get("status") != "aprovado" or CHECKIN or _report_de(_hoje()):
        return None
    fim = _fim_do_plano(plano)
    agora = _agora_min()
    reg = _estados_de_hoje()
    trabalho = [b for b in plano.get("blocos", []) if h._hora(b.get("inicio")) and cm.natureza_do_bloco(b) != cm.SEM_TEMPO]
    tudo_resolvido = bool(trabalho) and all((reg.get(b.get("id")) or {}).get("estado") in ("feito", "adiado") for b in trabalho)
    if fim is None or agora > 23 * 60 + 30 or not (agora >= fim - 10 or (tudo_resolvido and agora >= max(h._min(b["inicio"]) for b in trabalho))):
        return None
    with _trava:
        d = _ler_exec()
        if "report" in d["avisados"]:
            return None
        d["avisados"].append("report")
        _gravar(_arq_exec(), d)
        resumo = cm.resumo_do_dia(h.OPER)
        texto = f"Fim do dia. {resumo['frase']} Vamos ao report de um minuto?"
        CHECKIN = {"id": f"report|{int(time.time())}", "bloco": "report", "titulo": "Report do dia", "faltam": 0, "fim": None, "passo": "inicio",
                   "quando": time.time(), "dados": {}, "texto": texto,
                   "opcoes": [{"rotulo": "Fazer o report", "resposta": "report_agora"}, {"rotulo": "Hoje não", "resposta": "report_depois"}]}
        c = dict(CHECKIN)
    registrar_evento("convite_report", None)
    h.bus.emitir("checkin", **_publico_checkin())
    h.bus.comandos.put(("checkin", {"texto": c["texto"], "id": c["id"]}))
    return c


def _fechar_convite_report():
    global CHECKIN
    if CHECKIN and CHECKIN.get("bloco") == "report":
        CHECKIN = None
        h.bus.emitir("checkin_fim", motivo="report")


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


ROTULO_ACHADO = {"estimativa": "Tempo real", "faixa": "Hora de começar", "adiamento": "O que mais fica para depois", "energia": "Energia",
                 "motivo": "Por que as tarefas atrasam", "folga": "Imprevistos", "ajudou": "O que funciona para você", "rotina": "Fora do plano e se repete"}
NIVEL_ACHADO = {"confirmado": "Confirmado por você", "medido": "Medido", "provavel": "Provável", "hipotese": "Hipótese"}


def _aprendizados(eventos, faixa, dias_foco, perfil=None):
    """Cartões do que já dá para afirmar, dicas práticas e o que mudou no plano. Primeiro o que o guardião do chat escreveu em aprendizados.json,
    depois o que o motor da calibragem achou (só o medido, o provável e o confirmado) e por fim as contas da tela (pico de foco, concluídas no horário)."""
    escrito = h._ler_json(os.path.join(_pasta_cal(), "aprendizados.json")) or {}
    cartoes = [{"k": str(c.get("k") or ""), "v": str(c.get("v") or ""), "d": str(c.get("d") or "")} for c in (escrito.get("cartoes") or []) if c.get("v")][:4]
    dicas = [str(x) for x in (escrito.get("dicas") or []) if x][:4]
    mudancas = [str(x) for x in (escrito.get("mudancas") or []) if x][:4]
    perfil = perfil if perfil is not None else cm.atualizar_perfil(h.OPER)
    for a in perfil.get("achados") or []:
        if a.get("nivel") in ("confirmado", "medido", "provavel"):
            cartoes.append({"k": ROTULO_ACHADO.get(a.get("tipo"), "Aprendizado"), "v": a.get("texto"), "d": f"{NIVEL_ACHADO[a['nivel']]} · {a['n']} dados", "nivel": a["nivel"]})
    dicas += list(perfil.get("acoes") or [])
    mudancas += cm.ultimas_mudancas(h.OPER)
    if faixa and dias_foco >= 2:
        cartoes.append({"k": "Seus melhores picos", "v": faixa, "d": f"Onde você mais trabalhou focado em {dias_foco} dias medidos."})
    motivos = {}
    for ev in eventos:
        if ev.get("motivo") and ev.get("tipo") in ("extensao", "adiamento", "imprevisto", "motivo"):
            motivos[ev["motivo"]] = motivos.get(ev["motivo"], 0) + 1
    if motivos and not any(c.get("k") == "Por que as tarefas atrasam" for c in cartoes):
        nome, vezes = max(motivos.items(), key=lambda i: i[1])
        cartoes.append({"k": "Por que as tarefas atrasam", "v": nome, "d": f"Citado {vezes} {'vez' if vezes == 1 else 'vezes'} nos últimos 45 dias."})
        if vezes >= 2 and _dica(nome):
            dicas.append(_dica(nome))
    feitas = [ev for ev in eventos if ev.get("tipo") == "conclusao" and ev.get("medido")]
    if len(feitas) >= 3:
        no_prazo = sum(1 for ev in feitas if (ev.get("desvio") or 0) <= 5)
        cartoes.append({"k": "Concluídas no horário", "v": f"{no_prazo} de {len(feitas)}", "d": "Tarefas medidas em modo execução."})
    return cartoes[:4], list(dict.fromkeys(dicas))[:4], list(dict.fromkeys(mudancas))[:4]


def calibragem():
    """Tudo que a tela Calibragem mostra: dia da trilha, report de hoje e o que foi aprendido."""
    estado = h._ler_json(_arq_estado_cal()) or {}
    inicio = estado.get("inicio")
    hoje = date.today()
    trabalho = _dias_de_trabalho()
    eventos = _eventos()
    calor, dias_foco, faixa = _mapa_de_foco()
    perfil = cm.atualizar_perfil(h.OPER)
    cartoes, dicas, mudancas = _aprendizados(eventos, faixa, dias_foco, perfil)
    rep = _report_de(hoje.isoformat())
    hipotese = None
    if not rep:  # a pergunta do dia: a mesma até o report sair, e no máximo uma por dia
        hipotese = cm.hipotese_do_dia(h.OPER, perfil)
        if hipotese:
            cm.marcar_perguntado(h.OPER, hipotese["id"])
    elif (rep.get("hipotese") or {}).get("id"):
        hipotese = rep["hipotese"]
    base = {"total": TRILHA, "hoje": None, "campos": ["", "", "", ""], "aprendizados": cartoes, "dicas": dicas, "mudancas": mudancas,
            "calor": calor, "horas": [f"{x}h" for x in HORAS_CALOR], "dias_medidos": dias_foco, "reports": 0, "perdido": None,
            "resumo": cm.resumo_do_dia(h.OPER), "hipotese": hipotese, "opcoes": {"atrapalhou": cm.ATRAPALHOU, "ajudou": cm.AJUDOU},
            "continua": False, "recalibrar": None, "marcos": list(MARCOS),
            "estatisticas": estatisticas(), "conquistas": verificar_conquistas()}
    if not inicio:
        return {**base, "estado": "d1", "dia": 1, "trilha": [{"d": i + 1, "estado": "hoje" if i == 0 else "futuro", "marco": (i + 1) in MARCOS} for i in range(TRILHA)]}
    dias = []
    d = date.fromisoformat(inicio)
    while d <= hoje and len(dias) < 2000:  # a calibragem não termina no dia 30: segue contando, e a trilha mostra os últimos 30 dias
        if d.weekday() in trabalho or _report_de(d.isoformat()) or d == hoje:
            dias.append(d)
        d += timedelta(days=1)
    n = len(dias)
    com_report = {x for x in dias if _report_de(x.isoformat())}
    desde = max(0, n - TRILHA)
    trilha, perdido = [], None
    for i in range(desde, desde + TRILHA):
        if i < n:
            dia = dias[i]
            tem = dia in com_report
            est = ("ok" if tem else "hoje") if dia == hoje else ("ok" if tem else "miss")
            trilha.append({"d": i + 1, "estado": est, "marco": (i + 1) in MARCOS})
        else:
            trilha.append({"d": i + 1, "estado": "futuro", "marco": (i + 1) in MARCOS})
    hoje_na_trilha = bool(dias) and dias[-1] == hoje
    if n >= 2 and hoje_na_trilha and dias[-2] not in com_report:
        perdido = n - 1
    if rep:
        est = "final" if n == TRILHA else ("milestone" if n in MARCOS else "sent")
    else:
        est = "missed" if perdido else "pending"
    mtime, marcado = _mtime_semana_base(), estado.get("semana_base_mtime")
    recalibrar = None
    if marcado is None and mtime is not None:  # calibragem de antes da 0.11.0: guarda a referência agora, sem avisar
        with _trava:
            _gravar(_arq_estado_cal(), {**estado, "semana_base_mtime": mtime})
    elif mtime and marcado and mtime != marcado and n >= 7:
        recalibrar = (f"A sua semana-base mudou em {datetime.fromtimestamp(mtime):%d/%m}. Se a rotina mudou de verdade, recomece a calibragem "
                      "para o guardião não planejar com o ritmo antigo.")
    return {**base, "estado": est, "dia": max(1, n), "trilha": trilha, "reports": len(com_report), "perdido": perdido, "continua": n > TRILHA,
            "recalibrar": recalibrar, "hoje": rep, "campos": [str((rep or {}).get(k) or "") for k in ("ajustes", "picos", "funcionou", "ultima_hora")]}


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
    if caminho == "/calibragem/report":  # o report de toques vem em "report"; "campos" é o formato antigo, de 4 respostas abertas
        return salvar_report(dados["report"] if isinstance(dados.get("report"), dict) else dados.get("campos"), "tela")
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
